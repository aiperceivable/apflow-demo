def test_demo_server_imports_with_installed_apflow():
    """The deployment entry point must import against the installed SDK."""
    from apflow_demo.api.server import create_demo_app

    assert callable(create_demo_app)


def test_server_starts_and_serves_agent_card(tmp_path, monkeypatch):
    from starlette.testclient import TestClient
    from apflow_demo.api.server import create_demo_app
    from apflow_demo.config.settings import settings
    from apflow_demo.services.user_service import user_tracking_service

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'demo.sqlite3'}")
    monkeypatch.setattr(settings, "apflow_jwt_secret_key", "test-secret-key-with-at-least-32-bytes")

    async def track(*args, **kwargs):
        pass

    monkeypatch.setattr(user_tracking_service, "track_user_activity", track)
    with TestClient(create_demo_app()) as client:
        login = client.get("/auth/auto-login")
        assert login.status_code == 200
        assert "authorization" in login.cookies
        card = client.get("/.well-known/agent-card.json")
        assert card.status_code == 200
        assert card.json()["skills"]
        request = {"jsonrpc": "2.0", "id": "1", "method": "tasks/get", "params": {"id": "missing"}}
        response = client.post("/", json=request)
        assert response.status_code != 401
        response = client.post("/", json=request, headers={"Authorization": "Bearer invalid"})
        assert response.status_code == 401
        response = client.post(
            "/",
            headers={"A2A-Version": "1.0"},
            json={
                "jsonrpc": "2.0", "id": "list-1", "method": "SendMessage",
                "params": {"message": {
                    "messageId": "message-1", "role": "ROLE_USER", "parts": [{"data": {}}],
                    "metadata": {"skillId": "apflow.task.list"},
                }},
            },
        )
        assert response.status_code == 200
        assert "error" not in response.json()
        assert "completed" in str(response.json()).lower()
        for path in ("/api/quota/status", "/api/demo/tasks/init-status", "/api/executors/metadata"):
            assert client.get(path).status_code == 404


def test_legacy_rate_setting_does_not_restrict_sdk_modules(tmp_path, monkeypatch):
    from starlette.testclient import TestClient
    from apflow_demo.api.server import create_demo_app
    from apflow_demo.config.settings import settings
    from apflow_demo.services.user_service import user_tracking_service

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'legacy.sqlite3'}")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setattr(settings, "apflow_jwt_secret_key", "test-secret-key-with-at-least-32-bytes")

    async def track(*args, **kwargs):
        pass

    monkeypatch.setattr(user_tracking_service, "track_user_activity", track)
    with TestClient(create_demo_app()) as client:
        client.get("/auth/auto-login")
        response = client.post("/", headers={"A2A-Version": "1.0"}, json={
            "jsonrpc": "2.0", "id": "submit-test", "method": "SendMessage",
            "params": {"message": {"messageId": "submit-test", "role": "ROLE_USER",
                      "parts": [{"data": {"task_id": "missing"}}],
                      "metadata": {"skillId": "apflow.task.submit"}}},
        })
        assert "not available with quota enforcement" not in response.text


def test_a2a_create_and_submit_task(tmp_path, monkeypatch):
    import asyncio
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session, sessionmaker
    from starlette.testclient import TestClient
    from apflow.core.execution.dispatch import TaskDispatcher
    from apflow.core.storage.sqlalchemy.models import TaskDispatch
    from apflow_demo.api.server import create_demo_app
    from apflow_demo.config.settings import settings
    from apflow_demo.services.user_service import user_tracking_service
    from apflow_demo.storage.models import CustomTaskModel
    from apflow_demo.utils.jwt_utils import get_user_id_from_token

    database_url = f"sqlite:///{tmp_path / 'workflow.sqlite3'}"
    monkeypatch.setattr(settings, "database_url", database_url)
    monkeypatch.setattr(settings, "apflow_jwt_secret_key", "test-secret-key-with-at-least-32-bytes")

    async def track(*args, **kwargs):
        pass

    monkeypatch.setattr(user_tracking_service, "track_user_activity", track)
    with TestClient(create_demo_app()) as client:
        login = client.get("/auth/auto-login")
        user_id = get_user_id_from_token(login.cookies["authorization"])

        def send(skill, data, ident):
            return client.post("/", headers={"A2A-Version": "1.0"}, json={
                "jsonrpc": "2.0", "id": ident, "method": "SendMessage",
                "params": {"message": {"messageId": ident, "role": "ROLE_USER",
                          "parts": [{"data": data}], "metadata": {"skillId": skill}}},
            })

        created = send("apflow.task.create", {
            "name": "compatibility test", "params": {"executor_id": "aggregate_results_executor"}
        }, "create")
        assert created.status_code == 200
        assert "completed" in created.text.lower(), created.text
        engine = create_engine(database_url)
        with Session(engine) as session:
            task = session.execute(select(CustomTaskModel).where(
                CustomTaskModel.user_id == user_id,
                CustomTaskModel.name == "compatibility test",
            )).scalar_one()
            task_id = task.id
        submitted = send("apflow.task.submit", {"task_id": task_id}, "submit")
        assert submitted.status_code == 200
        assert "completed" in submitted.text.lower(), submitted.text
        with Session(engine) as session:
            assert session.get(TaskDispatch, task_id).state == "accepted"
        asyncio.run(TaskDispatcher(sessionmaker(engine, expire_on_commit=False)).run_once())
        with Session(engine) as session:
            assert session.get(TaskDispatch, task_id).state == "finished"
            assert session.get(CustomTaskModel, task_id).status == "completed"
        engine.dispose()


def test_login_tracks_users_and_admin_routes_require_admin(tmp_path, monkeypatch):
    import jwt
    from apflow.core.storage.factory import reset_session_pool_manager
    from starlette.testclient import TestClient
    from apflow_demo.api.server import create_demo_app
    from apflow_demo.config.settings import settings

    database_url = f"sqlite:///{tmp_path / 'users.sqlite3'}"
    secret = "test-secret-key-with-at-least-32-bytes"
    reset_session_pool_manager()
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.delenv("APFLOW_DATABASE_URL", raising=False)
    monkeypatch.setenv("APFLOW_JWT_SECRET", secret)
    monkeypatch.setattr(settings, "database_url", database_url)
    monkeypatch.setattr(settings, "apflow_jwt_secret_key", secret)
    try:
        with TestClient(create_demo_app()) as client:
            assert client.get("/auth/auto-login").status_code == 200
            assert client.get("/api/users/stats").status_code == 401
            token = jwt.encode({"sub": "admin", "roles": ["admin"]}, secret, algorithm="HS256")
            response = client.get("/api/users/stats", headers={"Authorization": f"Bearer {token}"})
            assert response.status_code == 200
            assert response.json()["total_users"] >= 1
    finally:
        reset_session_pool_manager()


