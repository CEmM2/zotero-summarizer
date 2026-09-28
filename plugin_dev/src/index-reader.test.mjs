import assert from "node:assert/strict";
import test from "node:test";

import { computeStats } from "./index-reader.ts";

// Audit note: LibraryStats already exposes cards_no_pdf and digests_missing
// and computeStats already populates them in the existing single-pass loops
// (index-reader.ts:103, 106, 112, 117). These tests lock that behaviour so a
// future refactor cannot silently drop either count.

function makeIndex({ items = {}, collections = {} } = {}) {
  return { generated_at: "2026-04-26T00:00:00Z", items, collections };
}

test("computeStats counts cards_no_pdf separately from cached/pending/degraded", () => {
  const index = makeIndex({
    items: {
      a: { citekey: "a", year: 2020, venue: "X", collections: ["c1"], card_state: "cached" },
      b: { citekey: "b", year: 2020, venue: "X", collections: ["c1"], card_state: "no_pdf" },
      c: { citekey: "c", year: 2020, venue: "X", collections: ["c1"], card_state: "no_pdf" },
      d: { citekey: "d", year: 2020, venue: "X", collections: ["c1"], card_state: "no_pdf" },
      e: { citekey: "e", year: 2020, venue: "X", collections: ["c1"], card_state: "pending" },
      f: { citekey: "f", year: 2020, venue: "X", collections: ["c1"], card_state: "degraded" },
    },
  });
  const s = computeStats(index);
  assert.equal(s.total_papers, 6);
  assert.equal(s.cards_cached, 1);
  assert.equal(s.cards_pending, 1);
  assert.equal(s.cards_degraded, 1);
  assert.equal(s.cards_no_pdf, 3);
});

test("computeStats counts cards_fallback separately from cached/degraded/no_pdf", () => {
  const index = makeIndex({
    items: {
      a: { citekey: "a", year: 2020, venue: "X", collections: ["c1"], card_state: "cached" },
      b: {
        citekey: "b",
        year: 2020,
        venue: "X",
        collections: ["c1"],
        card_state: "fallback",
        extraction_method: "fallback_pages",
      },
      c: {
        citekey: "c",
        year: 2020,
        venue: "X",
        collections: ["c1"],
        card_state: "fallback",
        extraction_method: "fallback_pages",
      },
      d: { citekey: "d", year: 2020, venue: "X", collections: ["c1"], card_state: "degraded" },
      e: { citekey: "e", year: 2020, venue: "X", collections: ["c1"], card_state: "no_pdf" },
    },
  });
  const s = computeStats(index);
  assert.equal(s.total_papers, 5);
  assert.equal(s.cards_cached, 1);
  assert.equal(s.cards_fallback, 2);
  assert.equal(s.cards_degraded, 1);
  assert.equal(s.cards_no_pdf, 1);
  assert.equal(
    s.cards_cached +
      s.cards_pending +
      s.cards_degraded +
      s.cards_fallback +
      s.cards_no_pdf,
    s.total_papers
  );
});

test("computeStats counts digests_missing separately from ok/stale", () => {
  const index = makeIndex({
    collections: {
      c1: { name: "c1", parent: null, path: "c1", item_count: 0, digest_state: "ok", redigest_state: "ok" },
      c2: { name: "c2", parent: null, path: "c2", item_count: 0, digest_state: "stale", redigest_state: "ok" },
      c3: { name: "c3", parent: null, path: "c3", item_count: 0, digest_state: "missing", redigest_state: "missing" },
      c4: { name: "c4", parent: null, path: "c4", item_count: 0, digest_state: "missing", redigest_state: "missing" },
    },
  });
  const s = computeStats(index);
  assert.equal(s.total_collections, 4);
  assert.equal(s.digests_ok, 1);
  assert.equal(s.digests_stale, 1);
  assert.equal(s.digests_missing, 2);
});

test("computeStats returns zeros for empty index", () => {
  const s = computeStats(makeIndex());
  assert.equal(s.total_papers, 0);
  assert.equal(s.total_collections, 0);
  assert.equal(s.cards_cached, 0);
  assert.equal(s.cards_pending, 0);
  assert.equal(s.cards_degraded, 0);
  assert.equal(s.cards_fallback, 0);
  assert.equal(s.cards_no_pdf, 0);
  assert.equal(s.digests_ok, 0);
  assert.equal(s.digests_stale, 0);
  assert.equal(s.digests_missing, 0);
});

test("computeStats sums over all card states in a single pass (no double-count)", () => {
  // The five card_state values are mutually exclusive — sum must equal
  // total_papers regardless of distribution.
  const index = makeIndex({
    items: {
      a: { citekey: "a", year: 2020, venue: "X", collections: [], card_state: "cached" },
      b: { citekey: "b", year: 2020, venue: "X", collections: [], card_state: "cached" },
      c: { citekey: "c", year: 2020, venue: "X", collections: [], card_state: "pending" },
      d: { citekey: "d", year: 2020, venue: "X", collections: [], card_state: "degraded" },
      e: { citekey: "e", year: 2020, venue: "X", collections: [], card_state: "fallback" },
      f: { citekey: "f", year: 2020, venue: "X", collections: [], card_state: "no_pdf" },
    },
  });
  const s = computeStats(index);
  assert.equal(
    s.cards_cached +
      s.cards_pending +
      s.cards_degraded +
      s.cards_fallback +
      s.cards_no_pdf,
    s.total_papers
  );
});

test("computeStats sums over all digest states without double-count", () => {
  const index = makeIndex({
    collections: {
      a: { name: "a", parent: null, path: "a", item_count: 0, digest_state: "ok", redigest_state: "ok" },
      b: { name: "b", parent: null, path: "b", item_count: 0, digest_state: "stale", redigest_state: "ok" },
      c: { name: "c", parent: null, path: "c", item_count: 0, digest_state: "missing", redigest_state: "missing" },
    },
  });
  const s = computeStats(index);
  assert.equal(
    s.digests_ok + s.digests_stale + s.digests_missing,
    s.total_collections
  );
});
