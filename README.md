# Bookly API

Bookly is an asynchronous FastAPI service for managing books, tags, and reviews. It uses SQLAlchemy for persistence, Alembic for database migrations, Redis for token state and rate limiting, and Celery for email delivery.

## Features

- Account signup, email verification, login, logout, and password reset
- JWT access and refresh tokens with rotation and session revocation
- Role-based authorization for users and administrators
- Book creation, browsing, updates, and deletion with ownership checks
- Book tags and user reviews
- Bounded pagination for collection endpoints
- Redis-backed authentication rate limiting
- Background email delivery with retry handling
- OpenAPI, Swagger UI, and ReDoc documentation

## Technology

- Python 3.11+
- FastAPI
- SQLAlchemy 2 with async sessions
- PostgreSQL and asyncpg
- Alembic
- Redis
- Celery
- Pytest and Ruff

## Local setup

Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows PowerShell, activate it with:

```powershell
.venv\Scripts\Activate.ps1
```

Copy the example environment file and adjust it for services running on your machine:

```bash
cp .env.example .env
```

For local development, set `ENVIRONMENT=development`, use `localhost` in the PostgreSQL and Redis URLs, and set `PUBLIC_BASE_URL=http://localhost:8000`.

Apply the database migrations:

```bash
alembic upgrade head
```

Start the API:

```bash
fastapi dev src
```

Start the Celery worker in another terminal:

```bash
celery -A src.celery_tasks.c_app worker --loglevel=INFO
```

The API is available at `http://localhost:8000`.

## Docker setup

Copy `.env.example` to `.env` and replace the example secrets and public URLs. Production mode requires a JWT secret of at least 32 characters and an HTTPS `PUBLIC_BASE_URL`.

Start PostgreSQL and Redis, run the migrations, and then start the application services:

```bash
docker compose up -d db redis
docker compose run --rm web alembic upgrade head
docker compose up --build
```

The API container listens on port `8000`.

## Configuration

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy PostgreSQL connection URL |
| `ENVIRONMENT` | `development`, `test`, or `production` |
| `JWT_SECRET` | Secret used to sign tokens; at least 32 characters in production |
| `JWT_ALGORITHM` | JWT signing algorithm; defaults to `HS256` |
| `REDIS_URL` | Redis connection URL |
| `AUTH_RATE_LIMIT` | Maximum authentication attempts per rate-limit window |
| `AUTH_RATE_WINDOW_SECONDS` | Authentication rate-limit window in seconds |
| `CORS_ORIGINS` | JSON array of allowed browser origins |
| `PUBLIC_BASE_URL` | Public URL used in verification and password-reset links |
| `MAIL_USERNAME` | SMTP username |
| `MAIL_PASSWORD` | SMTP password |
| `MAIL_SERVER` | SMTP server hostname |
| `MAIL_PORT` | SMTP server port |
| `MAIL_FROM` | Sender email address |
| `MAIL_FROM_NAME` | Sender display name |

See `.env.example` for a complete configuration template.

## API documentation

With the application running:

- Swagger UI: `http://localhost:8000/api/v1/docs`
- ReDoc: `http://localhost:8000/api/v1/redoc`
- OpenAPI schema: `http://localhost:8000/api/v1/openapi.json`

The API routes are grouped under:

- `/api/v1/auth`
- `/api/v1/books`
- `/api/v1/tags`
- `/api/v1/reviews`

Protected endpoints require an access token:

```text
Authorization: Bearer <access-token>
```

Book, tag, and review collection endpoints accept `limit` and `offset` query parameters. The maximum permitted `limit` is 100.

## Tests and linting

Run the test suite:

```bash
pytest -q
```

Run Ruff:

```bash
ruff check .
```
