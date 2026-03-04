"""
RAG document ingestion pipeline.

Supports txt, pdf, and markdown documents.
Splits into chunks and stores in Qdrant with metadata.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import structlog
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import models

from app.config import get_settings
from app.llm.router import get_llm_router
from app.rag.engine import COLLECTIONS, get_rag_engine

log = structlog.get_logger(__name__)


def _load_text(file_path: Path) -> str:
    """Load text from a file."""
    return file_path.read_text(encoding="utf-8")


def _load_pdf(file_path: Path) -> str:
    """Load text from a PDF file."""
    from pypdf import PdfReader
    reader = PdfReader(str(file_path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)


LOADERS = {
    ".txt": _load_text,
    ".md": _load_text,
    ".pdf": _load_pdf,
}


async def ingest_file(
    file_path: Path,
    collection_key: str,
    category: str = "",
    subcategory: str = "",
) -> int:
    """
    Ingest a single file into a Qdrant collection.

    Args:
        file_path: Path to the document
        collection_key: One of 'health', 'medication', 'tcm'
        category: Document category for metadata
        subcategory: Sub-category for metadata

    Returns:
        Number of chunks ingested
    """
    settings = get_settings()
    suffix = file_path.suffix.lower()

    if suffix not in LOADERS:
        raise ValueError(f"Unsupported file type: {suffix}. Supported: {list(LOADERS.keys())}")

    if collection_key not in COLLECTIONS:
        raise ValueError(f"Unknown collection: {collection_key}. Valid: {list(COLLECTIONS.keys())}")

    # Load document
    text = LOADERS[suffix](file_path)
    if not text.strip():
        log.warning("empty_document", path=str(file_path))
        return 0

    # Split into chunks
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.rag_chunk_size,
        chunk_overlap=settings.rag_chunk_overlap,
        separators=["\n\n", "\n", "。", "；", "，", " ", ""],
    )
    chunks = splitter.split_text(text)

    if not chunks:
        return 0

    # Generate embeddings
    router = get_llm_router()
    embeddings = await router.embed(chunks)

    # Prepare Qdrant points
    collection_name = COLLECTIONS[collection_key]
    engine = get_rag_engine()

    points = []
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{file_path}:{i}"))
        points.append(
            models.PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    "content": chunk,
                    "source": file_path.name,
                    "category": category,
                    "subcategory": subcategory,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "content_hash": hashlib.md5(chunk.encode()).hexdigest(),
                },
            )
        )

    # Upsert to Qdrant
    await engine.client.upsert(
        collection_name=collection_name,
        points=points,
    )

    log.info(
        "document_ingested",
        file=file_path.name,
        collection=collection_name,
        chunks=len(chunks),
    )
    return len(chunks)


async def ingest_directory(
    dir_path: Path,
    collection_key: str,
    category: str = "",
) -> dict:
    """Ingest all supported files in a directory."""
    results = {"total_files": 0, "total_chunks": 0, "errors": []}

    if not dir_path.is_dir():
        raise ValueError(f"Not a directory: {dir_path}")

    for file_path in sorted(dir_path.iterdir()):
        if file_path.suffix.lower() in LOADERS:
            try:
                n = await ingest_file(
                    file_path, collection_key,
                    category=category,
                    subcategory=file_path.stem,
                )
                results["total_files"] += 1
                results["total_chunks"] += n
            except Exception as e:
                results["errors"].append({"file": file_path.name, "error": str(e)})
                log.error("ingest_file_error", file=file_path.name, error=str(e))

    return results
