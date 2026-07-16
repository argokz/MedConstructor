import logging
import sys

import structlog


def configure_logging(enable_structlog: bool) -> None:
    if enable_structlog:
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.TimeStamper(fmt="iso", utc=True),
                structlog.processors.add_log_level,
                structlog.processors.JSONRenderer(),
            ],
            logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
            cache_logger_on_first_use=True,
        )
        logging.basicConfig(level=logging.INFO, format="%(message)s")
    else:
        structlog.configure(
            processors=[
                structlog.processors.TimeStamper(fmt="iso", utc=True),
                structlog.processors.add_log_level,
                structlog.dev.ConsoleRenderer(colors=False),
            ],
            logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
            cache_logger_on_first_use=True,
        )
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
