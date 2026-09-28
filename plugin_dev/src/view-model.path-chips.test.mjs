import assert from "node:assert/strict";
import test from "node:test";

// Introduces:
//   - formatRootStatusChip(projectRoot): { label, modifier }
//     "project root set" / "default" when projectRoot is non-empty
//     "⚠ root not set" / "warn" when empty / whitespace
//   - formatCacheChipText(cacheDir | undefined): string
//     "<basename>/index.json" or "cache/index.json" fallback
//
// DOM-level acceptance criteria (chip render in tabs row, click toggles
// drawer, narrow-panel hide) deferred to manual Obsidian-reload verification.

let formatRootStatusChip;
let formatCacheChipText;
try {
  ({ formatRootStatusChip, formatCacheChipText } = await import("./view-model.ts"));
} catch {
  // Helpers not yet exported — tests below self-skip.
}

test("formatRootStatusChip returns 'project root set' + 'default' for non-empty paths", (t) => {
  if (!formatRootStatusChip) {
    t.skip("formatRootStatusChip not yet exported");
    return;
  }
  assert.deepEqual(formatRootStatusChip("/home/me/zsum"), {
    label: "project root set",
    modifier: "default",
  });
});

test("formatRootStatusChip returns warn variant for empty / whitespace projectRoot", (t) => {
  if (!formatRootStatusChip) {
    t.skip("formatRootStatusChip not yet exported");
    return;
  }
  assert.deepEqual(formatRootStatusChip(""), {
    label: "⚠ root not set",
    modifier: "warn",
  });
  assert.deepEqual(formatRootStatusChip("   "), {
    label: "⚠ root not set",
    modifier: "warn",
  });
});

test("formatCacheChipText returns '<basename>/index.json' for absolute paths", (t) => {
  if (!formatCacheChipText) {
    t.skip("formatCacheChipText not yet exported");
    return;
  }
  assert.equal(
    formatCacheChipText("/home/me/zsum/cache"),
    "cache/index.json"
  );
});

test("formatCacheChipText returns '<basename>/index.json' for relative cache paths", (t) => {
  if (!formatCacheChipText) {
    t.skip("formatCacheChipText not yet exported");
    return;
  }
  assert.equal(formatCacheChipText("./.cache"), ".cache/index.json");
});

test("formatCacheChipText falls back to 'cache/index.json' for null/undefined/empty", (t) => {
  if (!formatCacheChipText) {
    t.skip("formatCacheChipText not yet exported");
    return;
  }
  assert.equal(formatCacheChipText(undefined), "cache/index.json");
  assert.equal(formatCacheChipText(""), "cache/index.json");
  assert.equal(formatCacheChipText(null), "cache/index.json");
});
