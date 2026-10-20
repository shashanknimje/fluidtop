"""Headless Textual integration for the streaming collector lifecycle."""

import plistlib
import unittest
from unittest.mock import patch

from fluidtop.fluidtop import FluidTopApp
from test_collector import reading


SOC = {
    "name": "Apple M4", "e_core_count": 4, "p_core_count": 4,
    "gpu_core_count": 10, "cpu_max_power": 22, "gpu_max_power": 15,
}


def decoded(timestamp):
    from fluidtop.parsers import parse_cpu_metrics, parse_gpu_metrics, parse_thermal_pressure
    record = plistlib.loads(reading(timestamp))
    return (parse_cpu_metrics(record), parse_gpu_metrics(record),
            parse_thermal_pressure(record), None, timestamp)


class FakeCollector:
    def __init__(self, timestamp):
        self.sample = decoded(timestamp)
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def latest(self):
        return self.sample

    def problem(self):
        return None

    def stop(self):
        self.stopped = True


class CollectorIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_headless_mount_updates_and_unmount_reaps_collector(self):
        collector = FakeCollector(1)
        with patch("fluidtop.fluidtop.get_soc_info", return_value=SOC), \
                patch("fluidtop.fluidtop.PowermetricsCollector", return_value=collector):
            app = FluidTopApp(1, "cyan", 30, 0)
            async with app.run_test(size=(120, 40)):
                self.assertTrue(collector.started)
                self.assertEqual(app.last_timestamp, 1)
                collector.sample = decoded(2)
                await app.update_metrics()
                self.assertEqual(app.last_timestamp, 2)
        self.assertTrue(collector.stopped)

    async def test_optional_max_count_restarts_and_reaps_old_collector(self):
        first, second = FakeCollector(1), FakeCollector(2)
        with patch("fluidtop.fluidtop.get_soc_info", return_value=SOC), \
                patch("fluidtop.fluidtop.PowermetricsCollector", side_effect=[first, second]):
            app = FluidTopApp(1, "cyan", 30, 1)
            async with app.run_test(size=(120, 40)):
                app.count = 1
                await app.update_metrics()
                self.assertTrue(first.stopped)
                self.assertTrue(second.started)
                self.assertEqual(app.last_timestamp, 2)
        self.assertTrue(second.stopped)


if __name__ == "__main__":
    unittest.main()
