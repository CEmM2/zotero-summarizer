import * as fs from "fs";
import * as path from "path";

export interface CollectionIndex {
  name: string;
  parent: string | null;
  path: string;
  item_count: number;
  digest_state: "ok" | "stale" | "missing";
  redigest_state: "ok" | "stale" | "missing";
}

export type PaperType = "research" | "review" | "survey" | "meta-analysis" | "tutorial";

export interface ItemIndex {
  citekey: string;
  year: number;
  venue: string;
  collections: string[];
  card_state: "cached" | "pending" | "degraded" | "no_pdf" | "fallback";
  paper_type?: PaperType | string;
  citation_count?: number | null;
  extraction_method?: string;
}

export const REVIEW_PAPER_TYPES: ReadonlySet<string> = new Set([
  "review",
  "survey",
  "meta-analysis",
]);

export function isReviewPaper(item: ItemIndex): boolean {
  return !!item.paper_type && REVIEW_PAPER_TYPES.has(item.paper_type);
}

export interface ZsumIndex {
  generated_at: string;
  collections: Record<string, CollectionIndex>;
  items: Record<string, ItemIndex>;
}

export interface LibraryStats {
  total_collections: number;
  total_papers: number;
  cards_cached: number;
  cards_pending: number;
  cards_degraded: number;
  cards_fallback: number;
  cards_no_pdf: number;
  digests_ok: number;
  digests_stale: number;
  digests_missing: number;
}

export interface IndexReadResult {
  index: ZsumIndex | null;
  kind: "ok" | "missing" | "parse" | "invalid" | "io";
  message?: string;
}

export async function readIndexDetailed(cacheDir: string): Promise<IndexReadResult> {
  const p = path.join(cacheDir, "index.json");
  try {
    const raw = await fs.promises.readFile(p, "utf8");
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || !parsed.collections || !parsed.items) {
      return {
        index: null,
        kind: "invalid",
        message: `index.json at ${p} is missing required keys (collections/items)`,
      };
    }
    return { index: parsed as ZsumIndex, kind: "ok" };
  } catch (e: any) {
    if (e?.code === "ENOENT") {
      return { index: null, kind: "missing", message: `index.json not found at ${p}` };
    }
    if (e instanceof SyntaxError) {
      return {
        index: null,
        kind: "parse",
        message: `index.json at ${p} is not valid JSON`,
      };
    }
    return {
      index: null,
      kind: "io",
      message: `unable to read index.json at ${p}: ${e?.message ?? e}`,
    };
  }
}

export async function readIndex(cacheDir: string): Promise<ZsumIndex | null> {
  const res = await readIndexDetailed(cacheDir);
  return res.index;
}

export function computeStats(index: ZsumIndex): LibraryStats {
  const s: LibraryStats = {
    total_collections: Object.keys(index.collections).length,
    total_papers: Object.keys(index.items).length,
    cards_cached: 0,
    cards_pending: 0,
    cards_degraded: 0,
    cards_fallback: 0,
    cards_no_pdf: 0,
    digests_ok: 0,
    digests_stale: 0,
    digests_missing: 0,
  };
  for (const it of Object.values(index.items)) {
    if (it.card_state === "cached") s.cards_cached++;
    else if (it.card_state === "pending") s.cards_pending++;
    else if (it.card_state === "degraded") s.cards_degraded++;
    else if (it.card_state === "fallback") s.cards_fallback++;
    else if (it.card_state === "no_pdf") s.cards_no_pdf++;
  }
  for (const c of Object.values(index.collections)) {
    if (c.digest_state === "ok") s.digests_ok++;
    else if (c.digest_state === "stale") s.digests_stale++;
    else s.digests_missing++;
  }
  return s;
}

export function getCollectionPapers(
  index: ZsumIndex,
  collectionKey: string
): ItemIndex[] {
  const items: ItemIndex[] = [];
  for (const it of Object.values(index.items)) {
    if (collectionKey === "root" || it.collections.includes(collectionKey)) {
      items.push(it);
    }
  }
  items.sort((a, b) => (b.year || 0) - (a.year || 0));
  return items;
}
