import time
from datetime import datetime
import structlog

from core.formula_engine.formula_loader import formula_loader
from core.tag_batch_processor import TagBatchProcessor
from core.config import settings

logger = structlog.get_logger()


class FormulaProcessorService:
    def __init__(self):
        self.processor = TagBatchProcessor(
            batch_size=settings.batch_size,
            num_workers=settings.num_workers
        )
        self.running = False
        self.stats = {
            'total_tags_processed': 0,
            'total_formulas_executed': 0,
            'batches_processed': 0,
            'start_time': None
        }

    def start(self) -> None:
        logger.info("service_starting")
        formula_loader.load_formulas()
        counts = formula_loader.get_formula_count()
        logger.info("formulas_loaded", single=counts['single'], pair=counts['pair'])

        self.running = True
        self.stats['start_time'] = datetime.utcnow()

        while self.running:
            try:
                tags_processed, formulas_executed = self.processor.process_batch()
                self.stats['total_tags_processed'] += tags_processed
                self.stats['total_formulas_executed'] += formulas_executed
                self.stats['batches_processed'] += 1

                if tags_processed == 0:
                    time.sleep(settings.poll_interval_ms / 1000.0)
            except KeyboardInterrupt:
                self.stop()
                break
            except Exception as e:
                logger.error("processing_error", error=str(e))
                time.sleep(5)

    def stop(self) -> None:
        self.running = False
        from infra.db_connection import db
        db.close_pool()
        logger.info("service_stopped", stats=self.stats)

    def get_stats(self) -> dict:
        uptime = (datetime.utcnow() - self.stats['start_time']).total_seconds() if self.stats['start_time'] else 0
        counts = formula_loader.get_formula_count()
        return {
            'total_tags_processed': self.stats['total_tags_processed'],
            'total_formulas_executed': self.stats['total_formulas_executed'],
            'batches_processed': self.stats['batches_processed'],
            'uptime_seconds': uptime,
            'formula_counts': counts
        }


formula_processor_service = FormulaProcessorService()
