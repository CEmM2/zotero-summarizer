import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import test from "node:test";

import {
  ZSUM_CONFIG_SCHEMA,
  ZsumConfigDocumentService,
  ZsumConfigSaveError,
} from "./config.ts";

async function makeTempDir(t) {
  const dir = await fs.promises.mkdtemp(path.join(os.tmpdir(), "zsum-config-"));
  t.after(async () => {
    await fs.promises.rm(dir, { recursive: true, force: true });
  });
  return dir;
}

test("schema exposes the supported editable field inventory", () => {
  const fields = new Set(
    ZSUM_CONFIG_SCHEMA.flatMap((section) => section.fields.map((field) => field.path))
  );

  assert.equal(fields.size, 47);
  assert.ok(fields.has("bbt_json"));
  assert.ok(fields.has("llm.routing.cards"));
  assert.ok(fields.has("llm.openai_compat.model"));
  assert.ok(fields.has("citations.timeout_seconds"));
  assert.ok(fields.has("restructure.max_digest_chars"));
});

test("round-trip save preserves comments, unknown keys, and legacy llm.provider", async (t) => {
  const dir = await makeTempDir(t);
  const configPath = path.join(dir, "config.yaml");
  await fs.promises.writeFile(
    configPath,
    [
      "# top comment",
      "cache_dir: ./cache",
      "vault_output: ./vault",
      "unknown_root_key: keep-me",
      "",
      "llm:",
      "  provider: anthropic",
      "  # routing comment",
      "  routing:",
      "    cards: anthropic",
      "    digests: anthropic",
      "    redigest: codex_exec",
      "",
    ].join("\n"),
    "utf8"
  );

  const service = await ZsumConfigDocumentService.open(configPath, "/");
  let state = service.getState();
  assert.equal(state.parseError, null);
  assert.equal(state.values["llm.routing.cards"], "anthropic");

  state = service.updateField("llm.routing.cards", "openai_compat");
  assert.equal(state.values["llm.routing.cards"], "openai_compat");

  await service.save();

  const saved = await fs.promises.readFile(configPath, "utf8");
  assert.match(saved, /# top comment/);
  assert.match(saved, /unknown_root_key: keep-me/);
  assert.match(saved, /provider: anthropic/);
  assert.match(saved, /# routing comment/);
  assert.match(saved, /cards: openai_compat/);
});

test("invalid provider and numeric values block save without touching the file", async (t) => {
  const dir = await makeTempDir(t);
  const configPath = path.join(dir, "config.yaml");
  await fs.promises.writeFile(
    configPath,
    "cache_dir: ./cache\nvault_output: ./vault\nllm:\n  routing:\n    cards: anthropic\n",
    "utf8"
  );

  const service = await ZsumConfigDocumentService.open(configPath, "/");
  const original = await fs.promises.readFile(configPath, "utf8");

  service.updateField("llm.routing.cards", "not-a-provider");
  await assert.rejects(
    () => service.save(),
    (error) =>
      error instanceof ZsumConfigSaveError &&
      error.validationErrors["llm.routing.cards"] !== undefined
  );
  assert.equal(await fs.promises.readFile(configPath, "utf8"), original);

  service.revert();
  service.updateField("max_text_chars", "NaN");
  await assert.rejects(
    () => service.save(),
    (error) =>
      error instanceof ZsumConfigSaveError &&
      error.validationErrors["max_text_chars"] !== undefined
  );
  assert.equal(await fs.promises.readFile(configPath, "utf8"), original);
});

test("parse errors disable save and recover via reload from disk", async (t) => {
  const dir = await makeTempDir(t);
  const configPath = path.join(dir, "config.yaml");
  await fs.promises.writeFile(configPath, "llm:\n  routing:\n    cards: [oops\n", "utf8");

  const service = await ZsumConfigDocumentService.open(configPath, "/");
  let state = service.getState();
  assert.ok(state.parseError);
  assert.equal(state.canSave, false);

  await fs.promises.writeFile(
    configPath,
    "cache_dir: ./cache\nvault_output: ./vault\nllm:\n  routing:\n    cards: anthropic\n",
    "utf8"
  );

  state = await service.reloadFromDisk();
  assert.equal(state.parseError, null);
  assert.equal(state.values["llm.routing.cards"], "anthropic");
  assert.equal(state.canSave, true);
});

test("edits stay buffered until save, and revert plus reload restore disk state", async (t) => {
  const dir = await makeTempDir(t);
  const configPath = path.join(dir, "config.yaml");
  await fs.promises.writeFile(
    configPath,
    "cache_dir: ./cache\nvault_output: ./vault\n",
    "utf8"
  );

  const service = await ZsumConfigDocumentService.open(configPath, "/");

  let state = service.updateField("cache_dir", "./buffered-cache");
  assert.equal(state.dirty, true);
  assert.equal(
    await fs.promises.readFile(configPath, "utf8"),
    "cache_dir: ./cache\nvault_output: ./vault\n"
  );

  state = service.revert();
  assert.equal(state.values.cache_dir, "./cache");
  assert.equal(state.dirty, false);

  state = service.updateField("cache_dir", "./still-unsaved");
  assert.equal(state.values.cache_dir, "./still-unsaved");

  await fs.promises.writeFile(
    configPath,
    "cache_dir: ./from-disk\nvault_output: ./vault\n",
    "utf8"
  );

  state = await service.reloadFromDisk();
  assert.equal(state.values.cache_dir, "./from-disk");
  assert.equal(state.dirty, false);
});

test("save uses an atomic rename and preserves list plus empty-string semantics", async (t) => {
  const dir = await makeTempDir(t);
  const configPath = path.join(dir, "config.yaml");
  await fs.promises.writeFile(
    configPath,
    [
      "cache_dir: ./cache",
      "vault_output: ./vault",
      "collections:",
      "  - Existing",
      "citations:",
      '  email: "keep@example.com"',
      "",
    ].join("\n"),
    "utf8"
  );

  const renameCalls = [];
  const spyIo = {
    readFile: (filePath, encoding) => fs.promises.readFile(filePath, encoding),
    writeFile: (filePath, contents, encoding) =>
      fs.promises.writeFile(filePath, contents, encoding),
    rename: async (sourcePath, targetPath) => {
      renameCalls.push([sourcePath, targetPath]);
      return fs.promises.rename(sourcePath, targetPath);
    },
    unlink: (filePath) => fs.promises.unlink(filePath),
    mkdir: (dirPath, options) => fs.promises.mkdir(dirPath, options),
  };

  const service = await ZsumConfigDocumentService.open(configPath, "/", spyIo);
  service.updateField("collections", "Alpha\n\nBeta\n");
  service.updateField("citations.email", "");

  await service.save();

  assert.equal(renameCalls.length, 1);
  assert.equal(path.dirname(renameCalls[0][0]), dir);
  assert.equal(renameCalls[0][1], configPath);
  assert.match(path.basename(renameCalls[0][0]), /^\.config\.yaml\.tmp-/);

  const reloaded = await ZsumConfigDocumentService.open(configPath, "/");
  const state = reloaded.getState();
  assert.equal(state.values.collections, "Alpha\nBeta");
  assert.equal(state.values["citations.email"], "");

  const saved = await fs.promises.readFile(configPath, "utf8");
  assert.match(saved, /collections:\n\s+- Alpha\n\s+- Beta/);
  assert.match(saved, /email: ""/);
});
