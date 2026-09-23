from tools.ci_stability_smoke import (
    smoke_action_aggregates,
    smoke_backup,
    smoke_bounded_executor,
    smoke_catalog_cache,
    smoke_delivery_table,
    smoke_event_bus,
    smoke_performance_indexes,
    smoke_scan_aggregates,
)


def test_reliability_regressions():
    """Keep the audit's reliability guarantees under a normal pytest runner."""
    smoke_backup()
    smoke_delivery_table()
    smoke_scan_aggregates()
    smoke_action_aggregates()
    smoke_performance_indexes()
    smoke_catalog_cache()
    smoke_event_bus()
    smoke_bounded_executor()
