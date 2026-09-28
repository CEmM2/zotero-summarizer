import { App, Modal, PluginSettingTab, Setting, Notice } from "obsidian";
import type ZsumPlugin from "./main";
import { ZsumRunner } from "./runner";
import { resolveConfigPath } from "./config";
import * as fs from "fs";
import * as path from "path";

export interface ZsumSettings {
  configPath: string;
  projectRoot: string;
  pythonCmd: string;
  costPerMTokenIn: number;
  costPerMTokenOut: number;
  tokensPerCardIn: number;
  tokensPerCardOut: number;
}

export const DEFAULT_SETTINGS: ZsumSettings = {
  configPath: "zsum.config.yaml",
  projectRoot: "",
  pythonCmd: "uv run zsum",
  costPerMTokenIn: 3.0,
  costPerMTokenOut: 15.0,
  tokensPerCardIn: 4000,
  tokensPerCardOut: 500,
};

class OutputModal extends Modal {
  constructor(app: App, private title: string, private body: string) {
    super(app);
  }
  onOpen() {
    this.titleEl.setText(this.title);
    const pre = this.contentEl.createEl("pre", { cls: "zsum-output-modal" });
    pre.setText(this.body || "(no output)");
  }
  onClose() {
    this.contentEl.empty();
  }
}

export class ZsumSettingsTab extends PluginSettingTab {
  constructor(app: App, private plugin: ZsumPlugin) {
    super(app, plugin);
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();

    containerEl.createEl("h2", { text: "Paths" });

    const configSetting = new Setting(containerEl)
      .setName("Config path")
      .setDesc("Vault-relative or absolute path to zsum.config.yaml")
      .addText((t) =>
        t
          .setPlaceholder("zsum.config.yaml")
          .setValue(this.plugin.settings.configPath)
          .onChange(async (v) => {
            this.plugin.settings.configPath = v;
            await this.plugin.saveSettings();
            this.updateConfigWarning(warnEl);
          })
      );
    const warnEl = configSetting.descEl.createDiv({ cls: "zsum-inline-warn" });
    this.updateConfigWarning(warnEl);

    new Setting(containerEl)
      .setName("Project root")
      .setDesc("Absolute path to the zotero-summarizer repo (where pyproject.toml lives)")
      .addText((t) =>
        t
          .setPlaceholder("/path/to/zotero-summarizer")
          .setValue(this.plugin.settings.projectRoot)
          .onChange(async (v) => {
            this.plugin.settings.projectRoot = v;
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Python command")
      .setDesc("Command used to invoke the pipeline (e.g. 'uv run zsum')")
      .addText((t) =>
        t
          .setPlaceholder("uv run zsum")
          .setValue(this.plugin.settings.pythonCmd)
          .onChange(async (v) => {
            this.plugin.settings.pythonCmd = v;
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Test command")
      .setDesc("Runs `<pythonCmd> stats` to verify the environment is reachable.")
      .addButton((b) =>
        b.setButtonText("Test").onClick(() => this.runTest())
      );

    containerEl.createEl("h2", { text: "Cost estimation" });

    const num = (
      name: string,
      desc: string,
      key: keyof ZsumSettings,
      step = 0.01
    ) => {
      new Setting(containerEl)
        .setName(name)
        .setDesc(desc)
        .addText((t) => {
          t.inputEl.type = "number";
          (t.inputEl as HTMLInputElement).step = String(step);
          t.setValue(String(this.plugin.settings[key]));
          t.onChange(async (v) => {
            const n = parseFloat(v);
            if (!isNaN(n)) {
              (this.plugin.settings[key] as number) = n;
              await this.plugin.saveSettings();
              this.updatePreview(previewEl);
            }
          });
        });
    };

    num("Cost per M input tokens (USD)", "", "costPerMTokenIn");
    num("Cost per M output tokens (USD)", "", "costPerMTokenOut");
    num("Tokens per card (in)", "", "tokensPerCardIn", 1);
    num("Tokens per card (out)", "", "tokensPerCardOut", 1);

    const previewEl = containerEl.createDiv({ cls: "zsum-cost-preview" });
    this.updatePreview(previewEl);
  }

  private updatePreview(el: HTMLElement) {
    const s = this.plugin.settings;
    const per =
      (s.tokensPerCardIn * s.costPerMTokenIn) / 1e6 +
      (s.tokensPerCardOut * s.costPerMTokenOut) / 1e6;
    el.setText(`Current estimate: $${per.toFixed(4)} per card`);
  }

  private updateConfigWarning(el: HTMLElement) {
    el.empty();
    const path = resolveConfigPath(
      this.plugin.settings.configPath,
      (this.app.vault.adapter as any).basePath ?? ""
    );
    try {
      if (!fs.existsSync(path)) {
        el.setText(`⚠ File not found: ${path}`);
      }
    } catch (e) {
      console.error("Failed to check config path:", e);
      el.setText(`⚠ Unable to check: ${path}`);
    }
  }

  private async runTest() {
    const runner = new ZsumRunner();
    let out = "";
    runner.on("log", (l) => (out += l.text + "\n"));
    runner.on("done", ({ exit_code }) => {
      new OutputModal(
        this.app,
        exit_code === 0 ? "zsum stats — OK" : `zsum stats — exit ${exit_code}`,
        out
      ).open();
    });
    try {
      const vaultBase = (this.app.vault.adapter as any).basePath ?? "";
      const configAbs = resolveConfigPath(this.plugin.settings.configPath, vaultBase);
      const cwd = this.plugin.settings.projectRoot || path.dirname(configAbs);
      runner.run(this.plugin.settings.pythonCmd, ["--config", configAbs, "stats"], cwd);
    } catch (e: any) {
      new Notice(`Failed to launch: ${e?.message ?? e}`);
    }
  }
}
