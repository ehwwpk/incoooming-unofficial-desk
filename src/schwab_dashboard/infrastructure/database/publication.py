from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from schwab_dashboard.infrastructure.database.tables.sync import SyncRunTable


def published_account_sync_run_ids(session: Session) -> tuple[str, ...] | None:
    """Return account-sync runs admitted by completed coordinated refreshes."""

    return published_child_sync_run_ids(
        session,
        source="schwab",
        match_position_count=True,
    )


def published_activity_sync_run_ids(session: Session) -> tuple[str, ...] | None:
    """Return activity-sync runs admitted by completed coordinated refreshes."""

    return published_child_sync_run_ids(
        session,
        source="schwab_activity",
        match_position_count=False,
    )


def published_child_sync_run_ids(
    session: Session,
    *,
    source: str,
    match_position_count: bool,
) -> tuple[str, ...] | None:
    """Return child runs that are safe to expose, in chronological order.

    ``None`` means the database predates coordinated full refreshes, so callers
    should retain the legacy rule of accepting any completed account sync. Once
    a full refresh has been attempted, pre-coordinator history and children of
    completed full refreshes may publish. A child inside a failed full refresh
    remains staged forever, even after a later refresh succeeds.
    """

    full_attempts = tuple(
        session.scalars(
            select(SyncRunTable)
            .where(SyncRunTable.source == "schwab_full")
            .order_by(SyncRunTable.started_at, SyncRunTable.id)
        )
    )
    if not full_attempts:
        return None

    first_full_started_at = full_attempts[0].started_at
    published = list(
        session.scalars(
            select(SyncRunTable.id)
            .where(
                SyncRunTable.source == source,
                SyncRunTable.status == "completed",
                SyncRunTable.completed_at < first_full_started_at,
            )
            .order_by(SyncRunTable.started_at, SyncRunTable.id)
        )
    )
    for full_run in full_attempts:
        if full_run.status != "completed":
            continue
        if full_run.completed_at is None:
            continue
        child_query = select(SyncRunTable.id).where(
            SyncRunTable.source == source,
            SyncRunTable.status == "completed",
            SyncRunTable.started_at >= full_run.started_at,
            SyncRunTable.completed_at <= full_run.completed_at,
            SyncRunTable.account_count == full_run.account_count,
        )
        if match_position_count:
            child_query = child_query.where(SyncRunTable.position_count == full_run.position_count)
        child_id = session.scalar(
            child_query.order_by(SyncRunTable.started_at.desc(), SyncRunTable.id.desc()).limit(1)
        )
        if child_id is not None and child_id not in published:
            published.append(child_id)
    return tuple(published)
