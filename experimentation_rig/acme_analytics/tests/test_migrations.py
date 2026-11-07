from src import migrate


def test_baseline_migrations_applied(conn):
    applied = set(migrate.applied_versions(conn))
    assert {"001", "002", "003", "004"} <= applied


def test_every_migration_has_both_directions():
    for version, parts in migrate.discover().items():
        assert "up" in parts, version
        assert "down" in parts, version


def test_reporting_views_exist(conn):
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'view'")}
    assert {"v_orders_clean", "v_monthly_revenue"} <= names
