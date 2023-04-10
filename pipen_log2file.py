"""pipen-log2file plugin: Save running logs to file"""
from __future__ import annotations
from typing import TYPE_CHECKING

import logging
from datetime import datetime

from rich.markup import _parse
from pipen import plugin

if TYPE_CHECKING:  # pragma: no cover
    from pipen import Pipen

__version__ = "0.0.0"


def _remove_rich_tags(text: str) -> str:
    """Remove rich tags from text"""
    return "".join(text for _, text, _ in _parse(text) if text)


def _add_handler(handler: logging.Handler | None):
    """Get all loggers"""
    if not handler:
        return

    for name in logging.root.manager.loggerDict:
        if not name.startswith("pipen."):
            continue
        logger = logging.getLogger(name)
        if handler not in logger.handlers:
            logger.addHandler(handler)


def _remove_handler(handler: logging.Handler | None):
    """Remove handler from all loggers"""
    if not handler:
        return

    for name in logging.root.manager.loggerDict:
        if not name.startswith("pipen."):
            continue
        logger = logging.getLogger(name)
        if handler in logger.handlers:
            logger.removeHandler(handler)


class _RemoveRichMarkupFilter(logging.Filter):
    """Remove rich tags from logs"""
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _remove_rich_tags(record.msg)
        return True


class PipenLog2FilePlugin:
    """pipen-log2file plugin: Save running logs to file"""
    name = "log2file"
    __version__: str = __version__

    def __init__(self) -> None:
        self._handler = None

    @plugin.impl
    async def on_init(self, pipen: Pipen):
        """Initialize the logging handler"""
        # In case the handler is already set
        # This happens when on_complete can not be reached due to errors
        if self._handler:  # pragma: no cover
            return

        logfile = pipen.workdir.joinpath(
            ".logs",
            f"run-{datetime.now():%Y_%m_%d_%H_%M_%S}.log"
        )
        logfile.parent.mkdir(parents=True, exist_ok=True)
        latest_log = pipen.workdir.joinpath("run-latest.log")
        if latest_log.exists() or latest_log.is_symlink():
            latest_log.unlink()
        latest_log.symlink_to(logfile.relative_to(pipen.workdir))

        self._handler = logging.FileHandler(logfile)
        self._handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-1.1s %(plugin_name)-7s %(message)s",
                datefmt="%m-%d %H:%M:%S",
            )
        )
        self._handler.addFilter(_RemoveRichMarkupFilter())
        _add_handler(self._handler)

    @plugin.impl
    async def on_complete(self, pipen: Pipen, succeeded: bool):
        """Remove the handler in case logger is used by other pipelines"""
        _remove_handler(self._handler)
        self._handler = None


log2file_plugin = PipenLog2FilePlugin()
