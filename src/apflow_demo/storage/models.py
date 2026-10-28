"""
SQLAlchemy models for demo user and task storage

Uses the same database as apflow (SQLite/PostgreSQL).
"""

from sqlalchemy import Column, String, Integer, DateTime, JSON, Index, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import declarative_base
from datetime import datetime, timezone

# Use the same Base as apflow
from apflow.core.storage.sqlalchemy.models import Base
from apflow.core.storage.sqlalchemy.models import TaskModel as BaseTaskModel


class DemoUser(Base):
    """
    User model for demo environment
    
    Stores user metadata, credentials (optional), and activity tracking.
    """
    __tablename__ = "demo_users"
    
    user_id = Column(String(255), primary_key=True, index=True)
    username = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    hashed_password = Column(String(255), nullable=True)
    status = Column(String(20), default="active")  # active, inactive, pending
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_active_at = Column(DateTime(timezone=True), server_default=func.now())
    source = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)
    
    __table_args__ = (
        Index('idx_user_status', 'status'),
    )


class CustomTaskModel(BaseTaskModel):
    """
    Custom TaskModel with extended fields
    
    Extends the base TaskModel with:
    - instance_id: String field for distributed service instance identification
    
    The token_usage field stores JSON data with token statistics:
    {
        "prompt_tokens": int,
        "completion_tokens": int,
        "total_tokens": int
    }
    
    The instance_id field stores the distributed service instance ID
    (e.g., "worker-1", "api-server-2").
    
    This uses single-table inheritance - all classes share the same table.
    The additional columns will be added to the existing table when it's created.
    """
    
    # Don't override __tablename__ - inherit from BaseTaskModel to use same table
    
    # token_usage is inherited from apflow's TaskModel.
    instance_id = Column(String(255), nullable=True, index=True, comment="Distributed service instance ID")
    
    # Configure mapper to use single-table inheritance
    # This ensures we use the same table as BaseTaskModel
    __mapper_args__ = {
        'concrete': False,  # Not concrete inheritance
    }

    def to_dict(self) -> dict:
        """Extend base `to_dict` to include custom fields.

        Calls the parent `to_dict` and then appends `token_usage` and
        `instance_id` so CLI and API JSON output include these fields.
        """
        base = super().to_dict()
        base.update({
            "token_usage": self.token_usage,
            "instance_id": self.instance_id,
        })
        return base

