"""
CLI extension for running the demo API server
"""

def serve_app() -> None:
    """Start the apflow-demo API server (direct command)."""
    from apflow.logger import get_logger
    logger = get_logger(__name__)
    logger.debug("Start the apflow-demo API server")
    from apflow_demo.main import start_server
    start_server()
