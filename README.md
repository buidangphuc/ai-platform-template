# FastAPI Backend Template

This repository contains a template for building backend services using FastAPI.

## Requirements

- Docker and Docker Compose
- Python 3.12+
- uv (Python dependency management tool)

## Repository Structure

```plaintext
backend/
├── app/                   # Feature-based modules with versioned API routers
│   ├── admin/api/v1/
│   ├── task/api/v1/
│   └── router.py          # Central router aggregating all feature routers
├── common/                # Shared resources (constants, exceptions, responses, security)
│   ├── log/
│   ├── exception/
│   ├── response/
│   └── security/
├── core/                  # Core setup: configuration, DI, app registration
│   ├── conf/
│   ├── conf_path/
│   └── registrar/
├── database/              # Database and cache layers
│   ├── db/                # ORM models, sessions, migrations
│   └── redis/             # Redis client and caching utilities
├── middleware/            # Custom FastAPI middleware (logging, error handling, rate limiting, etc.)
├── utils/                 # Generic helpers and utility functions
└── tests/                 # Unit and integration tests
```

## Running the Application

### Using Docker Compose (Recommended)

1. Clone the repository:
```bash
git clone <repository-url>
cd <repository-directory>
```

2. Start the development environment:
```bash
docker-compose -f docker-compose.local.yaml up -d
```

This will start all necessary services (API, database, etc.) in development mode with hot reloading enabled.

3. Access the API:
   - API: http://localhost:8000
   - Swagger UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

4. Stop the services:
```bash
docker-compose -f docker-compose.local.yaml down
```

### Manual Setup

1. Install uv:
```bash
pip install uv
```

2. Install dependencies:
```bash
uv sync --dev
```

3. Set up environment variables:
```bash
cp .env.example .env
```

4. Run the application:
```bash
uv run ./scripts/start_dev.sh
```

### Environment Variables

Key environment variables include:

- `ENVIRONMENT`: Runtime environment name
- `POSTGRES_HOST`: PostgreSQL host name
- `POSTGRES_USER`: PostgreSQL user name
- `POSTGRES_PASSWORD`: PostgreSQL password
- `POSTGRES_DB`: PostgreSQL database name
- `REDIS_HOST`: Redis host name
- `REDIS_PORT`: Redis port
- `API_KEY_PEPPER`: Pepper used when hashing API keys
- `TRACE_CONTENT`: Trace content mode, one of `off`, `redacted`, or `full`
- `LLM_PROVIDER`, `EMBEDDING_PROVIDER`, `VECTOR_STORE`, `STORAGE_BACKEND`, `JOB_BACKEND`: Local provider selectors for pluggable services

## Secrets

Copy `.env.example` to `.env` for local development. Keep real secrets in environment variables or your team's secret manager, not in Git. The template does not include Vault, cloud secret manager, or organization-specific secret workflows by default.
