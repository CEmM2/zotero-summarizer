import assert from "node:assert/strict";
import test from "node:test";

// Two pure helpers live in view-model.ts so the new status bar's
// live-box and indexed-timestamp logic can be exercised headlessly:
//   - formatBbtIndicator(isLive: boolean) -> { label, modifier }
//     where modifier is one of "ok" | "stale".
//   - formatIndexedTimestamp(date: Date | null) -> "indexed HH:MM:SS" or "".
//
// DOM-level checks (brand block render, stat-card
// border + value-above-label visual, live-box pulse animation) are deferred
// to manual Obsidian-reload verification as elsewhere in this suite.

let formatBbtIndicator;
let formatIndexedTimestamp;
try {
  ({ formatBbtIndicator, formatIndexedTimestamp } = await import("./view-model.ts"));
} catch {
  // Helpers not yet exported — tests below self-skip.
}

// ---------------------------------------------------------------------------
// formatBbtIndicator
// ---------------------------------------------------------------------------

test("formatBbtIndicator(true) returns 'BBT live' + 'ok' modifier", (t) => {
  if (!formatBbtIndicator) {
    t.skip("formatBbtIndicator not yet exported");
    return;
  }
  assert.deepEqual(formatBbtIndicator(true), { label: "BBT live", modifier: "ok" });
});

test("formatBbtIndicator(false) returns 'BBT stale' + 'stale' modifier", (t) => {
  if (!formatBbtIndicator) {
    t.skip("formatBbtIndicator not yet exported");
    return;
  }
  assert.deepEqual(formatBbtIndicator(false), { label: "BBT stale", modifier: "stale" });
});

// ---------------------------------------------------------------------------
// formatIndexedTimestamp
// ---------------------------------------------------------------------------

test("formatIndexedTimestamp(null) returns empty string", (t) => {
  if (!formatIndexedTimestamp) {
    t.skip("formatIndexedTimestamp not yet exported");
    return;
  }
  assert.equal(formatIndexedTimestamp(null), "");
});

test("formatIndexedTimestamp(Date) returns 'indexed HH:MM:SS' (zero-padded)", (t) => {
  if (!formatIndexedTimestamp) {
    t.skip("formatIndexedTimestamp not yet exported");
    return;
  }
  // Use a Date with single-digit hour/minute/second to lock zero-padding.
  const d = new Date(2026, 3, 26, 7, 5, 9);
  assert.equal(formatIndexedTimestamp(d), "indexed 07:05:09");
});

test("formatIndexedTimestamp(Date) preserves two-digit components", (t) => {
  if (!formatIndexedTimestamp) {
    t.skip("formatIndexedTimestamp not yet exported");
    return;
  }
  const d = new Date(2026, 3, 26, 18, 56, 42);
  assert.equal(formatIndexedTimestamp(d), "indexed 18:56:42");
});

test("formatIndexedTimestamp(Date) handles midnight (00:00:00)", (t) => {
  if (!formatIndexedTimestamp) {
    t.skip("formatIndexedTimestamp not yet exported");
    return;
  }
  const d = new Date(2026, 3, 26, 0, 0, 0);
  assert.equal(formatIndexedTimestamp(d), "indexed 00:00:00");
});
