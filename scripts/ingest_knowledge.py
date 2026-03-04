#!/usr/bin/env python3
"""
Ingest knowledge base documents into Qdrant vector store.

Usage:
    python scripts/ingest_knowledge.py [--collection health|medication|tcm] [--dir path]
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.rag.engine import get_rag_engine
from app.rag.ingest import ingest_directory


KNOWLEDGE_DIR = Path(__file__).parent.parent / "data" / "knowledge"

COLLECTION_MAP = {
    "health": KNOWLEDGE_DIR / "health",
    "medication": KNOWLEDGE_DIR / "medication",
    "tcm": KNOWLEDGE_DIR / "tcm",
}


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Ingest knowledge into Qdrant")
    parser.add_argument("--collection", choices=list(COLLECTION_MAP.keys()), default=None)
    parser.add_argument("--dir", type=str, default=None)
    args = parser.parse_args()

    # Ensure collections exist
    rag = get_rag_engine()
    await rag.ensure_collections()

    if args.collection:
        collections = {args.collection: args.dir or str(COLLECTION_MAP[args.collection])}
    else:
        collections = {k: str(v) for k, v in COLLECTION_MAP.items()}

    for coll_key, dir_path in collections.items():
        p = Path(dir_path)
        if not p.is_dir():
            print(f"⚠️ Directory not found: {p}, skipping {coll_key}")
            continue

        print(f"📚 Ingesting {coll_key} from {p}...")
        result = await ingest_directory(p, coll_key, category=coll_key)
        print(f"   ✅ Files: {result['total_files']}, Chunks: {result['total_chunks']}")
        if result["errors"]:
            for err in result["errors"]:
                print(f"   ❌ {err['file']}: {err['error']}")

    await rag.close()
    print("\n🎉 Ingestion complete!")


if __name__ == "__main__":
    asyncio.run(main())
