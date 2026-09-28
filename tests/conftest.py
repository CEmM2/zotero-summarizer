"""Shared test fixtures for zsum tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    (tmp_path / "cache" / "cards").mkdir(parents=True)
    (tmp_path / "cache" / "digests").mkdir(parents=True)
    (tmp_path / "vault").mkdir()
    return tmp_path


@pytest.fixture
def sample_bbt_json(tmp_path: Path) -> Path:
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()

    items = [
        _make_bbt_item(
            key="AAAA1111",
            item_id=101,
            citekey="smith2017PhaseField",
            title="Phase Field Modeling of Crack Propagation",
            authors=[("John", "Smith"), ("Alice", "Doe")],
            year="2017-06-15",
            venue="Journal of the Mechanics and Physics of Solids",
            doi="10.1016/j.jmps.2017.01.001",
            abstract="We present a phase field model for crack propagation.",
            pdf_path=str(pdf_dir / "Smith_2017_Phase Field Modeling.pdf"),
            tags=["phase-field", "fracture", "FEM"],
        ),
        _make_bbt_item(
            key="BBBB2222",
            item_id=102,
            citekey="zhao2020CrackProp",
            title="Dynamic Crack Propagation in Brittle Materials",
            authors=[("Wei", "Zhao")],
            year="2020-03-01",
            venue="Engineering Fracture Mechanics",
            doi="10.1016/j.engfracmech.2020.02.005",
            abstract="Dynamic fracture in brittle materials is studied.",
            pdf_path=str(pdf_dir / "Zhao_2020_Dynamic Crack.pdf"),
            tags=["dynamic fracture", "brittle"],
        ),
        _make_bbt_item(
            key="CCCC3333",
            item_id=103,
            citekey="jones2019NoPdf",
            title="A Paper Without a PDF",
            authors=[("Bob", "Jones")],
            year="2019",
            venue="Some Journal",
            doi="",
            abstract="This paper has no attachment.",
            pdf_path=None,
            tags=[],
        ),
    ]

    for item in items:
        for att in item.get("attachments", []):
            p = Path(att["path"])
            p.write_bytes(b"%PDF-1.4 fake pdf content " * 100)

    data = {
        "config": {
            "id": "test-library",
            "preferences": {"baseAttachmentPath": str(pdf_dir)},
        },
        "items": items,
    }

    bbt_path = tmp_path / "zot.json"
    with open(bbt_path, "w") as f:
        json.dump(data, f, indent=2)
    return bbt_path


@pytest.fixture
def sample_zotero_sqlite(tmp_path: Path) -> Path:
    db_path = tmp_path / "zotero.sqlite"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE collections (
            collectionID INTEGER PRIMARY KEY,
            collectionName TEXT,
            parentCollectionID INTEGER,
            key TEXT
        );
        CREATE TABLE collectionItems (
            collectionID INTEGER,
            itemID INTEGER
        );
        INSERT INTO collections VALUES (1, 'Phase Field Modeling', NULL, 'COL001');
        INSERT INTO collections VALUES (2, 'Bismuth-Copper', 1, 'COL002');
        INSERT INTO collectionItems VALUES (1, 101);
        INSERT INTO collectionItems VALUES (1, 102);
        INSERT INTO collectionItems VALUES (2, 101);
        INSERT INTO collectionItems VALUES (1, 103);
    """)
    conn.commit()
    conn.close()
    return db_path


def _make_bbt_item(
    *,
    key,
    item_id,
    citekey,
    title,
    authors,
    year,
    venue,
    doi,
    abstract,
    pdf_path,
    tags,
    library_id=None,
):
    item = {
        "key": key,
        "itemKey": key,
        "itemID": item_id,
        "itemType": "journalArticle",
        "citationKey": citekey,
        "title": title,
        "date": year,
        "publicationTitle": venue,
        "DOI": doi,
        "abstractNote": abstract,
        "url": "",
        "creators": [
            {"firstName": first, "lastName": last, "creatorType": "author"}
            for first, last in authors
        ],
        "tags": [{"tag": t, "type": 1} for t in tags],
        "attachments": [],
    }
    if library_id is not None:
        item["libraryID"] = library_id
    if pdf_path:
        item["attachments"].append(
            {
                "itemType": "attachment",
                "title": Path(pdf_path).name,
                "path": pdf_path,
                "tags": [],
            }
        )
    return item


@pytest.fixture
def real_pdf(tmp_path: Path) -> Path:
    """Create a minimal real PDF with extractable text using PyMuPDF."""
    fitz = pytest.importorskip("fitz")

    pdf_path = tmp_path / "real_paper.pdf"
    doc = fitz.open()

    for text in [
        "Introduction\n\nThis paper presents a novel phase field model for crack propagation "
        "in brittle materials. We develop a variational formulation that couples the displacement "
        "field with a damage order parameter. The phase field method has emerged as a powerful "
        "tool for modeling fracture due to its ability to handle complex crack topologies without "
        "explicit tracking of crack surfaces. Our approach builds on the Francfort-Marigo "
        "variational framework and extends it to handle dynamic loading conditions.",
        "Methods\n\nThe phase field approach regularizes sharp crack discontinuities using a "
        "diffuse damage variable. We implement the model using finite element discretization "
        "with adaptive mesh refinement. The governing equations are solved using a staggered "
        "scheme that alternates between the displacement and phase field equations. We validate "
        "our implementation against benchmark problems including the single edge notch tension "
        "and shear tests. The mesh refinement strategy ensures adequate resolution of the "
        "regularized crack region while keeping computational cost manageable.",
        "Conclusions\n\nThe proposed model accurately captures crack nucleation and propagation "
        "in brittle materials. Fracture toughness predictions agree within 5% of experimental "
        "measurements. The adaptive mesh refinement reduces computational cost by an order of "
        "magnitude compared to uniform fine meshes. Future work will extend the model to "
        "ductile fracture and multi-physics coupling with thermal and chemical fields.",
    ]:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=11)

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path
