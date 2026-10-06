"""Explicitly non-durable, private-cloud Account Service Pilot demo.

This is a separate entrypoint from ``prototype.server``. It accepts real
ZITADEL identities and real audio, but holds session and identity keys only
in process memory. Restart can make previous meetings unreadable. The
PostgreSQL database MUST use a dedicated, non-backed-up Pod-local volume.
This is not Account Service v1 retention/recovery acceptance or GA.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import signal
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

from .live_stt import RealtimeSTTConfig
from .postgres_service_store import PostgresServiceStore
from .real_analyzer import RealAnalyzer
from .schema import SchemaValidator
from .service_audio_transport import ServiceAudioGateway
from .service_browser_security import ServiceBrowserSecurity
from .service_candidate_runtime import ServiceCandidateRuntime
from .service_crypto import EphemeralPilotDemoKeyRegistry
from .service_identity_store import ServiceIdentityStore
from .service_oidc import OidcConfiguration, ServiceOidcClient
from .service_worker_supervisor import ServiceWorkerSupervisor


ROOT = Path(__file__).resolve().parents[1]
WEB = Path(__file__).resolve().parent / "web"


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required Pilot demo setting: {name}")
    return value


def _local_demo_dsn() -> str:
    dsn = _required("RONRO_SERVICE_POSTGRES_DSN")
    parsed = conninfo_to_dict(dsn)
    if (parsed.get("host") not in {"127.0.0.1", "localhost"}
            or parsed.get("hostaddr") not in {None, "127.0.0.1"}
            or parsed.get("dbname") != "ronro_pilot_demo"
            or parsed.get("port") not in {None, "5432"}
            or parsed.get("service") is not None):
        raise RuntimeError("Pilot demo database must be Pod-local and dedicated")
    return dsn


def _oidc() -> ServiceOidcClient:
    origin = _required("RONRO_SERVICE_PUBLIC_ORIGIN")
    return ServiceOidcClient(OidcConfiguration(
        issuer=_required("RONRO_SERVICE_OIDC_ISSUER"),
        client_id=_required("RONRO_SERVICE_OIDC_CLIENT_ID"),
        public_origin=origin,
        redirect_uri=origin + "/api/service/auth/callback",
        authorization_endpoint=_required("RONRO_SERVICE_OIDC_AUTHORIZATION_ENDPOINT"),
        token_endpoint=_required("RONRO_SERVICE_OIDC_TOKEN_ENDPOINT"),
        jwks_uri=_required("RONRO_SERVICE_OIDC_JWKS_URI"),
        token_endpoint_auth_method="none",
    ))


async def _migrate_when_ready(store: PostgresServiceStore) -> None:
    for attempt in range(30):
        try:
            await asyncio.to_thread(store.migrate)
            return
        except psycopg.OperationalError:
            if attempt == 29:
                raise RuntimeError("Pilot demo database unavailable") from None
            await asyncio.sleep(1)


async def run() -> None:
    if os.getenv("RONRO_SERVICE_PILOT_DEMO") != "enabled":
        raise RuntimeError("Pilot demo must be explicitly enabled")
    if os.getenv("RONRO_SERVICE_EPHEMERAL_STORAGE_ACK") != "enabled":
        raise RuntimeError("Pod-local non-backed-up storage must be acknowledged")
    dsn = _local_demo_dsn()
    origin = _required("RONRO_SERVICE_PUBLIC_ORIGIN")
    oidc = _oidc()
    stt = RealtimeSTTConfig.from_environment()
    if not stt.api_key or stt.finalization_mode != "server_vad_bounded":
        raise RuntimeError("Pilot demo STT configuration is incomplete")
    validator = SchemaValidator(ROOT / "schemas")
    store = PostgresServiceStore(
        dsn, validator, EphemeralPilotDemoKeyRegistry(),
        allow_ephemeral_pilot_registry=True,
    )
    await _migrate_when_ready(store)
    identity = ServiceIdentityStore(
        dsn, secrets.token_bytes(32), ServiceBrowserSecurity(origin),
        expected_issuer=oidc.config.issuer,
    )
    analyzer = RealAnalyzer.from_environment(
        schema_validator=validator,
        prompt_version=os.getenv("PROMPT_VERSION", "analyzer-prompt-v10-action-time-horizon"),
        output_schema_version="v3",
    )
    gateway = ServiceAudioGateway(identity, store, stt_config=stt)
    workers = ServiceWorkerSupervisor.from_service_components(
        store=store, identity=identity, analyzers=[analyzer],
    )
    pilot_host = "0.0.0.0"  # nosec B104 - isolated private Pilot deployment only
    runtime = ServiceCandidateRuntime(
        identity=identity, oidc=oidc, content=store, gateway=gateway,
        workers=workers, http_host=pilot_host, http_port=8000,
        audio_host=pilot_host, audio_port=8765,
        allow_pilot_network_bind=True,
        demo_html=(WEB / "service-demo.html").read_bytes(),
        demo_worklet=(WEB / "live-audio-worklet.js").read_bytes(),
        demo_script=(WEB / "service-demo.js").read_bytes(),
    )
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stopping.set)
    await runtime.start()
    try:
        await stopping.wait()
    finally:
        if not await runtime.stop(timeout_seconds=30):
            raise RuntimeError("Pilot demo workers did not stop cleanly")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
