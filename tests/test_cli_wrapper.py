import importlib


def test_cli_wrapper_imports_and_calls_app(monkeypatch):
    """Ensure the cli wrapper imports the demo package and delegates to framework app.

    This test patches `apflow.cli.main` with a fake callable to
    observe whether the wrapper calls it. It also asserts that the global
    task model class is set to our `CustomTaskModel` after running the wrapper.
    """
    # Patch the framework CLI app callable before importing the wrapper
    cli_main = importlib.import_module("apflow.cli")
    import click
    monkeypatch.setattr(cli_main, "cli", lambda: click.Group())

    called = {"ok": False}

    def fake_app():
        called["ok"] = True

    monkeypatch.setattr(cli_main, "main", fake_app)

    # Ensure demo package is reloaded so registration runs in this process
    importlib.reload(importlib.import_module("apflow_demo"))

    # Import the wrapper and call main() which should import demo and call fake_app
    cli_wrapper = importlib.import_module("apflow_demo.cli")
    importlib.reload(cli_wrapper)

    # Call the wrapper entrypoint
    cli_wrapper.main()

    assert called["ok"] is True

    # Verify registry now points to our CustomTaskModel
    from apflow.core.config import get_task_model_class
    from apflow_demo.storage.models import CustomTaskModel

    assert get_task_model_class() is CustomTaskModel
