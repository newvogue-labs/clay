import logging
import os

_CONFIGURED = False


def configure_clay_logging() -> None:
    global _CONFIGURED
    logger = logging.getLogger("clay")
    level = logging.getLevelNamesMapping().get(
        os.environ.get("CLAY_LOG_LEVEL", "INFO").upper(),
        logging.INFO,
    )
    logger.setLevel(level)
    if _CONFIGURED or logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
    )
    logger.addHandler(handler)
    logger.propagate = False
    _CONFIGURED = True
