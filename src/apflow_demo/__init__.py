"""
apflow-demo

Demo deployment of apflow with session and user management.
"""

import os
from pathlib import Path

__version__ = "0.3.0"

# Set default DATABASE_URL if not provided
def _initialize_database():
    # Find project root (where pyproject.toml or .env resides)
    current_path = Path(__file__).resolve()
    project_root = None
    for parent in current_path.parents:
        if (parent / "pyproject.toml").exists() or (parent / ".env").exists():
            project_root = parent
            break
    
    if not project_root:
        project_root = Path.cwd()

    # Load .env from project root if it exists
    env_path = project_root / ".env"
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=env_path)

    db = os.getenv("APFLOW_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not db:
        data_dir = project_root / ".data"
        data_dir.mkdir(parents=True, exist_ok=True)
        db_path = data_dir / "apflow-demo.sqlite3"
        
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

_initialize_database()

# Import custom TaskModel extension to register it on package load
# This ensures CustomTaskModel is used by both API server and CLI tools
from apflow_demo.extensions.custom_task_model_extension import *  # noqa: F401, F403

