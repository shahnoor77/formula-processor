# SQL Server Calculation Engine

A high-performance, production-ready calculation engine for processing IoT sensor data with dynamic formula evaluation. Built with Python 3.12, this system processes raw machine data from SQL Server, evaluates complex formulas, and stores calculated results in real-time.

## Features

- **Dynamic Formula Evaluation**: Safe AST-based formula compilation (no eval())
- **Complex IoT Formulas**: Support for conditional logic, boolean operators, mathematical functions
- **Incremental Processing**: Batch processing with crash recovery using last_processed_id
- **Formula Caching**: Version-tracked formula caching for optimal performance
- **Atomic Transactions**: Ensures data consistency during failures
- **Structured Logging**: JSON logging with structlog for production monitoring
- **Auto-Generated Calculations**: Dynamically creates calculations for any available tags
- **Dockerized**: Complete containerization with Docker Compose

## Supported Formula Types

- **Conditional Logic**: `if/else` statements
- **Boolean Operators**: `and`, `or` logic
- **Comparison Operators**: `>`, `<`, `>=`, `<=`, `==`, `!=`
- **Mathematical Functions**: `sqrt`, `pow`, `abs`, `min`, `max`, `round`
- **Arithmetic Operations**: `+`, `-`, `*`, `/`, `//`, `%`, `**`
- **Multi-Conditional**: Nested conditional expressions

## Architecture

```
┌─────────────────┐
│  SQL Server     │
│  (MachineData)  │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────┐
│  Calculation Engine             │
│  ┌───────────────────────────┐  │
│  │ Formula Registry Cache    │  │
│  └───────────────────────────┘  │
│  ┌───────────────────────────┐  │
│  │ Incremental Batch Reader  │  │
│  └───────────────────────────┘  │
│  ┌───────────────────────────┐  │
│  │ AST Formula Evaluator     │  │
│  └───────────────────────────┘  │
│  ┌───────────────────────────┐  │
│  │ Bulk Result Writer        │  │
│  └───────────────────────────┘  │
└─────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│  SQL Server     │
│ (calculated_tags)│
└─────────────────┘
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- SQL Server (running separately or via Docker)
- Python 3.12+ (for local development)
- Poetry (for dependency management)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/shahnoor77/sql-calculation-engine.git
cd sql-calculation-engine
```

2. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your database credentials
```

3. Set up the database schema:
```bash
# Connect to your SQL Server and run:
sqlcmd -S localhost,1433 -U sa -P YourPassword -i sql/01_create_tables.sql
```

4. Add sample formulas (optional):
```bash
sqlcmd -S localhost,1433 -U sa -P YourPassword -i sql/02_sample_formulas.sql
sqlcmd -S localhost,1433 -U sa -P YourPassword -i sql/06_test_working_formulas.sql
```

5. Start the calculation engine:
```bash
docker-compose up -d --build
```

### Verify Installation

Check the logs:
```bash
docker logs calculation_engine --tail 50
```

You should see:
- Formulas being compiled
- Batches being processed
- Results being generated

## Configuration

Edit `.env` file:

| Variable | Description | Default |
|----------|-------------|---------|
| DB_SERVER | SQL Server hostname | localhost |
| DB_PORT | SQL Server port | 1433 |
| DB_DATABASE | Database name | TestDB |
| DB_USERNAME | Database user | sa |
| DB_PASSWORD | Database password | - |
| BATCH_SIZE | Records per batch | 500 |
| POLL_INTERVAL_MS | Polling interval | 200 |
| SERVICE_NAME | Service identifier | calculation_service |
| FORMULA_REFRESH_SECONDS | Formula cache refresh | 30 |

## Database Schema

### formula_registry
Stores formula definitions:
```sql
CREATE TABLE formula_registry (
    id INT PRIMARY KEY,
    calculated_tag VARCHAR(100) NOT NULL,
    expression NVARCHAR(MAX) NOT NULL,
    version INT NOT NULL DEFAULT 1,
    is_active BIT NOT NULL DEFAULT 1,
    updated_at DATETIME2 DEFAULT SYSUTCDATETIME()
);
```

### calculated_tags
Stores calculation results:
```sql
CREATE TABLE calculated_tags (
    id BIGINT IDENTITY PRIMARY KEY,
    calculated_tag VARCHAR(100) NOT NULL,
    calculated_value FLOAT NOT NULL,
    source_timestamp DATETIME2 NOT NULL,
    calculated_at DATETIME2 DEFAULT SYSUTCDATETIME()
);
```

### calculation_state
Tracks processing state:
```sql
CREATE TABLE calculation_state (
    service_name VARCHAR(50) PRIMARY KEY,
    last_processed_id BIGINT NOT NULL DEFAULT 0,
    updated_at DATETIME2 DEFAULT SYSUTCDATETIME()
);
```

## Formula Examples

### Simple Conditional
```python
'1.0 if alarm_0001 > 15000 else 0.0'
```

### Boolean Logic
```python
'1.0 if (alarm_0003 >= 10000 and alarm_0003 <= 25000) else 0.0'
```

### Multi-Conditional
```python
'100.0 if (alarm_0012 < 20000 and alarm_0013 > 10000) else (50.0 if alarm_0012 < 25000 else 0.0)'
```

### Mathematical Functions
```python
'alarm_0019 / sqrt(pow(alarm_0019, 2) + pow(alarm_0020, 2)) if (pow(alarm_0019, 2) + pow(alarm_0020, 2)) > 0 else 0.0'
```

### OEE Calculation
```python
'(alarm_0010 / alarm_0011) * 100 if alarm_0011 > 0 else 0.0'
```

## Monitoring

### PowerShell Monitoring Scripts

Monitor raw data:
```powershell
.\monitor_raw_data.ps1
```

Monitor formulas:
```powershell
.\monitor_formulas.ps1
```

Monitor calculated results:
```powershell
.\monitor_calculated_tags.ps1
```

### Verification Scripts

Verify dynamic calculations:
```powershell
.\verify_dynamic_calculations.ps1
```

Verify complex formulas:
```powershell
.\verify_complex_formulas.ps1
```

Check all formulas status:
```powershell
.\verify_all_formulas.ps1
```

## Performance

- **Throughput**: 10,000+ tags/second
- **Batch Processing**: 500 records per batch (configurable)
- **Formula Caching**: Version-tracked, no recompilation unless changed
- **Incremental Processing**: Only processes new records
- **Connection Pooling**: Efficient database connection management

## Development

### Local Setup

1. Install Poetry:
```bash
pip install poetry
```

2. Install dependencies:
```bash
poetry install
```

3. Run locally:
```bash
poetry run python -m calculation_engine.main
```

### Project Structure

```
calculation_engine/
├── calculation_engine/
│   ├── __init__.py
│   ├── main.py              # Entry point
│   ├── config.py            # Configuration management
│   ├── models.py            # Data models
│   ├── logger.py            # Structured logging
│   ├── database.py          # Database operations
│   ├── formula_engine.py    # Formula compilation & evaluation
│   └── processor.py         # Main processing loop
├── sql/
│   ├── 01_create_tables.sql
│   ├── 02_sample_formulas.sql
│   ├── 04_complex_formulas.sql
│   ├── 05_query_complex_formulas.sql
│   └── 06_test_working_formulas.sql
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── README.md
```

## Documentation

- [System Summary](SYSTEM_SUMMARY.md) - Detailed system architecture
- [Complex Formulas Guide](COMPLEX_FORMULAS_GUIDE.md) - Formula reference
- [Data Flow Explanation](DATA_FLOW_EXPLANATION.md) - Processing pipeline

## Troubleshooting

### Container won't start
```bash
docker logs calculation_engine
```

### No results being generated
1. Check if formulas are active: `SELECT * FROM formula_registry WHERE is_active = 1`
2. Check if raw data exists: `SELECT COUNT(*) FROM MachineData`
3. Verify tag names match between formulas and data

### Formula compilation errors
Check logs for specific error messages. Common issues:
- Unsupported functions (only safe functions allowed)
- Missing tags in data
- Syntax errors in expressions

## Security

- No `eval()` usage - safe AST-based evaluation only
- Sandboxed formula execution
- No attribute access or imports allowed in formulas
- Environment-based configuration (no hardcoded credentials)
- SQL injection protection via parameterized queries

## License

MIT License - See LICENSE file for details

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## Author

**Shahnoor** - [GitHub](https://github.com/shahnoor77)

## Acknowledgments

- Built for high-performance IoT data processing
- Designed for industrial-scale deployments
- Production-tested with 100k+ records/minute
