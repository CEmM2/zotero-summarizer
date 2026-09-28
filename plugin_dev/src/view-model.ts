import type {
  ZsumConfigDocumentState,
  ZsumConfigSectionDefinition,
} from "./config";

export interface ZsumConfigNavGroup {
  id: string;
  label: string;
  sectionIds: readonly string[];
}

export const ZSUM_CONFIG_NAV_GROUPS: readonly ZsumConfigNavGroup[] = [
  { id: "paths", label: "Paths", sectionIds: ["paths"] },
  { id: "scope", label: "Scope & Extraction", sectionIds: ["scope", "extraction"] },
  {
    id: "llm",
    label: "LLM",
    sectionIds: ["llm-routing", "llm-anthropic", "llm-openai-compat", "llm-codex-exec", "llm-gemini-cli"],
  },
  { id: "output", label: "Output", sectionIds: ["output", "versioning"] },
  { id: "citations", label: "Citations", sectionIds: ["citations"] },
  { id: "restructure", label: "Restructure", sectionIds: ["restructure"] },
];

export function buildNavSections(
  schema: readonly ZsumConfigSectionDefinition[],
  groupId: string
): readonly ZsumConfigSectionDefinition[] {
  const group = ZSUM_CONFIG_NAV_GROUPS.find((g) => g.id === groupId);
  if (!group) return [];
  const orderedIds = group.sectionIds;
  const byId = new Map(schema.map((s) => [s.id, s]));
  return orderedIds
    .map((id) => byId.get(id))
    .filter((s): s is ZsumConfigSectionDefinition => Boolean(s));
}

export type ZsumViewTabId = "library" | "config";

export interface ZsumViewTabDefinition {
  id: ZsumViewTabId;
  label: string;
}

export type ZsumStageGroup = "local" | "llm";
export type ZsumStageVariant = "default" | "primary" | "llm" | "danger";

export interface ZsumStageButtonDefinition {
  label: string;
  args: string[];
  forceable: boolean;
  group: ZsumStageGroup;
  variant: ZsumStageVariant;
}

export interface ZsumConfigBanner {
  kind: "error" | "warning" | "success";
  text: string;
}

export interface ZsumConfigFieldViewModel {
  path: string;
  label: string;
  section: string;
  input: string;
  description?: string;
  options?: readonly { value: string; label: string }[];
  value: string | boolean;
  error?: string;
  pathPreview?: string;
}

export interface ZsumConfigSectionViewModel {
  id: string;
  label: string;
  fields: ZsumConfigFieldViewModel[];
}

export interface ZsumConfigActionViewModel {
  id: "save" | "revert" | "reload";
  label: string;
  disabled: boolean;
}

export interface ZsumConfigViewModel {
  path: string;
  dirty: boolean;
  dirtyBadgeLabel: string | null;
  banners: ZsumConfigBanner[];
  sections: ZsumConfigSectionViewModel[];
  actions: ZsumConfigActionViewModel[];
}

export interface ZsumConfigFeedback {
  kind: "error" | "success";
  text: string;
}

export const ZSUM_VIEW_TABS: readonly ZsumViewTabDefinition[] = [
  { id: "library", label: "Library" },
  { id: "config", label: "Config" },
];

export const ZSUM_LIBRARY_STAGE_BUTTONS: readonly ZsumStageButtonDefinition[] = [
  { label: "Skeleton", args: ["skeleton"], forceable: false, group: "local", variant: "default" },
  { label: "Citations", args: ["citations"], forceable: false, group: "local", variant: "default" },
  { label: "Publish", args: ["publish"], forceable: false, group: "local", variant: "default" },
  { label: "Reviews", args: ["reviews"], forceable: false, group: "local", variant: "default" },
  { label: "Stats", args: ["stats"], forceable: false, group: "local", variant: "default" },
  { label: "Cards", args: ["cards"], forceable: true, group: "llm", variant: "llm" },
  { label: "Digests", args: ["digests"], forceable: true, group: "llm", variant: "llm" },
  { label: "Redigest", args: ["redigest"], forceable: true, group: "llm", variant: "llm" },
  { label: "Restructure", args: ["restructure"], forceable: false, group: "llm", variant: "llm" },
  { label: "Full Run", args: ["all"], forceable: false, group: "llm", variant: "primary" },
  { label: "Cancel", args: ["cancel"], forceable: false, group: "llm", variant: "danger" },
];

export const ZSUM_CONFIG_ACTIONS = [
  { id: "save", label: "Save" },
  { id: "revert", label: "Revert" },
  { id: "reload", label: "Reload from disk" },
] as const;

export function buildCollectionRefreshQueue(collectionName: string): string[][] {
  return [
    ["digests", "--collection", collectionName],
    ["redigest", "--collection", collectionName],
  ];
}

export function computeStageRunArgs(
  definition: ZsumStageButtonDefinition,
  forceChecked: boolean
): string[] {
  const args = [...definition.args];
  if (forceChecked && definition.forceable) args.push("--force");
  return args;
}

export function filterPapersByCitekey<T extends { citekey: string }>(
  papers: readonly T[],
  query: string
): T[] {
  const trimmed = query.trim().toLowerCase();
  if (!trimmed) return papers.slice();
  return papers.filter((p) => p.citekey.toLowerCase().includes(trimmed));
}

export interface ZsumBbtIndicator {
  label: string;
  modifier: "ok" | "stale";
}

export function formatBbtIndicator(isLive: boolean): ZsumBbtIndicator {
  return isLive
    ? { label: "BBT live", modifier: "ok" }
    : { label: "BBT stale", modifier: "stale" };
}

export function formatIndexedTimestamp(date: Date | null): string {
  if (!date) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `indexed ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

export function formatConfigStatusText(
  dirty: boolean,
  lastSavedAt: Date | null
): string {
  if (dirty) return "Dirty state buffered in memory";
  if (!lastSavedAt) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `Saved ${pad(lastSavedAt.getHours())}:${pad(lastSavedAt.getMinutes())}:${pad(lastSavedAt.getSeconds())}`;
}

export interface ZsumCostInputs {
  costPerMTokenIn: number;
  costPerMTokenOut: number;
  tokensPerCardIn: number;
  tokensPerCardOut: number;
}

export function formatCostPreview(inputs: ZsumCostInputs): string {
  const per =
    (inputs.tokensPerCardIn * inputs.costPerMTokenIn) / 1e6 +
    (inputs.tokensPerCardOut * inputs.costPerMTokenOut) / 1e6;
  return `$${per.toFixed(4)} per card`;
}

export interface ZsumMetaChip {
  label: string;
  modifier: "default" | "warn";
}

export function formatRootStatusChip(projectRoot: string): ZsumMetaChip {
  return projectRoot.trim()
    ? { label: "project root set", modifier: "default" }
    : { label: "⚠ root not set", modifier: "warn" };
}

export function formatCacheChipText(
  cacheDir: string | null | undefined
): string {
  if (!cacheDir) return "cache/index.json";
  // Strip trailing slashes and grab the last path segment.
  const trimmed = cacheDir.replace(/[\\/]+$/, "");
  const lastSlash = Math.max(trimmed.lastIndexOf("/"), trimmed.lastIndexOf("\\"));
  const basename = lastSlash >= 0 ? trimmed.slice(lastSlash + 1) : trimmed;
  return `${basename || "cache"}/index.json`;
}

export function allCollectionKeys(
  collections: Record<string, unknown> | null | undefined
): readonly string[] {
  if (!collections) return [];
  return Object.keys(collections);
}

export type ZsumTypePillVariant = "research" | "review" | "survey" | "meta";

export function typePillVariant(paperType?: string): ZsumTypePillVariant {
  switch (paperType) {
    case "research":
      return "research";
    case "review":
      return "review";
    case "survey":
      return "survey";
    case "meta-analysis":
    case "tutorial":
      return "meta";
    default:
      return "research";
  }
}

export function formatRedigestStatus(
  state: "ok" | "stale" | "missing" | undefined | null
): string | null {
  if (!state) return null;
  return `redigest ${state}`;
}

export function buildConfigViewModel(
  schema: readonly ZsumConfigSectionDefinition[],
  state: ZsumConfigDocumentState,
  feedback: ZsumConfigFeedback | null = null
): ZsumConfigViewModel {
  const values = state.values as Record<string, string | boolean>;
  const errors = state.validationErrors as Record<string, string | undefined>;
  const previews = state.resolvedPathPreviews as Record<string, string | undefined>;
  const banners: ZsumConfigBanner[] = [];

  if (feedback) {
    banners.push({ kind: feedback.kind, text: feedback.text });
  }

  if (state.parseError) {
    banners.push({ kind: "error", text: state.parseError });
  } else if (!state.exists) {
    banners.push({
      kind: "warning",
      text: `Config file not found at ${state.path}. Save to create it.`,
    });
  }

  const sections = schema.map((section) => ({
    id: section.id,
    label: section.label,
    fields: section.fields.map((field) => ({
      path: field.path,
      label: field.label,
      section: field.section,
      input: field.input,
      description: field.description,
      options: field.options,
      value: values[field.path],
      error: errors[field.path],
      pathPreview: previews[field.path],
    })),
  }));

  return {
    path: state.path,
    dirty: state.dirty,
    dirtyBadgeLabel: state.dirty ? "Unsaved" : null,
    banners,
    sections,
    actions: ZSUM_CONFIG_ACTIONS.map((action) => {
      if (action.id === "save") {
        return {
          ...action,
          disabled: !state.dirty || !state.canSave,
        };
      }
      if (action.id === "revert") {
        return {
          ...action,
          disabled: !state.dirty,
        };
      }
      return {
        ...action,
        disabled: false,
      };
    }),
  };
}
