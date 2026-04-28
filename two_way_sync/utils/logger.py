import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def log_info(message):
    """Write an operational info log message."""
    logging.info(message)

def log_error(message):
    """Write an operational error log message."""
    logging.error(message)
