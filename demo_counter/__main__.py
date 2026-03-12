from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, Optional


def _send(obj: Dict[str, Any]) -> None:
    sys.stdout.flush()
    sys.stderr.flush()
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _read_line() -> Optional[Dict[str, Any]]:
    line = sys.stdin.readline()
    if not line:
        return None
    s = line.strip()
    if not s:
        return {}
    try:
        return json.loads(s)
    except Exception:
        # Ignore non-json
        return {}


class RpcClient:
    def __init__(self):
        self._next_id = 1

    def call(self, method: str, params: Dict[str, Any]) -> Any:
        req_id = self._next_id
        self._next_id += 1
        _send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})

        # Simple blocking wait for our response.
        while True:
            msg = _read_line()
            if msg is None:
                raise RuntimeError("host closed")
            if not isinstance(msg, dict):
                continue

            # Ignore host notifications while waiting.
            if msg.get("id") != req_id:
                # Re-emit notifications we receive so we don't lose them.
                # (In a real plugin SDK we'd queue these.)
                if "method" in msg and str(msg.get("method") or "").startswith("event."):
                    handle_event(msg)
                continue

            if "error" in msg:
                raise RuntimeError(str((msg.get("error") or {}).get("message") or "rpc error"))
            return msg.get("result")


rpc = RpcClient()


def log(message: str) -> None:
    try:
        _send({"jsonrpc": "2.0", "method": "plugin.log", "params": {"level": "info", "message": message}})
    except Exception:
        pass


def handle_event(msg: Dict[str, Any]) -> None:
    method = str(msg.get("method") or "")
    if method != "event.message_create":
        return

    params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
    event_id = params.get("event_id")
    ev = params.get("event") if isinstance(params.get("event"), dict) else {}

    channel_id = str(ev.get("channel_id") or "")
    content = str(ev.get("content") or "")

    # Only react if we see a trigger phrase.
    if "!demo" in content.lower():
        # Count how many times !demo was seen in this server.
        try:
            r = rpc.call("kv.get", {"key": "demo.count"})
            current = 0
            if isinstance(r, dict) and isinstance(r.get("value"), dict):
                current = int(r["value"].get("n") or 0)
        except Exception:
            current = 0

        current += 1

        try:
            rpc.call("kv.put", {"key": "demo.count", "value": {"n": current}})
        except Exception:
            pass

        # Send a message back (requires discord:send_message capability).
        try:
            rpc.call(
                "discord.send_message",
                {
                    "channel_id": channel_id,
                    "content": f"Demo Counter: I've seen !demo **{current}** time(s) in this server.",
                },
            )
        except Exception as e:
            log(f"send_message failed: {e}")

    # Ack so the event is marked delivered.
    try:
        rpc.call("event.ack", {"event_id": event_id})
    except Exception:
        pass


def main() -> None:
    log("demo_counter started")
    while True:
        msg = _read_line()
        if msg is None:
            return
        if not isinstance(msg, dict):
            continue

        # Host notifications
        if "method" in msg and "id" not in msg:
            if str(msg.get("method") or "").startswith("event."):
                handle_event(msg)


if __name__ == "__main__":
    main()
