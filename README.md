# Formula Processor

Processes raw IoT tag data from SQL Server, evaluates formulas, and stores results.

## Requirements

- Docker & Docker Compose
- SQL Server (external)
- Python 3.12+ / Poetry (for local dev only)

## Setup

1. Copy and configure environment:
```bash
cp .env.example .env
# fill in your DB credentials and table names
```

2. Run:
```bash
docker-compose up --build -d
```

3. Check health:
```
GET http://localhost:8000/system/health
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /system/health | Health check |
| GET | /system/stats | Processing stats |
| GET | /system/raw-data | Latest raw tags |
| GET | /variables/formulas | List active formulas |
| GET | /variables/executions | Latest executions |
| GET | /variables/executions/summary | Summary per formula |
| POST | /variables/refresh | Reload formula cache |
| POST | /variables/test-formula | Test a formula manually |

## Configuration

See `.env.example` for all available settings.

## Local Dev

```bash
poetry install
poetry run python main.py
```
