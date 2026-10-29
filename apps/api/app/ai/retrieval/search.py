"""pgvector retrieval. Always tenant-filtered, always parameterized."""
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redaction import redact_text


def _vec(values: list[float]) -> str:
    if not 1 <= len(values) <= 4096:
        raise ValueError("bad embedding size")
    return "[" + ",".join(repr(float(v)) for v in values) + "]"  # float() rejects non-numerics


async def store_chunk(db: AsyncSession, org_id: UUID, source: str, content: str, embedding: list[float]) -> None:
    await db.execute(
        text("INSERT INTO embeddings (org_id, source, content, embedding) VALUES (:org, :src, :c, CAST(:e AS vector))"),
        {"org": org_id, "src": source[:100], "c": redact_text(content)[:8000], "e": _vec(embedding)},  # redact BEFORE persisting
    )


async def similar_chunks(db: AsyncSession, org_id: UUID, embedding: list[float], k: int = 5) -> list[str]:
    k = max(1, min(k, 20))
    rows = await db.execute(
        text("SELECT content FROM embeddings WHERE org_id = :org ORDER BY embedding <=> CAST(:q AS vector) LIMIT :k"),
        {"org": org_id, "q": _vec(embedding), "k": k},
    )
    return [r[0] for r in rows]
