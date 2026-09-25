"""Short, synthetic deployed correction smoke; prints no transcript or Node text.

Requires the live endpoint to be idle. Pilot recording consent is set for this
machine-generated audio only; the temporary source AIFF is removed on exit.
The deployed private recording follows the configured seven-day policy.
"""

from __future__ import annotations

import asyncio
import json
import sys
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import websockets

from prototype.live_audio import AudioChunk, encode_audio_frame


BASE = "https://ronro.hakobune8.com"
SENTENCES = (
    "最初の議題は避難所の飲料水です。三つの避難所で初日の飲料水が足りない見込みです。",
    "この飲料水不足への対応として、既存倉庫の水を三つの避難所に再配置する案を検討します。",
)


def request(route: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    req = Request(BASE + route, data=body,
                  headers={"Content-Type": "application/json"} if body else {},
                  method="POST" if body else "GET")
    try:
        with urlopen(req, timeout=20) as response:
            return json.load(response)
    except HTTPError as exc:
        try:
            code = json.load(exc).get("error", {}).get("code", "unknown")
        except (ValueError, AttributeError):
            code = "unknown"
        raise RuntimeError(f"{route}: HTTP {exc.code}, code={code}") from exc


def make_pcm() -> bytes:
    silence = b"\0\0" * (24_000 * 2)
    parts = []
    with tempfile.TemporaryDirectory(prefix="ronro-synthetic-smoke-") as directory:
        for index, sentence in enumerate(SENTENCES):
            source = Path(directory) / f"speech-{index}.aiff"
            subprocess.run(["say", "-v", "Kyoko", "-r", "175", "-o", str(source), sentence], check=True)
            converted = subprocess.run(["ffmpeg", "-v", "error", "-i", str(source),
                                        "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1",
                                        "-ar", "24000", "pipe:1"], check=True, capture_output=True)
            parts.append(converted.stdout)
    return silence.join(parts) + silence


async def send_audio(url: str, pcm: bytes, controller: str) -> tuple[str | None, bool]:
    async with websockets.connect(url, open_timeout=15, max_size=2**22) as socket:
        ended = asyncio.Event()
        async def consume() -> None:
            try:
                async for message in socket:
                    if isinstance(message, str) and json.loads(message).get("type") == "session_ended":
                        ended.set()
            except websockets.ConnectionClosed:
                pass
        reader = asyncio.create_task(consume())
        chunk_bytes = 2_400 * 2
        for sequence, offset in enumerate(range(0, len(pcm), chunk_bytes)):
            payload = pcm[offset:offset + chunk_bytes]
            await socket.send(encode_audio_frame(AudioChunk(sequence, offset / 48_000, payload)))
            await asyncio.sleep(len(payload) / 48_000)
        await asyncio.sleep(3)
        correction_event = None
        corrected = False
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            snap = await asyncio.to_thread(request, "/api/live?controller_id=" + controller)
            graph = snap["state"]["graph"]
            nodes = [node for node in graph["nodes"] if node["type"] != "topic"
                     and node["status"] not in {"archived", "parked"}]
            if len(nodes) >= 2 and snap["live_state"]["runtime_state"] == "active":
                existing = next((edge for edge in graph["edges"]
                                 if edge["type"] == "discussion_provenance"), None)
                if existing:
                    source, target = existing["source_node_id"], existing["target_node_id"]
                    old = {"source_node_id": source, "target_node_id": target,
                           "relation_type": "discussion_provenance"}
                    new = None
                else:
                    target = snap["map"]["semantic_canvas"]["focus_id"]
                    source = next((node["id"] for node in nodes if node["id"] != target), None)
                    if not source or not target:
                        break
                    old = None
                    new = {"source_node_id": source, "target_node_id": target,
                           "relation_type": "discussion_provenance"}
                response = await asyncio.to_thread(request, "/api/live/commands", {
                    "controller_id": controller, "command_type": "correct_relation",
                    "old_relation": old, "new_relation": new,
                    "expected_revision": graph["revision"],
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                    "source_evidence_ids": []})
                after = response["snapshot"]
                correction_event = response["event"]["event_type"]
                corrected = any(edge["source_node_id"] == source and edge["target_node_id"] == target
                                and edge["type"] == "discussion_provenance"
                                for edge in after["map"]["semantic_canvas"]["edges"]) == (new is not None)
                break
            await asyncio.sleep(.5)
        await socket.send(json.dumps({"type": "stop"}))
        await asyncio.wait_for(ended.wait(), timeout=60)
        reader.cancel()
        return correction_event, corrected


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "--disconnect-during-stop":
        asyncio.run(disconnect_during_stop())
        return
    prior = request("/api/live")
    if prior.get("live_state", {}).get("runtime_state") not in {"idle", "ended", "ended_with_incomplete_processing"}:
        raise RuntimeError("A live session is running; refuse to interrupt it")
    controller = "synthetic-canvas-smoke-" + uuid.uuid4().hex[:12]
    pcm = make_pcm()
    started = request("/api/live/start", {"mode": "continuous", "controller_id": controller,
                                           "all_participants_consented": True})
    try:
        correction_event, corrected = asyncio.run(send_audio(started["websocket_url"], pcm, controller))
    except Exception:
        request("/api/live/stop", {"controller_id": controller})
        raise
    final = request("/api/live?controller_id=" + controller)
    graph = final["state"]["graph"]
    queue = final["live_state"]["queue"]
    print(json.dumps({"runtime_state": final["live_state"]["runtime_state"],
                      "evidence_count": len(final["state"]["evidence"]),
                      "node_count": len([node for node in graph["nodes"] if node["type"] != "topic"]),
                      "relation_count": len([edge for edge in graph["edges"] if edge["type"] == "discussion_provenance"]),
                      "correction_event": correction_event, "canvas_correction_verified": corrected,
                      "queue": {name: queue[name] for name in ("pending", "processing", "failed")},
                      "graph_revision": graph["revision"],
                      "rendered_revision": final["live_state"].get("rendered_revision")},
                     ensure_ascii=False))


async def disconnect_during_stop() -> None:
    """Synthetic boundary probe: finish visibly, never leave finalizing stuck."""

    prior = await asyncio.to_thread(request, "/api/live")
    if prior.get("live_state", {}).get("runtime_state") not in {"idle", "ended", "ended_with_incomplete_processing"}:
        raise RuntimeError("A live session is running; refuse to interrupt it")
    controller = "synthetic-stop-race-" + uuid.uuid4().hex[:12]
    pcm = await asyncio.to_thread(make_pcm)
    started = await asyncio.to_thread(request, "/api/live/start", {
        "mode": "continuous", "controller_id": controller,
        "all_participants_consented": True})
    async with websockets.connect(started["websocket_url"], open_timeout=15) as socket:
        for sequence in range(15):
            payload = pcm[sequence * 4800:(sequence + 1) * 4800]
            await socket.send(encode_audio_frame(AudioChunk(sequence, sequence / 10, payload)))
            await asyncio.sleep(.1)
        await asyncio.to_thread(request, "/api/live/stop", {"controller_id": controller})
        await socket.close()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        snap = await asyncio.to_thread(request, "/api/live?controller_id=" + controller)
        state = snap["live_state"]
        if state["runtime_state"] in {"ended", "ended_with_incomplete_processing"}:
            print(json.dumps({"runtime_state": state["runtime_state"],
                              "error_code": (state.get("error") or {}).get("code"),
                              "possible_evidence_gap_count": state["metrics"]["possible_evidence_gap_count"],
                              "queue": {name: state["queue"][name]
                                        for name in ("pending", "processing", "failed")},
                              "graph_revision": state["graph_revision"],
                              "rendered_revision": state["rendered_revision"]}))
            return
        await asyncio.sleep(.25)
    raise RuntimeError("Disconnect/stop race left the session finalizing")


if __name__ == "__main__":
    main()
