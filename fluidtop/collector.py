"""Bounded, file-free collection of macOS powermetrics PLIST samples."""

import os
import plistlib
import signal
import subprocess
import threading
from collections.abc import Iterator, Sequence

from .parsers import parse_cpu_metrics, parse_gpu_metrics, parse_thermal_pressure

# The selected CPU/GPU/thermal samplers emit much smaller records. Refuse an
# unexpectedly large/unterminated record rather than allocating indefinitely.
MAX_RECORD_BYTES = 8 * 1024 * 1024
READ_BYTES = 64 * 1024


class PlistStreamDecoder:
    """Decode NUL-separated PLIST documents across arbitrary pipe reads."""

    def __init__(self, max_record_bytes: int = MAX_RECORD_BYTES):
        if max_record_bytes < 1:
            raise ValueError("max_record_bytes must be positive")
        self.max_record_bytes = max_record_bytes
        self._pending = bytearray()
        self.invalid_records = 0

    @property
    def buffered_bytes(self) -> int:
        return len(self._pending)

    def _append(self, chunk: bytes) -> None:
        if len(self._pending) + len(chunk) > self.max_record_bytes:
            raise ValueError("powermetrics PLIST exceeds the maximum record size")
        self._pending.extend(chunk)

    def _complete(self) -> Iterator[dict]:
        record = bytes(self._pending)
        self._pending.clear()
        if not record.strip():
            return
        try:
            document = plistlib.loads(record)
            if not isinstance(document, dict):
                raise ValueError("powermetrics PLIST must be a dictionary")
        except (ValueError, TypeError, plistlib.InvalidFileException):
            self.invalid_records += 1
            return
        yield document

    def feed(self, chunk: bytes) -> Iterator[dict]:
        """Return complete documents; retain no history of previous samples.

        powermetrics emits NUL-separated PLIST documents, but XML's closing
        tag also lets us show the very first sample before the next NUL.
        """
        parts = chunk.split(b"\0")
        for part in parts[:-1]:
            self._append(part)
            yield from self._complete()
        self._append(parts[-1])
        if self._pending[-32:].rstrip().endswith(b"</plist>"):
            yield from self._complete()


def powermetrics_command(interval_ms: int, nice: int = 10) -> list[str]:
    """Run powermetrics without a persistent -o file or buffered stdout."""
    if interval_ms < 1:
        raise ValueError("interval_ms must be positive")
    command = [
        "nice", "-n", str(nice), "powermetrics",
        "--samplers", "cpu_power,gpu_power,thermal",
        "-f", "plist", "-b", "0", "-i", str(interval_ms),
    ]
    # fluidtop-launch already runs the application through sudo. Avoid a
    # nested sudo process in that path, while retaining direct CLI support.
    if os.geteuid() != 0:
        command.insert(0, "sudo")
    return command


class PowermetricsCollector:
    """Keep only the newest parsed reading in memory; own the child lifecycle."""

    def __init__(self, interval_ms: int, *, command: Sequence[str] | None = None,
                 max_record_bytes: int = MAX_RECORD_BYTES):
        self.command = list(command) if command is not None else powermetrics_command(interval_ms)
        self.decoder = PlistStreamDecoder(max_record_bytes)
        self.process: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest: tuple | None = None
        self._error: str | None = None
        self.invalid_samples = 0

    def start(self) -> None:
        if self.process is not None:
            raise RuntimeError("powermetrics collector already started")
        self.process = subprocess.Popen(
            self.command,
            stdout=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            bufsize=0,
            start_new_session=True,
        )
        self._reader = threading.Thread(
            target=self._read_stdout, name="fluidtop-powermetrics", daemon=True,
        )
        self._reader.start()

    def _read_stdout(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        try:
            while not self._stop.is_set():
                data = os.read(self.process.stdout.fileno(), READ_BYTES)
                if not data:
                    break
                for document in self.decoder.feed(data):
                    try:
                        reading = (
                            parse_cpu_metrics(document),
                            parse_gpu_metrics(document),
                            parse_thermal_pressure(document),
                            None,
                            document["timestamp"],
                        )
                    except (KeyError, TypeError, ValueError, ZeroDivisionError):
                        self.invalid_samples += 1
                        continue
                    with self._lock:
                        self._latest = reading
        except (OSError, ValueError) as error:
            if not self._stop.is_set():
                with self._lock:
                    self._error = str(error)

    def latest(self) -> tuple | None:
        with self._lock:
            return self._latest

    def problem(self) -> str | None:
        with self._lock:
            if self._error:
                return self._error
        if (not self._stop.is_set() and self.process is not None
                and self.process.poll() is not None
                and self._reader is not None and not self._reader.is_alive()):
            return f"powermetrics exited with status {self.process.returncode}"
        return None

    def _signal_group(self, sig: int) -> None:
        assert self.process is not None
        try:
            os.killpg(self.process.pid, sig)
        except ProcessLookupError:
            pass
        except PermissionError:
            # A direct, non-root CLI invocation may have launched sudo.
            # It can still relay TERM to its privileged child.
            if self.process.poll() is None:
                self.process.send_signal(sig)

    def stop(self) -> None:
        process = self.process
        if process is None:
            return
        self._stop.set()
        try:
            self._signal_group(signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._signal_group(signal.SIGKILL)
                process.wait(timeout=3)
            if self._reader is not None:
                self._reader.join(timeout=3)
                if self._reader.is_alive():
                    self._signal_group(signal.SIGKILL)
                    self._reader.join(timeout=3)
        finally:
            if process.stdout is not None:
                process.stdout.close()
            self.process = None
