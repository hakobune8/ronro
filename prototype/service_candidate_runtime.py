"""Loopback-only Account Service composition; never imported by Pilot.

This binds the existing owner HTTP and audio WSS candidates together with
background workers. It is intentionally not a public deployment entrypoint:
real IdP, key lifetime, backup deletion, and browser/PDF gates remain open.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

from .service_audio_transport import ServiceAudioGateway, serve_service_audio_candidate
from .service_identity_store import ServiceIdentityStore
from .service_meeting_http import create_service_meeting_server
from .service_oidc import ServiceOidcClient
from .service_worker_supervisor import ServiceWorkerSupervisor
from .postgres_service_store import PostgresServiceStore


class ServiceCandidateRuntime:
    def __init__(
        self, *, identity: ServiceIdentityStore, oidc: ServiceOidcClient,
        content: PostgresServiceStore, gateway: ServiceAudioGateway,
        workers: ServiceWorkerSupervisor,
        http_host: str = "127.0.0.1", http_port: int = 0,
        audio_host: str = "127.0.0.1", audio_port: int = 0,
        demo_html: bytes | None = None, demo_worklet: bytes | None = None,
        demo_script: bytes | None = None,
        shared_html: bytes | None = None,
        allow_pilot_network_bind: bool = False,
    ) -> None:
        allowed_hosts = {"127.0.0.1", "::1"}
        if allow_pilot_network_bind and demo_html is not None:
            # Only the explicitly enabled, authenticated private Pilot route.
            allowed_hosts.add("0.0.0.0")  # nosec B104
        if http_host not in allowed_hosts or audio_host not in allowed_hosts:
            raise ValueError("Service candidate may bind only to loopback")
        self.identity = identity
        self.oidc = oidc
        self.content = content
        self.gateway = gateway
        self.workers = workers
        self.http_host = http_host
        self.http_port = http_port
        self.audio_host = audio_host
        self.audio_port = audio_port
        self.demo_html = demo_html
        self.demo_worklet = demo_worklet
        self.demo_script = demo_script
        self.shared_html = shared_html
        self.allow_pilot_network_bind = allow_pilot_network_bind
        self.http_server: Any = None
        self.audio_server: Any = None
        self.http_thread: threading.Thread | None = None
        self._started = False
        self._closed = False
        self._workers_start_attempted = False

    async def start(self) -> None:
        if self._started or self._closed:
            raise RuntimeError("Service candidate cannot be started twice")
        self._started = True
        try:
            self.http_server = create_service_meeting_server(
                self.identity, self.oidc, self.content,
                host=self.http_host, port=self.http_port,
                demo_html=self.demo_html, demo_worklet=self.demo_worklet,
                demo_script=self.demo_script,
                shared_html=self.shared_html,
                allow_pilot_network_bind=self.allow_pilot_network_bind,
            )
            self.http_thread = threading.Thread(
                target=self.http_server.serve_forever,
                name="ronro-service-http", daemon=True,
            )
            self.http_thread.start()
            self.audio_server = await serve_service_audio_candidate(
                self.gateway, host=self.audio_host, port=self.audio_port,
                allow_pilot_network_bind=self.allow_pilot_network_bind,
            )
            self._workers_start_attempted = True
            self.workers.start()
        except BaseException:
            await self.stop()
            raise

    async def stop(self, *, timeout_seconds: float = 10.0) -> bool:
        """Stop intake before workers; report an in-flight worker honestly."""

        if timeout_seconds < 0:
            raise ValueError("Stop timeout must not be negative")
        self._closed = True
        stopped = True
        if self.audio_server is not None:
            try:
                self.audio_server.close()
                await asyncio.wait_for(self.audio_server.wait_closed(), timeout_seconds)
                self.audio_server = None
            except Exception:
                stopped = False
        if self.http_server is not None:
            try:
                if self.http_thread is not None and self.http_thread.is_alive():
                    await asyncio.to_thread(self.http_server.shutdown)
                self.http_server.server_close()
                self.http_server = None
            except Exception:
                stopped = False
        if self.http_thread is not None and self.http_thread.is_alive():
            await asyncio.to_thread(self.http_thread.join, timeout_seconds)
        try:
            workers_stopped = (await asyncio.to_thread(
                self.workers.stop, timeout_seconds=timeout_seconds,
            )) if self._workers_start_attempted else True
        except Exception:
            workers_stopped = False
        http_stopped = self.http_thread is None or not self.http_thread.is_alive()
        return bool(stopped and self.audio_server is None and
                    self.http_server is None and http_stopped and workers_stopped)
