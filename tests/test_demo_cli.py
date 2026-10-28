from typer.testing import CliRunner


def test_users_help_works_through_apflow_cli():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-c", "from apflow_demo.cli import main; main()", "users", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "stat" in result.stdout


def test_users_cli_lists_commands():
    from apflow_demo.cli.users import users_app

    result = CliRunner().invoke(users_app(), ["--help"])
    assert result.exit_code == 0
    assert "stat" in result.stdout
    assert "list" in result.stdout


def test_demo_cli_registers_commands_with_apflow(monkeypatch):
    import click
    import apflow.cli
    from apflow_demo.cli import main

    group = click.Group()
    monkeypatch.setattr(apflow.cli, "cli", lambda: group)
    monkeypatch.setattr(apflow.cli, "main", lambda: None)
    main()
    assert {"users", "serve"} <= set(group.commands)


def test_users_stat_uses_local_database_when_api_is_not_configured(monkeypatch):
    from apflow_demo.cli.users import users_app, user_tracking_service

    async def stats(period):
        return {"total_users": 2, "active_users": 1, "new_users": 1, "timestamp": "now"}

    monkeypatch.setattr(user_tracking_service, "get_user_stats", stats)
    monkeypatch.delenv("APFLOW_DEMO_API_URL", raising=False)
    result = CliRunner().invoke(users_app(), ["stat", "day", "--format", "json"])
    assert result.exit_code == 0, result.stdout
    assert '"total_users": 2' in result.stdout
