"""Retention windows and prune-job for ops.* telemetry tables.

Active tables (pruned by the scheduler-driven ``OpsRetentionJob``):

* ``ingest_runs`` — 30d (per-cycle execution telemetry, ~130k/mo)
* ``connector_status_history`` — 180d (~87k/mo)
* ``source_health_events`` — 180d (only rows with errors, 0..3k/mo)

Reserved windows (commented out, not actively pruned — kept for
future one-line activation):

* ``market_bars`` — 730d (product data; hypertable solution deferred to C0)
* ``orderbook_summaries`` — 30d (dormant table)
* ``market_features`` — 180d (synthetic, MVP-polish out of scope)
* ``news_items`` — 180d (context data; still synthetic)
* ``sentiment_snapshots`` — 180d (context data; still synthetic)
"""

RETENTION_WINDOWS_DAYS = {
    "ingest_runs": 30,
    "connector_status_history": 180,
    "source_health_events": 180,
    "ai_agent_runs": 180,
}


def retention_cutoff_days(table_name: str) -> int:
    return RETENTION_WINDOWS_DAYS[table_name]
