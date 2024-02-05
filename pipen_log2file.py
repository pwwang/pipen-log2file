"""pipen-log2file plugin: Save running logs to file"""
from __future__ import annotations

import sys
import logging
from math import ceil
from datetime import datetime
from typing import TYPE_CHECKING, List

from rich.markup import _parse
from xqute.utils import logger as xqute_logger
from pipen import plugin

if TYPE_CHECKING:  # pragma: no cover
    from pipen import Pipen, Proc
    from pipen.job import Job

__version__ = "0.7.0"

xqute_logger_handlers = xqute_logger.handlers


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
    priority = 1000
    __version__: str = __version__

    def __init__(self) -> None:
        self._handler: logging.FileHandler | None = None
        self._job_progress: List[str] = []
        self._xqute_handler: logging.Handler | None = None

    @plugin.impl
    async def on_init(self, pipen: Pipen):
        """Initialize the logging handler"""
        # If we are called by pipen-board or other plugins just to
        # gather the pipeline information
        if sys.argv[0].startswith("@pipen-"):
            return

        # default options
        pipen.config.plugin_opts.log2file_xqute = True
        pipen.config.plugin_opts.log2file_xqute_level = "INFO"
        pipen.config.plugin_opts.log2file_xqute_append = False

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

        self._handler = logging.FileHandler(logfile, delay=True)
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
        try:
            self._handler.close()
        except Exception:  # pragma: no cover
            pass
        self._handler = None

    @plugin.impl
    async def on_job_succeeded(self, proc: Proc, job: Job):
        self._log_job_progress(proc, job, "✔")

    @plugin.impl
    async def on_job_failed(self, proc: Proc, job: Job):
        self._log_job_progress(proc, job, "✘")

    @plugin.impl
    async def on_job_cached(self, proc: Proc, job: Job):
        self._log_job_progress(proc, job, "✔")

    @plugin.impl
    async def on_proc_start(self, proc: Proc):
        """Also save xqute logs"""
        if not proc.plugin_opts.log2file_xqute:
            return

        logfile = proc.workdir.joinpath("proc.xqute.log")
        if not proc.plugin_opts.log2file_xqute_append and logfile.exists():
            logfile.unlink()

        self._xqute_handler = logging.FileHandler(logfile, delay=True)
        self._xqute_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-7s %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        # handler.addFilter(_RemoveRichMarkupFilter())
        xqute_logger.addHandler(self._xqute_handler)
        xqute_logger.setLevel(proc.plugin_opts.log2file_xqute_level.upper())

    @plugin.impl
    async def on_proc_done(self, proc: Proc, succeeded: bool | str):
        if (
            self._xqute_handler
            and self._xqute_handler in xqute_logger.handlers
        ):
            xqute_logger.removeHandler(self._xqute_handler)
            try:
                self._xqute_handler.close()
            except Exception:  # pragma: no cover
                pass
            self._xqute_handler = None

        if not self._handler:
            return

        self._emit_log_progress(proc.name)

    def _emit_log_progress(self, procname: str):
        """Emit the job progress"""
        if not self._handler or not self._job_progress:
            return

        record = logging.LogRecord(
            name="pipen.main",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=f'{procname}: Progress {" ".join(self._job_progress)}',
            args=(),
            exc_info=None,
        )
        record.plugin_name = "log2f"
        self._handler.emit(record)
        self._job_progress.clear()

    def _log_job_progress(self, proc: Proc, job: Job, status: str):
        """Log the job progress"""
        if not self._handler:
            return

        job_index = str(job.index).zfill(len(str(proc.size - 1)))
        njobs_per_line = ceil(55.0 / (len(job_index) + 2))
        self._job_progress.append(f"{job_index}{status}")
        if len(self._job_progress) == njobs_per_line:
            self._emit_log_progress(proc.name)


log2file_plugin = PipenLog2FilePlugin()
