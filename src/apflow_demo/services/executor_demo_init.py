"""
Executor demo tasks initialization service

Creates demo tasks for all executors based on executor_metadata.
Each executor gets a demo task with inputs generated from its input_schema.
For system_info_executor, creates an aggregate task with child tasks for cpu, memory, and disk.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
import asyncio
import time
from apflow.core.extensions.executor_metadata import get_all_executor_metadata
from apflow.core.storage import create_pooled_session
from apflow.core.storage.sqlalchemy.task_repository import TaskRepository
from apflow.core.config import get_task_model_class
from apflow.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


def _generate_default_value_from_schema(property_schema: Dict[str, Any]) -> Any:
    """
    Generate a default value from a JSON schema property
    
    Args:
        property_schema: JSON schema property definition
        
    Returns:
        Default value based on schema type
    """
    schema_type = property_schema.get("type")
    default = property_schema.get("default")
    
    # If default is provided, use it
    if default is not None:
        return default
    
    # Generate based on type
    if schema_type == "string":
        # Check for enum
        if "enum" in property_schema:
            return property_schema["enum"][0]
        # Check for examples
        if "examples" in property_schema and property_schema["examples"]:
            return property_schema["examples"][0]
        # Use description or name as hint
        description = property_schema.get("description", "")
        if "url" in description.lower() or "endpoint" in description.lower():
            return "https://example.com"
        elif "email" in description.lower():
            return "demo@example.com"
        elif "path" in description.lower() or "file" in description.lower():
            return "/tmp/demo.txt"
        else:
            return "demo_value"
    
    elif schema_type == "integer":
        return property_schema.get("minimum", 0) or 0
    
    elif schema_type == "number":
        return float(property_schema.get("minimum", 0.0) or 0.0)
    
    elif schema_type == "boolean":
        return False
    
    elif schema_type == "array":
        return []
    
    elif schema_type == "object":
        return {}
    
    # Default fallback
    return None


def _generate_inputs_from_schema(input_schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate demo inputs from executor's input_schema
    
    Args:
        input_schema: Executor's input schema (JSON schema format)
        
    Returns:
        Dictionary of demo inputs
    """
    if not input_schema or input_schema.get("type") != "object":
        return {}
    
    properties = input_schema.get("properties", {})
    required = input_schema.get("required", [])
    inputs = {}
    
    # Generate values for all required fields and some optional ones
    fields_to_generate = set(required)
    # Also include first few optional fields for better demo
    optional_fields = [k for k in properties.keys() if k not in required]
    fields_to_generate.update(optional_fields[:3])  # Include up to 3 optional fields
    
    for field_name in fields_to_generate:
        if field_name in properties:
            field_schema = properties[field_name]
            inputs[field_name] = _generate_default_value_from_schema(field_schema)
    
    return inputs


def _generate_demo_task_for_system_info_executor(
    executor_id: str,
    executor_name: str,
    user_id: str,
    base_timestamp: int,
    task_index: int
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Generate aggregate task for system_info_executor with cpu, memory, disk child tasks
    
    Returns:
        Tuple of (tasks_data list, created_task_ids list)
    """
    user_prefix = user_id[:8].replace("_", "-")
    executor_id_safe = executor_id.replace("_", "-")
    
    # Create child tasks for cpu, memory, disk
    child_tasks = []
    child_task_ids = []
    resources = ["cpu", "memory", "disk"]
    
    for idx, resource in enumerate(resources):
        child_task_id = f"demo_executor_{user_prefix}_{executor_id_safe}_{base_timestamp}_{task_index}_child_{idx}"
        child_task = {
            "id": child_task_id,
            "name": f"Demo: {executor_name} - {resource.upper()}",
            "user_id": user_id,
            "schemas": {
                "method": executor_id,
                "demo_runnable": True,
                "demo_requirements": None
            },
            "inputs": {"resource": resource},
            "status": "pending",
            "parent_id": None,  # Will be set after parent is created
            "has_children": False,
            "dependencies": None,  # Child tasks have no dependencies
        }
        child_tasks.append(child_task)
        child_task_ids.append(child_task_id)
    
    # Create parent aggregate task
    parent_task_id = f"demo_executor_{user_prefix}_{executor_id_safe}_{base_timestamp}_{task_index}_parent"
    # Set dependencies: parent task depends on all child tasks
    dependencies = [{"id": child_id, "required": True} for child_id in child_task_ids]
    parent_task = {
        "id": parent_task_id,
        "name": f"Demo: {executor_name} (Aggregate)",
        "user_id": user_id,
        "schemas": {"method": executor_id},  # Use system_info_executor, not aggregate_results_executor
        "inputs": {
            "_demo_runnable": True,
            "_demo_requirements": None
        },  # Will be populated with dependency results by TaskManager
        "status": "pending",
        "parent_id": None,
        "has_children": True,
        "dependencies": dependencies,
    }
    
    # Set parent_id for child tasks
    for child_task in child_tasks:
        child_task["parent_id"] = parent_task_id
    
    # Combine all tasks (parent first, then children)
    all_tasks = [parent_task] + child_tasks
    all_task_ids = [parent_task_id] + child_task_ids
    
    return all_tasks, all_task_ids


def _generate_demo_task_for_executor(
    executor_id: str,
    executor_name: str,
    metadata: Dict[str, Any],
    user_id: str,
    base_timestamp: int,
    task_index: int
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Generate demo task(s) for a specific executor
    
    Args:
        executor_id: Executor ID
        executor_name: Executor name
        metadata: Executor metadata
        user_id: User ID
        base_timestamp: Base timestamp for task ID generation
        task_index: Task index for unique ID generation
        
    Returns:
        Tuple of (tasks_data list, created_task_ids list)
    """
    # Special handling for system_info_executor - create aggregate task
    if executor_id == "system_info_executor":
        return _generate_demo_task_for_system_info_executor(
            executor_id, executor_name, user_id, base_timestamp, task_index
        )
    
    # For other executors, generate inputs based on their specific requirements
    input_schema = metadata.get("input_schema", {})
    demo_inputs = {}
    demo_runnable = True
    demo_requirements = None
    
    # Generate inputs and demo metadata based on executor-specific logic
    if executor_id == "command_executor":
        demo_inputs = {"command": "echo 'Hello from demo'"}
        demo_runnable = True
        demo_requirements = "Set APFLOW_STDIO_ALLOW_COMMAND=1 to enable command execution"
    elif executor_id == "rest_executor":
        demo_inputs = {
            "url": "https://jsonplaceholder.typicode.com/posts/1",
            "method": "GET"
        }
        demo_runnable = True
        demo_requirements = None
    elif executor_id == "generate_executor":
        demo_inputs = {"requirement": "Get system information and display it"}
        demo_runnable = False
        demo_requirements = "Requires OPENAI_API_KEY environment variable"
    elif executor_id == "docker_executor":
        demo_inputs = {
            "image": "alpine:latest",
            "command": "echo 'Hello from Docker'"
        }
        demo_runnable = False
        demo_requirements = "Requires Docker daemon to be running"
    elif executor_id == "ssh_executor":
        demo_inputs = {
            "host": "example.com",
            "username": "demo_user",
            "command": "echo 'Hello from SSH'",
            "password": "demo_password"  # Demo only
        }
        demo_runnable = False
        demo_requirements = "Requires SSH server access (host, username, password/key)"
    elif executor_id == "mcp_executor":
        demo_inputs = {
            "transport": "stdio",
            "command": ["python", "-m", "mcp_server"],
            "operation": "list_tools"
        }
        demo_runnable = False
        demo_requirements = "Requires MCP server to be running"
    elif executor_id == "websocket_executor":
        demo_inputs = {
            "url": "ws://echo.websocket.org",
            "message": "Hello WebSocket"
        }
        demo_runnable = False
        demo_requirements = "WebSocket server may not be available"
    elif executor_id == "grpc_executor":
        demo_inputs = {
            "server": "localhost:50051",
            "service": "Greeter",
            "method": "SayHello",
            "request": {"name": "Demo"}
        }
        demo_runnable = False
        demo_requirements = "Requires gRPC server running on localhost:50051"
    elif executor_id == "apflow_api_executor":
        demo_inputs = {
            "base_url": "http://localhost:8000",
            "method": "tasks.get",
            "params": {"task_id": "demo-task-123"}
        }
        demo_runnable = False
        demo_requirements = "Requires running apflow API instance"
    elif executor_id == "llm_executor":
        demo_inputs = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Explain what an AI Agent workflow is in one sentence."}
            ],
            "temperature": 0.7
        }
        demo_runnable = False
        demo_requirements = "Requires OPENAI_API_KEY (or other provider keys) in .env"
    elif executor_id == "aggregate_results_executor":
        # For aggregate_results_executor, inputs will be populated by TaskManager
        demo_inputs = {}
        demo_runnable = True
        demo_requirements = None
    elif executor_id == "scrape_executor":
        demo_inputs = {
            "url": "https://aiperceivable.com",
            "extract_metadata": True,
            "max_chars": 5000
        }
        demo_runnable = True
        demo_requirements = None
    else:
        # Fallback: use schema-based generation
        demo_inputs = _generate_inputs_from_schema(input_schema)
        demo_runnable = True
        demo_requirements = None
    
    # Generate unique task ID
    user_prefix = user_id[:8].replace("_", "-")
    executor_id_safe = executor_id.replace("_", "-")
    task_id = f"demo_executor_{user_prefix}_{executor_id_safe}_{base_timestamp}_{task_index}"
    
    # Create task name
    task_name = f"Demo: {executor_name}"
    
    # Prepare task data with demo metadata in schemas
    task_data = {
        "id": task_id,
        "name": task_name,
        "user_id": user_id,
        "schemas": {
            "method": executor_id,
            "demo_runnable": demo_runnable,
            "demo_requirements": demo_requirements
        },
        "inputs": demo_inputs,
        "status": "pending",
        "parent_id": None,
        "has_children": False,
        "dependencies": None,  # Explicitly set to None for non-aggregate tasks
    }
    
    return [task_data], [task_id]


class ExecutorDemoInitService:
    """Service for initializing demo tasks for all executors"""

    async def check_demo_init_status(self, user_id: str) -> Dict[str, Any]:
        """
        Check demo init status for a specific user
        
        Returns information about which executors already have demo tasks
        and which ones can be initialized.
        
        Args:
            user_id: User ID to check status for
            
        Returns:
            Dictionary with:
            - can_init: bool - Whether demo init can be performed (has executors without demo tasks)
            - total_executors: int - Total number of executors
            - existing_executors: List[str] - Executor IDs that already have demo tasks
            - missing_executors: List[str] - Executor IDs that don't have demo tasks yet
            - executor_details: Dict[str, Dict] - Details for each executor (name, has_demo_task)
        """
        from apflow.core.extensions.executor_metadata import get_all_executor_metadata
        
        # Get all executor metadata
        all_metadata = get_all_executor_metadata()
        
        if not all_metadata:
            return {
                "can_init": False,
                "total_executors": 0,
                "existing_executors": [],
                "missing_executors": [],
                "executor_details": {},
            }
        
        # Check which executors already have demo tasks for this user
        TaskModel = get_task_model_class()
        existing_executor_ids = set()
        
        async with create_pooled_session() as db_session:
            # Query all tasks for this user that are demo tasks (name starts with "Demo:")
            try:
                from sqlalchemy import select
                
                logger.info(f"Querying demo tasks for user_id: {user_id}")
                
                # Query tasks by user_id
                stmt = select(TaskModel).where(TaskModel.user_id == user_id)
                
                # Execute query - handle both async and sync sessions
                is_async_session = isinstance(db_session, AsyncSession)
                
                if is_async_session:
                    result = await db_session.execute(stmt)
                else:
                    result = db_session.execute(stmt)
                    
                user_tasks = result.scalars().all()
                
                logger.info(
                    f"Query completed for user_id: {user_id[:20]}... "
                    f"Found {len(user_tasks)} total tasks for this user"
                )
                
                demo_task_count = 0
                tasks_without_demo_name = 0
                tasks_without_schemas = 0
                tasks_without_method = 0
                
                for task in user_tasks:
                    # Check if it's a demo task (name starts with "Demo:")
                    if task.name and task.name.startswith("Demo:"):
                        demo_task_count += 1
                        # Extract executor_id from schemas.method
                        if task.schemas and isinstance(task.schemas, dict):
                            executor_id = task.schemas.get("method")
                            if executor_id:
                                existing_executor_ids.add(executor_id)
                                logger.info(
                                    f"✓ Found demo task for executor '{executor_id}': "
                                    f"task_id={task.id}, name={task.name}"
                                )
                            else:
                                tasks_without_method += 1
                                logger.warning(
                                    f"✗ Demo task found but schemas.method is missing: "
                                    f"task_id={task.id}, name={task.name}, "
                                    f"schemas keys={list(task.schemas.keys()) if isinstance(task.schemas, dict) else 'N/A'}"
                                )
                        else:
                            tasks_without_schemas += 1
                            logger.warning(
                                f"✗ Demo task found but schemas is invalid: "
                                f"task_id={task.id}, name={task.name}, "
                                f"schemas type={type(task.schemas)}, schemas={task.schemas}"
                            )
                    else:
                        tasks_without_demo_name += 1
                        # Log first few non-demo tasks for debugging
                        if tasks_without_demo_name <= 3:
                            logger.debug(
                                f"Non-demo task: task_id={task.id}, "
                                f"name={task.name[:50] if task.name else 'None'}..., "
                                f"user_id={task.user_id[:20] if task.user_id else 'None'}..."
                            )
                
                if tasks_without_demo_name > 0 or tasks_without_schemas > 0 or tasks_without_method > 0:
                    logger.warning(
                        f"Found tasks that don't match demo task criteria: "
                        f"{tasks_without_demo_name} without 'Demo:' prefix, "
                        f"{tasks_without_schemas} with invalid schemas, "
                        f"{tasks_without_method} without schemas.method"
                    )
                
                logger.info(
                    f"Demo init status check for user_id {user_id[:20]}...: "
                    f"Found {demo_task_count} demo tasks, "
                    f"{len(existing_executor_ids)} executors with demo tasks: {sorted(existing_executor_ids)}"
                )
                
                # Diagnostic: If no demo tasks found for this user, check if any demo tasks exist at all
                if demo_task_count == 0 and len(user_tasks) == 0:
                    try:
                        # Check if there are any demo tasks in the database (any user_id)
                        all_demo_stmt = select(TaskModel).where(TaskModel.name.like("Demo:%"))
                        if is_async_session:
                            all_demo_result = await db_session.execute(all_demo_stmt)
                        else:
                            all_demo_result = db_session.execute(all_demo_stmt)
                        
                        all_demo_tasks = all_demo_result.scalars().all()
                        
                        if all_demo_tasks:
                            unique_user_ids = set(task.user_id for task in all_demo_tasks if task.user_id)
                            logger.warning(
                                f"No demo tasks found for user_id {user_id[:20]}..., "
                                f"but found {len(all_demo_tasks)} demo tasks in database "
                                f"for {len(unique_user_ids)} different user(s): {sorted(list(unique_user_ids))[:3]}..."
                            )
                    except Exception as diag_e:
                        logger.debug(f"Diagnostic query failed (non-critical): {diag_e}")
            except Exception as e:
                logger.warning(f"Failed to check existing demo tasks: {e}", exc_info=True)
                # If check fails, assume no existing tasks
                existing_executor_ids = set()
        
        # Build executor details
        executor_details = {}
        missing_executor_ids = []
        
        for executor_id, metadata in all_metadata.items():
            executor_name = metadata.get("name", executor_id)
            has_demo_task = executor_id in existing_executor_ids
            
            executor_details[executor_id] = {
                "id": executor_id,
                "name": executor_name,
                "has_demo_task": has_demo_task,
            }
            
            if not has_demo_task:
                missing_executor_ids.append(executor_id)
        
        return {
            "can_init": len(missing_executor_ids) > 0,
            "total_executors": len(all_metadata),
            "existing_executors": sorted(list(existing_executor_ids)),
            "missing_executors": sorted(missing_executor_ids),
            "executor_details": executor_details,
        }

    async def init_all_executor_demo_tasks_for_user(self, user_id: str) -> List[str]:
        """
        Initialize demo tasks for all executors for a specific user
        
        Creates one demo task per executor based on executor_metadata:
        - Uses executor_id as schemas.method
        - Generates demo inputs from executor's input_schema
        - Sets task name based on executor name
        - Sets user_id
        
        Skips executors that already have demo tasks for this user to avoid duplicates.
        These tasks are independent (not part of the same task tree), so they are created
        using batch insert for better performance and to avoid database connection conflicts.
        All tasks are created in a single transaction for efficiency.
        
        Args:
            user_id: User ID to create tasks for
            
        Returns:
            List of created task IDs
        """
        try:
            # Get all executor metadata
            all_metadata = get_all_executor_metadata()
            
            if not all_metadata:
                logger.warning("No executor metadata found")
                return []
            
            # Check which executors already have demo tasks for this user
            TaskModel = get_task_model_class()
            existing_executor_ids = set()
            
            async with create_pooled_session() as db_session:
                # Query all tasks for this user that are demo tasks (name starts with "Demo:")
                try:
                    from sqlalchemy import select
                    
                    is_async_session = isinstance(db_session, AsyncSession)
                    
                    # Query tasks by user_id and filter by name starting with "Demo:"
                    stmt = select(TaskModel).where(TaskModel.user_id == user_id)
                    if is_async_session:
                        result = await db_session.execute(stmt)
                    else:
                        result = db_session.execute(stmt)
                    
                    user_tasks = result.scalars().all()
                    
                    for task in user_tasks:
                        # Check if it's a demo task (name starts with "Demo:")
                        if task.name and task.name.startswith("Demo:"):
                            # Extract executor_id from schemas.method
                            if task.schemas and isinstance(task.schemas, dict):
                                executor_id = task.schemas.get("method")
                                if executor_id:
                                    existing_executor_ids.add(executor_id)
                except Exception as e:
                    logger.warning(f"Failed to check existing demo tasks: {e}, will create all tasks")
                    # If check fails, continue to create all tasks
            
            if existing_executor_ids:
                logger.info(
                    f"Found existing demo tasks for {len(existing_executor_ids)} executors: {existing_executor_ids}. "
                    f"Will skip these and create tasks for remaining executors."
                )
            
            base_timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
            
            # Prepare all task data as dictionaries (no database operations)
            # Tasks will be created using TaskModel instances and session.add()
            tasks_data = []
            created_task_ids = []
            skipped_count = 0
            
            for task_index, (executor_id, metadata) in enumerate(all_metadata.items()):
                # Skip if demo task already exists for this executor
                if executor_id in existing_executor_ids:
                    skipped_count += 1
                    logger.debug(f"Skipping executor '{executor_id}' - demo task already exists")
                    continue
                try:
                    executor_name = metadata.get("name", executor_id)
                    
                    # Use specialized generator for each executor
                    executor_tasks, executor_task_ids = _generate_demo_task_for_executor(
                        executor_id=executor_id,
                        executor_name=executor_name,
                        metadata=metadata,
                        user_id=user_id,
                        base_timestamp=base_timestamp,
                        task_index=task_index
                    )
                    
                    tasks_data.extend(executor_tasks)
                    created_task_ids.extend(executor_task_ids)
                    
                except Exception as e:
                    logger.warning(
                        f"Failed to prepare demo task for executor '{executor_id}': {e}",
                        exc_info=True
                    )
                    continue
            
            if not tasks_data:
                if skipped_count > 0:
                    logger.info(
                        f"All {len(all_metadata)} executors already have demo tasks for user: {user_id[:20]}... "
                        f"No new tasks created."
                    )
                return []
            
            # Use TaskRepository API to create tasks instead of raw SQL
            # Sort tasks: parent tasks (parent_id=None) first, then child tasks
            # This ensures foreign key constraints are satisfied
            sorted_tasks = sorted(tasks_data, key=lambda t: (t.get("parent_id") is not None, t.get("id")))
            
            logger.info(
                f"Creating {len(sorted_tasks)} tasks using TaskRepository API (sorted: parents first, then children). "
                f"Parent tasks: {sum(1 for t in sorted_tasks if t.get('parent_id') is None)}, "
                f"Child tasks: {sum(1 for t in sorted_tasks if t.get('parent_id') is not None)}"
            )
            
            # Create TaskModel instances from task data
            task_objects = []
            for task_data in sorted_tasks:
                try:
                    task_obj = TaskModel(
                        id=task_data.get("id"),
                        user_id=task_data.get("user_id"),
                        name=task_data.get("name"),
                        status=task_data.get("status", "pending"),
                        inputs=task_data.get("inputs", {}),
                        schemas=task_data.get("schemas", {}),
                        priority=2,
                        progress=0.0,
                        has_children=task_data.get("has_children", False),
                        has_references=task_data.get("has_references", False),
                        parent_id=task_data.get("parent_id"),
                        dependencies=task_data.get("dependencies"),
                    )
                    task_objects.append(task_obj)
                except Exception as e:
                    logger.error(
                        f"Failed to create TaskModel for task {task_data.get('id', 'unknown')}: {e}",
                        exc_info=True
                    )
                    if task_data["id"] in created_task_ids:
                        created_task_ids.remove(task_data["id"])
                    continue
            
            if not task_objects:
                logger.warning("No task objects were created")
                return []
            
            # Use create_pooled_session to ensure correct event loop binding
            # This avoids "Task got Future attached to a different loop" errors
            async with create_pooled_session() as db_session:
                task_repository = TaskRepository(db_session, task_model_class=TaskModel)
                db_session = task_repository.db
                try:
                    # Add tasks to session sequentially with explicit timestamp and flush to ensure distinct timestamps
                    # Set timestamp before each flush to ensure each task gets a distinct created_at
                    # For async, add tasks one by one, set timestamp, flush, then sleep
                    for task_obj in task_objects:
                        # Set timestamp explicitly before flush to ensure distinct created_at
                        current_timestamp = datetime.now(timezone.utc)
                        task_obj.created_at = current_timestamp
                        task_obj.updated_at = current_timestamp
                        db_session.add(task_obj)
                        # Flush to database
                        await db_session.flush()
                        # Sleep 100ms between each task to ensure distinct created_at timestamps
                        await asyncio.sleep(0.1)
                    await db_session.commit()
                    
                    
                    logger.info(f"Successfully created {len(task_objects)} demo tasks using TaskRepository API")
                except RuntimeError as e:
                    # Check if it's an event loop error
                    if "attached to a different loop" in str(e):
                        logger.error(
                            f"Event loop binding error when creating demo tasks: {e}. "
                            f"This usually happens when SQLAlchemy connection pool is bound to a different event loop. "
                            f"Try running tests with asyncio_mode='auto' in pytest configuration.",
                            exc_info=True
                        )
                    else:
                        logger.error(
                            f"RuntimeError when creating demo tasks: {e}",
                            exc_info=True
                        )
                    # Rollback on error
                    try:
                        await db_session.rollback()
                    except Exception as rollback_err:
                        logger.debug(f"Rollback error (ignored): {rollback_err}")
                    # Return empty list on failure
                    return []
                except Exception as e:
                    logger.error(
                        f"Failed to create demo tasks using TaskRepository API: {e}",
                        exc_info=True
                    )
                    # Rollback on error
                    try:
                        await db_session.rollback()
                    except Exception as rollback_err:
                        logger.debug(f"Rollback error (ignored): {rollback_err}")
                    # Return empty list on failure
                    return []
            
            logger.info(
                f"Initialized {len(created_task_ids)}/{len(all_metadata)} executor demo tasks for user: {user_id[:20]}... "
                f"(skipped {skipped_count} executors with existing demo tasks)"
            )
            return created_task_ids
            
        except Exception as e:
            logger.error(
                f"Error initializing executor demo tasks for user {user_id[:20] if user_id else 'unknown'}: {e}",
                exc_info=True,
            )
            raise

