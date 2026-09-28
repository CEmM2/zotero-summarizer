import {
  ItemView,
  WorkspaceLeaf,
  TFile,
  Notice,
  setIcon,
} from "obsidian";
import * as fs from "fs";
import * as path from "path";
import type ZsumPlugin from "./main";
import {
  ZsumIndex,
  readIndexDetailed,
  computeStats,
  getCollectionPapers,
  LibraryStats,
  ItemIndex,
  CollectionIndex,
  isReviewPaper,
} from "./index-reader";
import {
  resolveConfigPath,
  ZSUM_CONFIG_SCHEMA,
  ZsumConfig,
  ZsumConfigDocumentService,
  ZsumConfigDocumentState,
} from "./config";
import * as yaml from "js-yaml";
import { ZsumRunner, LogLine, RunnerState } from "./runner";
import { estimateCost } from "./cost";
import {
  buildCollectionRefreshQueue,
  buildConfigViewModel,
  buildNavSections,
  computeStageRunArgs,
  filterPapersByCitekey,
  allCollectionKeys,
  formatBbtIndicator,
  formatCacheChipText,
  formatConfigStatusText,
  formatCostPreview,
  formatIndexedTimestamp,
  formatRedigestStatus,
  formatRootStatusChip,
  typePillVariant,
  ZSUM_CONFIG_NAV_GROUPS,
  ZSUM_LIBRARY_STAGE_BUTTONS,
  ZSUM_VIEW_TABS,
  type ZsumConfigFeedback,
  type ZsumStageButtonDefinition,
  type ZsumViewTabId,
} from "./view-model";

const UNSAFE_FILENAME_CHARS = /[<>:"\\/|?*]/g;
function safeFilename(name: string): string {
  const safe = name.replace(UNSAFE_FILENAME_CHARS, "_").trim().replace(/\.+$/, "");
  if (!safe) throw new Error(`Cannot create safe filename from: ${name}`);
  return safe;
}

export const VIEW_TYPE_ZSUM = "zsum-view";

export class ZsumView extends ItemView {
  private plugin: ZsumPlugin;
  private index: ZsumIndex | null = null;
  private zsumConfig: ZsumConfig | null = null;
  private configService: ZsumConfigDocumentService | null = null;
  private configState: ZsumConfigDocumentState | null = null;
  private configFeedback: ZsumConfigFeedback | null = null;
  private selectedCollectionKey: string = "root";
  private runner: ZsumRunner;
  private logLines: LogLine[] = [];
  private userScrolledUp: boolean = false;
  private expandedNodes: Set<string> = new Set();
  private activeStage: string | null = null;
  private lastStageArgs: string[] = [];
  private queuedStageArgs: string[][] = [];
  private preserveLogOnNextRun: boolean = false;
  private sortByCitations: boolean = false;
  private paperSearchQuery: string = "";
  private papersHeaderCollectionKey: string | null = null;
  private papersScrollEl: HTMLElement | null = null;
  private papersSubtitleEl: HTMLElement | null = null;
  private lastIndexedAt: Date | null = null;
  private activeConfigNavSection: string = "paths";
  private lastConfigSavedAt: Date | null = null;
  private configBuilt: boolean = false;
  private configNavEl: HTMLElement | null = null;
  private configPanelsEl: HTMLElement | null = null;
  private configBannersEl: HTMLElement | null = null;
  private configFooterStatusEl: HTMLElement | null = null;
  private configFooterActionsEl: HTMLElement | null = null;
  private drawerEl: HTMLElement | null = null;
  private drawerOpen: boolean = false;
  private drawerTestOutputEl: HTMLElement | null = null;
  private drawerCostPreviewEl: HTMLElement | null = null;
  private drawerKeydownHandler: ((e: KeyboardEvent) => void) | null = null;
  private metaCacheChipEl: HTMLElement | null = null;
  private metaRootChipEl: HTMLElement | null = null;
  private activeTab: ZsumViewTabId = "library";

  // cached refs
  private tabsEl!: HTMLElement;
  private libraryPanelEl!: HTMLElement;
  private configPanelEl!: HTMLElement;
  private statusBarEl!: HTMLElement;
  private progressBarEl!: HTMLElement;
  private treeScrollEl!: HTMLElement;
  private papersPanelEl!: HTMLElement;
  private controlsEl!: HTMLElement;
  private logEl!: HTMLElement;
  private stagePadEl!: HTMLElement;
  private localGridEl!: HTMLElement;
  private llmGridEl!: HTMLElement;
  private costHeaderEl!: HTMLElement;
  private pipelineStripEl!: HTMLElement;
  private forceToggleEl!: HTMLInputElement;

  constructor(leaf: WorkspaceLeaf, plugin: ZsumPlugin) {
    super(leaf);
    this.plugin = plugin;
    this.runner = new ZsumRunner();
    this.runner.on("log", (l: LogLine) => this.appendLogLine(l));
    this.runner.on("state-change", (s: RunnerState) => this.updateRunState(s));
    this.runner.on("done", async (p: { exit_code: number; duration_ms: number }) => {
      this.appendLogLine({
        time: new Date().toTimeString().slice(0, 8),
        text: `[zsum] finished in ${(p.duration_ms / 1000).toFixed(1)}s (exit ${p.exit_code})`,
        level: p.exit_code === 0 ? "ok" : "error",
      });
      if (p.exit_code !== 0) {
        this.appendLogLine({
          time: new Date().toTimeString().slice(0, 8),
          text: "[zsum] error: stage failed. See stderr lines above for details.",
          level: "error",
        });
        if (this.wasCollectionDigestRun()) {
          const compatHint =
            "[zsum] hint: this run used '--collection'. Your installed zsum CLI may not support it yet.";
          this.appendLogLine({
            time: new Date().toTimeString().slice(0, 8),
            text: compatHint,
            level: "warn",
          });
          new Notice(
            "Regenerate digest may require a newer zsum CLI with '--collection' support."
          );
        }
        new Notice("zsum failed — see log for details");
      }
      if (p.exit_code !== 0) {
        this.queuedStageArgs = [];
      }
      const nextQueuedArgs =
        p.exit_code === 0 ? this.queuedStageArgs.shift() ?? null : null;
      if (nextQueuedArgs) {
        this.preserveLogOnNextRun = true;
        this.appendLogLine({
          time: new Date().toTimeString().slice(0, 8),
          text: `[zsum] queue: ${nextQueuedArgs.join(" ")}`,
          level: "info",
        });
        this.runStage(nextQueuedArgs);
        return;
      }
      this.lastStageArgs = [];
      await this.reloadIndex();
    });
  }

  getViewType(): string { return VIEW_TYPE_ZSUM; }
  getDisplayText(): string { return "Zotero Summarizer"; }
  getIcon(): string { return "book-open"; }

  async onOpen(): Promise<void> {
    this.buildSkeleton();
    this.drawerKeydownHandler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && this.drawerOpen) {
        this.closeDrawer();
        e.stopPropagation();
      }
    };
    this.contentEl.addEventListener("keydown", this.drawerKeydownHandler);
    await this.reloadIndex();
  }

  async onClose(): Promise<void> {
    this.runner.removeAllListeners();
    if (this.drawerKeydownHandler) {
      this.contentEl.removeEventListener("keydown", this.drawerKeydownHandler);
      this.drawerKeydownHandler = null;
    }
  }

  openDrawer() {
    if (!this.drawerEl) return;
    this.drawerOpen = true;
    this.drawerEl.addClass("is-open");
  }

  closeDrawer() {
    if (!this.drawerEl) return;
    this.drawerOpen = false;
    this.drawerEl.removeClass("is-open");
  }

  toggleDrawer() {
    if (this.drawerOpen) this.closeDrawer();
    else this.openDrawer();
  }

  expandAllCollections() {
    for (const key of allCollectionKeys(this.index?.collections)) {
      this.expandedNodes.add(key);
    }
    if (this.index) this.renderTree();
  }

  private setActiveTab(tab: ZsumViewTabId) {
    this.activeTab = tab;
    this.updateTabState();
  }

  private updateTabState() {
    const dirtyBadge = this.configState?.dirty ? "Unsaved" : null;
    const buttons = this.tabsEl.querySelectorAll<HTMLButtonElement>(".zsum-tab-btn");
    buttons.forEach((button) => {
      const tabId = button.dataset.tab as ZsumViewTabId | undefined;
      const baseLabel =
        ZSUM_VIEW_TABS.find((tab) => tab.id === tabId)?.label ?? button.dataset.tab ?? "";
      button.empty();
      button.createSpan({ text: baseLabel });
      if (tabId === "config" && dirtyBadge) {
        button.createSpan({ cls: "zsum-tab-badge", text: dirtyBadge });
      }
      button.toggleClass("is-active", tabId === this.activeTab);
    });

    this.libraryPanelEl.toggleClass("zsum-hidden", this.activeTab !== "library");
    this.configPanelEl.toggleClass("zsum-hidden", this.activeTab !== "config");
  }

  private setConfigState(
    state: ZsumConfigDocumentState | null,
    options: { syncRuntime?: boolean } = {}
  ) {
    this.configState = state;
    if (options.syncRuntime) {
      this.zsumConfig = this.configService?.readRuntimeConfig() ?? null;
    }
    this.renderConfigPanel();
    this.updateTabState();
  }

  private updateConfigField(fieldPath: string, value: unknown) {
    if (!this.configService || !this.configState) return;
    this.configFeedback = null;
    const nextState = this.configService.updateField(fieldPath as any, value);
    this.setConfigState(nextState);
  }

  private async handleConfigAction(actionId: "save" | "revert" | "reload") {
    if (!this.configService || !this.configState) return;

    if (actionId === "revert") {
      this.configFeedback = null;
      this.setConfigState(this.configService.revert());
      return;
    }

    if (actionId === "reload") {
      this.configFeedback = null;
      await this.reloadIndex();
      return;
    }

    try {
      this.configFeedback = null;
      await this.configService.save();
      this.lastConfigSavedAt = new Date();
      this.configFeedback = { kind: "success", text: "Config saved." };
      await this.reloadIndex();
      new Notice("Config saved.");
    } catch (error: any) {
      this.configFeedback = {
        kind: "error",
        text: error?.message ?? String(error),
      };
      this.renderConfigPanel();
      this.updateTabState();
    }
  }

  private renderConfigPanel() {
    if (!this.configBuilt) {
      this.buildConfigSkeleton();
      this.configBuilt = true;
    }

    if (!this.configState) {
      // Wipe panels area + show feedback (skeleton stays mounted).
      this.configPanelsEl?.empty();
      this.configBannersEl?.empty();
      this.configPanelsEl?.createDiv({
        cls: "zsum-empty-panel",
        text: this.configFeedback?.text ?? "Loading config…",
      });
      this.configFooterStatusEl?.setText("");
      this.refreshConfigFooterActions(null);
      this.refreshConfigNavActiveState();
      return;
    }

    const model = buildConfigViewModel(
      ZSUM_CONFIG_SCHEMA,
      this.configState,
      this.configFeedback
    );

    this.refreshConfigBanners(model.banners);
    this.refreshConfigPanels(model.sections);
    this.refreshConfigNavActiveState();
    this.refreshConfigFooterActions(model.actions);
    this.refreshConfigFooterStatus();
  }

  private buildConfigSkeleton() {
    this.configPanelEl.empty();

    const header = this.configPanelEl.createDiv({ cls: "zsum-config-header" });
    const headerLeft = header.createDiv({ cls: "zsum-config-header-left" });
    headerLeft.createDiv({ cls: "zsum-config-title", text: "Config" });
    headerLeft.createDiv({
      cls: "zsum-config-path",
      text: this.configState?.path ?? "Loading config…",
    });
    this.configBannersEl = header.createDiv({ cls: "zsum-config-banners" });

    const body = this.configPanelEl.createDiv({ cls: "zsum-config-body" });
    this.configNavEl = body.createDiv({
      cls: "zsum-config-nav",
      attr: { role: "tablist", "aria-label": "Config sections" },
    });
    for (const group of ZSUM_CONFIG_NAV_GROUPS) {
      const btn = this.configNavEl.createEl("button", {
        cls: "zsum-config-nav-btn",
        text: group.label,
      });
      btn.dataset.groupId = group.id;
      btn.addEventListener("click", () => {
        if (this.activeConfigNavSection === group.id) return;
        this.activeConfigNavSection = group.id;
        this.renderConfigPanel();
      });
    }
    this.configPanelsEl = body.createDiv({ cls: "zsum-config-panels" });

    const footer = this.configPanelEl.createDiv({ cls: "zsum-config-footer" });
    this.configFooterStatusEl = footer.createDiv({ cls: "zsum-config-footer-status" });
    this.configFooterActionsEl = footer.createDiv({ cls: "zsum-config-footer-actions" });
  }

  private refreshConfigBanners(banners: { kind: string; text: string }[]) {
    if (!this.configBannersEl) return;
    this.configBannersEl.empty();
    if (this.configState?.dirty) {
      this.configBannersEl.createDiv({
        cls: "zsum-config-banner-chip zsum-config-banner-chip-warn",
        text: "Unsaved edits",
      });
    } else if (this.configState && !this.configState.parseError) {
      this.configBannersEl.createDiv({
        cls: "zsum-config-banner-chip zsum-config-banner-chip-ok",
        text: "Comments preserved",
      });
    }
    for (const banner of banners) {
      this.configBannersEl.createDiv({
        cls: `zsum-config-banner zsum-config-banner-${banner.kind}`,
        text: banner.text,
      });
    }
  }

  private refreshConfigNavActiveState() {
    if (!this.configNavEl) return;
    const buttons = this.configNavEl.querySelectorAll<HTMLButtonElement>(
      ".zsum-config-nav-btn"
    );
    buttons.forEach((b) => {
      b.toggleClass(
        "is-active",
        b.dataset.groupId === this.activeConfigNavSection
      );
    });
  }

  private refreshConfigPanels(sections: { id: string; label: string; fields: any[] }[]) {
    if (!this.configPanelsEl) return;
    this.configPanelsEl.empty();
    const activeSectionIds = new Set(
      buildNavSections(ZSUM_CONFIG_SCHEMA, this.activeConfigNavSection).map((s) => s.id)
    );
    const activeSections = sections.filter((s) => activeSectionIds.has(s.id));
    if (!activeSections.length) {
      this.configPanelsEl.createDiv({
        cls: "zsum-empty-panel",
        text: "No sections in this group.",
      });
      return;
    }
    const panel = this.configPanelsEl.createDiv({ cls: "zsum-config-active-panel" });
    for (const section of activeSections) {
      this.renderConfigSection(panel, section);
    }
  }

  private renderConfigSection(
    parent: HTMLElement,
    section: { id: string; label: string; fields: any[] }
  ) {
    const sectionEl = parent.createDiv({ cls: "zsum-config-section" });
    sectionEl.createDiv({ cls: "zsum-config-section-title", text: section.label });

    for (const field of section.fields) {
      const fieldEl = sectionEl.createDiv({ cls: "zsum-config-field" });
      const metaEl = fieldEl.createDiv({ cls: "zsum-config-meta" });
      metaEl.createDiv({ cls: "zsum-config-label", text: field.label });
      if (field.description) {
        metaEl.createDiv({ cls: "zsum-config-description", text: field.description });
      }

      const controlEl = fieldEl.createDiv({ cls: "zsum-config-control" });
      if (field.input === "dropdown") {
        const selectEl = controlEl.createEl("select", { cls: "zsum-config-select" });
        for (const option of field.options ?? []) {
          const optionEl = selectEl.createEl("option", { text: option.label });
          optionEl.value = option.value;
        }
        selectEl.value = String(field.value);
        selectEl.addEventListener("change", () =>
          this.updateConfigField(field.path, selectEl.value)
        );
      } else if (field.input === "toggle") {
        const toggleLabel = controlEl.createEl("label", { cls: "zsum-config-toggle" });
        const checkboxEl = toggleLabel.createEl("input", { type: "checkbox" });
        checkboxEl.checked = Boolean(field.value);
        checkboxEl.addEventListener("change", () =>
          this.updateConfigField(field.path, checkboxEl.checked)
        );
        toggleLabel.createSpan({ text: Boolean(field.value) ? "Enabled" : "Disabled" });
      } else if (field.input === "textarea") {
        const textareaEl = controlEl.createEl("textarea", { cls: "zsum-config-textarea" });
        textareaEl.rows = 4;
        textareaEl.value = String(field.value);
        textareaEl.addEventListener("input", () =>
          this.updateConfigField(field.path, textareaEl.value)
        );
      } else {
        const inputEl = controlEl.createEl("input", {
          cls: "zsum-config-input",
          type: field.input === "number" ? "number" : "text",
        });
        inputEl.value = String(field.value);
        inputEl.addEventListener("input", () =>
          this.updateConfigField(field.path, inputEl.value)
        );
      }

      if (field.pathPreview) {
        controlEl.createDiv({ cls: "zsum-config-preview", text: field.pathPreview });
      }
      if (field.error) {
        controlEl.createDiv({ cls: "zsum-config-error", text: field.error });
      }
    }
  }

  private refreshConfigFooterActions(
    actions: { id: "save" | "revert" | "reload"; label: string; disabled: boolean }[] | null
  ) {
    if (!this.configFooterActionsEl) return;
    this.configFooterActionsEl.empty();
    if (!actions) return;
    for (const action of actions) {
      const cls =
        action.id === "save"
          ? "zsum-stage-btn zsum-stage-btn-primary"
          : "zsum-stage-btn";
      const btn = this.configFooterActionsEl.createEl("button", {
        cls,
        text: action.label,
      });
      btn.disabled = action.disabled;
      btn.addEventListener("click", () => this.handleConfigAction(action.id));
    }
  }

  private refreshConfigFooterStatus() {
    if (!this.configFooterStatusEl) return;
    const dirty = this.configState?.dirty === true;
    this.configFooterStatusEl.setText(
      formatConfigStatusText(dirty, this.lastConfigSavedAt)
    );
  }

  private startCollectionRefreshQueue(collectionName: string) {
    if (this.runner.state === "running") {
      new Notice("A pipeline stage is already running.");
      return;
    }
    const queue = buildCollectionRefreshQueue(collectionName);
    this.queuedStageArgs = queue.slice(1);
    this.runStage(queue[0]);
  }

  private buildSkeleton() {
    const root = this.contentEl;
    root.empty();
    root.addClass("zsum-view");

    this.tabsEl = root.createDiv({ cls: "zsum-tabs" });
    const tabGroup = this.tabsEl.createDiv({ cls: "zsum-tab-group" });
    for (const tab of ZSUM_VIEW_TABS) {
      const btn = tabGroup.createEl("button", {
        cls: "zsum-tab-btn",
        text: tab.label,
      });
      btn.dataset.tab = tab.id;
      btn.addEventListener("click", () => this.setActiveTab(tab.id));
    }

    const meta = this.tabsEl.createDiv({ cls: "zsum-plugin-meta" });
    this.metaCacheChipEl = meta.createDiv({
      cls: "zsum-meta-chip",
      text: formatCacheChipText(this.zsumConfig?.cache_dir),
    });
    const rootInit = formatRootStatusChip(this.plugin.settings.projectRoot ?? "");
    this.metaRootChipEl = meta.createDiv({
      cls: `zsum-meta-chip zsum-meta-chip-${rootInit.modifier}`,
      text: rootInit.label,
    });
    const metaSettingsBtn = meta.createEl("button", {
      cls: "zsum-icon-btn zsum-meta-settings-btn",
      text: "⚙",
      attr: { "aria-label": "Plugin settings" },
    });
    metaSettingsBtn.addEventListener("click", () => this.toggleDrawer());

    this.libraryPanelEl = root.createDiv({ cls: "zsum-tab-panel zsum-library-panel" });
    this.configPanelEl = root.createDiv({ cls: "zsum-tab-panel zsum-config-panel" });

    this.statusBarEl = this.libraryPanelEl.createDiv({ cls: "zsum-status-bar" });
    this.progressBarEl = this.libraryPanelEl.createDiv({ cls: "zsum-progress-bar zsum-hidden" });
    this.progressBarEl.createDiv({ cls: "zsum-progress-inner" });

    const content = this.libraryPanelEl.createDiv({ cls: "zsum-content" });

    const treePanel = content.createDiv({ cls: "zsum-tree-panel" });
    const treeHeader = treePanel.createDiv({ cls: "zsum-panel-header" });
    treeHeader.createSpan({ cls: "zsum-panel-header-title", text: "Collections" });
    const expandAllBtn = treeHeader.createEl("button", {
      cls: "zsum-icon-btn zsum-tree-expand-all",
      text: "+",
      attr: { "aria-label": "Expand all collections", title: "Expand all collections" },
    });
    expandAllBtn.addEventListener("click", () => this.expandAllCollections());
    this.treeScrollEl = treePanel.createDiv({ cls: "zsum-tree-scroll" });
    const legend = treePanel.createDiv({ cls: "zsum-legend" });
    legend.createSpan({ text: "Digest state: " });
    const mkDot = (cls: string, label: string) => {
      const s = legend.createSpan({ cls: "zsum-legend-item" });
      s.createSpan({ cls: `zsum-dot ${cls}` });
      s.createSpan({ text: " " + label });
    };
    mkDot("zsum-dot-ok", "up-to-date");
    mkDot("zsum-dot-stale", "stale");
    mkDot("zsum-dot-missing", "missing");

    this.papersPanelEl = content.createDiv({ cls: "zsum-papers-panel" });

    this.controlsEl = this.libraryPanelEl.createDiv({ cls: "zsum-controls" });

    // Controls head: Pipeline title + cost line + Force toggle + Clear Cache X
    const head = this.controlsEl.createDiv({ cls: "zsum-controls-head" });
    head.createDiv({ cls: "zsum-controls-title", text: "Pipeline" });
    this.costHeaderEl = head.createDiv({ cls: "zsum-controls-cost" });
    const headRight = head.createDiv({ cls: "zsum-controls-actions" });
    const forceLabel = headRight.createEl("label", {
      cls: "zsum-force-toggle",
      attr: { title: "Append --force to forceable stages on the next run" },
    });
    this.forceToggleEl = forceLabel.createEl("input", { type: "checkbox" });
    forceLabel.createSpan({ text: "Force" });
    const clearBtn = headRight.createEl("button", {
      text: "✕",
      cls: "zsum-icon-btn zsum-clear-cache-btn",
      attr: {
        "aria-label": "Clear cache",
        title: "Clear cached cards (shift-click = clear ALL cards + digests)",
      },
    });
    clearBtn.addEventListener("click", (e) => this.handleClearCacheClick(e));

    // Controls body: stage-pad (left) + log-pane (right)
    const body = this.controlsEl.createDiv({ cls: "zsum-controls-body" });
    this.stagePadEl = body.createDiv({ cls: "zsum-stage-pad" });

    const localSection = this.stagePadEl.createDiv({ cls: "zsum-stage-section" });
    localSection.createDiv({
      cls: "zsum-stage-section-title",
      text: "Local & network",
    });
    this.localGridEl = localSection.createDiv({ cls: "zsum-stage-grid" });

    const llmSection = this.stagePadEl.createDiv({ cls: "zsum-stage-section" });
    llmSection.createDiv({ cls: "zsum-stage-section-title", text: "LLM stages" });
    this.llmGridEl = llmSection.createDiv({ cls: "zsum-stage-grid" });

    const logPane = body.createDiv({ cls: "zsum-log-pane" });
    this.pipelineStripEl = logPane.createDiv({ cls: "zsum-pipeline-strip zsum-hidden" });
    this.logEl = logPane.createDiv({ cls: "zsum-log" });
    this.logEl.addEventListener("scroll", () => {
      const el = this.logEl;
      const atBottom = el.scrollHeight - el.scrollTop <= el.clientHeight + 20;
      this.userScrolledUp = !atBottom;
    });

    this.renderButtons();
    this.renderConfigPanel();
    this.updateTabState();
    this.buildSettingsDrawer();
  }

  private buildSettingsDrawer() {
    this.drawerEl = this.contentEl.createDiv({
      cls: "zsum-settings-drawer",
      attr: { role: "dialog", "aria-label": "Plugin settings" },
    });

    const head = this.drawerEl.createDiv({ cls: "zsum-drawer-head" });
    head.createDiv({ cls: "zsum-drawer-title", text: "Plugin Settings" });
    const closeBtn = head.createEl("button", {
      cls: "zsum-icon-btn",
      text: "✕",
      attr: { "aria-label": "Close settings" },
    });
    closeBtn.addEventListener("click", () => this.closeDrawer());

    const body = this.drawerEl.createDiv({ cls: "zsum-drawer-body" });
    this.buildDrawerCommandBlock(body);
    this.buildDrawerCostBlock(body);
  }

  private buildDrawerCommandBlock(parent: HTMLElement) {
    const block = parent.createDiv({ cls: "zsum-setting-block" });
    block.createDiv({ cls: "zsum-setting-block-title", text: "Command" });

    this.makeDrawerTextRow(block, "Config path", "configPath");
    this.makeDrawerTextRow(block, "Project root", "projectRoot");
    this.makeDrawerTextRow(block, "Python command", "pythonCmd");

    const testBtn = block.createEl("button", {
      cls: "zsum-stage-btn zsum-stage-btn-primary zsum-drawer-test-btn",
      text: "Test command",
    });
    testBtn.addEventListener("click", () => this.runDrawerTest());

    this.drawerTestOutputEl = block.createEl("pre", {
      cls: "zsum-test-output",
      text: "",
    });
  }

  private buildDrawerCostBlock(parent: HTMLElement) {
    const block = parent.createDiv({ cls: "zsum-setting-block" });
    block.createDiv({
      cls: "zsum-setting-block-title",
      text: "Cost estimation",
    });

    this.makeDrawerNumberRow(block, "Input $/M tokens", "costPerMTokenIn", 0.01);
    this.makeDrawerNumberRow(block, "Output $/M tokens", "costPerMTokenOut", 0.01);
    this.makeDrawerNumberRow(block, "Tokens per card (in)", "tokensPerCardIn", 1);
    this.makeDrawerNumberRow(block, "Tokens per card (out)", "tokensPerCardOut", 1);

    this.drawerCostPreviewEl = block.createDiv({
      cls: "zsum-drawer-cost-preview",
      text: formatCostPreview(this.plugin.settings),
    });
  }

  private makeDrawerTextRow(
    parent: HTMLElement,
    label: string,
    key: "configPath" | "projectRoot" | "pythonCmd"
  ) {
    const row = parent.createDiv({ cls: "zsum-setting-row" });
    row.createEl("label", { text: label });
    const input = row.createEl("input", {
      type: "text",
      attr: { "aria-label": label },
    });
    input.value = this.plugin.settings[key];
    input.addEventListener("input", async () => {
      this.plugin.settings[key] = input.value;
      await this.plugin.saveSettings();
      if (key === "projectRoot") this.refreshMetaChips();
    });
  }

  private makeDrawerNumberRow(
    parent: HTMLElement,
    label: string,
    key:
      | "costPerMTokenIn"
      | "costPerMTokenOut"
      | "tokensPerCardIn"
      | "tokensPerCardOut",
    step: number
  ) {
    const row = parent.createDiv({ cls: "zsum-setting-row" });
    row.createEl("label", { text: label });
    const input = row.createEl("input", {
      type: "number",
      attr: { step: String(step), "aria-label": label },
    });
    input.value = String(this.plugin.settings[key]);
    input.addEventListener("input", async () => {
      const n = parseFloat(input.value);
      if (Number.isNaN(n)) return;
      this.plugin.settings[key] = n;
      await this.plugin.saveSettings();
      this.refreshDrawerCostPreview();
      this.renderCostHeader();
    });
  }

  private refreshDrawerCostPreview() {
    if (!this.drawerCostPreviewEl) return;
    this.drawerCostPreviewEl.setText(formatCostPreview(this.plugin.settings));
  }

  private runDrawerTest() {
    if (!this.drawerTestOutputEl) return;
    this.drawerTestOutputEl.setText("Running zsum stats...");
    const runner = new ZsumRunner();
    let out = "";
    runner.on("log", (l: LogLine) => {
      out += l.text + "\n";
    });
    runner.on("done", (p: { exit_code: number; duration_ms: number }) => {
      const status = p.exit_code === 0 ? "OK" : `exit ${p.exit_code}`;
      this.drawerTestOutputEl?.setText(
        `zsum stats — ${status}\n${out || "(no output)"}`
      );
    });
    try {
      const vaultBase = (this.app.vault.adapter as any).basePath ?? "";
      const configAbs = resolveConfigPath(this.plugin.settings.configPath, vaultBase);
      const cwd = this.plugin.settings.projectRoot || path.dirname(configAbs);
      runner.run(this.plugin.settings.pythonCmd, ["--config", configAbs, "stats"], cwd);
    } catch (e: any) {
      this.drawerTestOutputEl.setText(`Failed to launch: ${e?.message ?? e}`);
    }
  }

  private handleClearCacheClick(e: MouseEvent) {
    if (this.runner.state === "running") {
      new Notice("A pipeline stage is already running.");
      return;
    }
    const all = e.shiftKey;
    const scope = all ? "--all" : "--cards";
    const label = all ? "ALL cached cards and digests" : "cached cards";
    const ok = typeof window !== "undefined"
      ? window.confirm(`Clear ${label}? This cannot be undone.`)
      : true;
    if (!ok) return;
    this.runStage(["clear-cache", scope]);
  }

  async reloadIndex(): Promise<void> {
    const vaultBase = (this.app.vault.adapter as any).basePath ?? "";
    try {
      this.configService = await ZsumConfigDocumentService.open(
        this.plugin.settings.configPath,
        vaultBase
      );
      this.setConfigState(this.configService.getState(), { syncRuntime: true });
    } catch (error: any) {
      console.error("Failed to open zsum config document:", error);
      this.configService = null;
      this.configFeedback = {
        kind: "error",
        text: `Failed to load config: ${error?.message ?? error}`,
      };
      this.setConfigState(null, { syncRuntime: true });
      this.index = null;
      this.renderEmpty("Failed to load config. Check plugin settings.");
      return;
    }

    if (!this.zsumConfig) {
      this.index = null;
      if (this.configState?.parseError) {
        this.renderEmpty("Config file is invalid. Fix it in the Config tab or on disk.");
      } else {
        this.renderEmpty("Config file not found. Check plugin settings.");
      }
      return;
    }

    const indexRes = await readIndexDetailed(this.zsumConfig.cache_dir);
    this.index = indexRes.index;
    if (!this.index) {
      if (indexRes.kind === "missing") {
        this.renderEmpty("No index found. Run 'Skeleton' or 'Full Run' to get started.");
      } else {
        const msg = "Failed to read index.json. Try re-running 'Skeleton' or 'Full Run'.";
        this.renderEmpty(msg);
        this.appendLogLine({
          time: new Date().toTimeString().slice(0, 8),
          text: `[zsum] error: ${indexRes.message ?? "index read failed"}`,
          level: "error",
        });
        new Notice(msg);
      }
      return;
    }

    this.lastIndexedAt = new Date();
    this.refreshMetaChips();
    await this.renderStatusBar();
    this.renderTree();
    this.renderPaperList(this.selectedCollectionKey);
    this.renderCostHeader();
  }

  private refreshMetaChips() {
    if (this.metaCacheChipEl) {
      this.metaCacheChipEl.setText(formatCacheChipText(this.zsumConfig?.cache_dir));
    }
    if (this.metaRootChipEl) {
      const chip = formatRootStatusChip(this.plugin.settings.projectRoot ?? "");
      this.metaRootChipEl.setText(chip.label);
      this.metaRootChipEl.removeClass("zsum-meta-chip-default");
      this.metaRootChipEl.removeClass("zsum-meta-chip-warn");
      this.metaRootChipEl.addClass(`zsum-meta-chip-${chip.modifier}`);
    }
  }

  private renderEmpty(msg: string) {
    this.statusBarEl.empty();
    this.statusBarEl.createSpan({ text: msg, cls: "zsum-empty" });
    this.treeScrollEl.empty();
    this.papersPanelEl.empty();
    this.papersHeaderCollectionKey = null;
    this.papersScrollEl = null;
    this.papersSubtitleEl = null;
    this.papersPanelEl.createDiv({ cls: "zsum-empty-panel", text: msg });
    this.renderCostHeader();
  }

  private async renderStatusBar() {
    this.statusBarEl.empty();
    if (!this.index) return;
    const s = computeStats(this.index);

    // Region 1: brand block (logo mark + name + config file basename).
    const brand = this.statusBarEl.createDiv({ cls: "zsum-brand" });
    brand.createDiv({ cls: "zsum-brand-mark", text: "ZS" });
    const brandText = brand.createDiv({ cls: "zsum-brand-text" });
    brandText.createDiv({ cls: "zsum-brand-name", text: "Zotero Summarizer" });
    const configBasename = this.configState?.path
      ? path.basename(this.configState.path)
      : "config.yaml";
    brandText.createDiv({ cls: "zsum-brand-path", text: configBasename });

    // Region 2: bordered stat cards (value above label).
    const stats = this.statusBarEl.createDiv({ cls: "zsum-stats" });
    const mk = (label: string, val: number | string, cls = "") => {
      const box = stats.createDiv({ cls: `zsum-stat ${cls}`.trim() });
      box.createDiv({ cls: "zsum-stat-val", text: String(val) });
      box.createDiv({ cls: "zsum-stat-label", text: label });
    };
    mk("Collections", s.total_collections);
    mk("Papers", s.total_papers);
    mk("Cached", s.cards_cached, "zsum-stat-ok");
    mk("Pending", s.cards_pending, "zsum-stat-muted");
    mk("Degraded", s.cards_degraded, "zsum-stat-warn");
    mk("Fallback", s.cards_fallback, "zsum-stat-fallback");
    mk("No PDF", s.cards_no_pdf, "zsum-stat-muted");
    mk("Digests OK", s.digests_ok, "zsum-stat-ok");
    mk("Stale", s.digests_stale, "zsum-stat-warn");
    mk("Missing", s.digests_missing, "zsum-stat-bad");

    // Region 3: live box (pulse dot + label + indexed timestamp).
    const liveBox = this.statusBarEl.createDiv({ cls: "zsum-live-box" });
    const live = await this.isBbtLive();
    const indicator = formatBbtIndicator(live);
    const indicatorRow = liveBox.createDiv({
      cls: `zsum-live-indicator zsum-live-${indicator.modifier}`,
    });
    const dot = indicatorRow.createSpan({ cls: "zsum-bbt-dot" });
    dot.addClass(live ? "zsum-dot-ok" : "zsum-dot-stale");
    if (live) dot.addClass("zsum-live");
    indicatorRow.createSpan({ text: indicator.label });
    if (!live) indicatorRow.title = "BBT JSON not updated recently";
    const stampText = formatIndexedTimestamp(this.lastIndexedAt);
    if (stampText) {
      liveBox.createDiv({ cls: "zsum-timestamp", text: stampText });
    }
  }

  private async isBbtLive(): Promise<boolean> {
    try {
      const vaultBase = (this.app.vault.adapter as any).basePath ?? "";
      const configAbs = resolveConfigPath(this.plugin.settings.configPath, vaultBase);
      const raw = await fs.promises.readFile(configAbs, "utf8");
      const parsed = yaml.load(raw) as any;
      let bbt = parsed?.bbt_json as string | undefined;
      if (!bbt) return false;
      if (bbt.startsWith("~")) {
        const home = process.env.HOME || process.env.USERPROFILE || "";
        bbt = path.join(home, bbt.slice(1));
      }
      const stat = await fs.promises.stat(bbt);
      const age = Date.now() - stat.mtimeMs;
      return age < 60 * 60 * 1000;
    } catch {
      return false;
    }
  }

  private renderTree() {
    this.treeScrollEl.empty();
    if (!this.index) return;

    // Root node
    const rootEl = this.treeScrollEl.createDiv({
      cls: "zsum-tree-item zsum-tree-root" + (this.selectedCollectionKey === "root" ? " is-selected" : ""),
    });
    rootEl.createSpan({ cls: "zsum-dot zsum-dot-missing" });
    rootEl.createSpan({ text: "All Collections", cls: "zsum-tree-name" });
    rootEl.createSpan({ text: String(Object.keys(this.index.items).length), cls: "zsum-tree-count" });
    rootEl.addEventListener("click", () => this.selectCollection("root"));

    // Build parent->children. Treat a parent that no longer exists in the
    // filtered collections dict as root so orphaned subtrees still render.
    const childrenOf: Record<string, string[]> = {};
    for (const [key, col] of Object.entries(this.index.collections)) {
      const p = col.parent && this.index.collections[col.parent] ? col.parent : "__root__";
      (childrenOf[p] ??= []).push(key);
    }
    for (const arr of Object.values(childrenOf)) {
      arr.sort((a, b) => this.index!.collections[a].name.localeCompare(this.index!.collections[b].name));
    }

    const renderNode = (key: string, depth: number) => {
      const col = this.index!.collections[key];
      if (!col) return;
      const kids = childrenOf[key] ?? [];
      const hasKids = kids.length > 0;
      const expanded = this.expandedNodes.has(key);

      const el = this.treeScrollEl.createDiv({
        cls: "zsum-tree-item" + (this.selectedCollectionKey === key ? " is-selected" : ""),
      });
      el.style.paddingLeft = `${8 + depth * 14}px`;

      const toggle = el.createSpan({ cls: "zsum-tree-toggle" });
      if (hasKids) {
        setIcon(toggle, expanded ? "chevron-down" : "chevron-right");
        toggle.addEventListener("click", (e) => {
          e.stopPropagation();
          if (expanded) this.expandedNodes.delete(key);
          else this.expandedNodes.add(key);
          this.renderTree();
        });
      }

      const dotCls =
        col.digest_state === "ok" ? "zsum-dot-ok" :
        col.digest_state === "stale" ? "zsum-dot-stale" : "zsum-dot-missing";
      el.createSpan({ cls: `zsum-dot ${dotCls}` });
      el.createSpan({ text: col.name, cls: "zsum-tree-name" });
      el.createSpan({ text: String(col.item_count), cls: "zsum-tree-count" });

      el.addEventListener("click", () => this.selectCollection(key));

      if (expanded) {
        for (const childKey of kids) renderNode(childKey, depth + 1);
      }
    };

    for (const rootKey of childrenOf["__root__"] ?? []) {
      renderNode(rootKey, 0);
    }
  }

  private selectCollection(key: string) {
    this.selectedCollectionKey = key;
    this.renderTree();
    this.renderPaperList(key);
  }

  private renderPaperList(collectionKey: string) {
    if (!this.index) {
      this.papersPanelEl.empty();
      this.papersHeaderCollectionKey = null;
      this.papersScrollEl = null;
      this.papersSubtitleEl = null;
      return;
    }

    if (this.papersHeaderCollectionKey !== collectionKey) {
      this.paperSearchQuery = "";
      this.buildPapersHeader(collectionKey);
      this.papersHeaderCollectionKey = collectionKey;
    }

    this.renderPaperRows(collectionKey);
  }

  private buildPapersHeader(collectionKey: string) {
    this.papersPanelEl.empty();
    if (!this.index) return;

    let title = "All Collections";
    if (collectionKey !== "root") {
      const col = this.index.collections[collectionKey];
      if (col) title = col.path || col.name;
    }

    const header = this.papersPanelEl.createDiv({ cls: "zsum-papers-header" });
    const titleEl = header.createDiv({ cls: "zsum-papers-title" });
    titleEl.createSpan({ text: title });
    this.papersSubtitleEl = titleEl.createSpan({ cls: "zsum-papers-subtitle" });

    const actions = header.createDiv({ cls: "zsum-papers-actions" });

    const searchInput = actions.createEl("input", {
      cls: "zsum-search-box",
      attr: {
        type: "search",
        placeholder: "Search citekey",
        "aria-label": "Filter papers by citekey",
      },
    });
    searchInput.value = this.paperSearchQuery;
    searchInput.addEventListener("input", () => {
      this.paperSearchQuery = searchInput.value;
      this.renderPaperRows(collectionKey);
    });

    const openBtn = actions.createEl("button", { cls: "zsum-icon-btn", attr: { "aria-label": "Open note" } });
    setIcon(openBtn, "external-link");
    openBtn.addEventListener("click", () => {
      if (collectionKey === "root") {
        new Notice("Select a specific collection to open its note.");
        return;
      }
      this.openCollectionNote(collectionKey);
    });

    const regenBtn = actions.createEl("button", { cls: "zsum-icon-btn", attr: { "aria-label": "Regenerate digest" } });
    setIcon(regenBtn, "refresh-cw");
    regenBtn.addEventListener("click", () => {
      if (collectionKey === "root") {
        new Notice("Select a specific collection to regenerate its digest.");
        return;
      }
      const col = this.index!.collections[collectionKey];
      if (!col) return;
      this.startCollectionRefreshQueue(col.name);
    });

    const sortBtn = actions.createEl("button", {
      cls: "zsum-icon-btn",
      attr: { "aria-label": this.sortByCitations ? "Sort by year" : "Sort by citations" },
    });
    setIcon(sortBtn, this.sortByCitations ? "calendar" : "trending-up");
    sortBtn.addEventListener("click", () => {
      this.sortByCitations = !this.sortByCitations;
      this.renderPaperRows(collectionKey);
    });

    const colHeader = this.papersPanelEl.createDiv({ cls: "zsum-col-header" });
    ["", "Citekey", "Type", "Year", "Venue", "Citations", "Card"].forEach((h) =>
      colHeader.createDiv({ text: h, cls: "zsum-col-head-cell" })
    );

    this.papersScrollEl = this.papersPanelEl.createDiv({ cls: "zsum-papers-scroll" });

    const paperLegend = this.papersPanelEl.createDiv({ cls: "zsum-legend zsum-papers-legend" });
    paperLegend.createSpan({ text: "Card state: " });
    const mkIcon = (icon: string, cls: string, label: string) => {
      const s = paperLegend.createSpan({ cls: "zsum-legend-item" });
      s.createSpan({ cls: `zsum-paper-status ${cls}`, text: icon });
      s.createSpan({ text: " " + label });
    };
    mkIcon("✓", "zsum-ok", "cached");
    mkIcon("✓", "zsum-fallback", "fallback");
    mkIcon("○", "zsum-muted", "pending");
    mkIcon("⚠", "zsum-warn", "degraded");
    mkIcon("—", "zsum-muted", "no PDF");
  }

  private renderPaperRows(collectionKey: string) {
    if (!this.index || !this.papersScrollEl || !this.papersSubtitleEl) return;
    const scroll = this.papersScrollEl;
    scroll.empty();

    let allPapers: ItemIndex[];
    if (collectionKey === "root") {
      allPapers = Object.values(this.index.items);
      allPapers.sort((a, b) => (b.year || 0) - (a.year || 0));
    } else {
      allPapers = getCollectionPapers(this.index, collectionKey);
    }

    const filtered = filterPapersByCitekey(allPapers, this.paperSearchQuery);
    if (this.sortByCitations) {
      filtered.sort((a, b) => (b.citation_count ?? -1) - (a.citation_count ?? -1));
    }

    const counts = this.summarizeCardStates(filtered);
    const redigestLabel =
      collectionKey !== "root"
        ? formatRedigestStatus(this.index.collections[collectionKey]?.redigest_state)
        : null;
    const filterSuffix =
      this.paperSearchQuery.trim() && filtered.length !== allPapers.length
        ? ` · showing ${filtered.length} of ${allPapers.length}`
        : "";
    this.papersSubtitleEl.setText(
      `  ${filtered.length} papers · ${counts.cached} cached · ${counts.pending} pending` +
        `${counts.degraded ? ` · ${counts.degraded} degraded` : ""}` +
        `${counts.fallback ? ` · ${counts.fallback} fallback` : ""}` +
        `${redigestLabel ? ` · ${redigestLabel}` : ""}` +
        filterSuffix
    );

    const reviews = filtered.filter(isReviewPaper);
    const research = filtered.filter((p) => !isReviewPaper(p));

    const renderRow = (p: ItemIndex) => {
      const row = scroll.createDiv({ cls: "zsum-paper-row", attr: { "data-citekey": p.citekey } });
      const icon = p.card_state === "cached" ? "✓" :
                   p.card_state === "fallback" ? "✓" :
                   p.card_state === "pending" ? "○" :
                   p.card_state === "degraded" ? "⚠" : "—";
      const iconCls =
        p.card_state === "cached" ? "zsum-ok" :
        p.card_state === "fallback" ? "zsum-fallback" :
        p.card_state === "degraded" ? "zsum-warn" : "zsum-muted";
      const statusEl = row.createDiv({ text: icon, cls: `zsum-paper-status ${iconCls}` });
      if (p.card_state === "fallback") {
        const method = p.extraction_method ?? "fallback_pages";
        statusEl.title = `Fallback extraction (${method})`;
      } else if (p.extraction_method) {
        statusEl.title = `Extraction: ${p.extraction_method}`;
      }
      row.createDiv({ cls: "zsum-citekey", text: p.citekey });
      const typeCell = row.createDiv({ cls: "zsum-type-pill-cell" });
      const variant = typePillVariant(p.paper_type);
      typeCell.createSpan({
        cls: `zsum-type-pill zsum-type-pill-${variant}`,
        text: p.paper_type ?? "research",
      });
      row.createDiv({ text: String(p.year || ""), cls: "zsum-paper-year" });
      row.createDiv({ text: p.venue || "", cls: "zsum-paper-venue" });
      row.createDiv({
        text: typeof p.citation_count === "number" ? String(p.citation_count) : "—",
        cls: "zsum-paper-citations",
      });
      row.createDiv({
        text: p.card_state.replace("_", " "),
        cls: `zsum-badge zsum-badge-${p.card_state}`,
      });
      row.addEventListener("click", () => this.openPaperNote(p.citekey));
    };

    if (reviews.length) {
      scroll.createDiv({ cls: "zsum-section-header", text: `Review Papers (${reviews.length})` });
      for (const p of reviews) renderRow(p);
      scroll.createDiv({ cls: "zsum-section-header", text: `Papers (${research.length})` });
    }
    for (const p of research) renderRow(p);

    if (!filtered.length && this.paperSearchQuery.trim()) {
      scroll.createDiv({
        cls: "zsum-empty-panel",
        text: `No papers match "${this.paperSearchQuery}"`,
      });
    }
  }

  private summarizeCardStates(papers: ItemIndex[]) {
    const c = { cached: 0, pending: 0, degraded: 0, fallback: 0, no_pdf: 0 };
    for (const p of papers) (c as any)[p.card_state]++;
    return c;
  }

  private renderButtons() {
    this.localGridEl.empty();
    this.llmGridEl.empty();
    for (const def of ZSUM_LIBRARY_STAGE_BUTTONS) {
      const grid = def.group === "local" ? this.localGridEl : this.llmGridEl;
      this.renderStageButton(grid, def);
    }
  }

  private renderStageButton(
    grid: HTMLElement,
    def: ZsumStageButtonDefinition
  ) {
    const stage = def.args[0];
    const btn = grid.createEl("button", {
      cls: `zsum-stage-btn zsum-stage-btn-${def.variant}`,
    });
    btn.dataset.stage = stage;
    btn.dataset.variant = def.variant;
    btn.dataset.iconLetter = def.label.charAt(0).toUpperCase();
    if (def.forceable) {
      btn.title = `${def.label} — toggle Force above to add --force`;
    }
    const icon = btn.createSpan({
      cls: "zsum-stage-icon",
      text: btn.dataset.iconLetter,
    });
    icon.dataset.role = "icon";
    btn.createSpan({ cls: "zsum-stage-label", text: def.label });

    if (stage === "cancel") {
      btn.disabled = true;
      btn.addEventListener("click", () => this.runner.cancel());
      return;
    }

    btn.addEventListener("click", () => {
      const args = computeStageRunArgs(def, this.forceToggleEl?.checked === true);
      this.runStage(args);
    });
  }

  private renderCostHeader() {
    this.costHeaderEl.empty();
    const pending = this.index
      ? Object.values(this.index.items).filter((i) => i.card_state === "pending").length
      : 0;
    const est = estimateCost(pending, this.plugin.settings);
    this.costHeaderEl.setText(`${est.cost_display} estimated · ${pending} cards pending`);
  }

  private openCollectionNote(collectionKey: string) {
    if (!this.zsumConfig || !this.index) return;
    const col = this.index.collections[collectionKey];
    if (!col) return;
    const notePath = path.join(this.zsumConfig.vault_output, "Collections", `${safeFilename(col.name)}.md`);
    this.openFileAbs(notePath, false);
  }

  private async openPaperNote(citekey: string) {
    if (!this.zsumConfig) return;
    // Paper notes are written by publisher.py as `@{citekey}.md`.
    const notePath = path.join(this.zsumConfig.vault_output, "Papers", `${safeFilename(`@${citekey}`)}.md`);
    await this.openFileAbs(notePath, true);
  }

  private async openFileAbs(absPath: string, popout: boolean) {
    const vaultBase = (this.app.vault.adapter as any).basePath ?? "";
    let vaultRelative: string | null = null;
    // Resolve symlinks so OneDrive / cloud-storage aliases match the vault basePath.
    let realVault: string;
    let realAbs: string;
    try {
      realVault = fs.realpathSync(vaultBase);
      realAbs = fs.realpathSync(absPath);
    } catch {
      realVault = vaultBase;
      realAbs = absPath;
    }
    if (realAbs.startsWith(realVault)) {
      vaultRelative = realAbs.slice(realVault.length).replace(/^[\\/]+/, "").replace(/\\/g, "/");
    }
    if (!vaultRelative) {
      new Notice(`Note is outside the vault: ${absPath}`);
      return;
    }
    const file = this.app.vault.getAbstractFileByPath(vaultRelative);
    if (file instanceof TFile) {
      if (popout) {
        try {
          const leaf = (this.app.workspace as any).openPopoutLeaf?.();
          if (leaf) {
            await leaf.openFile(file);
            return;
          }
        } catch {}
      }
      const leaf = this.app.workspace.getLeaf("tab");
      await leaf.openFile(file);
    } else {
      // Graceful fallback for unresolved paths: try opening in a normal tab
      // without showing a blocking UI error.
      try {
        await (this.app.workspace as any).openLinkText?.(vaultRelative, this.app.workspace.getActiveFile()?.path ?? "", true);
      } catch {
        // Silent by design (REQ-PL04 fallback behavior)
      }
    }
  }

  runStageExternal(args: string[]) {
    this.runStage(args);
  }

  private runStage(stageArgs: string[]) {
    if (this.runner.state === "running") {
      new Notice("A pipeline stage is already running.");
      return;
    }
    const preserveLog = this.preserveLogOnNextRun;
    this.preserveLogOnNextRun = false;
    if (!preserveLog) {
      this.logLines = [];
      this.logEl.empty();
      this.pipelineStripEl.empty();
      this.pipelineStripEl.addClass("zsum-hidden");
    }
    this.activeStage = stageArgs[0] ?? null;
    this.lastStageArgs = [...stageArgs];
    const cwd = this.plugin.settings.projectRoot
      || (this.zsumConfig
        ? path.dirname(resolveConfigPath(this.plugin.settings.configPath, (this.app.vault.adapter as any).basePath ?? ""))
        : (this.app.vault.adapter as any).basePath ?? process.cwd());
    const vaultBase = (this.app.vault.adapter as any).basePath ?? "";
    const configAbs = resolveConfigPath(this.plugin.settings.configPath, vaultBase);
    const fullArgs = ["--config", configAbs, ...stageArgs];
    try {
      this.runner.run(this.plugin.settings.pythonCmd, fullArgs, cwd);
      this.appendLogLine({
        time: new Date().toTimeString().slice(0, 8),
        text: `[zsum] $ ${this.plugin.settings.pythonCmd} ${stageArgs.join(" ")}`,
        level: "info",
      });
    } catch (e: any) {
      this.queuedStageArgs = [];
      this.lastStageArgs = [];
      new Notice(`Failed: ${e?.message ?? e}`);
    }
  }

  private wasCollectionDigestRun(): boolean {
    return (
      this.lastStageArgs[0] === "digests" &&
      this.lastStageArgs.includes("--collection")
    );
  }

  // Regex for stage header lines like "1/5 Index..."
  private static STAGE_RE = /^(\d)\/(\d)\s+(\w+)\.{3}$/;
  // Regex for completed stage lines like "  ✓ 44/44 cards [3:21]"
  private static DONE_RE = /^\s*✓\s+(.+)$/;
  // Regex for in-progress lines like "Progress: 30/46 cards generated"
  private static PROGRESS_RE = /Progress:\s*(\d+)\/(\d+)\s+(\w+)/;
  // Regex for final "Done!" line
  private static FINAL_RE = /^Done!\s+(.+)$/;

  private appendLogLine(line: LogLine) {
    this.logLines.push(line);
    const div = this.logEl.createDiv({ cls: `zsum-log-line zsum-log-${line.level}` });
    div.createSpan({ text: line.time, cls: "zsum-log-time" });
    div.createSpan({ text: " " + line.text });

    const atBottom =
      this.logEl.scrollHeight - this.logEl.scrollTop <= this.logEl.clientHeight + 20;
    if (!this.userScrolledUp || atBottom) {
      this.logEl.scrollTop = this.logEl.scrollHeight;
      this.userScrolledUp = false;
    }

    // Update pipeline progress strip
    this.parsePipelineLine(line.text);
  }

  private parsePipelineLine(text: string) {
    const stageMatch = text.match(ZsumView.STAGE_RE);
    if (stageMatch) {
      this.pipelineStripEl.removeClass("zsum-hidden");
      // Add or update current stage indicator
      let cur = this.pipelineStripEl.querySelector<HTMLElement>(".zsum-strip-current");
      if (!cur) {
        cur = this.pipelineStripEl.createDiv({ cls: "zsum-strip-current" });
      }
      cur.empty();
      cur.createSpan({ cls: "zsum-strip-spinner" });
      cur.createSpan({ text: `${stageMatch[1]}/${stageMatch[2]} ${stageMatch[3]}...` });
      return;
    }

    const doneMatch = text.match(ZsumView.DONE_RE);
    if (doneMatch) {
      // Replace current indicator with completed chip
      const cur = this.pipelineStripEl.querySelector<HTMLElement>(".zsum-strip-current");
      if (cur) cur.remove();
      const chip = this.pipelineStripEl.createDiv({ cls: "zsum-strip-done" });
      chip.createSpan({ text: "✓ ", cls: "zsum-strip-check" });
      chip.createSpan({ text: doneMatch[1] });
      return;
    }

    const progMatch = text.match(ZsumView.PROGRESS_RE);
    if (progMatch) {
      const cur = this.pipelineStripEl.querySelector<HTMLElement>(".zsum-strip-current");
      if (cur) {
        cur.empty();
        cur.createSpan({ cls: "zsum-strip-spinner" });
        cur.createSpan({ text: `${progMatch[3]}: ${progMatch[1]}/${progMatch[2]}` });
      }
      return;
    }

    const finalMatch = text.match(ZsumView.FINAL_RE);
    if (finalMatch) {
      const cur = this.pipelineStripEl.querySelector<HTMLElement>(".zsum-strip-current");
      if (cur) cur.remove();
      const chip = this.pipelineStripEl.createDiv({ cls: "zsum-strip-final" });
      chip.createSpan({ text: "✓ " + finalMatch[1] });
    }
  }

  private updateRunState(state: RunnerState) {
    const running = state === "running";
    this.progressBarEl.toggleClass("zsum-hidden", !running);
    const stageButtons = this.stagePadEl.querySelectorAll<HTMLButtonElement>(
      ".zsum-stage-btn"
    );
    stageButtons.forEach((b) => {
      const isCancel = b.dataset.stage === "cancel";
      const isActive = !isCancel && b.dataset.stage === this.activeStage;
      // Cancel is enabled only while running; everything else is disabled while
      // running EXCEPT clear-cache (which has its own button in the head).
      b.disabled = isCancel ? !running : running;

      const iconEl = b.querySelector<HTMLElement>('[data-role="icon"]');
      if (!iconEl) return;
      if (isActive && running) {
        iconEl.empty();
        iconEl.createSpan({ cls: "zsum-stage-spinner" });
        b.addClass("zsum-running");
      } else {
        if (b.classList.contains("zsum-running") || iconEl.childElementCount > 0) {
          iconEl.empty();
          iconEl.setText(b.dataset.iconLetter ?? "");
        } else if (!iconEl.textContent) {
          iconEl.setText(b.dataset.iconLetter ?? "");
        }
        b.removeClass("zsum-running");
      }
    });
    if (!running) this.activeStage = null;
  }
}
