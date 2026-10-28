> # ⚠️ ARCHIVED — not maintained, does not run against current apflow
>
> This repository is **archived** as of 2026-07-18 and is kept for reference only.
>
> **Why:** `apflow-demo` was a *hosted, anonymous public trial layer* for apflow
> (rate limiting, per-user quota, browser-fingerprint identity, BYO-key). It is
> pinned to **apflow 0.17.0**, while apflow is now **0.22.1** — a full
> architecture generation ahead. apflow 0.22 removed the integration seams this
> demo relied on (`apflow.api.a2a.server` tokens, `llm_key_context`, the typer
> CLI-plugin API, route-class injection), so **this code no longer installs or
> runs** without a rewrite-scale migration.
>
> **What to use instead:**
> - **Learn / try apflow** → the apflow repo's own `examples/quickstart.py`,
>   `docs/getting-started/`, and `llms.txt`.
> - **Interactive UI** → [`apflow-webapp`](https://github.com/aiperceivable/apflow-webapp)
>   (self-hosted, for trusted/authenticated users).
>
> **Why it's kept, not deleted:** the anonymous rate-limit / quota / BYO-key
> machinery here is a ready-made blueprint if a hosted public SaaS trial is ever
> revived — it should be **rebuilt against the then-current apflow**, not resurrected
> from this 0.17-era code.
>
> The code and documentation below describe a subsequent migration to apflow 0.24.1.
> The repository remains archived; the legacy hosted trial described above is not restored.

---

# apflow-demo

A demo A2A server built on apflow 0.24.1 or later. It provides browser session cookies, user activity tracking and administrative user endpoints alongside apflow's native A2A capabilities.

## Requirements

- Python 3.11 or newer
- apflow 0.24.1 or newer
- SQLite, or PostgreSQL with the apflow PostgreSQL dependencies

## Development

```bash
python -m pip install -e '.[dev]'
cp .env.example .env
# Set APFLOW_JWT_SECRET to a unique random value before starting the server.
python -m apflow_demo.main
```

If apflow 0.24.1 is not available in your package index and you have a local checkout at `../apflow`, install that checkout first:

```bash
python -m pip install -e '../apflow[all]'
python -m pip install -e '.[dev]'
```

The server listens on port 8000 by default. Call `GET /auth/auto-login` to obtain an HTTP-only session cookie, then use the cookie or a signed Bearer token with the A2A API. The agent card at `/.well-known/agent-card.json` lists available SDK skills. For background execution, start the apflow dispatcher separately against the same database; task submission alone does not run a dispatcher.

```bash
apflow-demo dispatcher
```

To run with Docker Compose, create `.env` first and then run `docker compose up --build`. The image installation requires apflow 0.24.1 to be available from the package index used during the build.

## Configuration

- `DATABASE_URL`: SQLite or PostgreSQL connection string. When unset, the application uses `.data/apflow-demo.sqlite3`.
- `APFLOW_JWT_SECRET` and `APFLOW_JWT_ALGORITHM`: signing key and algorithm for demo sessions.
- `APFLOW_API_HOST`, `APFLOW_API_PORT`, and `APFLOW_BASE_URL`: listener and advertised A2A address.
- `APFLOW_CORS_ORIGINS`: comma-separated allowed browser origins.
- `APFLOW_DEMO_API_URL` and `APFLOW_DEMO_ADMIN_TOKEN`: optional API URL and Bearer token for user-management CLI commands; without an API URL, the CLI reads the local database.

The service uses the same database as apflow. Existing DuckDB databases are not converted automatically: export or migrate the data separately before switching `DATABASE_URL` to SQLite or PostgreSQL. Database upgrades for existing apflow installations must follow apflow's migration guidance; creating missing tables does not migrate existing tables.

## Removed legacy features

The old demo task quotas, request rate limiting, demo result fallback, per-request LLM-key handling, executor metadata endpoints and automatic example-task creation were removed because they do not match apflow 0.24.1's execution and A2A interfaces. Old `RATE_LIMIT_*`, `MAX_CONCURRENT_TASK_TREES*`, and `DEMO_MODE` settings no longer provide these features. In particular, setting `RATE_LIMIT_ENABLED=true` does **not** enable rate limiting. Configure any required limits in an appropriate gateway or other supported system before exposing the service.

The old quota and demo-task tables, if present, are not deleted by this upgrade. The removed HTTP endpoints are `/api/quota/*`, `/api/demo/tasks/*`, and `/api/executors/metadata*`. Use the apflow A2A agent card to discover SDK capabilities instead.

## Tests

```bash
python -m pytest
```

The tests should use an isolated database rather than production data. A2A integration tests create temporary SQLite databases.

## License

Apache-2.0
