import * as fs from "fs";
import * as path from "path";
import { Document, parseDocument } from "yaml";

export interface ZsumConfig {
  cache_dir: string;
  vault_output: string;
}

export type ZsumLlmProvider = "anthropic" | "openai_compat" | "codex_exec" | "gemini_cli";
export type ZsumCodexSandbox =
  | "read-only"
  | "workspace-write"
  | "danger-full-access";
export type ZsumCitationProvider = "openalex";
export type ZsumCitationFallback = "" | "semantic_scholar";
export type ZsumConfigFieldInput =
  | "text"
  | "number"
  | "toggle"
  | "dropdown"
  | "textarea";

const FIELD_PATHS = [
  "bbt_json",
  "zotero_sqlite",
  "zotero_pdf_base",
  "vault_output",
  "cache_dir",
  "collections",
  "max_first_pages",
  "max_last_pages",
  "max_text_chars",
  "min_text_chars",
  "max_pdf_pages",
  "llm.routing.cards",
  "llm.routing.digests",
  "llm.routing.redigest",
  "llm.anthropic.model",
  "llm.anthropic.api_key_env",
  "llm.anthropic.max_tokens_card",
  "llm.anthropic.max_tokens_digest",
  "llm.openai_compat.base_url",
  "llm.openai_compat.model",
  "llm.openai_compat.api_key",
  "llm.openai_compat.max_tokens_card",
  "llm.openai_compat.max_tokens_digest",
  "llm.openai_compat.enable_thinking",
  "llm.openai_compat.structured_output",
  "llm.codex_exec.model",
  "llm.codex_exec.binary",
  "llm.codex_exec.sandbox",
  "llm.codex_exec.max_tokens_card",
  "llm.codex_exec.max_tokens_digest",
  "llm.gemini_cli.model",
  "llm.gemini_cli.binary",
  "llm.gemini_cli.approval_mode",
  "llm.gemini_cli.max_tokens_card",
  "llm.gemini_cli.max_tokens_digest",
  "generate_paper_notes",
  "prompt_version",
  "citations.enabled",
  "citations.provider",
  "citations.fallback",
  "citations.email",
  "citations.api_key",
  "citations.rate_limit_delay",
  "citations.max_age_days",
  "citations.top_n",
  "citations.timeout_seconds",
  "restructure.max_digest_chars",
] as const;

const PATH_PREVIEW_FIELDS = [
  "bbt_json",
  "zotero_sqlite",
  "zotero_pdf_base",
  "vault_output",
  "cache_dir",
] as const;

export type ZsumEditableFieldPath = (typeof FIELD_PATHS)[number];
export type ZsumPathPreviewField = (typeof PATH_PREVIEW_FIELDS)[number];
export type ZsumEditableFieldValue = string | boolean;
export type ZsumEditableConfigValues = Record<
  ZsumEditableFieldPath,
  ZsumEditableFieldValue
>;
export type ZsumConfigValidationErrors = Partial<
  Record<ZsumEditableFieldPath, string>
>;
export type ZsumResolvedPathPreviews = Partial<
  Record<ZsumPathPreviewField, string>
>;

export interface ZsumConfigOption {
  value: string;
  label: string;
}

export interface ZsumConfigFieldDefinition {
  path: ZsumEditableFieldPath;
  label: string;
  section: string;
  input: ZsumConfigFieldInput;
  description?: string;
  options?: readonly ZsumConfigOption[];
}

export interface ZsumConfigSectionDefinition {
  id: string;
  label: string;
  fields: readonly ZsumConfigFieldDefinition[];
}

export interface ZsumConfigDocumentState {
  path: string;
  exists: boolean;
  dirty: boolean;
  parseError: string | null;
  validationErrors: ZsumConfigValidationErrors;
  values: ZsumEditableConfigValues;
  resolvedPathPreviews: ZsumResolvedPathPreviews;
  canSave: boolean;
}

export interface ZsumConfigIo {
  readFile(filePath: string, encoding: "utf8"): Promise<string>;
  writeFile(filePath: string, contents: string, encoding: "utf8"): Promise<void>;
  rename(sourcePath: string, targetPath: string): Promise<void>;
  unlink(filePath: string): Promise<void>;
  mkdir(dirPath: string, options: { recursive: boolean }): Promise<unknown>;
}

export class ZsumConfigSaveError extends Error {
  readonly validationErrors: ZsumConfigValidationErrors;

  constructor(message: string, validationErrors: ZsumConfigValidationErrors = {}) {
    super(message);
    this.name = "ZsumConfigSaveError";
    this.validationErrors = validationErrors;
  }
}

interface FieldSerializationSuccess {
  ok: true;
  value: unknown;
}

interface FieldSerializationFailure {
  ok: false;
  error: string;
}

type FieldSerializationResult =
  | FieldSerializationSuccess
  | FieldSerializationFailure;

interface InternalFieldDefinition extends ZsumConfigFieldDefinition {
  defaultValue: ZsumEditableFieldValue;
  tokens: string[];
  toInput(value: unknown): ZsumEditableFieldValue;
  serialize(value: ZsumEditableFieldValue): FieldSerializationResult;
}

const NODE_CONFIG_IO: ZsumConfigIo = {
  readFile: (filePath, encoding) => fs.promises.readFile(filePath, encoding),
  writeFile: (filePath, contents, encoding) =>
    fs.promises.writeFile(filePath, contents, encoding),
  rename: (sourcePath, targetPath) => fs.promises.rename(sourcePath, targetPath),
  unlink: (filePath) => fs.promises.unlink(filePath),
  mkdir: (dirPath, options) => fs.promises.mkdir(dirPath, options),
};

const LLM_PROVIDER_OPTIONS: readonly ZsumConfigOption[] = [
  { value: "anthropic", label: "Anthropic" },
  { value: "openai_compat", label: "OpenAI Compatible" },
  { value: "codex_exec", label: "Codex Exec" },
  { value: "gemini_cli", label: "Gemini CLI" },
];

const CODEX_SANDBOX_OPTIONS: readonly ZsumConfigOption[] = [
  { value: "read-only", label: "Read Only" },
  { value: "workspace-write", label: "Workspace Write" },
  { value: "danger-full-access", label: "Danger Full Access" },
];

const GEMINI_APPROVAL_OPTIONS: readonly ZsumConfigOption[] = [
  { value: "yolo", label: "Auto-approve (yolo)" },
  { value: "unless-allow-listed", label: "Unless Allow-listed" },
  { value: "always", label: "Always Ask" },
];

const CITATION_PROVIDER_OPTIONS: readonly ZsumConfigOption[] = [
  { value: "openalex", label: "OpenAlex" },
];

const CITATION_FALLBACK_OPTIONS: readonly ZsumConfigOption[] = [
  { value: "", label: "None" },
  { value: "semantic_scholar", label: "Semantic Scholar" },
];

const THINKING_OPTIONS: readonly ZsumConfigOption[] = [
  { value: "", label: "Server Default" },
  { value: "true", label: "Enabled" },
  { value: "false", label: "Disabled" },
];

function textField(
  section: string,
  pathKey: ZsumEditableFieldPath,
  label: string,
  defaultValue: string,
  extra: Partial<ZsumConfigFieldDefinition> = {}
): InternalFieldDefinition {
  return {
    path: pathKey,
    label,
    section,
    input: "text",
    description: extra.description,
    options: extra.options,
    defaultValue,
    tokens: pathKey.split("."),
    toInput: (value) => (value == null ? defaultValue : String(value)),
    serialize: (value) => ({ ok: true, value: String(value) }),
  };
}

function dropdownField(
  section: string,
  pathKey: ZsumEditableFieldPath,
  label: string,
  defaultValue: string,
  options: readonly ZsumConfigOption[],
  extra: Partial<ZsumConfigFieldDefinition> = {}
): InternalFieldDefinition {
  const allowed = new Set(options.map((option) => option.value));
  return {
    path: pathKey,
    label,
    section,
    input: "dropdown",
    description: extra.description,
    options,
    defaultValue,
    tokens: pathKey.split("."),
    toInput: (value) => (value == null ? defaultValue : String(value)),
    serialize: (value) => {
      const normalized = String(value);
      if (!allowed.has(normalized)) {
        return {
          ok: false,
          error: `Expected one of: ${options.map((option) => option.value).join(", ")}`,
        };
      }
      return { ok: true, value: normalized };
    },
  };
}

function toggleField(
  section: string,
  pathKey: ZsumEditableFieldPath,
  label: string,
  defaultValue: boolean,
  extra: Partial<ZsumConfigFieldDefinition> = {}
): InternalFieldDefinition {
  return {
    path: pathKey,
    label,
    section,
    input: "toggle",
    description: extra.description,
    options: extra.options,
    defaultValue,
    tokens: pathKey.split("."),
    toInput: (value) => (typeof value === "boolean" ? value : defaultValue),
    serialize: (value) => {
      if (typeof value !== "boolean") {
        return { ok: false, error: "Expected a boolean value." };
      }
      return { ok: true, value };
    },
  };
}

function numberField(
  section: string,
  pathKey: ZsumEditableFieldPath,
  label: string,
  defaultValue: number | null,
  options: {
    nullable?: boolean;
    integer?: boolean;
    description?: string;
  } = {}
): InternalFieldDefinition {
  const { nullable = false, integer = true, description } = options;
  return {
    path: pathKey,
    label,
    section,
    input: "number",
    description,
    defaultValue: defaultValue == null ? "" : String(defaultValue),
    tokens: pathKey.split("."),
    toInput: (value) =>
      value == null ? (nullable ? "" : defaultValue == null ? "" : String(defaultValue)) : String(value),
    serialize: (value) => {
      const normalized = String(value).trim();
      if (normalized === "") {
        return nullable
          ? { ok: true, value: null }
          : { ok: false, error: "A numeric value is required." };
      }
      const parsed = Number(normalized);
      if (!Number.isFinite(parsed)) {
        return { ok: false, error: "Value must be a valid number." };
      }
      if (integer && !Number.isInteger(parsed)) {
        return { ok: false, error: "Value must be an integer." };
      }
      return { ok: true, value: parsed };
    },
  };
}

function textareaListField(
  section: string,
  pathKey: ZsumEditableFieldPath,
  label: string,
  extra: Partial<ZsumConfigFieldDefinition> = {}
): InternalFieldDefinition {
  return {
    path: pathKey,
    label,
    section,
    input: "textarea",
    description: extra.description,
    options: extra.options,
    defaultValue: "",
    tokens: pathKey.split("."),
    toInput: (value) =>
      Array.isArray(value)
        ? value
            .map((entry) => String(entry).trim())
            .filter((entry) => entry.length > 0)
            .join("\n")
        : "",
    serialize: (value) => ({
      ok: true,
      value: String(value)
        .split(/\r?\n/)
        .map((entry) => entry.trim())
        .filter((entry) => entry.length > 0),
    }),
  };
}

function nullableBooleanDropdownField(
  section: string,
  pathKey: ZsumEditableFieldPath,
  label: string,
  extra: Partial<ZsumConfigFieldDefinition> = {}
): InternalFieldDefinition {
  return {
    path: pathKey,
    label,
    section,
    input: "dropdown",
    description: extra.description,
    options: THINKING_OPTIONS,
    defaultValue: "",
    tokens: pathKey.split("."),
    toInput: (value) => {
      if (value === true) return "true";
      if (value === false) return "false";
      return "";
    },
    serialize: (value) => {
      const normalized = String(value);
      if (normalized === "") {
        return { ok: true, value: null };
      }
      if (normalized === "true") {
        return { ok: true, value: true };
      }
      if (normalized === "false") {
        return { ok: true, value: false };
      }
      return {
        ok: false,
        error: 'Expected one of: "", "true", "false"',
      };
    },
  };
}

const FIELD_DEFINITIONS: readonly InternalFieldDefinition[] = [
  textField("paths", "bbt_json", "Better BibTeX JSON", "~/Zotero/zot.json"),
  textField(
    "paths",
    "zotero_sqlite",
    "Zotero SQLite",
    "~/Zotero/zotero.sqlite"
  ),
  textField("paths", "zotero_pdf_base", "PDF Base Path", ""),
  textField("paths", "vault_output", "Vault Output", "./vault"),
  textField("paths", "cache_dir", "Cache Directory", "./cache"),
  textareaListField("scope", "collections", "Collections"),
  numberField("extraction", "max_first_pages", "Max First Pages", 3),
  numberField("extraction", "max_last_pages", "Max Last Pages", 2),
  numberField("extraction", "max_text_chars", "Max Text Chars", 24000),
  numberField("extraction", "min_text_chars", "Min Text Chars", 500),
  numberField("extraction", "max_pdf_pages", "Max PDF Pages", null, {
    nullable: true,
  }),
  dropdownField(
    "llm-routing",
    "llm.routing.cards",
    "Cards Provider",
    "anthropic",
    LLM_PROVIDER_OPTIONS
  ),
  dropdownField(
    "llm-routing",
    "llm.routing.digests",
    "Digests Provider",
    "anthropic",
    LLM_PROVIDER_OPTIONS
  ),
  dropdownField(
    "llm-routing",
    "llm.routing.redigest",
    "Redigest Provider",
    "anthropic",
    LLM_PROVIDER_OPTIONS
  ),
  textField("llm-anthropic", "llm.anthropic.model", "Anthropic Model", ""),
  textField(
    "llm-anthropic",
    "llm.anthropic.api_key_env",
    "Anthropic API Key Env",
    "ANTHROPIC_API_KEY"
  ),
  numberField(
    "llm-anthropic",
    "llm.anthropic.max_tokens_card",
    "Anthropic Card Tokens",
    1024
  ),
  numberField(
    "llm-anthropic",
    "llm.anthropic.max_tokens_digest",
    "Anthropic Digest Tokens",
    2048
  ),
  textField(
    "llm-openai-compat",
    "llm.openai_compat.base_url",
    "OpenAI Compatible Base URL",
    "http://localhost:1234/v1"
  ),
  textField(
    "llm-openai-compat",
    "llm.openai_compat.model",
    "OpenAI Compatible Model",
    ""
  ),
  textField(
    "llm-openai-compat",
    "llm.openai_compat.api_key",
    "OpenAI Compatible API Key",
    "lm-studio"
  ),
  numberField(
    "llm-openai-compat",
    "llm.openai_compat.max_tokens_card",
    "OpenAI Compatible Card Tokens",
    1024
  ),
  numberField(
    "llm-openai-compat",
    "llm.openai_compat.max_tokens_digest",
    "OpenAI Compatible Digest Tokens",
    2048
  ),
  nullableBooleanDropdownField(
    "llm-openai-compat",
    "llm.openai_compat.enable_thinking",
    "OpenAI Compatible Thinking"
  ),
  toggleField(
    "llm-openai-compat",
    "llm.openai_compat.structured_output",
    "Structured Output",
    false,
    {
      description:
        "Enable JSON Schema structured output via response_format. Requires a compatible server (LM Studio, vLLM).",
    }
  ),
  textField("llm-codex-exec", "llm.codex_exec.model", "Codex Model", ""),
  textField(
    "llm-codex-exec",
    "llm.codex_exec.binary",
    "Codex Binary",
    "codex"
  ),
  dropdownField(
    "llm-codex-exec",
    "llm.codex_exec.sandbox",
    "Codex Sandbox",
    "read-only",
    CODEX_SANDBOX_OPTIONS
  ),
  numberField(
    "llm-codex-exec",
    "llm.codex_exec.max_tokens_card",
    "Codex Card Tokens",
    1024
  ),
  numberField(
    "llm-codex-exec",
    "llm.codex_exec.max_tokens_digest",
    "Codex Digest Tokens",
    2048
  ),
  textField("llm-gemini-cli", "llm.gemini_cli.model", "Gemini Model", "", {
    description: "Leave empty to let Gemini CLI auto-select a model.",
  }),
  textField(
    "llm-gemini-cli",
    "llm.gemini_cli.binary",
    "Gemini Binary",
    "gemini"
  ),
  dropdownField(
    "llm-gemini-cli",
    "llm.gemini_cli.approval_mode",
    "Gemini Approval Mode",
    "yolo",
    GEMINI_APPROVAL_OPTIONS,
    {
      description:
        "Tool approval mode. 'yolo' auto-approves (safe since zsum uses no tools).",
    }
  ),
  numberField(
    "llm-gemini-cli",
    "llm.gemini_cli.max_tokens_card",
    "Gemini Card Tokens",
    1024
  ),
  numberField(
    "llm-gemini-cli",
    "llm.gemini_cli.max_tokens_digest",
    "Gemini Digest Tokens",
    2048
  ),
  toggleField(
    "output",
    "generate_paper_notes",
    "Generate Paper Notes",
    true
  ),
  numberField("versioning", "prompt_version", "Prompt Version", 1),
  toggleField("citations", "citations.enabled", "Enable Citations", true),
  dropdownField(
    "citations",
    "citations.provider",
    "Citations Provider",
    "openalex",
    CITATION_PROVIDER_OPTIONS
  ),
  dropdownField(
    "citations",
    "citations.fallback",
    "Citations Fallback",
    "semantic_scholar",
    CITATION_FALLBACK_OPTIONS
  ),
  textField("citations", "citations.email", "Citations Email", ""),
  textField("citations", "citations.api_key", "Citations API Key", ""),
  numberField(
    "citations",
    "citations.rate_limit_delay",
    "Citations Rate Limit Delay",
    0.1,
    { integer: false }
  ),
  numberField(
    "citations",
    "citations.max_age_days",
    "Citations Max Age Days",
    30
  ),
  numberField("citations", "citations.top_n", "Citations Top N", 10),
  numberField(
    "citations",
    "citations.timeout_seconds",
    "Citations Timeout Seconds",
    10.0,
    { integer: false }
  ),
  numberField(
    "restructure",
    "restructure.max_digest_chars",
    "Restructure Max Digest Chars",
    800
  ),
];

const SECTION_LABELS = new Map<string, string>([
  ["paths", "Paths"],
  ["scope", "Scope"],
  ["extraction", "Extraction"],
  ["llm-routing", "LLM Routing"],
  ["llm-anthropic", "LLM Anthropic"],
  ["llm-openai-compat", "LLM OpenAI Compatible"],
  ["llm-codex-exec", "LLM Codex Exec"],
  ["llm-gemini-cli", "LLM Gemini CLI"],
  ["output", "Output"],
  ["versioning", "Versioning"],
  ["citations", "Citations"],
  ["restructure", "Restructure"],
]);

const FIELD_MAP = new Map<ZsumEditableFieldPath, InternalFieldDefinition>(
  FIELD_DEFINITIONS.map((field) => [field.path, field])
);

export const ZSUM_CONFIG_SCHEMA: readonly ZsumConfigSectionDefinition[] =
  Array.from(SECTION_LABELS.entries()).map(([id, label]) => ({
    id,
    label,
    fields: FIELD_DEFINITIONS.filter((field) => field.section === id).map(
      (field) => ({
        path: field.path,
        label: field.label,
        section: field.section,
        input: field.input,
        description: field.description,
        options: field.options,
      })
    ),
  }));

function makeDefaultValues(): ZsumEditableConfigValues {
  const values = {} as ZsumEditableConfigValues;
  for (const field of FIELD_DEFINITIONS) {
    values[field.path] = field.defaultValue;
  }
  return values;
}

function cloneValues(values: ZsumEditableConfigValues): ZsumEditableConfigValues {
  return { ...values };
}

function clonePresence(
  presence: Partial<Record<ZsumEditableFieldPath, boolean>>
): Partial<Record<ZsumEditableFieldPath, boolean>> {
  return { ...presence };
}

function valuesEqual(
  left: ZsumEditableConfigValues,
  right: ZsumEditableConfigValues
): boolean {
  return FIELD_DEFINITIONS.every((field) => left[field.path] === right[field.path]);
}

function formatDocumentErrors(doc: Document.Parsed): string | null {
  const messages = doc.errors.map((error) => error.message.trim()).filter(Boolean);
  if (messages.length === 0) return null;
  return messages.join("\n");
}

function isRootMapping(doc: Document.Parsed): boolean {
  const root = doc.toJS();
  return root !== null && typeof root === "object" && !Array.isArray(root);
}

function normalizeInputValue(
  field: InternalFieldDefinition,
  value: unknown
): ZsumEditableFieldValue {
  if (field.input === "toggle") {
    if (typeof value === "boolean") return value;
    if (value === "true") return true;
    if (value === "false") return false;
    return Boolean(value);
  }
  return value == null ? "" : String(value);
}

function validateValues(
  values: ZsumEditableConfigValues
): {
  errors: ZsumConfigValidationErrors;
  serialized: Partial<Record<ZsumEditableFieldPath, unknown>>;
} {
  const errors: ZsumConfigValidationErrors = {};
  const serialized: Partial<Record<ZsumEditableFieldPath, unknown>> = {};

  for (const field of FIELD_DEFINITIONS) {
    const result = field.serialize(values[field.path]);
    if (!result.ok) {
      errors[field.path] = result.error;
      continue;
    }
    serialized[field.path] = result.value;
  }

  return { errors, serialized };
}

function getPlainValueIn(root: unknown, tokens: string[]): unknown {
  let current = root;
  for (const token of tokens) {
    if (
      current == null ||
      typeof current !== "object" ||
      Array.isArray(current) ||
      !(token in current)
    ) {
      return undefined;
    }
    current = (current as Record<string, unknown>)[token];
  }
  return current;
}

function extractValues(
  doc: Document.Parsed
): {
  values: ZsumEditableConfigValues;
  presence: Partial<Record<ZsumEditableFieldPath, boolean>>;
} {
  const values = makeDefaultValues();
  const presence: Partial<Record<ZsumEditableFieldPath, boolean>> = {};
  const root = doc.toJS();

  for (const field of FIELD_DEFINITIONS) {
    const hasField = doc.hasIn(field.tokens);
    presence[field.path] = hasField;
    const rawValue = hasField ? getPlainValueIn(root, field.tokens) : undefined;
    values[field.path] = field.toInput(rawValue);
  }

  return { values, presence };
}

function expandHome(p: string): string {
  if (p.startsWith("~")) {
    const home = process.env.HOME || process.env.USERPROFILE || "";
    return path.join(home, p.slice(1));
  }
  return p;
}

function resolveConfiguredPath(rawPath: string, configDir: string): string {
  if (!rawPath) return "";
  const expanded = expandHome(rawPath);
  return path.isAbsolute(expanded) ? expanded : path.resolve(configDir, expanded);
}

function makeResolvedPathPreviews(
  values: ZsumEditableConfigValues,
  configDir: string
): ZsumResolvedPathPreviews {
  const previews: ZsumResolvedPathPreviews = {};

  for (const fieldPath of PATH_PREVIEW_FIELDS) {
    previews[fieldPath] = resolveConfiguredPath(
      String(values[fieldPath]),
      configDir
    );
  }

  return previews;
}

async function writeFileAtomic(
  filePath: string,
  contents: string,
  io: ZsumConfigIo
): Promise<void> {
  const dirPath = path.dirname(filePath);
  const tempPath = path.join(
    dirPath,
    `.${path.basename(filePath)}.tmp-${process.pid}-${Date.now()}`
  );

  await io.mkdir(dirPath, { recursive: true });
  await io.writeFile(tempPath, contents, "utf8");

  try {
    await io.rename(tempPath, filePath);
  } catch (error) {
    await io.unlink(tempPath).catch(() => undefined);
    throw error;
  }
}

function buildRuntimeConfig(
  values: ZsumEditableConfigValues,
  configDir: string
): ZsumConfig {
  return {
    cache_dir: resolveConfiguredPath(String(values.cache_dir), configDir),
    vault_output: resolveConfiguredPath(String(values.vault_output), configDir),
  };
}

export function resolveConfigPath(
  configPath: string,
  vaultBasePath: string
): string {
  if (path.isAbsolute(configPath)) return configPath;
  return path.join(vaultBasePath, configPath);
}

export class ZsumConfigDocumentService {
  private readonly absPath: string;
  private readonly io: ZsumConfigIo;
  private readonly configDir: string;

  private exists = false;
  private parseError: string | null = null;
  private loadedDocument: Document.Parsed | null = null;
  private loadedValues: ZsumEditableConfigValues = makeDefaultValues();
  private loadedPresence: Partial<Record<ZsumEditableFieldPath, boolean>> = {};
  private draftValues: ZsumEditableConfigValues = makeDefaultValues();
  private validationErrors: ZsumConfigValidationErrors = {};

  private constructor(absPath: string, io: ZsumConfigIo) {
    this.absPath = absPath;
    this.io = io;
    this.configDir = path.dirname(absPath);
  }

  static async open(
    configPath: string,
    vaultBasePath: string,
    io: ZsumConfigIo = NODE_CONFIG_IO
  ): Promise<ZsumConfigDocumentService> {
    const service = new ZsumConfigDocumentService(
      resolveConfigPath(configPath, vaultBasePath),
      io
    );
    await service.reloadFromDisk();
    return service;
  }

  getState(): ZsumConfigDocumentState {
    return {
      path: this.absPath,
      exists: this.exists,
      dirty: !this.parseError && !valuesEqual(this.draftValues, this.loadedValues),
      parseError: this.parseError,
      validationErrors: { ...this.validationErrors },
      values: cloneValues(this.draftValues),
      resolvedPathPreviews: makeResolvedPathPreviews(
        this.draftValues,
        this.configDir
      ),
      canSave:
        !this.parseError && Object.keys(this.validationErrors).length === 0,
    };
  }

  updateField(
    fieldPath: ZsumEditableFieldPath,
    value: unknown
  ): ZsumConfigDocumentState {
    const field = FIELD_MAP.get(fieldPath);
    if (!field) {
      throw new Error(`Unknown config field: ${fieldPath}`);
    }
    if (this.parseError) {
      return this.getState();
    }

    this.draftValues[fieldPath] = normalizeInputValue(field, value);
    this.validationErrors = validateValues(this.draftValues).errors;
    return this.getState();
  }

  revert(): ZsumConfigDocumentState {
    this.draftValues = cloneValues(this.loadedValues);
    this.validationErrors = validateValues(this.draftValues).errors;
    return this.getState();
  }

  async reloadFromDisk(): Promise<ZsumConfigDocumentState> {
    let raw = "";
    let exists = true;

    try {
      raw = await this.io.readFile(this.absPath, "utf8");
    } catch (error: unknown) {
      const code =
        typeof error === "object" && error !== null && "code" in error
          ? String((error as { code?: string }).code)
          : "";
      if (code === "ENOENT") {
        exists = false;
        raw = "";
      } else {
        throw error;
      }
    }

    const source = raw.trim() === "" ? "{}\n" : raw;
    const doc = parseDocument(source);
    const parseError = formatDocumentErrors(doc);

    this.exists = exists;
    this.parseError = parseError;

    if (parseError) {
      this.loadedDocument = null;
      this.loadedValues = makeDefaultValues();
      this.loadedPresence = {};
      this.draftValues = cloneValues(this.loadedValues);
      this.validationErrors = {};
      return this.getState();
    }

    if (!isRootMapping(doc)) {
      this.loadedDocument = null;
      this.parseError = "Config root must be a YAML mapping.";
      this.loadedValues = makeDefaultValues();
      this.loadedPresence = {};
      this.draftValues = cloneValues(this.loadedValues);
      this.validationErrors = {};
      return this.getState();
    }

    const extracted = extractValues(doc);
    this.loadedDocument = doc;
    this.loadedValues = extracted.values;
    this.loadedPresence = clonePresence(extracted.presence);
    this.draftValues = cloneValues(extracted.values);
    this.validationErrors = validateValues(this.draftValues).errors;

    return this.getState();
  }

  async save(): Promise<ZsumConfigDocumentState> {
    if (this.parseError) {
      throw new ZsumConfigSaveError(
        "Cannot save while the YAML document has parse errors."
      );
    }

    const validation = validateValues(this.draftValues);
    this.validationErrors = validation.errors;
    if (Object.keys(validation.errors).length > 0) {
      throw new ZsumConfigSaveError(
        "Cannot save while validation errors are present.",
        validation.errors
      );
    }

    const baseDocument = (this.loadedDocument ?? parseDocument("{}\n")).clone();

    for (const field of FIELD_DEFINITIONS) {
      if (this.draftValues[field.path] === this.loadedValues[field.path]) {
        continue;
      }
      baseDocument.setIn(field.tokens, validation.serialized[field.path]);
    }

    const serialized = baseDocument.toString();
    await writeFileAtomic(this.absPath, serialized, this.io);
    this.exists = true;
    return this.reloadFromDisk();
  }

  readRuntimeConfig(): ZsumConfig | null {
    if (!this.exists || this.parseError) {
      return null;
    }
    return buildRuntimeConfig(this.draftValues, this.configDir);
  }
}

export async function readZsumConfig(
  configPath: string,
  vaultBasePath: string
): Promise<ZsumConfig | null> {
  try {
    const service = await ZsumConfigDocumentService.open(
      configPath,
      vaultBasePath
    );
    return service.readRuntimeConfig();
  } catch (error) {
    console.error("Failed to read zsum config:", error);
    return null;
  }
}
