import { spawn, ChildProcess } from "child_process";
import { EventEmitter } from "events";
import { homedir, platform } from "os";
import { existsSync } from "fs";

export type LogLevel = "ok" | "warn" | "error" | "info";

export interface LogLine {
  time: string;
  text: string;
  level: LogLevel;
}

export type RunnerState = "idle" | "running" | "done" | "failed";

function fmtTime(d = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

const MUPDF_WARN_RE = /\b(format error|syntax error|xlib error|invalid (stream|object)|object is not a stream|incorrect header check|expected generation number|unknown PDF|cannot find|cannot recognize|cannot load|cannot parse|unknown cmap|premature end|unexpected end|bad encryption|ExtGState|CIDFont|BaseFont)\b/i;

function classify(text: string, isStderr: boolean): LogLevel {
  if (text.includes("✓")) return "ok";
  if (text.includes("⚠")) return "warn";
  if (isStderr && MUPDF_WARN_RE.test(text)) return "warn";
  if (isStderr || text.startsWith("Error")) return "error";
  return "info";
}

export function parseCmd(pythonCmd: string, stageArgs: string[]): [string, string[]] {
  const parts = pythonCmd.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return ["", stageArgs];
  return [parts[0], [...parts.slice(1), ...stageArgs]];
}

const IS_WIN = platform() === "win32";

export function getCancelSignal(
  platformName: NodeJS.Platform = platform()
): NodeJS.Signals | undefined {
  return platformName === "win32" ? undefined : "SIGTERM";
}

/** Return a login shell path (zsh or bash) that will source the user's profile. */
function loginShell(): string {
  const zsh = "/bin/zsh";
  const bash = "/bin/bash";
  if (process.env.SHELL) return process.env.SHELL;
  if (existsSync(zsh)) return zsh;
  return bash;
}

/** Shell-escape a single argument for POSIX shells. */
function posixQuote(arg: string): string {
  return "'" + arg.replace(/'/g, "'\\''") + "'";
}


export class ZsumRunner extends EventEmitter {
  private child: ChildProcess | null = null;
  private _state: RunnerState = "idle";
  private startTime: number = 0;
  private stderrBuf: string = "";
  private stdoutBuf: string = "";

  get state(): RunnerState {
    return this._state;
  }

  private setState(s: RunnerState) {
    this._state = s;
    this.emit("state-change", s);
  }

  run(pythonCmd: string, stageArgs: string[], cwd: string): void {
    if (this._state === "running") {
      throw new Error("Runner is already running");
    }
    const [cmd, args] = parseCmd(pythonCmd, stageArgs);
    if (!cmd) {
      throw new Error("Empty python command");
    }
    this.startTime = Date.now();
    this.stderrBuf = "";
    this.stdoutBuf = "";
    this.setState("running");

    try {
      if (IS_WIN) {
        // Windows: cmd.exe inherits the full user PATH from the registry,
        // so shell: true is sufficient — no profile-sourcing needed.
        this.child = spawn(cmd, args, { cwd, shell: true });
      } else {
        // macOS/Linux: GUI apps don't source shell profiles, so we run
        // through the user's login shell interactively to pick up PATH.
        const fullCmd = [cmd, ...args].map(posixQuote).join(" ");
        const sh = loginShell();
        this.child = spawn(sh, ["-li", "-c", fullCmd], {
          cwd,
          env: { ...process.env, HOME: homedir() },
        });
      }
    } catch (e: any) {
      this.emitLog(`Error launching ${cmd}: ${e?.message ?? e}`, true);
      this.setState("failed");
      this.emit("done", { exit_code: -1, duration_ms: 0 });
      return;
    }

    this.child.stdout?.on("data", (d: Buffer) => this.handleData(d, false));
    this.child.stderr?.on("data", (d: Buffer) => this.handleData(d, true));

    this.child.on("error", (err: NodeJS.ErrnoException) => {
      if (err.code === "ENOENT") {
        this.emitLog(
          `Command not found: ${cmd}. Check Python command in settings.`,
          true
        );
      } else {
        this.emitLog(`Error launching process: ${err.message}`, true);
      }
      if (this._state === "running") {
        const duration = Date.now() - this.startTime;
        this.setState("failed");
        this.emit("done", { exit_code: -1, duration_ms: duration });
        this.child = null;
      }
    });

    this.child.on("close", (code) => {
      if (this.stdoutBuf) this.flushLine(this.stdoutBuf, false);
      if (this.stderrBuf) this.flushLine(this.stderrBuf, true);
      this.stdoutBuf = "";
      this.stderrBuf = "";
      if (this._state !== "running") return;
      const duration = Date.now() - this.startTime;
      const exitCode = code ?? -1;
      this.setState(exitCode === 0 ? "done" : "failed");
      this.emit("done", { exit_code: exitCode, duration_ms: duration });
      this.child = null;
    });
  }

  private handleData(data: Buffer, isStderr: boolean) {
    const text = data.toString("utf8");
    const buf = isStderr ? this.stderrBuf + text : this.stdoutBuf + text;
    const lines = buf.split(/\r?\n/);
    const remainder = lines.pop() ?? "";
    for (const line of lines) {
      if (line.length > 0) this.flushLine(line, isStderr);
    }
    if (isStderr) this.stderrBuf = remainder;
    else this.stdoutBuf = remainder;
  }

  private flushLine(text: string, isStderr: boolean) {
    this.emitLog(text, isStderr);
  }

  private emitLog(text: string, isStderr: boolean) {
    const line: LogLine = {
      time: fmtTime(),
      text,
      level: classify(text, isStderr),
    };
    this.emit("log", line);
  }

  cancel(): void {
    if (!this.child || this._state !== "running") return;
    const signal = getCancelSignal();
    try {
      this.child.kill(signal);
    } catch (e) {
      console.error("Failed to terminate process:", e);
    }
    const child = this.child;
    setTimeout(() => {
      if (child && !child.killed) {
        try {
          child.kill();
        } catch (e) {
          console.error("Failed to force-kill process:", e);
        }
      }
    }, 3000);
  }
}
