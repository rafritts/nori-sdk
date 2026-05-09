import json
import logging
import time


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        })


def configure_file_logging(path: str, level: int = logging.DEBUG) -> None:
    """Attach a JSON-lines file handler to the nori logger."""
    handler = logging.FileHandler(path)
    handler.setLevel(level)
    handler.setFormatter(_JsonFormatter())
    logging.getLogger("nori").setLevel(level)
    logging.getLogger("nori").addHandler(handler)
