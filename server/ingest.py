"""Build the retrieval index from the guide PDFs in data/guides/.

Run:  python -m server.ingest
"""

from . import rag


def main() -> None:
    print("Building index from", rag.config.GUIDES_DIR)
    stats = rag.build_index()
    print(f"Indexed {stats['documents']} documents -> {stats['chunks']} chunks")
    for doc, n in sorted(stats["per_doc"].items()):
        print(f"  {n:5d}  {doc}")
    print("Saved to", rag.CHUNKS_PATH)


if __name__ == "__main__":
    main()
