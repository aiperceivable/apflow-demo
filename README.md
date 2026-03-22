# apflow-demo

Demo deployment of apflow with rate limiting and quota management.

This is an independent application that wraps `apflow` (v0.10.0+) as a core library, adding demo-specific features like:
- **LLM Quota Management**: Per-user task tree limits with LLM-consuming restrictions
- **Rate limiting**: Per user/IP daily limits
- **Built-in Demo Mode**: Uses apflow v0.6.0's `use_demo` parameter for automatic demo data fallback
- **User Identification**: Browser fingerprinting + session cookie hybrid approach (no registration required)
- **Demo-specific API middleware**: Quota checking and demo data injection
- **Usage tracking**: Task execution and quota usage statistics
- **Concurrency control**: System-wide and per-user concurrent task tree limits
- **LLM API Key Support**: Supports `X-LLM-API-KEY` header with prefixed format (`openai:sk-...` or `anthropic:sk-ant-...`) or direct format (`sk-...`)
- **Executor Metadata API**: Query executor metadata and schemas using apflow's executor_metadata utilities
- **Executor Demo Tasks**: Automatically generate demo tasks for all executors based on executor_metadata
- **User Management CLI**: Built-in commands to analyze user statistics and activity
- **Automatic Database Setup**: Zero-config initialization with local DuckDB fallback

## Architecture

This application uses `apflow[all]>=0.6.0` as a dependency and leverages new v0.6.0 features:
- **TaskRoutes Extension**: Uses `task_routes_class` parameter (no monkey patching)
- **Task Tree Lifecycle Hooks**: Uses `register_task_tree_hook()` for explicit lifecycle events
- **Executor-Specific Hooks**: Uses `add_executor_hook()` for quota checks at executor level
- **Built-in Demo Mode**: Uses `use_demo` parameter for automatic demo data
- **Automatic User ID Extraction**: Leverages JWT extraction with browser fingerprinting fallback
- **Database Storage**: Uses the same database as apflow (DuckDB/PostgreSQL) for quota tracking, no Redis required

## Quick Start

### Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Start with docker-compose
docker-compose up

# Or run directly
python -m apflow_demo.main
```

### Production

```bash
# Build Docker image
docker build -f docker/Dockerfile -t apflow-demo .

# Run with docker-compose
docker-compose up -d
```

## Configuration

See `.env.example` for configuration options.

Key environment variables:
- `DEMO_MODE=true`: Enable demo mode
- `RATE_LIMIT_ENABLED=true`: Enable rate limiting
- `RATE_LIMIT_DAILY_PER_USER=10`: Total task trees per day (free users)
- `RATE_LIMIT_DAILY_LLM_PER_USER=1`: LLM-consuming task trees per day (free users)
- `RATE_LIMIT_DAILY_PER_USER_PREMIUM=10`: Total task trees per day (premium users)
- `MAX_CONCURRENT_TASK_TREES=10`: System-wide concurrent task trees
- `MAX_CONCURRENT_TASK_TREES_PER_USER=1`: Per-user concurrent task trees
- `RATE_LIMIT_DAILY_PER_IP=50`: Daily limit per IP

**Note**: Rate limiting uses the same database as apflow (DuckDB/PostgreSQL), no Redis required.

## LLM Quota System

The demo includes a comprehensive LLM quota management system:

### User Identification

**No Registration Required**: The demo uses a session cookie + browser fingerprinting hybrid approach:
- **Session Cookie**: Set on first request (`demo_session_id`), persists for 30 days.
- **Browser Fingerprinting**: Generated from `User-Agent` + IP + headers (fallback if cookie cleared).
- **Auto-Login**: Transparently handles guest user creation and session persistence across visits.
- **User-Agent Tracking**: Captures browser/OS metadata to generate descriptive guest usernames (e.g., `Guest_Mac_Chrome_abc123`).
- **Privacy-Friendly**: No personal data collected, fingerprints are hashed.

### Free Users (No LLM Key in Header)
- **Total Quota**: 10 task trees per day
- **LLM-consuming Limit**: Only 1 LLM-consuming task tree per day
- **Concurrency**: 1 task tree at a time
- **Behavior**: When LLM quota exceeded, uses built-in demo mode (`use_demo=True`)

### Premium Users (LLM Key in Header)
- **Total Quota**: 10 task trees per day
- **LLM-consuming Limit**: All 10 can be LLM-consuming (no separate limit)
- **Concurrency**: 1 task tree at a time
- **Behavior**: Uses own LLM API keys, no demo data fallback

### Usage

**Free User Example** (No authentication required):
```bash
# First LLM-consuming task tree - succeeds
# User ID is automatically generated from browser fingerprint
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{"method": "tasks.generate", "params": {"requirement": "..."}}'

# Second LLM-consuming task tree - uses built-in demo mode
# Executor hooks automatically set use_demo=True when quota exceeded
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{"method": "tasks.generate", "params": {"requirement": "..."}}'
```

**Premium User Example** (With LLM API Key):
```bash
# Provide LLM API key in header
# All 10 task trees can be LLM-consuming
# Supported formats:
#   - Prefixed: "openai:sk-xxx..." or "anthropic:sk-ant-xxx..."
#   - Direct: "sk-xxx..." (auto-detected as OpenAI) or "sk-ant-xxx..." (auto-detected as Anthropic)
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -H "X-LLM-API-KEY: openai:sk-xxx..." \
  -d '{"method": "tasks.generate", "params": {"requirement": "..."}}'
```

**Check Quota Status**:
```bash
# User ID is automatically detected from session cookie or browser fingerprint
curl http://localhost:8000/api/quota/status
```

## Executor Metadata API

The demo provides endpoints to query executor metadata using apflow's executor_metadata utilities:

**Get All Executor Metadata**:
```bash
curl http://localhost:8000/api/executors/metadata
```

**Get Specific Executor Metadata**:
```bash
curl http://localhost:8000/api/executors/metadata/system_info_executor
```

The metadata includes:
- `id`: Executor ID
- `name`: Executor name
- `description`: Executor description
- `input_schema`: JSON schema for task inputs
- `examples`: List of example descriptions
- `tags`: List of tags
- `type`: Executor type (optional)

## Executor Demo Tasks Initialization

The demo can automatically create demo tasks for all executors based on executor_metadata:

**Check Demo Init Status**:
```bash
# Check which executors already have demo tasks and which ones can be initialized
curl http://localhost:8000/api/demo/tasks/init-status
```

Response includes:
- `can_init`: Whether demo init can be performed (has executors without demo tasks)
- `total_executors`: Total number of executors
- `existing_executors`: List of executor IDs that already have demo tasks
- `missing_executors`: List of executor IDs that don't have demo tasks yet
- `executor_details`: Details for each executor (id, name, has_demo_task)
- `message`: Status description

**Initialize Executor Demo Tasks**:
```bash
# Creates one demo task per executor with inputs generated from input_schema
# Skips executors that already have demo tasks to avoid duplicates
curl -X POST http://localhost:8000/api/demo/tasks/init-executors
```

Each executor gets a demo task with:
- `schemas.method` = executor_id
- `inputs` = Generated from executor's `input_schema` (uses examples or default values)
- `name` = "Demo: {executor_name}"
- `user_id` = Current user ID (from session cookie or browser fingerprint)

**Note**: The initialization process automatically skips executors that already have demo tasks for the current user, preventing duplicate task creation.

## User Management CLI

The demo includes a plugin for the `apflow-demo` CLI to manage and analyze users.

### List Users
List recently active users with their status and source.
```bash
apflow-demo users list --limit 10
```
Options:
- `--limit` (`-l`): Number of users to display (default: 20)
- `--status` (`-s`): Filter by status (`active`, `inactive`)
- `--format` (`-f`): Output format (`table`, `json`)
- `--show-ua`: Show full User-Agent string in the output

### User Statistics
Display aggregate user statistics for different time periods.
```bash
apflow-demo users stat day
```
Available periods: `all`, `day`, `week`, `month`, `year`.

## Database Management

The application features **Automatic Database Initialization**.

- **Zero-Config**: If `DATABASE_URL` is not set in `.env` or environment, it automatically creates a DuckDB database at `.data/apflow-demo.duckdb`.
- **Sync/Async Support**: Fully compatible with both synchronous (DuckDB) and asynchronous (PostgreSQL) engines.
- **Auto-Migration**: Automatically adds missing columns (like `user_agent`) to existing tables during startup.

## Local Development

```bash
# Start with docker-compose
docker-compose up

# Or run directly (uses same database as apflow)
# Option 1: run module directly
python -m apflow_demo.main

# Option 2: use the packaged CLI wrapper (recommended for demo features)
# After `pip install -e .`, run the wrapper which preloads demo extensions:
```bash
apflow-demo tasks all --limit 3
```
```

### Production Deployment

1. **Build Docker image**:
   ```bash
   docker build -f docker/Dockerfile -t apflow-demo:latest .
   ```

2. **Deploy with docker-compose**:
   ```bash
   docker-compose up -d
   ```

3. **Or deploy to cloud**:
   - Update environment variables in `.env` or docker-compose.yml
   - Set `DEMO_MODE=true` and `RATE_LIMIT_ENABLED=true`
   - Configure database connection (same as apflow)
   - Deploy to your cloud provider

### Integration with apflow-webapp

1. **Deploy demo API** (this repository) to your server
2. **Deploy apflow-webapp** and configure it to point to demo API:
   ```bash
   NEXT_PUBLIC_API_URL=https://demo-api.aiperceivable.com
   ```
3. **Add demo link** in aiperceivable-website (already configured)

## License

Apache-2.0

