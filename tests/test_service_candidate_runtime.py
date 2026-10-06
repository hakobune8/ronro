"""Synthetic loopback composition checks; Pilot and Provider are not started."""

from __future__ import annotations

import asyncio
import http.client
import socket
import unittest
from unittest.mock import Mock

from prototype.service_candidate_runtime import ServiceCandidateRuntime


async def inert_gateway(_connection):
    return None


class ServiceCandidateRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def runtime(self, *, audio_port=0, workers=None, demo_html=None):
        return ServiceCandidateRuntime(
            identity=Mock(), oidc=Mock(), content=Mock(),
            gateway=inert_gateway,
            workers=workers or Mock(stop=Mock(return_value=True)),
            audio_port=audio_port,
            demo_html=demo_html,
            demo_worklet=b"/* synthetic worklet */" if demo_html is not None else None,
            demo_script=b"/* synthetic script */" if demo_html is not None else None,
        )

    @staticmethod
    def can_connect(port):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            return False

    async def test_starts_and_stops_both_loopback_listeners_and_workers(self):
        workers = Mock(stop=Mock(return_value=True))
        runtime = self.runtime(workers=workers)
        await runtime.start()
        http_port = runtime.http_server.server_address[1]
        audio_port = runtime.audio_server.sockets[0].getsockname()[1]
        try:
            self.assertEqual(runtime.http_server.server_address[0], "127.0.0.1")
            self.assertEqual(runtime.audio_server.sockets[0].getsockname()[0], "127.0.0.1")
            self.assertTrue(self.can_connect(http_port))
            self.assertTrue(self.can_connect(audio_port))
            workers.start.assert_called_once_with()
        finally:
            self.assertTrue(await runtime.stop())
        self.assertFalse(self.can_connect(http_port))
        self.assertFalse(self.can_connect(audio_port))
        workers.stop.assert_called_once()
        self.assertTrue(await runtime.stop())

    async def test_audio_bind_failure_closes_http_before_starting_workers(self):
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            runtime = self.runtime(audio_port=occupied.getsockname()[1])
            with self.assertRaises(OSError):
                await runtime.start()
        self.assertIsNone(runtime.audio_server)
        self.assertIsNone(runtime.http_server)
        self.assertFalse(runtime.http_thread.is_alive())
        runtime.workers.start.assert_not_called()
        runtime.workers.stop.assert_not_called()

    async def test_worker_start_failure_closes_both_listeners(self):
        workers = Mock(start=Mock(side_effect=RuntimeError("synthetic start failure")),
                       stop=Mock(return_value=True))
        runtime = self.runtime(workers=workers)
        with self.assertRaisesRegex(RuntimeError, "synthetic start failure"):
            await runtime.start()
        self.assertIsNone(runtime.audio_server)
        self.assertIsNone(runtime.http_server)
        self.assertFalse(runtime.http_thread.is_alive())
        workers.stop.assert_called_once()

    async def test_repeated_stop_does_not_hide_in_flight_worker(self):
        workers = Mock(stop=Mock(side_effect=[False, False, True]))
        runtime = self.runtime(workers=workers)
        await runtime.start()
        self.assertFalse(await runtime.stop(timeout_seconds=0.01))
        self.assertFalse(await runtime.stop(timeout_seconds=0.01))
        self.assertTrue(await runtime.stop(timeout_seconds=0.01))
        self.assertEqual(workers.stop.call_count, 3)

    async def test_demo_routes_are_opt_in_and_do_not_expose_audio_or_state(self):
        for html, expected in ((None, 404), (b"synthetic demo", 200)):
            runtime = self.runtime(demo_html=html)
            await runtime.start()
            try:
                port = runtime.http_server.server_address[1]

                def request(path):
                    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                    try:
                        connection.request("GET", path)
                        response = connection.getresponse()
                        return response.status, response.read(), response.getheader("Cache-Control")
                    finally:
                        connection.close()

                status, body, cache = await asyncio.to_thread(request, "/service-demo")
                self.assertEqual(status, expected)
                self.assertEqual(cache, "no-store")
                if html is not None:
                    self.assertEqual(body, html)
                    self.assertEqual((await asyncio.to_thread(
                        request, "/static/service-audio-worklet.js"))[0], 200)
                    self.assertEqual((await asyncio.to_thread(
                        request, "/static/service-demo.js"))[0], 200)
                    self.assertEqual((await asyncio.to_thread(request, "/"))[0], 303)
            finally:
                self.assertTrue(await runtime.stop())

    def test_public_bind_is_rejected(self):
        with self.assertRaises(ValueError):
            ServiceCandidateRuntime(
                identity=Mock(), oidc=Mock(), content=Mock(),
                gateway=inert_gateway, workers=Mock(), http_host="0.0.0.0",
            )
        with self.assertRaises(ValueError):
            ServiceCandidateRuntime(
                identity=Mock(), oidc=Mock(), content=Mock(),
                gateway=inert_gateway, workers=Mock(), audio_host="0.0.0.0",
            )

    def test_pilot_network_bind_requires_explicit_demo(self):
        with self.assertRaises(ValueError):
            ServiceCandidateRuntime(
                identity=Mock(), oidc=Mock(), content=Mock(),
                gateway=inert_gateway, workers=Mock(),
                http_host="0.0.0.0", audio_host="0.0.0.0",
                allow_pilot_network_bind=True,
            )
        runtime = ServiceCandidateRuntime(
            identity=Mock(), oidc=Mock(), content=Mock(),
            gateway=inert_gateway, workers=Mock(),
            http_host="0.0.0.0", audio_host="0.0.0.0",
            demo_html=b"demo", allow_pilot_network_bind=True,
        )
        self.assertEqual(runtime.http_host, "0.0.0.0")
