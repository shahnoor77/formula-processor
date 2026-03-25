import re
from typing import List, Tuple, Dict
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import structlog

from infra.db_connection import db
from core.config import settings
from core.formula_engine.formula_loader import formula_loader
from core.formula_engine.formula_executor import formula_executor

INTERVAL_DURATION_SECONDS = 10 * 60

logger = structlog.get_logger()


class TagRecord:
    def __init__(self, id: int, node_id: str, value: float, timestamp: datetime, quality: str):
        self.id = id
        self.node_id = node_id
        self.value = value
        self.timestamp = timestamp
        self.quality = quality


def fetch_all_latest_values() -> Dict[str, float]:
    """Fetch the latest value for every node in the source table."""
    query = f"""
    SELECT t.NodeId, t.value
    FROM {settings.table_source} t
    INNER JOIN (
        SELECT NodeId, MAX(Id) as MaxId
        FROM {settings.table_source}
        GROUP BY NodeId
    ) latest ON t.NodeId = latest.NodeId AND t.Id = latest.MaxId
    """
    result = {}
    try:
        with db.cursor() as cursor:
            cursor.execute(query)
            for row in cursor.fetchall():
                try:
                    result[row.NodeId] = float(row.value)
                except (TypeError, ValueError):
                    pass
    except Exception as e:
        logger.error("fetch_all_latest_values_error", error=str(e))
    return result


def process_tag_formulas(tag: TagRecord, formulas: List, interval: int, latest_values: Dict[str, float]) -> List[dict]:
    results = []
    processed_on = datetime.now(timezone.utc)
    bracketed = f'[{tag.node_id}]'

    for formula_info in formulas:
        if bracketed not in formula_info.formula:
            continue

        resolved = formula_info.formula.replace(bracketed, str(tag.value))

        remaining = re.findall(r'\[([^\]]+)\]', resolved)
        skip = False
        for node_id in remaining:
            if node_id in latest_values:
                resolved = resolved.replace(f'[{node_id}]', str(latest_values[node_id]))
            else:
                results.append({
                    'variable_id': formula_info.variable_id,
                    'result': None,
                    'error': f'UNRESOLVED_NODE: {node_id}',
                    'result_on': tag.timestamp,
                    'processed_on': processed_on,
                    'interval': interval,
                    'created_by': 'system',
                    'tag_id': tag.id
                })
                skip = True
                break
        if skip:
            continue

        result, error = formula_executor.execute_single(resolved, tag.value)
        results.append({
            'variable_id': formula_info.variable_id,
            'result': str(result) if error is None else None,
            'error': error,
            'result_on': tag.timestamp,
            'processed_on': processed_on,
            'interval': interval,
            'created_by': 'system',
            'tag_id': tag.id
        })

    return results


class TagBatchProcessor:
    def __init__(self, batch_size: int = 200, num_workers: int = 4):
        self.batch_size = batch_size
        self.num_workers = num_workers
        self._last_processed_id = self._get_last_processed_id()
        self._processing_start_time = None
        self._total_tags_in_run = 0
        self._interval_start_time = datetime.now(timezone.utc)
        self._current_interval = self._get_current_interval()
        logger.info("processor_initialized",
                    batch_size=batch_size,
                    num_workers=self.num_workers,
                    last_processed_id=self._last_processed_id,
                    current_interval=self._current_interval)

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
            db.commit()

        with db.cursor() as cursor:
            cursor.execute(f"SELECT last_processed_id FROM {settings.table_processing_state} WHERE service_name = 'formula_processor'")
            row = cursor.fetchone()
            if row:
                return row.last_processed_id
            cursor.execute(f"INSERT INTO {settings.table_processing_state} (service_name, last_processed_id) VALUES ('formula_processor', 0)")
            db.commit()
            return 0

    def _get_current_interval(self) -> int:
        with db.cursor() as cursor:
            cursor.execute(f"SELECT MIN(Time) as CurrentInterval FROM {settings.table_variables} WHERE IsDeleted = 0 AND FormulaType = 'SINGLE'")
            row = cursor.fetchone()
            return int(row.CurrentInterval) if row and row.CurrentInterval else 10

    def _increment_interval(self) -> None:
        new_interval = self._current_interval + 10
        with db.cursor() as cursor:
            cursor.execute(
                f"UPDATE {settings.table_variables} SET Time = ?, UpdatedOn = GETUTCDATE(), UpdatedBy = 'system' WHERE IsDeleted = 0 AND FormulaType = 'SINGLE'",
                (new_interval,)
            )
            db.commit()
        logger.info("interval_updated", old=self._current_interval, new=new_interval)
        self._current_interval = new_interval
        self._interval_start_time = datetime.now(timezone.utc)

    def _check_and_update_interval(self) -> None:
        elapsed = (datetime.now(timezone.utc) - self._interval_start_time).total_seconds()
        if elapsed >= INTERVAL_DURATION_SECONDS:
            self._increment_interval()

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
                if self._processing_start_time is None:
                    self._processing_start_time = datetime.utcnow()
                logger.info("batch_fetched", count=len(tags), first_id=tags[0].id, last_id=tags[-1].id)
            else:
                if self._processing_start_time is not None:
                    elapsed = (datetime.utcnow() - self._processing_start_time).total_seconds()
                    tags_per_sec = self._total_tags_in_run / elapsed if elapsed > 0 else 0
                    logger.info("processing_complete",
                                total_tags=self._total_tags_in_run,
                                elapsed_seconds=round(elapsed, 2),
                                tags_per_second=round(tags_per_sec, 2))
                    self._processing_start_time = None
                    self._total_tags_in_run = 0
                logger.info("no_new_tags", last_processed_id=self._last_processed_id)

            return tags

    def process_batch(self) -> Tuple[int, int]:
        self._check_and_update_interval()
        formula_loader.refresh_if_needed()

        tags = self.fetch_batch()
        if not tags:
            return 0, 0

        formulas = formula_loader.get_single_formulas() + formula_loader.get_pair_formulas()
        if not formulas:
            logger.warning("no_formulas_loaded")
            return 0, 0

        logger.info("executing_formulas", tag_count=len(tags), formula_count=len(formulas))

        all_results = []
        current_interval = self._current_interval
        latest_values = fetch_all_latest_values()

        try:
            with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
                futures = {
                    executor.submit(process_tag_formulas, tag, formulas, current_interval, latest_values): tag
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
                all_results.extend(process_tag_formulas(tag, formulas, current_interval, latest_values))

        successful = [r for r in all_results if r['error'] is None]
        failed = [r for r in all_results if r['error'] is not None]

        logger.info("formulas_executed", successful=len(successful), failed=len(failed))

        if failed:
            logger.warning("formula_failures", count=len(failed), samples=[r['error'] for r in failed[:3]])

        last_id = tags[-1].id
        try:
            self._save_with_transaction(successful, failed, last_id)
            self._last_processed_id = last_id
            self._total_tags_in_run += len(tags)
            logger.info("batch_processed",
                    tags=len(tags),
                    successful=len(successful),
                    failed=len(failed),
                    last_id=last_id)
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
                        TagId BIGINT NOT NULL,
                        VariableId BIGINT NOT NULL,
                        ErrorMessage NVARCHAR(MAX),
                        FailedAt DATETIME2 NOT NULL DEFAULT GETUTCDATE(),
                        RetryCount INT DEFAULT 0,
                        IsResolved BIT DEFAULT 0
                    );
                END
                """)
                failed_sql = f"""
                INSERT INTO {settings.table_failed_executions} (TagId, VariableId, ErrorMessage, FailedAt, RetryCount, IsResolved)
                VALUES (?, ?, ?, GETUTCDATE(), 0, 0)
                """
                cursor.fast_executemany = True
                cursor.executemany(failed_sql, [(r['tag_id'], r['variable_id'], r['error']) for r in failed])

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
