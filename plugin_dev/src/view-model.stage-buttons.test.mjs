import assert from "node:assert/strict";
import test from "node:test";

import {
  ZSUM_LIBRARY_STAGE_BUTTONS,
  // Helpers this scaffold relies on:
  // computeStageRunArgs (pure helper that builds the CLI args
  // for a stage click given the button definition and the force-toggle state).
  // Stubs below skip when these symbols are not yet exported, so the test file
  // is safe to commit before the implementation lands.
} from "./view-model.ts";

// ---------------------------------------------------------------------------
// Stage button definitions carry `variant` and `group` fields, and
// ZSUM_LIBRARY_STAGE_BUTTONS is reorganised to declare local-vs-LLM grouping
// and visual variants for every stage (including a Cancel entry inside `llm`).
// ---------------------------------------------------------------------------

test("every stage button declares a `group` of 'local' or 'llm'", () => {
  for (const button of ZSUM_LIBRARY_STAGE_BUTTONS) {
    assert.ok(
      button.group === "local" || button.group === "llm",
      `Button "${button.label}" missing group; saw ${JSON.stringify(button.group)}`
    );
  }
});

test("every stage button declares a `variant` from the canonical set", () => {
  const allowed = new Set(["default", "primary", "llm", "danger"]);
  for (const button of ZSUM_LIBRARY_STAGE_BUTTONS) {
    assert.ok(
      allowed.has(button.variant),
      `Button "${button.label}" has invalid variant ${JSON.stringify(button.variant)}`
    );
  }
});

test("local group contains the five non-LLM stages in expected order", () => {
  const local = ZSUM_LIBRARY_STAGE_BUTTONS.filter((b) => b.group === "local");
  const labels = local.map((b) => b.label);
  assert.deepEqual(labels, ["Skeleton", "Citations", "Publish", "Reviews", "Stats"]);
  for (const button of local) {
    assert.equal(button.variant, "default", `${button.label} should be variant=default`);
  }
});

test("LLM group contains the four LLM stages plus Full Run and Cancel", () => {
  const llm = ZSUM_LIBRARY_STAGE_BUTTONS.filter((b) => b.group === "llm");
  const byArg = Object.fromEntries(llm.map((b) => [b.args[0], b]));

  assert.equal(byArg["cards"]?.variant, "llm");
  assert.equal(byArg["digests"]?.variant, "llm");
  assert.equal(byArg["redigest"]?.variant, "llm");
  assert.equal(byArg["restructure"]?.variant, "llm");
  assert.equal(byArg["all"]?.variant, "primary");
  assert.equal(byArg["cancel"]?.variant, "danger");

  assert.equal(byArg["all"]?.label, "Full Run");
  assert.equal(byArg["cancel"]?.label, "Cancel");
});

test("forceability is preserved across the reorganisation", () => {
  const byArg = Object.fromEntries(
    ZSUM_LIBRARY_STAGE_BUTTONS.map((b) => [b.args[0], b])
  );
  assert.equal(byArg["cards"].forceable, true);
  assert.equal(byArg["digests"].forceable, true);
  assert.equal(byArg["redigest"].forceable, true);
  for (const arg of [
    "skeleton",
    "citations",
    "publish",
    "reviews",
    "stats",
    "restructure",
    "all",
    "cancel",
  ]) {
    assert.equal(
      byArg[arg].forceable,
      false,
      `${arg} should be forceable=false`
    );
  }
});

// ---------------------------------------------------------------------------
// The view-side helper computeStageRunArgs(definition, forceChecked)
// produces the final CLI args for a stage click. It must:
//   - return a copy of definition.args when force is unchecked
//   - append "--force" only when forceChecked AND definition.forceable
//   - never mutate the original definition.args
// ---------------------------------------------------------------------------

let computeStageRunArgs;
try {
  ({ computeStageRunArgs } = await import("./view-model.ts"));
} catch {
  // Helper not yet exported — tests below self-skip.
}

test("computeStageRunArgs returns args verbatim when force is unchecked", (t) => {
  if (!computeStageRunArgs) {
    t.skip("computeStageRunArgs not yet exported");
    return;
  }
  const cards = ZSUM_LIBRARY_STAGE_BUTTONS.find((b) => b.args[0] === "cards");
  const result = computeStageRunArgs(cards, false);
  assert.deepEqual(result, ["cards"]);
});

test("computeStageRunArgs appends --force when forceable AND checked", (t) => {
  if (!computeStageRunArgs) {
    t.skip("computeStageRunArgs not yet exported");
    return;
  }
  const cards = ZSUM_LIBRARY_STAGE_BUTTONS.find((b) => b.args[0] === "cards");
  const result = computeStageRunArgs(cards, true);
  assert.deepEqual(result, ["cards", "--force"]);
});

test("computeStageRunArgs does NOT append --force for non-forceable stages", (t) => {
  if (!computeStageRunArgs) {
    t.skip("computeStageRunArgs not yet exported");
    return;
  }
  const skeleton = ZSUM_LIBRARY_STAGE_BUTTONS.find((b) => b.args[0] === "skeleton");
  assert.deepEqual(computeStageRunArgs(skeleton, true), ["skeleton"]);

  const all = ZSUM_LIBRARY_STAGE_BUTTONS.find((b) => b.args[0] === "all");
  assert.deepEqual(computeStageRunArgs(all, true), ["all"]);
});

test("computeStageRunArgs does not mutate the original definition.args", (t) => {
  if (!computeStageRunArgs) {
    t.skip("computeStageRunArgs not yet exported");
    return;
  }
  const digests = ZSUM_LIBRARY_STAGE_BUTTONS.find((b) => b.args[0] === "digests");
  const before = digests.args.slice();
  computeStageRunArgs(digests, true);
  assert.deepEqual(digests.args, before, "definition.args mutated by helper");
});
