import assert from "node:assert/strict";
import test from "node:test";

// filterPapersByCitekey — a pure helper that returns a new
// array of items whose citekey contains the query (case-insensitive). When the
// query is empty the original list is returned unchanged.
//
// typePillVariant — maps an ItemIndex.paper_type value (or
// undefined) to one of the four CSS variant keys: "research" | "review" |
// "survey" | "meta". The PaperType union in index-reader.ts has five members
// (research | review | survey | meta-analysis | tutorial) plus the
// undefined-fallback case; the mapping must collapse meta-analysis → meta and
// fall back to "research" for anything unknown including undefined and empty.

let filterPapersByCitekey;
let typePillVariant;
try {
  ({ filterPapersByCitekey, typePillVariant } = await import("./view-model.ts"));
} catch {
  // Helpers not yet exported — tests below self-skip.
}

const PAPERS = [
  { citekey: "smith2017PhaseField", year: 2017, venue: "JMPS", card_state: "cached", paper_type: "research", collections: [] },
  { citekey: "DUBOIS2016Review", year: 2016, venue: "Prog. Mat. Sci.", card_state: "no_pdf", paper_type: "review", collections: [] },
  { citekey: "miller2020SurveyLME", year: 2020, venue: "Corros.", card_state: "cached", paper_type: "survey", collections: [] },
  { citekey: "chen2022MetaInterfaces", year: 2022, venue: "Nat. Mat.", card_state: "cached", paper_type: "meta-analysis", collections: [] },
  { citekey: "kim2024Tutorial", year: 2024, venue: "Nat. Rev.", card_state: "cached", paper_type: "tutorial", collections: [] },
];

// ---------------------------------------------------------------------------
// filterPapersByCitekey
// ---------------------------------------------------------------------------

test("filterPapersByCitekey returns the original array when query is empty", (t) => {
  if (!filterPapersByCitekey) {
    t.skip("filterPapersByCitekey not yet exported");
    return;
  }
  const result = filterPapersByCitekey(PAPERS, "");
  assert.equal(result.length, PAPERS.length);
  for (let i = 0; i < PAPERS.length; i++) {
    assert.equal(result[i].citekey, PAPERS[i].citekey);
  }
});

test("filterPapersByCitekey returns the original array when query is whitespace", (t) => {
  if (!filterPapersByCitekey) {
    t.skip("filterPapersByCitekey not yet exported");
    return;
  }
  const result = filterPapersByCitekey(PAPERS, "   ");
  assert.equal(result.length, PAPERS.length);
});

test("filterPapersByCitekey matches substring of citekey case-insensitively", (t) => {
  if (!filterPapersByCitekey) {
    t.skip("filterPapersByCitekey not yet exported");
    return;
  }
  const result = filterPapersByCitekey(PAPERS, "DUBOIS");
  assert.equal(result.length, 1);
  assert.equal(result[0].citekey, "DUBOIS2016Review");

  // Lowercase query against mixed-case citekeys still matches.
  const lower = filterPapersByCitekey(PAPERS, "dubois");
  assert.equal(lower.length, 1);
  assert.equal(lower[0].citekey, "DUBOIS2016Review");
});

test("filterPapersByCitekey returns empty list when no citekey matches", (t) => {
  if (!filterPapersByCitekey) {
    t.skip("filterPapersByCitekey not yet exported");
    return;
  }
  const result = filterPapersByCitekey(PAPERS, "noSuchPaper");
  assert.deepEqual(result, []);
});

test("filterPapersByCitekey does not mutate the input array", (t) => {
  if (!filterPapersByCitekey) {
    t.skip("filterPapersByCitekey not yet exported");
    return;
  }
  const before = PAPERS.slice();
  filterPapersByCitekey(PAPERS, "smith");
  assert.deepEqual(
    PAPERS.map((p) => p.citekey),
    before.map((p) => p.citekey)
  );
});

// ---------------------------------------------------------------------------
// typePillVariant
// ---------------------------------------------------------------------------

test("typePillVariant maps research → research", (t) => {
  if (!typePillVariant) {
    t.skip("typePillVariant not yet exported");
    return;
  }
  assert.equal(typePillVariant("research"), "research");
});

test("typePillVariant maps review → review", (t) => {
  if (!typePillVariant) {
    t.skip("typePillVariant not yet exported");
    return;
  }
  assert.equal(typePillVariant("review"), "review");
});

test("typePillVariant maps survey → survey", (t) => {
  if (!typePillVariant) {
    t.skip("typePillVariant not yet exported");
    return;
  }
  assert.equal(typePillVariant("survey"), "survey");
});

test("typePillVariant collapses meta-analysis → meta", (t) => {
  if (!typePillVariant) {
    t.skip("typePillVariant not yet exported");
    return;
  }
  assert.equal(typePillVariant("meta-analysis"), "meta");
});

test("typePillVariant maps tutorial → meta (visual fallback for non-research, non-review/survey types)", (t) => {
  if (!typePillVariant) {
    t.skip("typePillVariant not yet exported");
    return;
  }
  // Tutorial is a non-research, non-review/survey type; sharing the meta pill
  // colour keeps the four-variant CSS palette stable and visually distinct
  // from research papers.
  assert.equal(typePillVariant("tutorial"), "meta");
});

test("typePillVariant falls back to research for undefined or empty", (t) => {
  if (!typePillVariant) {
    t.skip("typePillVariant not yet exported");
    return;
  }
  assert.equal(typePillVariant(undefined), "research");
  assert.equal(typePillVariant(""), "research");
});

test("typePillVariant falls back to research for unknown values", (t) => {
  if (!typePillVariant) {
    t.skip("typePillVariant not yet exported");
    return;
  }
  // Defensive: if the index ever ships a new paper_type value, the pill
  // never disappears; it just renders as the neutral research variant.
  assert.equal(typePillVariant("dataset"), "research");
});
