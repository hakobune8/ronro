"""Fail-closed configuration checks for the isolated Pilot demo entrypoint."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from prototype.service_pilot_demo import _local_demo_dsn
from prototype.service_audio_transport import _AUDIO_PATH


class ServicePilotDemoConfigTests(unittest.TestCase):
    def test_existing_live_ingress_routes_only_the_demo_audio_alias(self):
        self.assertEqual(
            _AUDIO_PATH.fullmatch("/live/service/sessions/demo-id/audio").group(1),
            "demo-id",
        )
        self.assertIsNone(_AUDIO_PATH.fullmatch("/live"))

    def test_requires_dedicated_loopback_database(self):
        valid = "postgresql://demo:synthetic@127.0.0.1:5432/ronro_pilot_demo"
        with patch.dict(os.environ, {"RONRO_SERVICE_POSTGRES_DSN": valid}):
            self.assertEqual(_local_demo_dsn(), valid)
        for dsn in (
            "postgresql://demo:synthetic@db.example/ronro_pilot_demo",
            "postgresql://demo:synthetic@127.0.0.1/other_db",
            "host=localhost hostaddr=10.0.0.1 dbname=ronro_pilot_demo",
            "host=localhost port=55454 dbname=ronro_pilot_demo",
        ):
            with self.subTest(dsn=dsn), patch.dict(os.environ, {"RONRO_SERVICE_POSTGRES_DSN": dsn}):
                with self.assertRaises(RuntimeError):
                    _local_demo_dsn()
