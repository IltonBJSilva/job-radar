
import logging
import os
import sys

# JOBRADAR_LOG_PATH permite apontar para outro arquivo (os testes usam um
# temporário para não misturar linhas falsas no log real de produção).
_LOG_PATH = os.getenv("JOBRADAR_LOG_PATH") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "jobradar.log"
)


def get_logger(name: str = "jobradar") -> logging.Logger:
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%H:%M:%S"
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler(_LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger