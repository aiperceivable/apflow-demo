"""
Demo extensions module
"""

# Import custom task model extension first to ensure it's registered
# This ensures both API server and CLI tools use the custom TaskModel
try:
    import apflow_demo.extensions.custom_task_model_extension  # noqa: F401
except ImportError:
    pass  # Extension may not be available in all environments

