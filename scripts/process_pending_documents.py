#!/usr/bin/env python3
import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

load_dotenv(ROOT_DIR / ".env")

# Default to the isolated bespoke stack. These can still be overridden via the
# dedicated PROCESS_PENDING_DOCUMENTS_* environment variables.
os.environ["POSTGRES_URL"] = os.getenv(
    "PROCESS_PENDING_DOCUMENTS_POSTGRES_URL",
    "postgresql+asyncpg://user:password@localhost:55432/market_bespoke_db",
)
os.environ["MINIO_ENDPOINT"] = os.getenv(
    "PROCESS_PENDING_DOCUMENTS_MINIO_ENDPOINT",
    "localhost:19000",
)
os.environ["MINIO_ACCESS_KEY"] = os.getenv(
    "PROCESS_PENDING_DOCUMENTS_MINIO_ACCESS_KEY",
    "admin",
)
os.environ["MINIO_SECRET_KEY"] = os.getenv(
    "PROCESS_PENDING_DOCUMENTS_MINIO_SECRET_KEY",
    "password",
)
os.environ["MINIO_BUCKET_NAME"] = os.getenv(
    "PROCESS_PENDING_DOCUMENTS_MINIO_BUCKET_NAME",
    "market-maps-bespoke",
)

from sqlalchemy import func, select

from src.db.session import AsyncSessionLocal
from src.models.relational import PendingDocument, Site

RETRYABLE_STATUSES = ("pending", "failed", "rejected", "processing")
DEFAULT_STATUSES = ("pending",)
VALID_ACTIONS = ("extract_all", "extract_partial", "skip")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bulk-process pending large documents through the existing scrape/vector-storage path.",
    )
    parser.add_argument(
        "--site-id",
        help="Target site/pipeline ID. If omitted and exactly one site has matching pending docs, it is selected automatically.",
    )
    parser.add_argument(
        "--statuses",
        nargs="+",
        default=list(DEFAULT_STATUSES),
        help="Pending document statuses to include. Defaults to: pending",
    )
    parser.add_argument(
        "--action",
        choices=VALID_ACTIONS,
        default="extract_all",
        help="How to process each pending document. Defaults to extract_all.",
    )
    parser.add_argument(
        "--char-limit",
        type=int,
        help="Optional truncation length when using --action extract_partial.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional maximum number of pending documents to process.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="How many pending documents to process in parallel. Defaults to 1 for safety.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List matching pending documents without processing them.",
    )
    return parser.parse_args()


async def resolve_target_site(site_id: str | None, statuses: Sequence[str]) -> tuple[Site, int]:
    async with AsyncSessionLocal() as session:
        if site_id:
            result = await session.execute(select(Site).where(Site.id == site_id))
            site = result.scalars().first()
            if not site:
                raise SystemExit(f"Site not found: {site_id}")

            count_result = await session.execute(
                select(func.count(PendingDocument.id)).where(
                    PendingDocument.site_id == site.id,
                    PendingDocument.status.in_(list(statuses)),
                )
            )
            return site, int(count_result.scalar() or 0)

        result = await session.execute(
            select(
                Site,
                func.count(PendingDocument.id).label("pending_count"),
            )
            .join(PendingDocument, PendingDocument.site_id == Site.id)
            .where(PendingDocument.status.in_(list(statuses)))
            .group_by(Site.id)
            .order_by(func.count(PendingDocument.id).desc(), Site.created_at.asc())
        )
        candidates = result.all()

    if not candidates:
        raise SystemExit(
            f"No sites have pending documents in statuses: {', '.join(statuses)}"
        )

    if len(candidates) > 1:
        lines = [
            "Multiple sites have matching pending documents. Re-run with --site-id.",
            "",
        ]
        for site, count in candidates:
            lines.append(f"- {site.id} | {site.name} | {count} docs")
        raise SystemExit("\n".join(lines))

    site, count = candidates[0]
    return site, int(count or 0)


async def fetch_pending_documents(
    site_id: str,
    statuses: Sequence[str],
    limit: int | None,
) -> list[dict]:
    async with AsyncSessionLocal() as session:
        stmt = (
            select(PendingDocument)
            .where(
                PendingDocument.site_id == site_id,
                PendingDocument.status.in_(list(statuses)),
            )
            .order_by(PendingDocument.created_at.asc())
        )
        if limit:
            stmt = stmt.limit(limit)

        result = await session.execute(stmt)
        docs = result.scalars().all()

    return [
        {
            "id": str(doc.id),
            "url": doc.url,
            "status": doc.status,
            "estimated_size": doc.estimated_size,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
        }
        for doc in docs
    ]


async def update_pending_document_status(doc_id: str, status: str) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PendingDocument).where(PendingDocument.id == doc_id)
        )
        doc = result.scalars().first()
        if not doc:
            return
        doc.status = status
        await session.commit()


async def process_single_document(
    site_id: str,
    site_name: str,
    doc: dict,
    action: str,
    char_limit: int | None,
) -> tuple[str, int]:
    if action == "skip":
        await update_pending_document_status(doc["id"], "skipped")
        return "skipped", 0

    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError(
            "GEMINI_API_KEY must be set to process pending documents."
        )

    from src.agents.nodes import scrape_node, vector_storage_node
    from src.api.events import event_manager

    await event_manager.publish(
        site_id,
        {
            "type": "log",
            "message": f"[PendingBulk] Starting extraction for {doc['url']}",
        },
    )

    state = {
        "pipeline_id": site_id,
        "niche": site_name,
        "urls_to_scrape": [doc["url"]],
        "current_url": None,
        "raw_text": None,
    }

    try:
        state = await scrape_node(state)

        if not state.get("raw_text"):
            await update_pending_document_status(doc["id"], "failed")
            await event_manager.publish(
                site_id,
                {
                    "type": "log",
                    "message": f"[PendingBulk] Failed to extract text for {doc['url']}",
                },
            )
            return "failed", 0

        if action == "extract_partial" and char_limit:
            state["raw_text"] = state["raw_text"][:char_limit]
            await event_manager.publish(
                site_id,
                {
                    "type": "log",
                    "message": f"[PendingBulk] Truncated text to {char_limit} characters.",
                },
            )

        state["is_relevant"] = True
        state["relevance_reason"] = "Bulk pending document processing bypass"

        before_chunks = state.get("stored_chunks", 0)
        state = await vector_storage_node(state)
        stored_chunks = state.get("stored_chunks", 0) - before_chunks

        if stored_chunks <= 0:
            await update_pending_document_status(doc["id"], "failed")
            await event_manager.publish(
                site_id,
                {
                    "type": "log",
                    "message": f"[PendingBulk] Vector storage produced no chunks for {doc['url']}",
                },
            )
            return "failed", 0

        await update_pending_document_status(doc["id"], "processed")
        await event_manager.publish(
            site_id,
            {
                "type": "log",
                "message": f"[PendingBulk] Processed {doc['url']} into {stored_chunks} chunks.",
            },
        )
        return "processed", stored_chunks
    except Exception:
        await update_pending_document_status(doc["id"], "failed")
        raise


async def run(args: argparse.Namespace) -> None:
    statuses = tuple(dict.fromkeys(args.statuses))
    invalid_statuses = sorted(set(statuses) - set(RETRYABLE_STATUSES))
    if invalid_statuses:
        raise SystemExit(
            f"Unsupported statuses: {', '.join(invalid_statuses)}. "
            f"Allowed: {', '.join(RETRYABLE_STATUSES)}"
        )

    if args.action == "extract_partial" and not args.char_limit:
        raise SystemExit("--char-limit is required when using --action extract_partial")

    if args.concurrency < 1:
        raise SystemExit("--concurrency must be at least 1")

    site, total_matching = await resolve_target_site(args.site_id, statuses)
    docs = await fetch_pending_documents(str(site.id), statuses, args.limit)

    print(f"Site: {site.name}")
    print(f"Site ID: {site.id}")
    print(f"Matching pending documents: {total_matching}")
    print(f"Selected for this run: {len(docs)}")

    if not docs:
        return

    if args.list:
        print("")
        for index, doc in enumerate(docs, start=1):
            print(
                f"[{index}] {doc['id']} | {doc['status']} | {doc['estimated_size']} chars | {doc['url']}"
            )
        return

    semaphore = asyncio.Semaphore(args.concurrency)
    results = {
        "processed": 0,
        "failed": 0,
        "skipped": 0,
        "stored_chunks": 0,
    }

    async def worker(index: int, doc: dict) -> None:
        async with semaphore:
            await update_pending_document_status(doc["id"], "processing")
            try:
                status, stored_chunks = await process_single_document(
                    str(site.id),
                    site.name,
                    doc,
                    args.action,
                    args.char_limit,
                )
                results[status] += 1
                results["stored_chunks"] += stored_chunks
                print(
                    f"[{index}/{len(docs)}] {status.upper()} | +{stored_chunks} chunks | {doc['url']}"
                )
            except Exception as exc:
                results["failed"] += 1
                print(f"[{index}/{len(docs)}] FAILED | {doc['url']} | {exc}")

    await asyncio.gather(
        *(worker(index, doc) for index, doc in enumerate(docs, start=1))
    )

    print("")
    print("Summary")
    print(f"- Processed: {results['processed']}")
    print(f"- Failed: {results['failed']}")
    print(f"- Skipped: {results['skipped']}")
    print(f"- New chunks stored: {results['stored_chunks']}")


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
