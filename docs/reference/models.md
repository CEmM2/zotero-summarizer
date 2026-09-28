# Data Models

All data models are defined in `src/zsum/models.py` using [Pydantic v2](https://docs.pydantic.dev/latest/).

## Item

A single Zotero library item (paper).

```python
class Item(BaseModel):
    citekey: str
    zotero_key: str
    library_id: int | None        # Zotero library ID (for cross-library dedup)
    item_id: int | None           # Zotero item ID
    title: str
    authors: list[str]
    year: int | None
    venue: str
    doi: str
    abstract: str
    url: str
    tags: list[str]
    pdf_path: Path | None
    paper_type: str               # "research", "review", "survey", etc.
```

**Properties:**

| Property | Type | Description |
|---|---|---|
| `has_pdf` | `bool` | `True` if `pdf_path` is set and the file exists |
| `is_review` | `bool` | `True` for review/survey/meta-analysis classifications |

## Collection

A Zotero collection (folder) with hierarchy and member papers.

```python
class Collection(BaseModel):
    key: str                      # Zotero collection key
    name: str                     # Display name
    parent_key: str | None        # Parent collection key
    path: str                     # Full path (e.g., "/Phase Field/Fracture")
    item_citekeys: list[str]      # Member paper citekeys
    child_keys: list[str]         # Child collection keys
```

## LibraryIndex

Unified index containing all items and collections.

```python
class LibraryIndex(BaseModel):
    items: dict[str, Item]               # citekey -> Item
    collections: dict[str, Collection]   # collection_key -> Collection
```

**Properties:**

| Property | Type | Description |
|---|---|---|
| `stats` | `dict` | Counts: `total_items`, `with_pdf`, `missing_pdf`, `total_collections` |

## PaperCard

Structured summary of a single paper, produced by the LLM.

```python
class PaperCard(BaseModel):
    citekey: str
    title: str
    authors: list[str]
    year: int | None
    venue: str
    doi: str
    problem: str                  # Research question or gap
    methods: list[str]            # Methodological approaches
    key_findings: list[str]       # Main results
    limitations: list[str]        # Acknowledged limitations
    keywords: list[str]           # Key terms
    text_quality: str             # "good", "degraded", or "no_pdf"
    paper_type: str               # "research", "review", etc.
```

**Class variable:**

- `LLM_CONTENT_FIELDS` — fields populated by the LLM that trigger warnings if empty: `problem`, `methods`, `key_findings`, `limitations`

## CardMeta

Provenance metadata stored in cached card JSON files (in the `_meta` block).

```python
class CardMeta(BaseModel):
    model: str              # LLM model name
    prompt_version: int     # Config prompt_version at generation time
    generated_at: str       # ISO 8601 timestamp
```

!!! note
    `CardMeta` is defined as a Pydantic model but is not instantiated at runtime. The `_meta` block is written as a raw dict by `cache.py:save_card()` and stripped when loading.

## CitationRecord

Citation count for a single paper.

```python
class CitationRecord(BaseModel):
    citekey: str
    citation_count: int | None
    source: str                 # "openalex" or "semantic_scholar"
    fetched_at: str             # ISO 8601 timestamp
    external_id: str            # Provider-specific ID
```

## StructureSuggestion

A single structural change proposed by the advisor.

```python
class StructureSuggestion(BaseModel):
    type: str                      # rename, split, merge, new, too-broad
    target: str | list[str]        # Collection(s) affected
    proposed: str | list[str]      # Proposed change
    rationale: str                 # Why this change is suggested
```

## StructureAdvice

Full advisory output from the restructure command.

```python
class StructureAdvice(BaseModel):
    overall_assessment: str
    suggestions: list[StructureSuggestion]
    proposed_hierarchy: dict
```

## TextQuality

Enum for PDF extraction quality flags.

```python
class TextQuality(StrEnum):
    GOOD = "good"
    DEGRADED = "degraded"
    NO_PDF = "no_pdf"
```

## ExtractionResult

Result of extracting text from a single PDF (defined in `extractor.py`).

```python
@dataclass
class ExtractionResult:
    citekey: str
    text: str
    page_count: int
    pages_used: list[int]
    quality: str              # "good", "degraded", or "no_pdf"
    warnings: list[str]
```

## Paper Types

Valid paper type values are defined as a `frozenset`:

```python
PAPER_TYPES = frozenset({"research", "review", "survey", "meta-analysis", "tutorial"})
```

The default is `"research"`. Classification is performed by the heuristic classifier at index time, with optional LLM override during card generation.
