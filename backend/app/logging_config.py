from logging.config import dictConfig


def configure_logging(log_level: str, debug: bool) -> None:
    app_level = log_level.upper()
    root_level = "INFO"

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                    "level": root_level,
                }
            },
            "root": {
                "handlers": ["console"],
                "level": root_level,
            },
            "loggers": {
                "app": {
                    "handlers": ["console"],
                    "level": app_level,
                    "propagate": False,
                },
                "uvicorn": {
                    "handlers": ["console"],
                    "level": "INFO",
                    "propagate": False,
                },
                "uvicorn.error": {
                    "handlers": ["console"],
                    "level": "INFO",
                    "propagate": False,
                },
                "uvicorn.access": {
                    "handlers": ["console"],
                    "level": "INFO",
                    "propagate": False,
                },
                "sqlalchemy.engine": {
                    "handlers": ["console"],
                    "level": "WARNING",
                    "propagate": False,
                },
                "aiosqlite": {
                    "handlers": ["console"],
                    "level": "WARNING",
                    "propagate": False,
                },
                "apscheduler": {
                    "handlers": ["console"],
                    "level": "INFO" if debug else "WARNING",
                    "propagate": False,
                },
            },
        }
    )
