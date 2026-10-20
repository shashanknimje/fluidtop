"""Collector regressions without macOS, sudo, or real powermetrics."""

import plistlib
import sys
import time
import tracemalloc
import unittest
from unittest.mock import patch

from fluidtop.collector import PlistStreamDecoder, PowermetricsCollector, powermetrics_command


def reading(timestamp: int) -> bytes:
    return plistlib.dumps({
        "timestamp": timestamp,
        "thermal_pressure": "Nominal",
        "processor": {
            "clusters": [
                {"name": "E-Cluster", "cpus": [{"cpu": 0, "idle_ratio": 0.2}]},
                {"name": "P-Cluster", "cpus": [{"cpu": 1, "idle_ratio": 0.6}]},
            ],
            "cpu_energy": 1000, "gpu_energy": 2000, "ane_energy": 300,
            "combined_power": 3300,
        },
        "gpu": {"idle_ratio": 0.5},
    })


class DecoderTests(unittest.TestCase):
    def test_partial_nul_separated_records_and_xml_first_sample(self):
        first, second = reading(1), reading(2)
        stream = PlistStreamDecoder()
        self.assertEqual(list(stream.feed(first[:17])), [])
        self.assertEqual([x["timestamp"] for x in stream.feed(first[17:])], [1])
        self.assertEqual([x["timestamp"] for x in stream.feed(b"\0" + second + b"\0")], [2])
        self.assertEqual(stream.buffered_bytes, 0)

    def test_bad_record_does_not_block_next_valid_reading(self):
        stream = PlistStreamDecoder()
        self.assertEqual([x["timestamp"] for x in stream.feed(b"junk\0" + reading(4) + b"\0")], [4])
        self.assertEqual(stream.invalid_records, 1)

    def test_record_limit_prevents_unbounded_allocation(self):
        stream = PlistStreamDecoder(max_record_bytes=16)
        list(stream.feed(b"a" * 16))
        with self.assertRaisesRegex(ValueError, "maximum record size"):
            list(stream.feed(b"b"))
        self.assertLessEqual(stream.buffered_bytes, 16)

    def test_many_samples_keep_bounded_memory(self):
        stream = PlistStreamDecoder()
        data = reading(1)
        tracemalloc.start()
        try:
            for _ in range(10000):
                result = list(stream.feed(data + b"\0"))
                self.assertEqual(len(result), 1)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(stream.buffered_bytes, 0)
        self.assertLess(peak, 3 * 1024 * 1024)


class ProcessTests(unittest.TestCase):
    def test_command_streams_unbuffered_plist_without_output_file(self):
        with patch("fluidtop.collector.os.geteuid", return_value=0):
            command = powermetrics_command(1000)
        self.assertEqual(command[:4], ["nice", "-n", "10", "powermetrics"])
        self.assertEqual(command[-6:], ["-f", "plist", "-b", "0", "-i", "1000"])
        self.assertNotIn("-o", command)
        with patch("fluidtop.collector.os.geteuid", return_value=501):
            self.assertEqual(powermetrics_command(500)[0], "sudo")

    def test_fake_subprocess_emits_latest_only_then_cleans_up(self):
        data = reading(1) + b"\0" + reading(2) + b"\0"
        cmd = [sys.executable, "-u", "-c", "import sys,time; "
               f"sys.stdout.buffer.write({data!r}); sys.stdout.buffer.flush(); time.sleep(10)"]
        collector = PowermetricsCollector(1000, command=cmd)
        collector.start()
        process = collector.process
        try:
            for _ in range(100):
                latest = collector.latest()
                if latest is not None and latest[-1] == 2:
                    break
                time.sleep(0.02)
            self.assertIsNotNone(collector.latest())
            self.assertEqual(collector.latest()[-1], 2)
            self.assertEqual(collector.latest()[0]["E-Cluster_active"], 80)
            self.assertIsNone(collector.problem())
        finally:
            collector.stop()
        self.assertIsNone(collector.process)
        self.assertIsNotNone(process)
        self.assertIsNotNone(process.returncode)
        self.assertFalse(collector._reader.is_alive())
        collector.stop()  # idempotent

    def test_clean_failure_for_early_child_exit(self):
        collector = PowermetricsCollector(1000, command=[sys.executable, "-c", "import sys; sys.exit(19)"])
        collector.start()
        try:
            for _ in range(100):
                failure = collector.problem()
                if failure:
                    break
                time.sleep(0.02)
            self.assertEqual(failure, "powermetrics exited with status 19")
        finally:
            collector.stop()

    def test_oversized_input_reports_error(self):
        cmd = [sys.executable, "-u", "-c", "import sys,time; sys.stdout.buffer.write(b'x'*100); sys.stdout.buffer.flush(); time.sleep(10)"]
        collector = PowermetricsCollector(1000, command=cmd, max_record_bytes=30)
        collector.start()
        try:
            for _ in range(100):
                failure = collector.problem()
                if failure:
                    break
                time.sleep(0.02)
            self.assertIn("maximum record size", failure)
        finally:
            collector.stop()


if __name__ == "__main__":
    unittest.main()
