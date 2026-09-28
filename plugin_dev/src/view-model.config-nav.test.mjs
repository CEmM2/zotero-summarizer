import assert from "node:assert/strict";
import test from "node:test";

import { ZSUM_CONFIG_SCHEMA } from "./config.ts";

// Introduces:
//   - ZSUM_CONFIG_NAV_GROUPS: readonly array of { id, label, sectionIds: string[] }
//   - buildNavSections(schema, groupId): returns the schema sections in the
//     given nav group, preserving plan order.
//
// Introduces:
//   - formatConfigStatusText(dirty, lastSavedAt): footer status string
//     ("Dirty state buffered in memory" | "Saved HH:MM:SS" | "")
//
// DOM-level acceptance criteria (sidebar nav rail, only-active panel render,
// banner chip swap, multi-section auto-fit grid) are deferred to manual
// Obsidian-reload verification as elsewhere in this suite.

let ZSUM_CONFIG_NAV_GROUPS;
let buildNavSections;
let formatConfigStatusText;
try {
  ({
    ZSUM_CONFIG_NAV_GROUPS,
    buildNavSections,
    formatConfigStatusText,
  } = await import("./view-model.ts"));
} catch {
  // Helpers not yet exported — tests below self-skip.
}

// ---------------------------------------------------------------------------
// nav-group mapping
// ---------------------------------------------------------------------------

test("ZSUM_CONFIG_NAV_GROUPS lists six tabs in plan order", (t) => {
  if (!ZSUM_CONFIG_NAV_GROUPS) {
    t.skip("ZSUM_CONFIG_NAV_GROUPS not yet exported");
    return;
  }
  assert.deepEqual(
    ZSUM_CONFIG_NAV_GROUPS.map((g) => g.id),
    ["paths", "scope", "llm", "output", "citations", "restructure"]
  );
});

test("every nav-group entry has a non-empty label and at least one sectionId", (t) => {
  if (!ZSUM_CONFIG_NAV_GROUPS) {
    t.skip("ZSUM_CONFIG_NAV_GROUPS not yet exported");
    return;
  }
  for (const g of ZSUM_CONFIG_NAV_GROUPS) {
    assert.ok(g.label && g.label.length > 0, `${g.id} missing label`);
    assert.ok(
      Array.isArray(g.sectionIds) && g.sectionIds.length > 0,
      `${g.id} missing sectionIds`
    );
  }
});

test("nav groups cover every schema section exactly once (no orphans, no duplicates)", (t) => {
  if (!ZSUM_CONFIG_NAV_GROUPS) {
    t.skip("ZSUM_CONFIG_NAV_GROUPS not yet exported");
    return;
  }
  const schemaIds = new Set(ZSUM_CONFIG_SCHEMA.map((s) => s.id));
  const seen = new Set();
  for (const g of ZSUM_CONFIG_NAV_GROUPS) {
    for (const id of g.sectionIds) {
      assert.ok(
        schemaIds.has(id),
        `${g.id} references unknown schema section "${id}"`
      );
      assert.ok(
        !seen.has(id),
        `schema section "${id}" assigned to more than one nav group`
      );
      seen.add(id);
    }
  }
  // Every schema section must appear in exactly one nav group.
  for (const id of schemaIds) {
    assert.ok(seen.has(id), `schema section "${id}" is orphaned (no nav group)`);
  }
});

test("LLM nav group bundles routing + three provider sections", (t) => {
  if (!ZSUM_CONFIG_NAV_GROUPS) {
    t.skip("ZSUM_CONFIG_NAV_GROUPS not yet exported");
    return;
  }
  const llm = ZSUM_CONFIG_NAV_GROUPS.find((g) => g.id === "llm");
  assert.ok(llm, "llm nav group missing");
  assert.deepEqual(llm.sectionIds, [
    "llm-routing",
    "llm-anthropic",
    "llm-openai-compat",
    "llm-codex-exec",
  ]);
});

test("scope nav group bundles scope + extraction; output bundles output + versioning", (t) => {
  if (!ZSUM_CONFIG_NAV_GROUPS) {
    t.skip("ZSUM_CONFIG_NAV_GROUPS not yet exported");
    return;
  }
  const scope = ZSUM_CONFIG_NAV_GROUPS.find((g) => g.id === "scope");
  const output = ZSUM_CONFIG_NAV_GROUPS.find((g) => g.id === "output");
  assert.deepEqual(scope.sectionIds, ["scope", "extraction"]);
  assert.deepEqual(output.sectionIds, ["output", "versioning"]);
});

test("buildNavSections returns the schema sections in plan order for a group", (t) => {
  if (!buildNavSections) {
    t.skip("buildNavSections not yet exported");
    return;
  }
  const llmSections = buildNavSections(ZSUM_CONFIG_SCHEMA, "llm");
  assert.deepEqual(
    llmSections.map((s) => s.id),
    ["llm-routing", "llm-anthropic", "llm-openai-compat", "llm-codex-exec"]
  );
});

test("buildNavSections returns [] for an unknown group id", (t) => {
  if (!buildNavSections) {
    t.skip("buildNavSections not yet exported");
    return;
  }
  assert.deepEqual(buildNavSections(ZSUM_CONFIG_SCHEMA, "no-such-group"), []);
});

// ---------------------------------------------------------------------------
// footer status text formatter
// ---------------------------------------------------------------------------

test("formatConfigStatusText returns 'Dirty state buffered in memory' when dirty", (t) => {
  if (!formatConfigStatusText) {
    t.skip("formatConfigStatusText not yet exported");
    return;
  }
  assert.equal(
    formatConfigStatusText(true, null),
    "Dirty state buffered in memory"
  );
  // Even with a saved timestamp, dirty wins.
  assert.equal(
    formatConfigStatusText(true, new Date(2026, 3, 26, 18, 56, 42)),
    "Dirty state buffered in memory"
  );
});

test("formatConfigStatusText returns 'Saved HH:MM:SS' when clean and lastSavedAt is set", (t) => {
  if (!formatConfigStatusText) {
    t.skip("formatConfigStatusText not yet exported");
    return;
  }
  const stamp = new Date(2026, 3, 26, 7, 5, 9);
  assert.equal(formatConfigStatusText(false, stamp), "Saved 07:05:09");
});

test("formatConfigStatusText returns '' when clean and never saved", (t) => {
  if (!formatConfigStatusText) {
    t.skip("formatConfigStatusText not yet exported");
    return;
  }
  assert.equal(formatConfigStatusText(false, null), "");
});
