"""Retrieval-Augmented Generation over the IB guides (local, no embeddings).

Embeddings are unavailable on the course Portkey key, so retrieval uses BM25 over
page-level chunks. Each chunk keeps its source document + page so answers can cite
"Document, p.N". Retrieved text is DATA, not instructions — callers wrap it accordingly
(see server/sanitize.py and the agent prompt builders).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path

from pypdf import PdfReader
from rank_bm25 import BM25Okapi

from . import config

CHUNKS_PATH = config.INDEX_DIR / "chunks.json"
_WORD = re.compile(r"[a-z0-9]+")

# Topic -> substrings of guide filenames, so Interview Practice / Knowledge can scope
# retrieval to the right material.
TOPIC_DOCS = {
    "accounting": ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "3 More-Advanced", "4 Three-Statement", "primer-accounting"],
    "valuation": ["6.1", "6.2", "6.3", "6.4", "7 Valuation", "primer-valuation"],
    "dcf": ["7 Valuation", "primer-valuation"],
    "ma": ["10.1", "10.2", "10.3", "10.4", "primer-ma-lbo-fig"],
    "lbo": ["12.1", "12.2", "12.3", "12.4", "primer-ma-lbo-fig"],
    "fig": ["FIG-Questions", "primer-ma-lbo-fig"],
    "debt_equity": ["14.1", "14.2", "14.3", "15 Debt", "primer-ma-lbo-fig"],
    "behavioral": ["400"],
    "deal": ["Santander-Webster"],
}


def doc_title(filename: str) -> str:
    """Human-friendly title for citations."""
    name = filename.replace("Quick-Reference-Guides_", "").rsplit(".", 1)[0]
    name = re.sub(r"^\d+(\.\d+)?\s*", "", name)          # drop leading section numbers
    name = name.replace("-", " ").replace("_", " ").strip()
    return name or filename


def _tokenize(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _chunk_page(text: str, size: int = 1100, overlap: int = 150) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) <= size:
        return [text] if text else []
    out, i = [], 0
    while i < len(text):
        out.append(text[i:i + size])
        i += size - overlap
    return out


@dataclass
class Chunk:
    id: int
    doc: str          # filename
    title: str        # friendly title
    page: int         # 1-indexed
    text: str


def _extract_pages(path: Path) -> list[str]:
    """Return a list of 'pages' (text blocks) for a supported file. PDFs page-split;
    DOCX/TXT/MD become a single block (page 1)."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        pages = []
        reader = PdfReader(str(path))
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001
                pages.append("")
        return pages
    if ext == ".docx":
        import docx  # python-docx
        d = docx.Document(str(path))
        return ["\n".join(p.text for p in d.paragraphs)]
    if ext in (".txt", ".md"):
        return [path.read_text(encoding="utf-8", errors="replace")]
    return []


def build_index() -> dict:
    """Extract, chunk, and persist guide + uploaded documents to data/index/chunks.json."""
    config.INDEX_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for ext in ("*.pdf", "*.md", "*.txt", "*.docx"):
        files += sorted(config.GUIDES_DIR.glob(ext))
    if config.UPLOADS_DIR.exists():
        for ext in ("*.pdf", "*.docx", "*.txt", "*.md"):
            files += sorted(config.UPLOADS_DIR.glob(ext))
    chunks: list[Chunk] = []
    per_doc = {}
    cid = 0
    for f in files:
        try:
            pages = _extract_pages(f)
        except Exception as e:  # noqa: BLE001
            print(f"  skip {f.name}: {type(e).__name__}")
            continue
        title = doc_title(f.name)
        n = 0
        for pageno, text in enumerate(pages, start=1):
            for piece in _chunk_page(text):
                if len(piece) < 40:
                    continue
                chunks.append(Chunk(cid, f.name, title, pageno, piece))
                cid += 1
                n += 1
        per_doc[f.name] = n
    CHUNKS_PATH.write_text(json.dumps([asdict(c) for c in chunks]))
    return {"documents": len(files), "chunks": len(chunks), "per_doc": per_doc}


class Retriever:
    """Loads the persisted chunks and serves BM25 retrieval with optional topic filter."""

    def __init__(self):
        self.chunks: list[dict] = []
        self.bm25: BM25Okapi | None = None
        self._loaded = False

    def load(self) -> None:
        if not CHUNKS_PATH.exists():
            raise RuntimeError("Index not built. Run: python -m server.ingest")
        self.chunks = json.loads(CHUNKS_PATH.read_text())
        self.bm25 = BM25Okapi([_tokenize(c["text"]) for c in self.chunks])
        self._loaded = True

    def ensure(self) -> None:
        if not self._loaded:
            self.load()

    @property
    def ready(self) -> bool:
        return CHUNKS_PATH.exists()

    def documents(self) -> list[dict]:
        self.ensure()
        seen = {}
        for c in self.chunks:
            seen.setdefault(c["doc"], c["title"])
        return [{"doc": d, "title": t} for d, t in sorted(seen.items())]

    def retrieve(self, query: str, k: int = 5, topic: str | None = None) -> list[dict]:
        self.ensure()
        if not query.strip():
            return []
        scores = self.bm25.get_scores(_tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        allow = None
        if topic and topic in TOPIC_DOCS:
            subs = TOPIC_DOCS[topic]
            allow = lambda doc: any(s in doc for s in subs)  # noqa: E731
        out = []
        for i in order:
            if scores[i] <= 0:
                break
            c = self.chunks[i]
            if allow and not allow(c["doc"]):
                continue
            out.append({
                "doc": c["doc"], "title": c["title"], "page": c["page"],
                "text": c["text"], "score": round(float(scores[i]), 3),
                "citation": f"{c['title']}, p.{c['page']}",
            })
            if len(out) >= k:
                break
        return out


retriever = Retriever()
