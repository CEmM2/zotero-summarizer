import assert from "node:assert/strict";
import test from "node:test";

import { ZSUM_CONFIG_SCHEMA } from "./config.ts";
import {
  buildCollectionRefreshQueue,
  buildConfigViewModel,
  formatRedigestStatus,
  ZSUM_LIBRARY_STAGE_BUTTONS,
  ZSUM_VIEW_TABS,
} from "./view-model.ts";

function makeValues() {
  return Object.fromEntries(
    ZSUM_CONFIG_SCHEMA.flatMap((section) =>
      section.fields.map((field) => [
        field.path,
        field.input === "toggle" ? false : "",
      ])
    )
  );
}

function makeState(overrides = {}) {
  return {
    path: "/tmp/config.yaml",
    exists: true,
    dirty: false,
    parseError: null,
    validationErrors: {},
    values: {
      ...makeValues(),
      "llm.routing.cards": "anthropic",
      "llm.routing.digests": "openai_compat",
      "llm.routing.redigest": "codex_exec",
      "llm.openai_compat.model": "gpt-4.1-mini",
      "generate_paper_notes": true,
    },
    resolvedPathPreviews: {
      cache_dir: "/tmp/cache",
      vault_output: "/tmp/vault",
    },
    canSave: true,
    ...overrides,
  };
}

test("tabs expose library and config surfaces", () => {
  assert.deepEqual(
    ZSUM_VIEW_TABS.map((tab) => tab.label),
    ["Library", "Config"]
  );
});

test("config view model renders planned sections and control types", () => {
  const model = buildConfigViewModel(ZSUM_CONFIG_SCHEMA, makeState());
  const labels = model.sections.map((section) => section.label);

  assert.deepEqual(labels, [
    "Paths",
    "Scope",
    "Extraction",
    "LLM Routing",
    "LLM Anthropic",
    "LLM OpenAI Compatible",
    "LLM Codex Exec",
    "LLM Gemini CLI",
    "Output",
    "Versioning",
    "Citations",
    "Restructure",
  ]);

  const fields = Object.fromEntries(
    model.sections.flatMap((section) =>
      section.fields.map((field) => [field.path, field])
    )
  );
  assert.equal(fields["llm.routing.cards"].input, "dropdown");
  assert.equal(fields["llm.routing.digests"].input, "dropdown");
  assert.equal(fields["llm.routing.redigest"].input, "dropdown");
  assert.equal(fields["llm.openai_compat.model"].input, "text");
  assert.equal(fields["cache_dir"].pathPreview, "/tmp/cache");
  assert.equal(fields["generate_paper_notes"].input, "toggle");
});

test("dirty state badge and explicit save actions follow the workflow contract", () => {
  const model = buildConfigViewModel(
    ZSUM_CONFIG_SCHEMA,
    makeState({ dirty: true, canSave: true })
  );
  const actions = Object.fromEntries(model.actions.map((action) => [action.id, action]));

  assert.equal(model.dirty, true);
  assert.equal(model.dirtyBadgeLabel, "Unsaved");
  assert.equal(actions.save.disabled, false);
  assert.equal(actions.revert.disabled, false);
  assert.equal(actions.reload.disabled, false);
});

test("parse errors and missing files surface inline while save stays disabled", () => {
  const parseModel = buildConfigViewModel(
    ZSUM_CONFIG_SCHEMA,
    makeState({
      parseError: "unexpected end of stream",
      canSave: false,
    })
  );
  assert.equal(parseModel.actions.find((action) => action.id === "save")?.disabled, true);
  assert.match(parseModel.banners[0].text, /unexpected end of stream/);

  const missingModel = buildConfigViewModel(
    ZSUM_CONFIG_SCHEMA,
    makeState({
      exists: false,
      path: "/vault/config.yaml",
    })
  );
  assert.match(missingModel.banners[0].text, /\/vault\/config\.yaml/);
  assert.match(missingModel.banners[0].text, /Save to create it/);
});

test("success feedback appears only when explicit save feedback is provided", () => {
  const noFeedbackModel = buildConfigViewModel(ZSUM_CONFIG_SCHEMA, makeState());
  assert.equal(
    noFeedbackModel.banners.some((banner) => banner.kind === "success"),
    false
  );

  const successModel = buildConfigViewModel(
    ZSUM_CONFIG_SCHEMA,
    makeState(),
    { kind: "success", text: "Config saved." }
  );
  assert.equal(successModel.banners[0].kind, "success");
  assert.equal(successModel.banners[0].text, "Config saved.");
});

test("library controls list every stage grouped local-then-llm with Cancel last", () => {
  // The canonical stage list: local stages first (excluding
  // Clear Cache, which moved to the controls-head), then LLM stages, then Full
  // Run, then Cancel. The order inside each group is the click order intended
  // for the new stage-pad grid.
  assert.deepEqual(
    ZSUM_LIBRARY_STAGE_BUTTONS.map((button) => button.label),
    [
      "Skeleton",
      "Citations",
      "Publish",
      "Reviews",
      "Stats",
      "Cards",
      "Digests",
      "Redigest",
      "Restructure",
      "Full Run",
      "Cancel",
    ]
  );
});

test("collection refresh queue runs digests before redigest", () => {
  assert.deepEqual(buildCollectionRefreshQueue("My Collection"), [
    ["digests", "--collection", "My Collection"],
    ["redigest", "--collection", "My Collection"],
  ]);
});

test("redigest status text maps directly from plugin index state", () => {
  assert.equal(formatRedigestStatus("ok"), "redigest ok");
  assert.equal(formatRedigestStatus("stale"), "redigest stale");
  assert.equal(formatRedigestStatus("missing"), "redigest missing");
  assert.equal(formatRedigestStatus(null), null);
});
