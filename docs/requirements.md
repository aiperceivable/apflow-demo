> Historical document: the legacy quota and demo-task features described here were removed during the apflow 0.24.1 upgrade. See README.md for the current behavior.

# LLM Quota System Requirements

## Executive Summary

This document specifies the requirements for implementing a quota management system for the apflow-demo application. The system limits LLM API consumption costs by enforcing per-user task tree limits and providing demo data fallback when quotas are exceeded. The implementation supports both free users (with strict limits) and premium users (with LLM key authentication via headers).

**Key Features:**
- Per-user daily task tree quotas (default: 10 task trees)
- Separate limits for LLM-consuming task trees based on user type
- Demo data fallback mechanism when quotas are exceeded
- System-wide concurrency limits
- Integration with `task.generate()`, `task.execute()`, and executor components

## 1. Background & Context

### 1.1 Purpose

The apflow-demo application provides a demonstration environment for the apflow orchestration framework. To control operational costs while maintaining a good user experience, the system needs to:

1. Limit LLM API consumption per user
2. Provide graceful degradation when quotas are exceeded
3. Support different user tiers (free vs premium)
4. Track usage and enforce concurrency limits

### 1.2 Scope

This requirements document covers:
- Quota management system for task trees
- Integration points with apflow core methods (`task.generate`, `task.execute`)
- Demo data injection mechanism
- User type detection and limit enforcement
- Concurrency control

### 1.3 Definitions

- **Task Tree**: A hierarchical structure of tasks where a root task may have child tasks, forming a tree-like execution graph
- **LLM-consuming Task Tree**: A task tree that contains at least one task requiring LLM API calls
- **Non-LLM Task Tree**: A task tree containing only tasks that do not require LLM API calls (e.g., `system_info`)
- **Free User**: A user without LLM API key provided in request headers
- **Premium User**: A user with LLM API key provided in request headers
- **Daily Quota**: The maximum number of task trees a user can execute per day
- **Concurrent Task Tree**: A task tree that is currently executing (not yet completed)

## 2. Functional Requirements

### 2.1 User Types & Quota Limits

#### 2.1.1 Free Users (No LLM Key in Header)

**Total Quota:**
- Default: 10 task trees per day
- Configurable via environment variable: `RATE_LIMIT_DAILY_PER_USER` (default: 10)

**LLM-consuming Task Trees:**
- Maximum: 1 LLM-consuming task tree per day (out of the 10 total)
- Once the LLM-consuming limit is reached, subsequent LLM-consuming task trees must use demo data

**Concurrency:**
- Per-user: 1 task tree at a time
- System-wide: Maximum 10 concurrent task trees across all users

**Behavior:**
- Non-LLM task trees (e.g., `system_info`) do not count against the LLM-consuming limit
- Non-LLM task trees still count against the total quota of 10
- When LLM-consuming quota is exceeded, `task.generate()` and `task.execute()` return demo data
- When total quota is exceeded, new task tree creation is rejected

#### 2.1.2 Premium Users (LLM Key in Header)

**Total Quota:**
- Default: 10 task trees per day
- Configurable via environment variable: `RATE_LIMIT_DAILY_PER_USER_PREMIUM` (default: 10)

**LLM-consuming Task Trees:**
- All 10 task trees can be LLM-consuming (no separate limit)
- Users provide their own LLM API keys, reducing system costs

**Concurrency:**
- Per-user: 1 task tree at a time
- System-wide: Maximum 10 concurrent task trees across all users

**Behavior:**
- LLM API calls use the user-provided API key from headers
- When total quota is exceeded, new task tree creation is rejected
- Demo data fallback is not used for premium users (they use their own keys)

### 2.2 Task Tree Classification

#### 2.2.1 LLM-consuming Tasks

Tasks that require LLM API calls include:
- Tasks with `agent` executors that call LLM APIs
- Tasks with `llm` executors
- Tasks that generate content using language models
- Any task that makes API calls to OpenAI, Anthropic, or similar services

**Detection Method:**
- Analyze task executor type
- Check task configuration for LLM-related settings
- Monitor actual API calls during execution

#### 2.2.2 Non-LLM Tasks

Tasks that do not require LLM API calls include:
- `system_info` tasks
- File system operations
- Data transformation tasks
- HTTP requests to non-LLM APIs
- Database operations

**Behavior:**
- Do not count against LLM-consuming quota
- Still count against total daily quota
- Execute normally without demo data fallback

### 2.3 Quota Management

#### 2.3.1 Per-User Daily Tracking

**Storage:**
- Use **SQLAlchemy** with a relational database (DuckDB for local, PostgreSQL for production)
- Table: `demo_quota_counters`
- Schema:
  - `user_id` (String): Unique user identifier
  - `date` (String, ISO YYYY-MM-DD): Date for quota tracking
  - `counter_type` (String): 'total' or 'llm'
  - `count` (Integer): Current usage count
- Composite Primary Key: `(user_id, date, counter_type)`

**Reset Mechanism:**
- Daily quotas are reset based on the `date` string in the database.
- Track by date string (ISO format: YYYY-MM-DD) in UTC.

#### 2.3.2 Per-Task-Tree Tracking

**Task Tree Identification:**
- Each task tree has a unique root task ID.
- Table: `demo_task_tree_tracking`
- Store task tree metadata:
  - `task_tree_id` (String): Primary Key
  - `user_id` (String): Foreign user identifier
  - `is_llm_consuming` (String): 'true' or 'false'
  - `started_at` (DateTime): Creation timestamp
  - `completed_at` (DateTime): Nullable completion timestamp

#### 2.3.3 System-Wide Concurrency Limits

**Global Concurrency Tracking:**
- Table: `demo_concurrency_counters`
- Schema:
  - `scope` (String): 'system' or 'user'
  - `identifier` (String): 'global' or `user_id`
  - `count` (Integer): Currently running task trees
- Atomic increment/decrement operations (via database updates).
- Maximum value: 10 (configurable via `MAX_CONCURRENT_TASK_TREES`).

**Per-User Concurrency:**
- Tracks active task trees for each user under the `user` scope in `demo_concurrency_counters`.
- Maximum value: 1 per user by default.
- Check before starting new task tree.

**Concurrency Control:**
- Before starting a task tree:
  1. Check global concurrency limit
  2. Check user-specific concurrency limit
  3. If both available, increment counters and proceed
  4. If limit reached, reject request with appropriate error

- After task tree completion:
  1. Decrement global concurrency counter
  2. Decrement user-specific concurrency counter
  3. Update task tree status to `completed`

### 2.4 Demo Data Fallback

#### 2.4.1 When Demo Data is Used

Demo data fallback is triggered when:
1. **Free user exceeds LLM-consuming quota**: After 1 LLM-consuming task tree, subsequent LLM-consuming task trees use demo data
2. **Free user exceeds total quota**: After 10 task trees, new task trees are rejected (no demo data fallback)
3. **System concurrency limit reached**: Request is queued or rejected (no demo data fallback)

#### 2.4.2 Demo Data Source

**Pre-computed Results:**
- Stored in `demo/precomputed_results/` directory
- JSON files named by task ID (e.g., `task_123.json`)
- Loaded into memory cache on application startup
- Updated via `DemoResultsCache` extension

**Result Structure:**
```json
{
  "id": "task_id",
  "status": "completed",
  "result": {
    "output": "pre-computed result data"
  },
  "progress": 1.0,
  "started_at": "2024-01-15T10:00:00Z",
  "completed_at": "2024-01-15T10:05:00Z"
}
```

#### 2.4.3 Integration Points

**task.generate() Method:**
- Check quota before generating task tree
- If LLM-consuming quota exceeded (free user), return demo data structure
- Demo data should match the expected format of a generated task tree
- Include metadata indicating demo mode: `{"demo_mode": true, "reason": "quota_exceeded"}`

**task.execute() Method:**
- Check quota before executing task
- If LLM-consuming quota exceeded (free user), return pre-computed result
- Skip actual LLM API calls
- Return demo result with appropriate metadata

**Executor Integration:**
- Intercept executor calls before LLM API invocation
- Check if demo data should be used
- If yes, return cached demo result instead of making API call
- If no, proceed with normal execution

## 3. Technical Requirements

### 3.1 Rate Limiter Enhancement

**Current Implementation:**
- `RateLimiter` class in `src/apflow_demo/extensions/rate_limiter.py`
- Tracks per-user and per-IP daily limits.
- Uses **SQLAlchemy Repository Pattern** (`QuotaRepository`) for storage.
- Supports **DuckDB** and **PostgreSQL** with unified sync/async compatibility.

**Enhancements Required:**
1. Add LLM-consuming task tree counter
2. Add concurrent task tree tracking
3. Add system-wide concurrency limit enforcement
4. Add task tree classification (LLM vs non-LLM)
5. Add user type detection (free vs premium)

**New Methods:**
```python
class RateLimiter:
    @classmethod
    def check_task_tree_quota(cls, user_id: str, is_llm_consuming: bool, has_llm_key: bool) -> tuple[bool, dict]
    
    @classmethod
    def check_concurrency_limit(cls, user_id: str) -> tuple[bool, dict]
    
    @classmethod
    def start_task_tree(cls, user_id: str, task_tree_id: str, is_llm_consuming: bool) -> bool
    
    @classmethod
    def complete_task_tree(cls, user_id: str, task_tree_id: str) -> None
    
    @classmethod
    def get_user_quota_status(cls, user_id: str) -> dict
```

### 3.2 Task Tree Detection

**LLM-consuming Detection:**
- Analyze task executor configuration
- Check for LLM-related executor types (e.g., `openai`, `anthropic`, `llm`)
- Inspect task schema for LLM model references
- Monitor executor initialization for LLM API clients

**Implementation Approach:**
1. **Static Analysis**: Check task configuration before execution
2. **Runtime Detection**: Monitor executor instantiation
3. **Hybrid Approach**: Use static analysis first, runtime detection as fallback

**Detection Logic:**
```python
def is_llm_consuming_task(task: Task) -> bool:
    """Check if task requires LLM API calls"""
    # Check executor type
    if task.executor_type in ['openai', 'anthropic', 'llm', 'agent']:
        return True
    
    # Check task schema for LLM model references
    if 'model' in task.schema and 'llm' in task.schema.get('model', '').lower():
        return True
    
    # Check executor configuration
    if task.executor_config and 'llm' in str(task.executor_config).lower():
        return True
    
    return False

def is_llm_consuming_task_tree(root_task: Task) -> bool:
    """Check if task tree contains any LLM-consuming tasks"""
    # Traverse task tree
    # Return True if any task is LLM-consuming
    pass
```

### 3.3 Demo Data Injection Mechanism

**Integration Strategy:**
1. **Middleware Approach**: Intercept requests at API level
2. **Decorator Approach**: Wrap `task.generate()` and `task.execute()` methods
3. **Executor Override**: Create custom executor that checks quota before LLM calls

**Recommended Approach: Route-Level Interception**

Since middleware body reading can be complex, implement interception at the route level by wrapping apflow routes:

```python
# Custom route wrapper
async def wrapped_task_generate(request: Request):
    # Extract user_id and check quota
    user_id = extract_user_id(request)
    is_premium = has_llm_key_in_header(request)
    
    # Check quota
    allowed, info = RateLimiter.check_task_tree_quota(
        user_id=user_id,
        is_llm_consuming=True,  # Assume LLM-consuming, verify later
        has_llm_key=is_premium
    )
    
    if not allowed and not is_premium:
        # Return demo data
        return demo_task_generate_response(request)
    
    # Proceed with normal execution
    return await original_task_generate(request)
```

### 3.4 Header Parsing for LLM Key Detection

**Header Format:**
- Header name: `X-LLM-API-KEY` or `Authorization: Bearer <llm_key>`
- Alternative: `X-OpenAI-API-KEY`, `X-Anthropic-API-KEY` (provider-specific)

**Detection Logic:**
```python
def has_llm_key_in_header(request: Request) -> bool:
    """Check if request contains LLM API key"""
    # Check X-LLM-API-KEY header
    if request.headers.get("X-LLM-API-KEY"):
        return True
    
    # Check Authorization header for LLM key pattern
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer ") and len(auth_header) > 20:
        # Assume it's an LLM key if it's a bearer token
        return True
    
    # Check provider-specific headers
    if request.headers.get("X-OpenAI-API-KEY") or request.headers.get("X-Anthropic-API-KEY"):
        return True
    
    return False

def extract_llm_key_from_header(request: Request) -> Optional[str]:
    """Extract LLM API key from headers"""
    # Return first available LLM key
    pass
```

## 4. User Identification & Management

### 4.1 Hybrid User Identification

The demo implements a privacy-friendly, zero-registration user identification system using a hybrid approach.

**Mechanism Components:**
1. **Session Cookie**: A persistent cookie (`demo_session_id`) set on the first request.
2. **Browser Fingerprint**: A hash generated from `User-Agent`, IP address, and other headers.
3. **Auto-Login**: Transparently associations requests with a `user_id` without explicit login.

**User Selection Flow:**
- If a session cookie exists, use the `session_id`.
- If no cookie but a fingerprint is generated, use the fingerprint.
- If both are missing, generate a new random `user_id`.

### 4.2 User-Agent Tracking & Descriptive Usernames

**Descriptive Usernames**:
- The system parses the `User-Agent` to extract OS and Browser information.
- Guests are assigned descriptive usernames like `Guest_Mac_Chrome_abc123`.
- If parsing fails, a generic `Guest_User_abc123` is used.

**User Metadata Storage**:
- Table: `demo_users`
- Stores:
  - `user_id` (Primary Key)
  - `username` (Descriptive or generated)
  - `user_agent` (String, full UA string for auditing)
  - `last_active_at` (DateTime)
  - `source` (e.g., 'web', 'cli', 'api')
  - timestamps (`created_at`, `updated_at`)

### 4.3 CLI Management

The demo adds a `users` plugin to the CLI for administrator auditing:
- `apflow-demo users list`: View recently active users and their metadata.
- `apflow-demo users stat`: View aggregate growth and activity statistics.

### 4.1 task.generate() Integration

**Current Behavior:**
- Creates a new task tree
- Generates task structure based on input
- May involve LLM calls for task generation

**Required Changes:**
1. Check quota before generation
2. If quota exceeded (free user, LLM-consuming), return demo data
3. Track task tree creation in quota system
4. Mark task tree as LLM-consuming if applicable

**Implementation:**
```python
async def task_generate_with_quota(request: Request):
    user_id = extract_user_id(request)
    is_premium = has_llm_key_in_header(request)
    
    # Check quota
    allowed, quota_info = RateLimiter.check_task_tree_quota(
        user_id=user_id,
        is_llm_consuming=True,  # Will verify after generation
        has_llm_key=is_premium
    )
    
    if not allowed:
        if is_premium:
            # Premium user exceeded quota - reject
            raise HTTPException(429, "Daily quota exceeded")
        else:
            # Free user - return demo data
            return get_demo_task_tree(request)
    
    # Check concurrency
    concurrency_allowed, concurrency_info = RateLimiter.check_concurrency_limit(user_id)
    if not concurrency_allowed:
        raise HTTPException(429, "Concurrency limit reached")
    
    # Generate task tree
    task_tree = await original_task_generate(request)
    
    # Detect if LLM-consuming
    is_llm_consuming = is_llm_consuming_task_tree(task_tree.root_task)
    
    # Start tracking
    RateLimiter.start_task_tree(
        user_id=user_id,
        task_tree_id=task_tree.root_task.id,
        is_llm_consuming=is_llm_consuming
    )
    
    return task_tree
```

### 4.2 task.execute() Integration

**Current Behavior:**
- Executes a task within a task tree
- May call LLM APIs via executor
- Returns execution result

**Required Changes:**
1. Check if task tree has exceeded LLM-consuming quota
2. If exceeded and free user, return demo result
3. Skip actual LLM API calls when using demo data
4. Track execution in usage statistics

**Implementation:**
```python
async def task_execute_with_quota(request: Request, task_id: str):
    user_id = extract_user_id(request)
    is_premium = has_llm_key_in_header(request)
    
    # Get task tree info
    task_tree_info = get_task_tree_info(task_id)
    
    # Check if should use demo data
    if not is_premium and task_tree_info.get('llm_quota_exceeded'):
        # Return demo result
        demo_result = DemoResultsCache.get_result(task_id)
        if demo_result:
            return {
                "task_id": task_id,
                "status": "completed",
                "result": demo_result,
                "demo_mode": True,
                "reason": "llm_quota_exceeded"
            }
    
    # Proceed with normal execution
    result = await original_task_execute(request, task_id)
    
    # Track execution
    UsageTracker.track_task_execution(
        task_id=task_id,
        user_id=user_id,
        used_demo_result=False
    )
    
    return result
```

### 4.3 Executor Integration

**Question: Does executor need to return demo data?**

**Answer: Yes, executor integration is recommended for the following reasons:**

1. **Granular Control**: Executor-level interception provides fine-grained control over LLM API calls
2. **Cost Efficiency**: Prevents unnecessary API calls even if quota check is missed at higher levels
3. **Consistency**: Ensures demo data is used consistently across all execution paths
4. **Error Handling**: Can gracefully handle quota exceeded scenarios during execution

**Implementation Approach:**

Create a custom executor wrapper that checks quota before LLM API calls:

```python
class QuotaAwareExecutor:
    """Executor wrapper that checks quota before LLM API calls"""
    
    def __init__(self, original_executor, user_id: str, task_tree_id: str):
        self.original_executor = original_executor
        self.user_id = user_id
        self.task_tree_id = task_tree_id
    
    async def execute(self, task: Task, inputs: dict) -> dict:
        # Check if executor requires LLM
        if self.requires_llm():
            # Check quota
            quota_info = RateLimiter.get_user_quota_status(self.user_id)
            
            if quota_info.get('llm_quota_exceeded') and not quota_info.get('is_premium'):
                # Return demo data
                demo_result = DemoResultsCache.get_result(task.id)
                if demo_result:
                    return demo_result
        
        # Proceed with normal execution
        return await self.original_executor.execute(task, inputs)
    
    def requires_llm(self) -> bool:
        """Check if executor requires LLM API calls"""
        executor_type = type(self.original_executor).__name__.lower()
        return 'llm' in executor_type or 'openai' in executor_type or 'anthropic' in executor_type
```

## 5. Configuration & Limits

### 5.1 Environment Variables

**Quota Configuration:**
```bash
# Free user limits
RATE_LIMIT_DAILY_PER_USER=10                    # Total task trees per day
RATE_LIMIT_DAILY_LLM_PER_USER=1                # LLM-consuming task trees per day

# Premium user limits
RATE_LIMIT_DAILY_PER_USER_PREMIUM=10           # Total task trees per day (no separate LLM limit)

# Concurrency limits
MAX_CONCURRENT_TASK_TREES=10                    # System-wide concurrent task trees
MAX_CONCURRENT_TASK_TREES_PER_USER=1            # Per-user concurrent task trees

# Database configuration
# If DATABASE_URL is missing, defaults to: 
# duckdb:///.data/apflow-demo.duckdb
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/db

# Demo mode
DEMO_MODE=true                                   # Enable demo mode
RATE_LIMIT_ENABLED=true                          # Enable rate limiting
```

### 5.2 Default Values

| Configuration | Free User | Premium User |
|--------------|-----------|--------------|
| Total Daily Quota | 10 | 10 |
| LLM-consuming Quota | 1 | 10 (no separate limit) |
| Concurrent Task Trees (per user) | 1 | 1 |
| System-wide Concurrent | 10 | 10 |

### 5.3 Per-User Overrides

**Future Enhancement:**
- Admin API to override per-user limits
- Database storage for custom limits
- Priority-based quota allocation

## 6. Demo Data Mechanism

### 6.1 Demo Data Storage

**Location:**
- `demo/precomputed_results/` directory
- JSON files named by task ID: `{task_id}.json`

**Loading:**
- Loaded on application startup via `DemoResultsCache._load_cache()`
- Cached in memory for fast access
- Updated when new demo results are pre-computed

### 6.2 Demo Data Format

**Task Tree Generation Demo Data:**
```json
{
  "demo_mode": true,
  "reason": "llm_quota_exceeded",
  "task_tree": {
    "root_task_id": "demo_root_001",
    "tasks": [
      {
        "id": "demo_root_001",
        "name": "Demo Task",
        "status": "pending",
        "executor": "demo_executor"
      }
    ]
  }
}
```

**Task Execution Demo Data:**
```json
{
  "id": "task_id",
  "status": "completed",
  "result": {
    "output": "This is a pre-computed demo result",
    "metadata": {
      "demo_mode": true,
      "original_task_id": "task_id"
    }
  },
  "progress": 1.0,
  "started_at": "2024-01-15T10:00:00Z",
  "completed_at": "2024-01-15T10:05:00Z"
}
```

### 6.3 Demo Data Matching

**Task ID Matching:**
- Exact match: Use task ID to look up demo result
- Pattern matching: Use task type/name to find similar demo results
- Fallback: Return generic demo result if specific match not found

**Implementation:**
```python
def get_demo_result(task_id: str, task_type: str = None) -> Optional[dict]:
    """Get demo result for task"""
    # Try exact match
    result = DemoResultsCache.get_result(task_id)
    if result:
        return result
    
    # Try pattern matching by task type
    if task_type:
        similar_tasks = DemoResultsCache.find_similar_tasks(task_type)
        if similar_tasks:
            return DemoResultsCache.get_result(similar_tasks[0])
    
    # Return generic demo result
    return get_generic_demo_result(task_type)
```

## 7. API Specifications

### 7.1 Response Format When Using Demo Data

**Success Response with Demo Data:**
```json
{
  "result": {
    "task_id": "task_123",
    "status": "completed",
    "result": {
      "output": "demo result data"
    }
  },
  "demo_mode": true,
  "demo_reason": "llm_quota_exceeded",
  "quota_info": {
    "user_quota_used": 1,
    "user_quota_limit": 1,
    "total_quota_used": 5,
    "total_quota_limit": 10
  }
}
```

### 7.2 Error Messages for Quota Exceeded

**Total Quota Exceeded:**
```json
{
  "error": {
    "code": -32001,
    "message": "Daily task tree quota exceeded",
    "data": {
      "reason": "total_quota_exceeded",
      "user_quota_used": 10,
      "user_quota_limit": 10,
      "reset_time": "2024-01-16T00:00:00Z"
    }
  }
}
```

**Concurrency Limit Exceeded:**
```json
{
  "error": {
    "code": -32002,
    "message": "Concurrency limit reached",
    "data": {
      "reason": "concurrency_limit_exceeded",
      "current_concurrent": 10,
      "max_concurrent": 10,
      "user_concurrent": 1,
      "max_user_concurrent": 1
    }
  }
}
```

### 7.3 Usage Statistics Endpoints

**Get User Quota Status:**
```
GET /api/quota/status
Headers: Authorization: Bearer <token>

Response:
{
  "user_id": "user123",
  "quota": {
    "total_used": 5,
    "total_limit": 10,
    "llm_used": 1,
    "llm_limit": 1,
    "reset_time": "2024-01-16T00:00:00Z"
  },
  "concurrency": {
    "current": 1,
    "max": 1
  },
  "is_premium": false
}
```

**Get System Statistics:**
```
GET /api/quota/system-stats
Headers: Authorization: Bearer <admin_token>

Response:
{
  "total_concurrent": 8,
  "max_concurrent": 10,
  "total_users_active": 8,
  "quota_distribution": {
    "free_users": 5,
    "premium_users": 3
  }
}
```

## 8. Error Handling

### 8.1 Quota Exceeded Scenarios

**Scenario 1: Free User Exceeds LLM-consuming Quota**
- Action: Return demo data for `task.generate()` and `task.execute()`
- Response: Include `demo_mode: true` flag
- Status Code: 200 (success, but with demo data)

**Scenario 2: Free User Exceeds Total Quota**
- Action: Reject new task tree creation
- Response: Error message with quota information
- Status Code: 429 (Too Many Requests)

**Scenario 3: Premium User Exceeds Total Quota**
- Action: Reject new task tree creation
- Response: Error message with quota information
- Status Code: 429 (Too Many Requests)

**Scenario 4: System Concurrency Limit Reached**
- Action: Reject new task tree creation
- Response: Error message with concurrency information
- Status Code: 429 (Too Many Requests)

### 8.2 Demo Data Unavailable

**Scenario: Demo result not found for task**
- Action: Return generic demo result or error
- Fallback: Use task type to find similar demo result
- Last Resort: Return error indicating demo data unavailable


## 9. Future Enhancements

### 9.1 Advanced Quota Management

- **Dynamic Quota Adjustment**: Adjust quotas based on system load
- **Priority-based Quota**: Higher priority users get more quota
- **Quota Trading**: Users can trade quota allocations
- **Quota Rollover**: Unused quota carries over to next day (limited)

### 9.2 Enhanced Demo Data

- **Dynamic Demo Generation**: Generate demo data on-the-fly based on task parameters
- **Demo Data Versioning**: Support multiple versions of demo data
- **Demo Data Customization**: Allow users to provide custom demo data

### 9.3 Analytics & Monitoring

- **Quota Usage Dashboard**: Visual dashboard for quota usage
- **Predictive Quota**: Predict when users will exceed quota
- **Cost Tracking**: Track actual LLM API costs vs demo data usage
- **Usage Patterns**: Analyze usage patterns to optimize quotas

### 9.4 Multi-Tenancy Support

- **Organization-level Quotas**: Quotas at organization level
- **Team Quotas**: Shared quotas for teams
- **Quota Pools**: Pool quotas across multiple users

## 10. Implementation Checklist

### Phase 1: Core Quota System
- [ ] Enhance `RateLimiter` with LLM-consuming task tree tracking
- [ ] Implement concurrent task tree tracking
- [ ] Add user type detection (free vs premium)
- [ ] Implement system-wide concurrency limits

### Phase 2: Task Tree Detection
- [ ] Implement LLM-consuming task detection logic
- [ ] Add task tree classification (LLM vs non-LLM)
- [ ] Create task tree metadata storage

### Phase 3: Demo Data Integration
- [ ] Enhance `DemoResultsCache` for task tree matching
- [ ] Implement demo data injection in `task.generate()`
- [ ] Implement demo data injection in `task.execute()`
- [ ] Create executor wrapper for quota checking

### Phase 4: API Integration
- [ ] Create route wrappers for apflow routes
- [ ] Implement quota status endpoints
- [ ] Add error handling for quota exceeded scenarios
- [ ] Add demo mode indicators in responses

### Phase 5: Testing & Validation
- [ ] Unit tests for quota checking logic
- [ ] Integration tests for demo data fallback
- [ ] Load testing for concurrency limits
- [ ] End-to-end testing with real task trees

### Phase 6: Documentation & Deployment
- [ ] Update API documentation
- [ ] Create user guide for quota system
- [ ] Deploy to staging environment
- [ ] Monitor and optimize performance

## Appendix A: Database Schema (SQLAlchemy)

**Table: `demo_users`** (Stores user persistence and metadata)
- `user_id`: String(255), PK
- `username`: String(255), Not Null
- `status`: String(20), Default: 'active'
- `user_agent`: String(500), Nullable
- `source`: String(50), Nullable
- `created_at`: DateTime(timezone=True)
- `last_active_at`: DateTime(timezone=True)

**Table: `demo_quota_counters`** (Daily usage tracking)
- `user_id`: String(255), PK
- `date`: String(10), PK (ISO Date)
- `counter_type`: String(50), PK ('total' or 'llm')
- `count`: Integer

**Table: `demo_concurrency_counters`** (Real-time concurrency)
- `scope`: String(50), PK ('system' or 'user')
- `identifier`: String(255), PK ('global' or user_id)
- `count`: Integer

## Appendix B: Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RATE_LIMIT_DAILY_PER_USER` | 10 | Total task trees per day for free users |
| `RATE_LIMIT_DAILY_LLM_PER_USER` | 1 | LLM-consuming task trees per day for free users |
| `RATE_LIMIT_DAILY_PER_USER_PREMIUM` | 10 | Total task trees per day for premium users |
| `MAX_CONCURRENT_TASK_TREES` | 10 | System-wide concurrent task trees |
| `MAX_CONCURRENT_TASK_TREES_PER_USER` | 1 | Per-user concurrent task trees |
| `DEMO_MODE` | `false` | Enable demo mode |
| `RATE_LIMIT_ENABLED` | `false` | Enable rate limiting |

## Appendix C: Glossary

- **Task Tree**: Hierarchical structure of related tasks
- **LLM-consuming**: Requires Language Model API calls
- **Free User**: User without LLM API key in headers
- **Premium User**: User with LLM API key in headers
- **Daily Quota**: Maximum task trees allowed per day
- **Concurrency Limit**: Maximum simultaneous task trees
- **Demo Data**: Pre-computed results used when quota exceeded
- **Quota Reset**: Daily reset at midnight UTC

---

**Document Version**: 1.0  
**Last Updated**: 2024-01-15  
**Author**: apflow-demo Team

