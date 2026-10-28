"""
Service for tracking user activity and managing demo users
"""

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy import select, func, text, inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from apflow.core.storage import create_pooled_session
from apflow_demo.storage.models import DemoUser, Base

logger = logging.getLogger(__name__)


class UserTrackingService:
    """Service for managing demo users and tracking their activity"""

    async def ensure_tables_exist(self):
        """Ensure that demo_users table exists in the database"""
        async with create_pooled_session() as session:
            # We use the underlying engine to create tables
            # This is a bit hacky but works for demo/embedded DB
            engine = session.bind
            
            # Helper to run sync metadata creation
            def _create_all(conn):
                Base.metadata.create_all(conn)
                # Avoid a failed DDL statement aborting PostgreSQL's transaction.
                columns = {column["name"] for column in inspect(conn).get_columns("demo_users")}
                if "user_agent" not in columns:
                    conn.execute(text("ALTER TABLE demo_users ADD COLUMN user_agent VARCHAR"))
                    logger.info("Added user_agent column to demo_users table")

            if isinstance(session, AsyncSession):
                async with engine.begin() as conn:
                    await conn.run_sync(_create_all)
            else:
                # Sync engine (like DuckDB)
                with engine.begin() as conn:
                    _create_all(conn)
            
            logger.info("Checked/Created demo tables")
    async def _generate_username_from_ua(self, user_id: str, user_agent: Optional[str] = None) -> str:
        if not user_id:
            return "Guest_Unknown"
            
        if not user_agent:
            # Fallback to simple hash-based name
            # Strip common prefixes to get a cleaner suffix
            user_id_str = str(user_id)
            clean_id = user_id_str.replace("demo_user_", "").replace("user_", "")
            return f"Guest_{clean_id[:8]}"
            
        # Common Browser patterns (Order: specialized before generic)
        browser_map = {
            r"Edg/|Edge/": "Edge",
            r"Chrome/": "Chrome",
            r"Firefox/": "Firefox",
            r"Safari/": "Safari",
            r"PostmanRuntime/": "Postman"
        }
        
        # Common OS patterns
        os_map = {
            r"iPhone|iPad|iOS": "iOS",
            r"Android": "Android",
            r"Windows": "Win",
            r"Macintosh|Mac OS X": "Mac",
            r"Linux": "Linux"
        }
        
        detected_browser = ""
        for pattern, label in browser_map.items():
            if re.search(pattern, user_agent, re.I):
                detected_browser = f"_{label}"
                break
                
        detected_os = "Guest"
        for pattern, label in os_map.items():
            if re.search(pattern, user_agent, re.I):
                detected_os = label
                break
        
        # Strip common prefixes for the suffix
        user_id_str = str(user_id)
        clean_id = user_id_str.replace("demo_user_", "").replace("user_", "")
        suffix = clean_id[:8]
        
        return f"{detected_os}{detected_browser}_{suffix}"

    async def track_user_activity(
        self, 
        user_id: str, 
        source: Optional[str] = None,
        username_hint: Optional[str] = None,
        user_agent: Optional[str] = None,
        created_at: Optional[datetime] = None
    ) -> DemoUser:
        if not user_id:
            logger.warning("track_user_activity called with empty user_id, skipping")
            return None

        # Ensure tables exist first
        try:
            await self.ensure_tables_exist()
        except Exception as e:
            logger.error(f"Failed to ensure tables exist: {e}")

        async with create_pooled_session() as session:
            try:
                # Check if user exists
                stmt = select(DemoUser).where(DemoUser.user_id == user_id)
                if isinstance(session, AsyncSession):
                    result = await session.execute(stmt)
                    user = result.scalar_one_or_none()
                else:
                    result = session.execute(stmt)
                    user = result.scalar_one_or_none()

                now = datetime.now(timezone.utc)

                if not user:
                    # Create new user
                    username = username_hint or await self._generate_username_from_ua(user_id, user_agent)
                    
                    user_data = {
                        "user_id": user_id,
                        "username": username,
                        "source": source,
                        "last_active_at": now,
                        "status": "active",
                        "user_agent": user_agent,
                    }
                    if created_at:
                        user_data["created_at"] = created_at
                        
                    user = DemoUser(**user_data)
                    session.add(user)
                    logger.info(f"Created new demo user: {user_id} ({username})")
                    # Try to commit - may fail due to concurrent insertion of same user_id
                    if isinstance(session, AsyncSession):
                        await session.commit()
                    else:
                        session.commit()
                else:
                    # Update activity status
                    user.last_active_at = now
                    if source:
                        user.source = source
                    if user_agent:
                        user_agent_short = user_agent[:50] + "..." if len(user_agent) > 50 else user_agent
                        user.user_agent = user_agent
                        logger.debug(f"Updated user agent for {user_id}: {user_agent_short}")
                    
                    logger.debug(f"Updated activity for user: {user_id}")
                    if isinstance(session, AsyncSession):
                        await session.commit()
                    else:
                        session.commit()
                
                return user
            except Exception as e:
                # Handle race conditions (IntegrityError) during concurrent new user creation
                from sqlalchemy.exc import IntegrityError
                if isinstance(e, IntegrityError) or "UniqueViolationError" in str(e):
                    logger.info(f"User {user_id} created concurrently, retrying update")
                    if isinstance(session, AsyncSession):
                        await session.rollback()
                    else:
                        session.rollback()
                    # Re-run after rollback to update existing record
                    return await self.track_user_activity(user_id, source, username_hint, user_agent)
                else:
                    logger.error(f"Unexpected error in track_user_activity: {e}", exc_info=True)
                    if isinstance(session, AsyncSession):
                        await session.rollback()
                    else:
                        session.rollback()
                    raise

    async def get_user_stats(self, period: str = "all") -> Dict[str, Any]:
        """
        Get user statistics for different time periods
        
        Args:
            period: all, day, week, month, year
            
        Returns:
            Dictionary with statistics:
            {
                "total_users": int,
                "active_users": int,
                "period": str,
                "new_users": int
            }
        """
        async with create_pooled_session() as session:
            # Total users count
            total_stmt = select(func.count(DemoUser.user_id))
            if isinstance(session, AsyncSession):
                total_result = await session.execute(total_stmt)
            else:
                total_result = session.execute(total_stmt)
            total_users = total_result.scalar() or 0

            # Time filtering
            now = datetime.now(timezone.utc)
            since = None
            
            if period == "day":
                since = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif period == "week":
                since = now - timedelta(days=7)
            elif period == "month":
                since = now - timedelta(days=30)
            elif period == "year":
                since = now - timedelta(days=365)

            # New users in period
            new_users = 0
            active_users = total_users
            
            if since:
                new_stmt = select(func.count(DemoUser.user_id)).where(DemoUser.created_at >= since)
                active_stmt = select(func.count(DemoUser.user_id)).where(DemoUser.last_active_at >= since)
                
                if isinstance(session, AsyncSession):
                    new_result = await session.execute(new_stmt)
                    active_result = await session.execute(active_stmt)
                else:
                    new_result = session.execute(new_stmt)
                    active_result = session.execute(active_stmt)
                
                new_users = new_result.scalar() or 0
                active_users = active_result.scalar() or 0

            return {
                "total_users": total_users,
                "active_users": active_users,
                "new_users": new_users,
                "period": period,
                "timestamp": now.isoformat()
            }

from datetime import timedelta
user_tracking_service = UserTrackingService()
