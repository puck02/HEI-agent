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

from app.config import get_settings
from app.rag.engine import get_rag_engine, COLLECTIONS


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

    settings = get_settings()
    engine = get_rag_engine()
    
    print(f"🚀 RAG Engine: {engine.__class__.__name__}")
    print(f"📁 Knowledge dir: {KNOWLEDGE_DIR}")
    print()

    # Ensure collections exist
    await engine.ensure_collections()

    if args.collection:
        collections = {args.collection: args.dir or str(COLLECTION_MAP[args.collection])}
    else:
        collections = {k: str(v) for k, v in COLLECTION_MAP.items()}

    total_files = 0
    total_chunks = 0
    total_errors = 0

    for coll_key, dir_path in collections.items():
        p = Path(dir_path)
        if not p.is_dir():
            print(f"⚠️  Directory not found: {p}, skipping {coll_key}")
            continue

        print(f"📚 Ingesting {coll_key} from {p}...")
        
        for file_path in sorted(p.iterdir()):
            suffix = file_path.suffix.lower()
            if suffix not in {".txt", ".md", ".pdf"}:
                continue
            
            try:
                n = await engine.ingest_file(
                    file_path, coll_key,
                    category=coll_key,
                    subcategory=file_path.stem,
                )
                total_files += 1
                total_chunks += n
                print(f"   ✅ {file_path.name}: {n} chunks")
            except Exception as e:
                total_errors += 1
                print(f"   ❌ {file_path.name}: {e}")

    await engine.close()
    
    print()
    print(f"🎉 Ingestion complete!")
    print(f"   📄 Files: {total_files}")
    print(f"   🧩 Chunks: {total_chunks}")
    if total_errors:
        print(f"   ❌ Errors: {total_errors}")


if __name__ == "__main__":
    asyncio.run(main())
