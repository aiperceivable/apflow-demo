"""
CLI extension for user management and statistics
"""

import asyncio
import json
import os
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy.ext.asyncio import AsyncSession
from apflow_demo.services.user_service import user_tracking_service

# Initialize UI
console = Console()

# Create and register the command group using decorator
# This automatically registers with apflow CLI without entry points


class UsersApp(typer.Typer):
    """CLI extension for user management."""

    def __init__(self):
        super().__init__(help="Manage and analyze users")

        # Register commands as instance methods
        self.command()(self.stat)
        self.command()(self.list)

    def stat(
        self,
        period: str = typer.Argument(
            "all", help="Statistics period: all, day, week, month, year"
        ),
        output_format: str = typer.Option(
            "table", "--format", "-f", help="Output format: table, json"
        ),
    ):
        """
        Display user statistics for a given period
        
        Example: apflow users stat day
        """
        valid_periods = ["all", "day", "week", "month", "year"]
        if period not in valid_periods:
            console.print(f"[red]Error:[/red] Invalid period '{period}'. Valid options: {', '.join(valid_periods)}")
            raise typer.Exit(code=1)

        try:
            # Try to use API server if configured
            try:
                import httpx
            except ImportError:
                httpx = None
            
            api_server_url = os.getenv("APFLOW_DEMO_API_URL")
            auth_token = os.getenv("APFLOW_DEMO_ADMIN_TOKEN")
            
            if api_server_url and httpx:
                # Use API to query stats
                try:
                    url = f"{api_server_url}/api/users/stats"
                    params = {"period": period}
                    
                    headers = {}
                    if auth_token:
                        headers["Authorization"] = f"Bearer {auth_token}"
                    
                    response = httpx.get(url, params=params, headers=headers, timeout=10.0)
                    response.raise_for_status()
                    data = response.json()
                    
                    if data.get("success"):
                        stats = {k: v for k, v in data.items() if k != "success"}
                    else:
                        raise Exception(data.get("message", "API request failed"))
                        
                except Exception as api_error:
                    console.print(f"[yellow]Warning:[/yellow] Failed to query via API ({api_error}), falling back to direct database access")
                    stats = None
            else:
                if not api_server_url:
                    console.print(f"[dim]Note:[/dim] API server not configured, using direct database access")
                elif not httpx:
                    console.print(f"[dim]Note:[/dim] httpx not available, using direct database access")
                stats = None
            
            # Fallback to direct database access if API is not available
            if stats is None:
                async def _get_stats():
                    return await user_tracking_service.get_user_stats(period)
                stats = asyncio.run(_get_stats())
            
            if output_format == "json":
                console.print(json.dumps(stats, indent=2))
                return

            table = Table(title=f"User Statistics ({period})")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            
            table.add_row("Total Users", str(stats["total_users"]))
            table.add_row(f"Active Users ({period})", str(stats["active_users"]))
            table.add_row(f"New Users ({period})", str(stats["new_users"]))
            
            console.print(table)
            console.print(f"[dim]Generated at: {stats['timestamp']}[/dim]")
            
        except Exception as e:
            console.print(f"[red]Error fetching statistics:[/red] {str(e)}")
            raise typer.Exit(code=1)

    def list(
        self,
        limit: int = typer.Option(20, "--limit", "-l", help="Number of users to display"),
        status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
        output_format: str = typer.Option(
            "table", "--format", "-f", help="Output format: table, json"
        ),
        show_ua: bool = typer.Option(False, "--show-ua", help="Show User-Agent in table output")
    ):
        """
        List demo users (latest active first)
        """
        try:
            # Try to use API server if configured
            try:
                import httpx
            except ImportError:
                httpx = None
            
            api_server_url = os.getenv("APFLOW_DEMO_API_URL")
            auth_token = os.getenv("APFLOW_DEMO_ADMIN_TOKEN")
            
            if api_server_url and httpx:
                # Use API to query users
                try:
                    url = f"{api_server_url}/api/users/list"
                    params = {"limit": limit}
                    if status:
                        params["status"] = status
                    
                    headers = {}
                    if auth_token:
                        headers["Authorization"] = f"Bearer {auth_token}"
                    
                    response = httpx.get(url, params=params, headers=headers, timeout=10.0)
                    response.raise_for_status()
                    data = response.json()
                    
                    if data.get("success"):
                        users_data = data.get("users", [])
                    else:
                        raise Exception(data.get("message", "API request failed"))
                        
                except Exception as api_error:
                    console.print(f"[yellow]Warning:[/yellow] Failed to query via API ({api_error}), falling back to direct database access")
                    users_data = None
            else:
                if not api_server_url:
                    console.print(f"[dim]Note:[/dim] API server not configured, using direct database access")
                elif not httpx:
                    console.print(f"[dim]Note:[/dim] httpx not available, using direct database access")
                users_data = None
            
            # Fallback to direct database access if API is not available
            if users_data is None:
                from sqlalchemy import select
                from sqlalchemy.sql import desc
                from apflow.core.storage import create_pooled_session
                from apflow_demo.storage.models import DemoUser
                from sqlalchemy.ext.asyncio import AsyncSession

                async def _list_users_db():
                    async with create_pooled_session() as session:
                        stmt = select(DemoUser).order_by(desc(DemoUser.last_active_at)).limit(limit)
                        if status:
                            stmt = stmt.where(DemoUser.status == status)
                        
                        if isinstance(session, AsyncSession):
                            result = await session.execute(stmt)
                            return result.scalars().all()
                        else:
                            result = session.execute(stmt)
                            return result.scalars().all()

                users_db_objects = asyncio.run(_list_users_db())
                users_data = []
                for user in users_db_objects:
                    users_data.append({
                        "user_id": user.user_id,
                        "username": user.username,
                        "status": user.status,
                        "last_active_at": user.last_active_at.isoformat() if user.last_active_at else None,
                        "source": user.source,
                        "user_agent": user.user_agent,
                        "created_at": user.created_at.isoformat() if user.created_at else None,
                    })
            
            if not users_data:
                if output_format == "json":
                    console.print("[]")
                else:
                    console.print("No users found.")
                return

            if output_format == "json":
                console.print(json.dumps(users_data, indent=2))
                return

            table = Table(title=f"Latest Users (Top {limit})")
            table.add_column("User ID", style="dim")
            table.add_column("Username", style="cyan")
            table.add_column("Status", style="green")
            table.add_column("Last Active", style="magenta")
            table.add_column("Source", style="yellow")
            if show_ua:
                table.add_column("User-Agent", style="dim")
            
            for user in users_data:
                last_active = user.get("last_active_at")
                if last_active:
                    from datetime import datetime
                    dt = datetime.fromisoformat(last_active.replace("Z", "+00:00"))
                    last_active_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    last_active_str = "N/A"
                
                table.add_row(
                    user["user_id"][:20] + "..." if len(user["user_id"]) > 20 else user["user_id"],
                    user["username"],
                    user["status"],
                    last_active_str,
                    user.get("source") or "unknown"
                )
                if show_ua:
                    ua = user.get("user_agent") or "N/A"
                    table.add_row("", "", "", "", "", ua)
            
            console.print(table)
            
        except Exception as e:
            console.print(f"[red]Error listing users:[/red] {str(e)}")
            raise typer.Exit(code=1)


# Entry point function for apflow.cli_plugins
def users_app() -> UsersApp:
    """Entry point for users CLI extension"""
    return UsersApp()
