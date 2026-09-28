import { Plugin, WorkspaceLeaf, Notice } from "obsidian";
import { ZsumSettings, DEFAULT_SETTINGS, ZsumSettingsTab } from "./settings";
import { ZsumView, VIEW_TYPE_ZSUM } from "./view";

export default class ZsumPlugin extends Plugin {
  settings!: ZsumSettings;

  async onload(): Promise<void> {
    await this.loadSettings();
    this.registerView(VIEW_TYPE_ZSUM, (leaf) => new ZsumView(leaf, this));
    this.addRibbonIcon("book-open", "Open Zotero Summarizer", () => {
      this.activateView();
    });
    this.addCommand({
      id: "open",
      name: "Open view",
      callback: () => this.activateView(),
    });
    this.addCommand({
      id: "refresh",
      name: "Refresh",
      callback: () => this.refreshViews(),
    });
    this.addCommand({
      id: "run-all",
      name: "Run full pipeline",
      callback: () => {
        const leaves = this.app.workspace.getLeavesOfType(VIEW_TYPE_ZSUM);
        if (leaves.length === 0) {
          new Notice("Open the Zotero Summarizer view first.");
          return;
        }
        const view = leaves[0].view as ZsumView;
        view.runStageExternal(["all"]);
      },
    });
    this.addSettingTab(new ZsumSettingsTab(this.app, this));
  }

  async onunload(): Promise<void> {}

  async loadSettings(): Promise<void> {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }

  async saveSettings(): Promise<void> {
    await this.saveData(this.settings);
  }

  async activateView(): Promise<void> {
    const existing = this.app.workspace.getLeavesOfType(VIEW_TYPE_ZSUM);
    let leaf: WorkspaceLeaf;
    if (existing.length > 0) {
      leaf = existing[0];
    } else {
      leaf = this.app.workspace.getLeaf("tab");
      await leaf.setViewState({ type: VIEW_TYPE_ZSUM, active: true });
    }
    this.app.workspace.revealLeaf(leaf);
  }

  refreshViews(): void {
    const leaves = this.app.workspace.getLeavesOfType(VIEW_TYPE_ZSUM);
    for (const leaf of leaves) {
      const view = leaf.view as ZsumView;
      view.reloadIndex();
    }
  }
}
