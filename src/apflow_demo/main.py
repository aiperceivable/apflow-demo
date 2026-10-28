"""
Main entry point for apflow-demo

This is the demo application layer that extends apflow with
demo session and user management features.

Follows the structure pattern from apflow/api/main.py for consistency.
"""

import os
import sys
import warnings
import uvicorn
import time
from pathlib import Path
from typing import Any
from apflow_demo.api.server import create_demo_app
from apflow_demo.config.settings import settings
from apflow.logger import get_logger

# Suppress specific warnings for cleaner output
warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="websockets")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="uvicorn")

# Add project root to Python path for development
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Initialize logger
logger = get_logger(__name__)
start_time = time.time()
logger.info("Starting apflow-demo service")


def _load_environment_variables():
    """Load environment variables from .env file if it exists"""
    from dotenv import load_dotenv
    env_file = Path(__file__).parent.parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        logger.debug(f"Loaded environment variables from {env_file}")


def start_server() -> None:
    """
    Start the demo API server
    
    Initializes the demo ASGI application and starts uvicorn.
    """

    print("Starting apflow-demo service...")
    logger.info("Start apflow-demo service...")

    # Load environment variables
    _load_environment_variables()
    
    app = create_demo_app()

    # Log startup time
    startup_time = time.time() - start_time
    logger.info(f"Service initialization completed in {startup_time:.2f} seconds")
    
    # Get host and port from settings
    host = settings.apflow_api_host
    port = settings.apflow_api_port
    
    logger.info(f"Starting apflow-demo on {host}:{port}")
    
    # Run server
    uvicorn.run(
        app,
        host=host,
        port=port,
        workers=1,  # Single worker for async app
        loop="asyncio",  # Use asyncio event loop
        limit_concurrency=100,  # Increase concurrency limit
        limit_max_requests=1000,  # Increase max requests
        access_log=True,  # Enable access logging for debugging
        timeout_graceful_shutdown=5.0,  # Graceful shutdown timeout (5 seconds)
    )


def main() -> None:
    """
    Main entry point for demo API service (backward compatibility)
    
    This function is kept for backward compatibility when called directly
    as a module (e.g., `python -m apflow_demo.main`).
    For CLI usage, use `apflow-demo serve` instead.
    """
    start_server()


if __name__ == "__main__":
    main()

