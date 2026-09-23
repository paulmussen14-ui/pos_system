"""Configuración centralizada de logging. Escribe errores a un archivo rotativo."""

import logging
from logging.handlers import RotatingFileHandler

from config import LOGS_DIR

_LOG_FILE = LOGS_DIR / "pos_errors.log"


def configurar_logger() -> logging.Logger:
    logger = logging.getLogger("pos_system")
    if logger.handlers:
        return logger  # ya configurado (evita handlers duplicados)

    logger.setLevel(logging.INFO)

    handler = RotatingFileHandler(_LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    return logger


logger = configurar_logger()
