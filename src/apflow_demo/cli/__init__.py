"""CLI entry point for the demo."""


def main() -> None:
    """Delegate to the apflow CLI after the demo model is registered."""
    import click
    from typer.main import get_command
    from apflow.cli import cli, main as apflow_main
    from apflow_demo.cli.users import users_app

    group = cli()
    group.add_command(get_command(users_app()), name="users")

    @click.command(name="serve")
    def serve() -> None:
        from apflow_demo.cli.serve import serve_app

        serve_app()

    group.add_command(serve)

    apflow_main()
