import pytest


@pytest.mark.asyncio
async def test_user_activity_and_statistics_use_configured_database(tmp_path, monkeypatch):
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    from apflow.core.storage.factory import reset_session_pool_manager
    from apflow_demo.services.user_service import UserTrackingService

    reset_session_pool_manager()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.sqlite3'}")
    monkeypatch.delenv("APFLOW_DATABASE_URL", raising=False)
    alters = []

    def before_execute(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("ALTER TABLE demo_users ADD COLUMN user_agent"):
            alters.append(statement)

    event.listen(Engine, "before_cursor_execute", before_execute)
    try:
        service = UserTrackingService()
        await service.track_user_activity("alice", user_agent="Firefox/123")
        await service.track_user_activity("alice", user_agent="Firefox/124")
        stats = await service.get_user_stats("all")
        assert stats["total_users"] == 1
        assert stats["active_users"] == 1
        assert not alters
    finally:
        event.remove(Engine, "before_cursor_execute", before_execute)
        reset_session_pool_manager()
