"""setup-model command: pull an Ollama model and configure zsum to use it."""

from __future__ import annotations

import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path
from typing import Any

import click
import yaml

OLLAMA_ENDPOINT = "http://localhost:11434/v1"
OLLAMA_API_KEY = "ollama"

_TIERS_FILENAME = "model_tiers.yaml"


def _load_model_tiers() -> dict[str, dict[str, Any]]:
    """Load model tiers from the bundled YAML data file."""
    ref = resources.files("zsum").joinpath(_TIERS_FILENAME)
    raw = yaml.safe_load(ref.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not raw:
        raise RuntimeError(f"Invalid or empty {_TIERS_FILENAME}")
    return raw


MODEL_TIERS: dict[str, dict[str, Any]] = _load_model_tiers()
TIER_ORDER = list(MODEL_TIERS.keys())


def _check_ollama_installed() -> bool:
    return shutil.which("ollama") is not None


def _check_ollama_running() -> bool:
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _pull_model(model: str) -> bool:
    """Stream ollama pull output to stdout. Returns True on success."""
    try:
        proc = subprocess.Popen(
            ["ollama", "pull", model],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            click.echo(line, nl=False)
        proc.wait()
        return proc.returncode == 0
    except (FileNotFoundError, OSError) as e:
        click.echo(click.style(f"Error running ollama pull: {e}", fg="red"), err=True)
        return False


def _verify_model(model: str) -> bool:
    """Send a tiny completion to confirm the model responds."""
    try:
        import openai

        client = openai.OpenAI(base_url=OLLAMA_ENDPOINT, api_key=OLLAMA_API_KEY)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with the single word: ok"}],
            max_tokens=8,
        )
        text = (resp.choices[0].message.content or "").strip().lower()
        return bool(text)
    except Exception as e:  # noqa: BLE001
        click.echo(click.style(f"Verification failed: {e}", fg="yellow"), err=True)
        return False


def _load_yaml(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise click.ClickException(f"Could not parse config file {path}: {e}") from e
    except OSError as e:
        raise click.ClickException(f"Could not read config file {path}: {e}") from e
    return data if isinstance(data, dict) else {}


def _update_config(config_path: Path, model: str, dry_run: bool) -> None:
    """Write or update config.yaml with Ollama / openai_compat settings."""
    data = _load_yaml(config_path) if config_path.exists() else {}

    llm = data.setdefault("llm", {})
    llm["provider"] = "openai_compat"
    oc = llm.setdefault("openai_compat", {})
    oc["base_url"] = OLLAMA_ENDPOINT
    oc["model"] = model
    oc["api_key"] = OLLAMA_API_KEY
    oc.setdefault("max_tokens_card", 4096)
    oc.setdefault("max_tokens_digest", 8192)
    routing = llm.setdefault("routing", {})
    routing["cards"] = "openai_compat"
    routing["digests"] = "openai_compat"
    routing["redigest"] = "openai_compat"

    yaml_text = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)

    if dry_run:
        click.echo(click.style(f"\n[dry-run] Would write to {config_path}:", fg="cyan"))
        click.echo(yaml_text)
        return

    config_path.write_text(yaml_text, encoding="utf-8")
    click.echo(click.style(f"Config written to {config_path}", fg="green"))


def run_setup_model(
    *,
    size: str,
    model: str | None,
    list_tiers: bool,
    dry_run: bool,
    config_path: Path,
) -> None:
    """Core logic for setup-model, extracted for testability."""
    if list_tiers:
        click.echo("Available model tiers:\n")
        for tier in TIER_ORDER:
            info = MODEL_TIERS[tier]
            marker = " (default)" if tier == "medium" else ""
            click.echo(
                f"  {click.style(tier, bold=True)}{marker}\n"
                f"    model : {info['model']}\n"
                f"    params: {info['params']}\n"
            )
        return

    chosen_model = model if model else MODEL_TIERS[size]["model"]

    click.echo(f"Setting up Ollama model: {click.style(chosen_model, bold=True)}")
    if dry_run:
        click.echo(click.style("[dry-run mode — no changes will be made]", fg="cyan"))

    if not _check_ollama_installed():
        click.echo(
            click.style("Ollama is not installed.", fg="red")
            + " Install it from https://ollama.com/download and re-run this command.",
            err=True,
        )
        sys.exit(1)

    if not dry_run and not _check_ollama_running():
        click.echo(
            click.style("Ollama daemon is not running.", fg="red")
            + " Start it with `ollama serve` or open the Ollama desktop app, then retry.",
            err=True,
        )
        sys.exit(1)

    if dry_run:
        click.echo(f"[dry-run] Would run: ollama pull {chosen_model}")
    else:
        click.echo(f"\nPulling {chosen_model} …")
        if not _pull_model(chosen_model):
            click.echo(
                click.style(f"ollama pull {chosen_model} failed.", fg="red"),
                err=True,
            )
            sys.exit(1)
        click.echo(click.style("Pull complete.", fg="green"))

    _update_config(config_path, chosen_model, dry_run)

    if not dry_run:
        click.echo(f"\nVerifying {chosen_model} responds …")
        if _verify_model(chosen_model):
            click.echo(click.style("Model verified successfully.", fg="green"))
        else:
            click.echo(
                click.style("Warning: verification failed.", fg="yellow")
                + " The model was pulled but did not respond to a test prompt.\n"
                "You can still try running `zsum all`.",
            )

    if not dry_run:
        click.echo(
            f"\n{click.style('Done!', fg='green', bold=True)} "
            f"Run `zsum all` to generate your summaries."
        )


@click.command(name="setup-model")
@click.option(
    "--size",
    type=click.Choice(TIER_ORDER, case_sensitive=False),
    default="medium",
    show_default=True,
    help="Model tier to pull (ignored when --model is set).",
)
@click.option("--model", default=None, help="Override with any Ollama model name (e.g. llama3.2).")
@click.option("--list", "list_tiers", is_flag=True, help="List available tiers and exit.")
@click.option("--dry-run", is_flag=True, help="Show what would happen without pulling or writing.")
@click.pass_context
def setup_model(ctx, size, model, list_tiers, dry_run):
    """Pull an Ollama model and configure zsum to use it."""
    config_path = Path(ctx.obj["config_path"])
    run_setup_model(
        size=size,
        model=model,
        list_tiers=list_tiers,
        dry_run=dry_run,
        config_path=config_path,
    )
