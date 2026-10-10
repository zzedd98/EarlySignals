"""
Logs structurés et barre de progression pour le seed builder.
"""
import logging
import sys
from typing import Any, Optional

def setup_logging(debug: bool = False) -> None:
    """Configure le logging (stdout, niveau INFO ou DEBUG)."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    # Réduire le bruit des libs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def log_struct(logger: logging.Logger, level: int, msg: str, **kwargs: Any) -> None:
    """Log un message avec champs structurés (pour parsing optionnel)."""
    extra = " ".join(f"{k}={v!r}" for k, v in kwargs.items())
    full = f"{msg} {extra}" if extra else msg
    logger.log(level, full)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
