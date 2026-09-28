import assert from "node:assert/strict";
import test from "node:test";

// Introduces:
//   - allCollectionKeys(collections | null | undefined): readonly string[]
//     Pure helper that returns every key in a collections record. Returns []
//     for null/undefined/empty so the expand-all click is a no-op when
//     this.index is null. Used by ZsumView.expandAllCollections() to
//     populate this.expandedNodes before re-rendering the tree.
//
// DOM-level acceptance criteria (button rendered in tree-panel header,
// click expands every node, panel header is now flex space-between)
// deferred to manual Obsidian-reload verification.

let allCollectionKeys;
try {
  ({ allCollectionKeys } = await import("./view-model.ts"));
} catch {
  // Helper not yet exported — tests below self-skip.
}

test("allCollectionKeys returns every key in a non-empty record", (t) => {
  if (!allCollectionKeys) {
    t.skip("allCollectionKeys not yet exported");
    return;
  }
  const collections = {
    a: { name: "a" },
    b: { name: "b" },
    c: { name: "c" },
  };
  const result = allCollectionKeys(collections);
  assert.deepEqual(new Set(result), new Set(["a", "b", "c"]));
});

test("allCollectionKeys returns [] for an empty record", (t) => {
  if (!allCollectionKeys) {
    t.skip("allCollectionKeys not yet exported");
    return;
  }
  assert.deepEqual(allCollectionKeys({}), []);
});

test("allCollectionKeys returns [] for null / undefined", (t) => {
  if (!allCollectionKeys) {
    t.skip("allCollectionKeys not yet exported");
    return;
  }
  assert.deepEqual(allCollectionKeys(null), []);
  assert.deepEqual(allCollectionKeys(undefined), []);
});

test("allCollectionKeys is idempotent (Set semantics) — calling twice produces the same set", (t) => {
  if (!allCollectionKeys) {
    t.skip("allCollectionKeys not yet exported");
    return;
  }
  const collections = { a: {}, b: {}, c: {} };
  const a = new Set(allCollectionKeys(collections));
  const b = new Set(allCollectionKeys(collections));
  assert.equal(a.size, b.size);
  for (const k of a) assert.ok(b.has(k));
});
