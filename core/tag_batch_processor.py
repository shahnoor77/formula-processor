import re
from typing import List, Tuple, Dict, Optional
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import structlog

from infra.db_connection import db
from core.config import settings
from core.formula_engine.formula_loader import formula_loader, FormulaInfo
from core.formula_engine.formula_executor import formula_executor
logger = structlog.get_logger()

# Detect outer aggregate wrapping the entire formula
_OUTER_AGG = re.compile(r'^\s*(sum|avg|average)\s*\((.+)\)\s*$', re.IGNORECASE | re.DOTALL)


def extract_node_ids(formula: str) -> List[str]:
    return list(set(re.findall(r'\[([^\]]+)\]', formula)))


def fetch_all_latest_values() -> Dict[str, float]:
    """Fetch latest value per node. Retries once on connection failure."""
    query = f"""
    SELECT t.NodeId, t.value
    FROM {settings.table_source} t
    INNER JOIN (
        SELECT NodeId, MAX(Id) as MaxId FROM {settings.table_source} GROUP BY NodeId
    ) latest ON t.NodeId = latest.NodeId AND t.Id = latest.MaxId
    """
    for attempt in range(2):
        try:
            with db.cursor() as cursor:
                cursor.execute(query)
                result = {}
                for row in cursor.fetchall():
                    try:
                        result[row.NodeId] = float(row.value)
                    except (TypeError, ValueError):
                        pass
                return result
        except Exception as e:
            logger.error("fetch_latest_values_error", attempt=attempt + 1, error=str(e))
            if attempt == 0:
                try:
                    db.connect()
                except Exception:
                    pass
    return {}


def fetch_node_readings_in_window(node_id: str, window_start: datetime, window_end: datetime) -> List[float]:
    """
    Fetch all values for a node between window_start and window_end.
    Uses CreatedOn (DB insert time) instead of timestamp (device time)
    to avoid timezone inconsistencies between device and DB server.
    """
    query = f"""
    SELECT value FROM {settings.table_source}
    WHERE NodeId = ?
      AND CreatedOn >= ?
      AND CreatedOn <= ?
    ORDER BY CreatedOn ASC
    """
    values = []
    try:
        with db.cursor() as cursor:
            cursor.execute(query, (node_id, window_start, window_end))
            for row in cursor.fetchall():
                try:
                    values.append(float(row.value))
                except (TypeError, ValueError):
                    pass
    except Exception as e:
        logger.error("fetch_node_readings_error", node_id=node_id, error=str(e))
    return values


def set_formula_interval(variable_id: int, current_interval: datetime, minutes: int) -> datetime:
    """Advance TimeInterval by Time minutes. Returns new deadline."""
    next_interval = current_interval + timedelta(minutes=minutes)
    try:
        with db.cursor() as cursor:
            cursor.execute(
                f"UPDATE {settings.table_variables} SET TimeInterval = ?, UpdatedOn = GETUTCDATE(), UpdatedBy = 'system' WHERE VariableId = ?",
                (next_interval, variable_id)
            )
    except Exception as e:
        logger.error("set_formula_interval_error", variable_id=variable_id, error=str(e))
    return next_interval


def init_formula_interval(variable_id: int, minutes: int) -> datetime:
    """Set initial TimeInterval = NOW + Time for a new formula."""
    next_interval = datetime.utcnow() + timedelta(minutes=minutes)
    try:
        with db.cursor() as cursor:
            cursor.execute(
                f"UPDATE {settings.table_variables} SET TimeInterval = ?, UpdatedOn = GETUTCDATE(), UpdatedBy = 'system' WHERE VariableId = ?",
                (next_interval, variable_id)
            )
        logger.info("interval_initialized", variable_id=variable_id, next_run=next_interval.isoformat())
    except Exception as e:
        logger.error("init_formula_interval_error", variable_id=variable_id, error=str(e))
    return next_interval


def execute_windowed_formula(formula: str, node_ids: List[str], window_start: datetime, window_end: datetime) -> Tuple[Optional[float], Optional[str]]:
    """
    Execute a windowed formula by collecting all readings per node in the window.

    Handles two cases:
    1. Outer aggregate wrapping inner expression: SUM([a] + [b]) or AVG([a] * 2)
       - Fetch all readings for each node
       - Compute inner expression for each aligned reading
       - Apply outer aggregate on results

    2. No outer aggregate: ([a] + [b]) / 2 with Time > 0
       - Use latest value of each node in the window
       - Execute formula directly
    """
    # Fetch all readings for each node in the window
    node_readings: Dict[str, List[float]] = {}
    for node_id in node_ids:
        readings = fetch_node_readings_in_window(node_id, window_start, window_end)
        if readings:
            node_readings[node_id] = readings

    if not node_readings:
        return None, f'NO_DATA_IN_WINDOW: {", ".join(node_ids)}'

    # Check for outer aggregate
    agg_match = _OUTER_AGG.match(formula)

    if agg_match:
        func_name = agg_match.group(1).lower()
        inner_expr = agg_match.group(2).strip()

        # Compute inner expression for each time step
        # Use the minimum number of readings across all nodes
        min_len = min(len(v) for v in node_readings.values())
        computed = []
        for i in range(min_len):
            row_values = {nid: node_readings[nid][i] for nid in node_readings}
            resolved = inner_expr
            for nid, val in row_values.items():
                resolved = resolved.replace(f'[{nid}]', str(val))
            remaining = re.findall(r'\[([^\]]+)\]', resolved)
            if remaining:
                continue  # Skip rows with unresolved nodes
            result, error = formula_executor.execute_single(resolved, list(row_values.values())[0])
            if error is None and result is not None:
                computed.append(result)

        if not computed:
            return None, 'NO_COMPUTABLE_ROWS_IN_WINDOW'

        if func_name == 'sum':
            return sum(computed), None
        else:  # avg / average
            return sum(computed) / len(computed), None

    else:
        # No outer aggregate — use latest value per node in window
        latest_in_window = {nid: readings[-1] for nid, readings in node_readings.items()}
        resolved = formula
        for nid, val in latest_in_window.items():
            resolved = resolved.replace(f'[{nid}]', str(val))
        remaining = re.findall(r'\[([^\]]+)\]', resolved)
        if remaining:
            return None, f'UNRESOLVED_NODE: {", ".join(remaining)}'
        ref_val = list(latest_in_window.values())[0]
        return formula_executor.execute_single(resolved, ref_val)


def process_tag_formulas(tag, formulas: List[FormulaInfo], latest_values: Dict[str, float]) -> List[dict]:
    """Process all continuous (non-windowed) formulas for a single tag."""
    results = []
    processed_on = datetime.now(timezone.utc)
    bracketed = f'[{tag.node_id}]'

    for formula_info in formulas:
        if formula_info.is_windowed:
            continue
        if bracketed not in formula_info.formula:
            continue

        node_ids = extract_node_ids(formula_info.formula)
        node_values = {nid: latest_values[nid] for nid in node_ids if nid in latest_values}
        node_values[tag.node_id] = tag.value

        resolved = formula_info.formula
        for nid, val in node_values.items():
            resolved = resolved.replace(f'[{nid}]', str(val))

        remaining = re.findall(r'\[([^\]]+)\]', resolved)
        if remaining:
            results.append({
                'variable_id': formula_info.variable_id,
                'result': None,
                'error': f'UNRESOLVED_NODE: {", ".join(remaining)}',
                'result_on': tag.timestamp,
                'processed_on': processed_on,
                'time_interval': None,
                'created_by': 'system',
                'tag_id': tag.id
            })
            continue

        result, error = formula_executor.execute_single(resolved, tag.value)
        results.append({
            'variable_id': formula_info.variable_id,
            'result': str(result) if error is None else None,
            'error': error,
            'result_on': tag.timestamp,
            'processed_on': processed_on,
            'time_interval': None,
            'created_by': 'system',
            'tag_id': tag.id
        })

    return results


def process_windowed_formulas(formulas: List[FormulaInfo]) -> List[dict]:
    """Execute all windowed formulas that are due."""
    results = []
    now = datetime.utcnow()
    processed_on = datetime.now(timezone.utc)

    for formula_info in formulas:
        if not formula_info.is_windowed:
            continue

        # Initialize interval if not set
        if formula_info.time_interval is None:
            next_deadline = init_formula_interval(formula_info.variable_id, formula_info.time_window)
            formula_info.time_interval = next_deadline
            continue

        deadline = formula_info.time_interval
        if hasattr(deadline, 'tzinfo') and deadline.tzinfo:
            deadline = deadline.replace(tzinfo=None)

        if now < deadline:
            continue  # Not due yet

        # If deadline is stale (more than one window behind), skip and reset to now
        if (now - deadline).total_seconds() > formula_info.time_window * 60:
            logger.info("stale_interval_reset", variable_id=formula_info.variable_id,
                        stale_deadline=deadline.isoformat())
            next_deadline = init_formula_interval(formula_info.variable_id, formula_info.time_window)
            formula_info.time_interval = next_deadline
            continue

        # Window: from (deadline - Time) to deadline
        window_start = deadline - timedelta(minutes=formula_info.time_window)
        window_end = deadline

        node_ids = extract_node_ids(formula_info.formula)
        if not node_ids:
            next_deadline = set_formula_interval(formula_info.variable_id, deadline, formula_info.time_window)
            formula_info.time_interval = next_deadline
            continue

        result, error = execute_windowed_formula(formula_info.formula, node_ids, window_start, window_end)

        # Advance to next window
        next_deadline = set_formula_interval(formula_info.variable_id, deadline, formula_info.time_window)
        formula_info.time_interval = next_deadline

        if error is None:
            logger.info("windowed_executed",
                        variable_id=formula_info.variable_id,
                        window_start=window_start.isoformat(),
                        window_end=window_end.isoformat(),
                        result=result,
                        next_run=next_deadline.isoformat())
        else:
            logger.warning("windowed_failed", variable_id=formula_info.variable_id, error=error)

        results.append({
            'variable_id': formula_info.variable_id,
            'result': str(result) if error is None else None,
            'error': error,
            'result_on': processed_on,
            'processed_on': processed_on,
            'time_interval': deadline,
            'created_by': 'system',
            'tag_id': None
        })

    return results


class TagRecord:
    def __init__(self, id: int, node_id: str, value: float, timestamp: datetime, quality: str):
        self.id = id
        self.node_id = node_id
        self.value = value
        self.timestamp = timestamp
        self.quality = quality


class TagBatchProcessor:
    def __init__(self, batch_size: int = 500, num_workers: int = 4):
        self.batch_size = batch_size
        self.num_workers = num_workers
        self._last_processed_id = self._get_last_processed_id()
        logger.info("processor_initialized",
                    batch_size=batch_size,
                    num_workers=self.num_workers,
                    last_processed_id=self._last_processed_id)

    def _get_last_processed_id(self) -> int:
        create_sql = f"""
        IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = '{settings.table_processing_state}')
        BEGIN
            CREATE TABLE {settings.table_processing_state} (
                service_name NVARCHAR(100) PRIMARY KEY,
                last_processed_id BIGINT NOT NULL,
                updated_at DATETIME2 DEFAULT GETUTCDATE()
            );
        END
        """
        with db.cursor() as cursor:
            cursor.execute(create_sql)

        with db.cursor() as cursor:
            cursor.execute(f"SELECT last_processed_id FROM {settings.table_processing_state} WHERE service_name = 'formula_processor'")
            row = cursor.fetchone()
            if row:
                stored_id = row.last_processed_id
                if stored_id == 0:
                    cursor.execute(f"SELECT ISNULL(MAX(Id), 0) as max_id FROM {settings.table_source}")
                    max_row = cursor.fetchone()
                    latest_id = max_row.max_id if max_row else 0
                    cursor.execute(
                        f"UPDATE {settings.table_processing_state} SET last_processed_id = ?, updated_at = GETUTCDATE() WHERE service_name = 'formula_processor'",
                        (latest_id,)
                    )
                    logger.info("starting_from_latest", id=latest_id)
                    return latest_id
                return stored_id
            else:
                with db.cursor() as c2:
                    c2.execute(f"SELECT ISNULL(MAX(Id), 0) as max_id FROM {settings.table_source}")
                    max_row = c2.fetchone()
                    latest_id = max_row.max_id if max_row else 0
                with db.cursor() as c3:
                    c3.execute(
                        f"INSERT INTO {settings.table_processing_state} (service_name, last_processed_id) VALUES ('formula_processor', ?)",
                        (latest_id,)
                    )
                logger.info("first_run_starting_from_latest", id=latest_id)
                return latest_id

    def fetch_batch(self) -> List[TagRecord]:
        query = f"""
        SELECT TOP (?) Id, NodeId, value, timestamp, quality
        FROM {settings.table_source}
        WHERE Id > ?
        ORDER BY Id ASC
        """
        with db.cursor() as cursor:
            cursor.execute(query, (self.batch_size, self._last_processed_id))
            rows = cursor.fetchall()
            tags = [
                TagRecord(
                    id=row.Id,
                    node_id=row.NodeId,
                    value=float(row.value),
                    timestamp=row.timestamp,
                    quality=row.quality
                )
                for row in rows
            ]
            if tags:
                logger.info("batch_fetched", count=len(tags), first_id=tags[0].id, last_id=tags[-1].id)
            else:
                logger.info("no_new_tags", last_processed_id=self._last_processed_id)
            return tags

    def process_batch(self) -> Tuple[int, int]:
        formula_loader.refresh_if_needed()
        all_formulas = formula_loader.get_single_formulas() + formula_loader.get_pair_formulas()

        # Windowed formulas run independently of tag batches
        windowed_results = process_windowed_formulas(all_formulas)

        # Continuous formulas run per incoming tag
        tags = self.fetch_batch()
        all_results = list(windowed_results)

        if tags:
            continuous = [f for f in all_formulas if not f.is_windowed]
            if continuous:
                logger.info("executing_formulas", tag_count=len(tags), formula_count=len(continuous))
                latest_values = fetch_all_latest_values()

                try:
                    with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
                        futures = {
                            executor.submit(process_tag_formulas, tag, continuous, latest_values): tag
                            for tag in tags
                        }
                        for future in as_completed(futures):
                            try:
                                all_results.extend(future.result())
                            except Exception as e:
                                logger.error("thread_error", tag_id=futures[future].id, error=str(e))
                except Exception as e:
                    logger.error("threading_error", error=str(e))
                    for tag in tags:
                        all_results.extend(process_tag_formulas(tag, continuous, latest_values))

        successful = [r for r in all_results if r['error'] is None]
        failed = [r for r in all_results if r['error'] is not None]

        logger.info("formulas_executed", successful=len(successful), failed=len(failed))
        if failed:
            logger.warning("formula_failures", count=len(failed), samples=[r['error'] for r in failed[:3]])

        last_id = tags[-1].id if tags else self._last_processed_id
        try:
            self._save_with_transaction(successful, failed, last_id)
            if tags:
                self._last_processed_id = last_id
            logger.info("batch_processed", tags=len(tags), successful=len(successful), failed=len(failed), last_id=last_id)
            return len(tags), len(successful)
        except Exception as e:
            logger.error("transaction_failed", error=str(e))
            return 0, 0

    def _save_with_transaction(self, successful: List[dict], failed: List[dict], last_id: int) -> None:
        try:
            db.connect()
            cursor = db._conn.cursor()

            if successful:
                insert_sql = f"""
                INSERT INTO {settings.table_executions}
                    (VariableId, Result, ResultOn, ProcessedOn, CreatedBy, CreatedOn, IsDeleted)
                VALUES (?, ?, ?, ?, ?, GETUTCDATE(), 0)
                """
                data = [
                    (r['variable_id'], r['result'], r['result_on'], r['processed_on'], r['created_by'])
                    for r in successful
                ]
                cursor.fast_executemany = True
                cursor.executemany(insert_sql, data)
                logger.info("results_saved", count=len(successful))

            if failed:
                cursor.execute(f"""
                IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = '{settings.table_failed_executions}')
                BEGIN
                    CREATE TABLE {settings.table_failed_executions} (
                        Id BIGINT IDENTITY(1,1) PRIMARY KEY,
                        TagId BIGINT NULL,
                        VariableId BIGINT NOT NULL,
                        ErrorMessage NVARCHAR(MAX),
                        FailedAt DATETIME2 NOT NULL DEFAULT GETUTCDATE(),
                        RetryCount INT DEFAULT 0,
                        IsResolved BIT DEFAULT 0
                    );
                END
                ELSE
                BEGIN
                    -- Ensure TagId allows NULL for windowed formula failures
                    IF EXISTS (
                        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                        WHERE TABLE_NAME = '{settings.table_failed_executions}'
                          AND COLUMN_NAME = 'TagId'
                          AND IS_NULLABLE = 'NO'
                    )
                    BEGIN
                        ALTER TABLE {settings.table_failed_executions} ALTER COLUMN TagId BIGINT NULL;
                    END
                END
                """)
                failed_sql = f"""
                INSERT INTO {settings.table_failed_executions} (TagId, VariableId, ErrorMessage, FailedAt, RetryCount, IsResolved)
                VALUES (?, ?, ?, GETUTCDATE(), 0, 0)
                """
                cursor.fast_executemany = True
                cursor.executemany(failed_sql, [(r.get('tag_id'), r['variable_id'], r['error']) for r in failed])

            cursor.execute(
                f"UPDATE {settings.table_processing_state} SET last_processed_id = ?, updated_at = GETUTCDATE() WHERE service_name = 'formula_processor'",
                (last_id,)
            )

            db.commit()
            cursor.close()
            logger.info("transaction_committed", last_id=last_id)

        except Exception as e:
            db.rollback()
            logger.error("transaction_rollback", error=str(e))
            raise
