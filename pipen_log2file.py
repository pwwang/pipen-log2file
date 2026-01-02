"""pipen-log2file plugin: Save running logs to file"""

from __future__ import annotations

import sys
import logging
import time
from hashlib import sha256
from datetime import datetime
from tempfile import mkdtemp
from pathlib import Path
from typing import TYPE_CHECKING

from panpath import PanPath, CloudPath
from rich.markup import _parse
from xqute.utils import logger as xqute_logger
from xqute.path import MountedPath
from pipen import plugin
from pipen.utils import brief_list

if TYPE_CHECKING:  # pragma: no cover
    from pipen import Pipen, Proc
    from pipen.job import Job

__version__ = "1.0.1"

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
        # Get the final formatted message (after %s interpolation)
        # and remove rich tags from it
        if record.args:
            # If there are args, getMessage() will perform interpolation
            original_msg = record.getMessage()
            record.msg = _remove_rich_tags(original_msg)
            record.args = ()  # Clear args since msg is now fully formatted
        else:
            # No interpolation needed, just remove tags from msg
            record.msg = _remove_rich_tags(record.msg)
        return True


class PipenLog2FilePlugin:
    """pipen-log2file plugin: Save running logs to file"""

    name = "log2file"
    priority = 1000
    __version__: str = __version__
    __slots__ = (
        "_handler",
        "_job_statuses",
        "_xqute_handler",
        "_last_update_time",
        "_last_cloud_sync_time",
        "logfile",
        "latest_logfile",
        "xqute_logfile",
        "proc_counter",
        "pipen",
    )

    def __init__(self) -> None:
        self._handler: logging.FileHandler | None = None
        self._job_statuses: dict = {
            "init": [],
            "submitted": [],
            "queued": [],
            "running": [],
            "killed": [],
            "succeeded": [],
            "failed": [],
            "cached": [],
        }
        self._last_update_time: float = time.time()
        self._last_cloud_sync_time: float = 0.0
        self._xqute_handler: logging.Handler | None = None
        # The logfile for the current pipeline
        self.logfile: MountedPath | CloudPath = None
        self.latest_logfile: MountedPath | CloudPath = None
        self.xqute_logfile: MountedPath | CloudPath = None
        self.proc_counter: int = 0
        self.pipen: Pipen | None = None

    async def _sync_logfile(
        self, logfile: MountedPath | CloudPath, force: bool = False
    ):
        """Sync the log file to cloud storage"""
        if not self.pipen or not isinstance(self.pipen.workdir, CloudPath):
            # Not in cloud storage
            return

        # Check if enough time has passed since last sync
        if not force:
            interval = self.pipen.config.plugin_opts.get(
                "log2file_update_freq", 10.0
            )
            elapsed = time.time() - self._last_cloud_sync_time
            if elapsed < interval:
                return

        try:
            old_content = await logfile.spec.a_read_text()
        except Exception:
            old_content = None

        new_content = await logfile.a_read_text()
        if old_content == new_content:
            return

        await logfile.spec.parent.a_mkdir(parents=True, exist_ok=True)
        await logfile.spec.a_write_text(new_content)
        self._last_cloud_sync_time = time.time()

    async def _emit_message(self, msg: str):
        """Emit a log message"""
        if not self._handler:
            return

        record = logging.LogRecord(
            name="pipen.main",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )
        record.plugin_name = "log2f"
        self._handler.emit(record)

        await self._sync_logfile(self.logfile)
        await self._sync_logfile(self.latest_logfile)

    def _update_job_statuses(self, job_index: int, status: str):
        """Update the job statuses"""
        if status == "init":
            self._job_statuses["init"].append(job_index)
        else:
            # Remove from other statuses
            for st in self._job_statuses.values():
                if job_index in st:
                    st.remove(job_index)
            self._job_statuses[status].append(job_index)

    async def _log_job_statuses(self, proc: Proc, always: bool = False):
        """Log the job progress"""
        if not self._handler or not self.pipen:
            return

        update_freq = proc.plugin_opts.get("log2file_update_freq", 5.0)
        if (
            not always
            and time.time() - self._last_update_time < update_freq
            and proc.size > 5
        ):
            return

        await self._emit_message(
            f"{proc.name}: Jobs Status: "
            + ", ".join(
                f"{st}: {brief_list(self._job_statuses[st])}"
                for st in self._job_statuses
                if self._job_statuses[st]
            )
        )
        self._last_update_time = time.time()

    @plugin.impl
    async def on_init(self, pipen: Pipen):
        """Initialize the logging handler"""
        # If we are called by pipen-board or other plugins just to
        # gather the pipeline information
        if sys.argv[0].startswith("@pipen-"):
            return

        # default options
        pipen.config.plugin_opts.setdefault("log2file_xqute", True)
        pipen.config.plugin_opts.setdefault("log2file_xqute_level", "INFO")
        pipen.config.plugin_opts.setdefault("log2file_xqute_append", False)
        # log2file_update_freq is set in on_init based on workdir type

        # In case the handler is already set
        # This happens when on_complete can not be reached due to errors
        if self._handler:  # pragma: no cover
            return

        self.pipen = pipen
        if "workdir" in pipen._kwargs:
            # kwargs have higher priority than config
            pipen.workdir = PanPath(pipen._kwargs["workdir"]) / pipen.name

        lfname = f"run-{datetime.now():%Y_%m_%d_%H_%M_%S}.log"
        if isinstance(pipen.workdir, CloudPath):
            pipen.config.plugin_opts.setdefault("log2file_update_freq", 10.0)
            dig = sha256(str(pipen.workdir).encode()).hexdigest()[:8]
            self.logfile = MountedPath(
                PanPath(mkdtemp(suffix=f"-{dig}")).joinpath(".logs", lfname),
                spec=pipen.workdir.joinpath(".logs", lfname),
            )
            self.latest_logfile = MountedPath(
                self.logfile.parent.parent.joinpath("run-latest.log"),
                spec=pipen.workdir.joinpath("run-latest.log"),
            )

        else:
            pipen.config.plugin_opts.setdefault("log2file_update_freq", 5.0)
            self.logfile = MountedPath(pipen.workdir.joinpath(".logs", lfname))
            self.latest_logfile = MountedPath(pipen.workdir.joinpath("run-latest.log"))

        await self.logfile.parent.a_mkdir(parents=True, exist_ok=True)
        if (
            await self.latest_logfile.a_exists()
            or await self.latest_logfile.a_is_symlink()
        ):
            await self.latest_logfile.a_unlink()

        await self.latest_logfile.a_symlink_to(
            Path(str(self.logfile.absolute())).relative_to(
                str(self.logfile.parent.parent.absolute())
            )
        )

        self._handler = logging.FileHandler(self.logfile)
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

        await self._sync_logfile(self.logfile, force=True)
        await self._sync_logfile(self.latest_logfile, force=True)

    @plugin.impl
    async def on_job_init(self, job: Job):
        self._update_job_statuses(job.index, "init")
        await self._log_job_statuses(job.proc)

    @plugin.impl
    async def on_job_queued(self, job: Job):
        self._update_job_statuses(job.index, "queued")
        await self._log_job_statuses(job.proc)

    @plugin.impl
    async def on_job_submitted(self, job: Job):
        self._update_job_statuses(job.index, "submitted")
        await self._log_job_statuses(job.proc)

    @plugin.impl
    async def on_job_started(self, job: Job):
        self._update_job_statuses(job.index, "running")
        await self._log_job_statuses(job.proc)

    @plugin.impl
    async def on_job_killed(self, job: Job):
        self._update_job_statuses(job.index, "killed")
        await self._log_job_statuses(job.proc)

    @plugin.impl
    async def on_job_succeeded(self, job: Job):
        self._update_job_statuses(job.index, "succeeded")
        await self._log_job_statuses(job.proc)

    @plugin.impl
    async def on_job_failed(self, job: Job):
        self._update_job_statuses(job.index, "failed")
        await self._log_job_statuses(job.proc)

    @plugin.impl
    async def on_job_cached(self, job: Job):
        self._update_job_statuses(job.index, "cached")
        await self._log_job_statuses(job.proc)

    @plugin.impl
    async def on_proc_start(self, proc: Proc):
        """Also save xqute logs"""
        self.proc_counter += 1
        await self._emit_message(
            f"{proc.name}: Running Process: "
            f"{self.proc_counter}/{len(proc.pipeline.procs)} "
            f"({100 * self.proc_counter / len(proc.pipeline.procs):.1f}%)"
        )

        if not proc.plugin_opts.log2file_xqute:
            return

        if isinstance(proc.workdir, CloudPath):
            self.xqute_logfile = MountedPath(
                self.logfile.parent.joinpath(f"{proc.name}.xqute.log"),
                spec=proc.workdir.joinpath("proc.xqute.log"),
            )
        else:
            self.xqute_logfile = MountedPath(proc.workdir.joinpath("proc.xqute.log"))

        if (
            not proc.plugin_opts.log2file_xqute_append
            and await self.xqute_logfile.a_exists()
        ):
            await self.xqute_logfile.a_unlink()

        self._xqute_handler = logging.FileHandler(self.xqute_logfile, delay=True)
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
        """Remove xqute log handler and sync log files"""
        # May be duplicate when all job statuses have been logged
        # self._log_job_statuses(proc, always=True)

        self._last_update_time = 0.0
        for val in self._job_statuses.values():
            val.clear()

        if self._xqute_handler and self._xqute_handler in xqute_logger.handlers:
            xqute_logger.removeHandler(self._xqute_handler)
            try:
                self._xqute_handler.close()
            except Exception:  # pragma: no cover
                pass
            self._xqute_handler = None

        await self._sync_logfile(self.xqute_logfile)
        self.xqute_logfile = None

        if not self._handler:
            return

        await self._sync_logfile(self.logfile, force=True)
        await self._sync_logfile(self.latest_logfile, force=True)


log2file_plugin = PipenLog2FilePlugin()
