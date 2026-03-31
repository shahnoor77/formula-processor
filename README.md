# Formula Processor

## Problem Statement

Industrial machines generate continuous sensor data via OPC-UA/MQTT protocols. This raw data — temperature, pressure, speed, flow rate, etc. — needs to be transformed into meaningful calculated values using formulas defined by process engineers. These formulas change over time as processes evolve, and the system must handle those changes without downtime or manual intervention.

The challenge: how do you run an arbitrary set of user-defined formulas against a continuous stream of sensor data, reliably, at scale, without requiring code changes every time a formula is added or modified?

---

## Background

The data pipeline works as follows:

1. OPC-UA devices publish sensor readings
2. An MQTT subscriber writes those readings to a SQL Server table (`MQTT_OPC_UA_Data`) with a `NodeId` identifying the sensor
3. Process engineers define formulas in a `Variables` table using the node ID in brackets: `[ns=2;s=Channel1.Device1.Pressure]`
4. Calculated results need to be stored in an `Executions` table for downstream reporting and analysis

Before this system, there was no automated way to evaluate these formulas against live data. Results were either calculated manually or not at all.

---

## Possible Solutions

**Option 1 — Scheduled SQL jobs**
Write SQL stored procedures that run on a schedule. Simple but inflexible — adding a new formula requires a DBA, and complex math is awkward in SQL.

**Option 2 — Event-driven triggers**
Database triggers that fire on insert. Fast but hard to maintain, difficult to debug, and SQL Server triggers have limitations on complex expressions.

**Option 3 — External processing service**
A separate service that reads from the source table, evaluates formulas using a proper expression engine, and writes results back. More infrastructure but full flexibility.

---

## Our Approach

We built an external processing service in Python that:

- Continuously polls `MQTT_OPC_UA_Data` for new tag readings
- Loads all active formulas from the `Variables` table (refreshes every 30 seconds)
- For each incoming tag, finds all formulas that reference that node ID
- Resolves any other node IDs in the formula by fetching their latest values
- Evaluates the formula using a safe AST-based expression compiler
- Saves results to the `Executions` table atomically

For formulas with a time window (`Time > 0`), the engine collects all readings within that window and applies the aggregate function (SUM, AVG) across all readings before saving a single result.

---

## Why This Approach

- **No code changes for new formulas** — engineers add/update formulas in the DB, the engine picks them up within 30 seconds
- **Any formula syntax** — the engine normalizes `IF/THEN/ELSE`, `AVG()`, `SUM()`, and standard math expressions before evaluation
- **Safe execution** — uses Python AST parsing, not `eval()`. Only whitelisted operators and functions are allowed
- **Fault tolerant** — failed formula executions are logged to `FailedExecutions` without stopping the engine
- **Consistent time windows** — uses DB insert time (`CreatedOn`) for window queries to avoid device clock drift issues

---

## How It Works

### Continuous formulas (`Time = 0` or NULL)
- Engine fetches batches of 500 new tags
- For each tag, matches formulas containing `[NodeId]`
- Resolves all node references, evaluates, saves result
- Runs in parallel using 4 worker threads

### Windowed formulas (`Time > 0`)
- On first load, sets `TimeInterval = NOW + Time minutes`
- Waits until `TimeInterval` is reached
- Collects all readings for referenced nodes from `CreatedOn >= window_start AND CreatedOn <= window_end`
- Evaluates formula (with aggregate if present), saves single result
- Advances `TimeInterval` by `Time` minutes for next window

### Formula syntax supported
```
[node_id] * 0.001
([node_a] + [node_b]) / 2
1 if [node_id] > 100 else 0
SUM([node_id])                    # windowed: sum all readings in window
AVG([node_a] + [node_b])          # windowed: avg of (a+b) per reading
IF (cond) THEN expr ELSE expr     # converted to Python ternary
AVG(a, b, c)                      # multi-argument average
```

---

## Setup

**Requirements:** Docker, SQL Server (external)

1. Copy and fill in credentials:
```bash
cp deploy/.env.example deploy/.env
```

2. Add required columns to your DB:
```sql
ALTER TABLE Variables ADD TimeInterval DATETIME2 NULL;
ALTER TABLE Variables ADD FormulaType NVARCHAR(50) DEFAULT '';
```

3. Run:
```bash
cd deploy
docker-compose up -d
```

4. Check health:
```
GET http://your-server:8000/system/health
```

---

## Configuration (`.env`)

| Variable | Description |
|---|---|
| `DB_SERVER` | SQL Server host |
| `DB_DATABASE` | Database name |
| `DB_USERNAME` / `DB_PASSWORD` | Credentials |
| `BATCH_SIZE` | Tags per batch (default 500) |
| `POLL_INTERVAL_MS` | Poll interval when idle (default 1000ms) |
| `TABLE_SOURCE` | Source table name |
| `TABLE_VARIABLES` | Formulas table name |
| `TABLE_EXECUTIONS` | Results table name |

---

## API

| Method | Path | Description |
|---|---|---|
| GET | `/system/health` | Health check |
| GET | `/system/stats` | Processing stats |
| GET | `/system/raw-data` | Latest raw tags |
| GET | `/variables/formulas` | Active formulas |
| GET | `/variables/executions` | Latest results |
| POST | `/variables/test-formula` | Test a formula manually |
| POST | `/variables/refresh` | Force formula cache reload |
