"""
demo_counter — Advanced MMO Maid plugin demo.

Commands:
  !demo          — Count and greet (KV read/write + send message)
  !demo info     — Show server info (get_channel, get_member, list_roles)
  !demo edit     — Send a message, then edit it after 2 seconds
  !demo react    — Send a message and add reactions to it
  !demo embed    — Send a rich embed message
  !demo stats    — Show per-user command usage from KV (batch KV ops)
  !demo reset    — Reset the counter to zero (KV delete)
  !demo help     — Show available commands

Tests capabilities:
  storage:kv, discord:send_message, discord:edit_message,
  discord:delete_message, discord:add_reaction, discord:read,
  events:message_content
"""
from __future__ import annotations

import json
import sys
import time
from typing import Any, Dict, Optional


# ── JSON-RPC transport ────────────────────────────────────────────────────────

def _send(obj: Dict[str, Any]) -> None:
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
        return {}


class RpcClient:
    def __init__(self):
        self._next_id = 1

    def call(self, method: str, params: Dict[str, Any]) -> Any:
        req_id = self._next_id
        self._next_id += 1
        _send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})

        while True:
            msg = _read_line()
            if msg is None:
                raise RuntimeError("host closed")
            if not isinstance(msg, dict):
                continue
            if msg.get("id") == req_id:
                if "error" in msg:
                    err = msg.get("error") or {}
                    raise RuntimeError(str(err.get("message") if isinstance(err, dict) else err))
                return msg.get("result")
            # Handle notifications that arrive while waiting for our response
            if "method" in msg and "id" not in msg:
                _pending_notifications.append(msg)

    def log(self, message: str, level: str = "info") -> None:
        _send({"jsonrpc": "2.0", "method": "plugin.log",
               "params": {"level": level, "message": message}})


rpc = RpcClient()
_pending_notifications = []


# ── KV helpers ────────────────────────────────────────────────────────────────

def kv_get(key: str, default=None) -> Any:
    """Get a value from KV, returning default if not found."""
    try:
        result = rpc.call("kv.get", {"key": key})
        if isinstance(result, dict) and result.get("value") is not None:
            return result["value"]
    except Exception:
        pass
    return default


def kv_put(key: str, value: Any) -> None:
    rpc.call("kv.put", {"key": key, "value": value})


def kv_del(key: str) -> None:
    try:
        rpc.call("kv.del", {"key": key})
    except Exception:
        pass


# ── Discord helpers ───────────────────────────────────────────────────────────

def send(channel_id: str, content: str = "", embed: dict = None) -> Optional[str]:
    """Send a message and return the message_id."""
    params = {"channel_id": channel_id}
    if content:
        params["content"] = content
    if embed:
        params["embed"] = embed
    try:
        result = rpc.call("discord.send_message", params)
        if isinstance(result, dict):
            return str(result.get("message_id") or "")
    except Exception as e:
        rpc.log(f"send_message failed: {e}", "error")
    return None


def edit(channel_id: str, message_id: str, content: str) -> None:
    try:
        rpc.call("discord.edit_message", {
            "channel_id": channel_id,
            "message_id": message_id,
            "content": content,
        })
    except Exception as e:
        rpc.log(f"edit_message failed: {e}", "error")


def delete(channel_id: str, message_id: str) -> None:
    try:
        rpc.call("discord.delete_message", {
            "channel_id": channel_id,
            "message_id": message_id,
        })
    except Exception as e:
        rpc.log(f"delete_message failed: {e}", "error")


def react(channel_id: str, message_id: str, emoji: str) -> None:
    try:
        rpc.call("discord.add_reaction", {
            "channel_id": channel_id,
            "message_id": message_id,
            "emoji": emoji,
        })
    except Exception as e:
        rpc.log(f"add_reaction failed: {e}", "error")


def get_member(user_id: str) -> Optional[dict]:
    try:
        return rpc.call("discord.get_member", {"user_id": user_id})
    except Exception:
        return None


def get_channel(channel_id: str) -> Optional[dict]:
    try:
        return rpc.call("discord.get_channel", {"channel_id": channel_id})
    except Exception:
        return None


def list_roles() -> list:
    try:
        result = rpc.call("discord.list_roles", {})
        return result if isinstance(result, list) else []
    except Exception:
        return []


# ── Command handlers ──────────────────────────────────────────────────────────

def cmd_count(channel_id: str, user_id: str, username: str) -> None:
    """!demo — Increment counter and greet."""
    data = kv_get("counter", {"total": 0, "users": {}})
    if not isinstance(data, dict):
        data = {"total": 0, "users": {}}

    data["total"] = data.get("total", 0) + 1
    users = data.get("users", {})
    users[user_id] = users.get(user_id, 0) + 1
    data["users"] = users
    kv_put("counter", data)

    msg_id = send(channel_id,
        f"Hey **{username}**! Counter is now at **{data['total']}** "
        f"(you: **{users[user_id]}** times)."
    )
    if msg_id:
        react(channel_id, msg_id, "👋")


def cmd_info(channel_id: str, user_id: str) -> None:
    """!demo info — Show channel, member, and role info."""
    lines = ["**Server Info**\n"]

    # Channel info
    ch = get_channel(channel_id)
    if ch:
        lines.append(f"📝 Channel: **{ch.get('name', '?')}** (type: {ch.get('type', '?')})")
        if ch.get("topic"):
            lines.append(f"   Topic: {ch['topic']}")

    # Member info
    member = get_member(user_id)
    if member:
        display = member.get("display_name") or member.get("nick") or member.get("username") or "?"
        role_count = len(member.get("roles", []))
        joined = str(member.get("joined_at") or "?")[:10]
        lines.append(f"👤 You: **{display}** ({role_count} roles, joined {joined})")

    # Roles
    roles = list_roles()
    if roles:
        # Skip @everyone and sort by position
        named = [r for r in roles if r.get("name") != "@everyone"]
        named.sort(key=lambda r: r.get("position", 0), reverse=True)
        top_5 = named[:5]
        role_names = ", ".join(f"**{r.get('name', '?')}**" for r in top_5)
        lines.append(f"🎭 Top roles ({len(named)} total): {role_names}")

    send(channel_id, "\n".join(lines))


def cmd_edit(channel_id: str) -> None:
    """!demo edit — Send a message, wait, then edit it."""
    msg_id = send(channel_id, "⏳ This message will be edited in 2 seconds...")
    if not msg_id:
        return
    rpc.log(f"Sent message {msg_id}, waiting 2s before edit")
    time.sleep(2)
    edit(channel_id, msg_id, "✅ Message edited! The edit_message capability works.")
    react(channel_id, msg_id, "✏️")


def cmd_react(channel_id: str) -> None:
    """!demo react — Send a message and add multiple reactions."""
    msg_id = send(channel_id, "React test — watch the reactions appear:")
    if not msg_id:
        return
    for emoji in ["1️⃣", "2️⃣", "3️⃣", "✅", "🎉"]:
        react(channel_id, msg_id, emoji)
        time.sleep(0.3)  # Small delay to stay within rate limits


def cmd_embed(channel_id: str, username: str) -> None:
    """!demo embed — Send a rich embed."""
    data = kv_get("counter", {"total": 0, "users": {}})
    total = data.get("total", 0) if isinstance(data, dict) else 0

    embed = {
        "title": "Demo Counter Dashboard",
        "description": f"Plugin is running and has counted **{total}** total interactions.",
        "color": 0x58A6FF,
        "fields": [
            {"name": "Triggered by", "value": username, "inline": True},
            {"name": "Total count", "value": str(total), "inline": True},
            {"name": "Capabilities tested", "value": (
                "✅ storage:kv\n"
                "✅ discord:send_message\n"
                "✅ discord:read\n"
                "✅ events:message_content"
            ), "inline": False},
        ],
        "footer": {"text": "MMO Maid Plugin System"},
    }
    send(channel_id, embed=embed)


def cmd_stats(channel_id: str) -> None:
    """!demo stats — Show per-user stats from KV."""
    data = kv_get("counter", {"total": 0, "users": {}})
    if not isinstance(data, dict):
        send(channel_id, "No stats yet — use the counter first.")
        return

    total = data.get("total", 0)
    users = data.get("users", {})

    if not users:
        send(channel_id, f"Counter is at **{total}** but no per-user data yet.")
        return

    # Sort by count descending
    sorted_users = sorted(users.items(), key=lambda x: x[1], reverse=True)
    lines = [f"**Counter Stats** (total: **{total}**)\n"]
    for i, (uid, count) in enumerate(sorted_users[:10], 1):
        member = get_member(uid)
        name = "Unknown"
        if member:
            name = member.get("display_name") or member.get("nick") or member.get("username") or uid
        lines.append(f"{i}. **{name}** — {count} time(s)")

    send(channel_id, "\n".join(lines))


def cmd_reset(channel_id: str) -> None:
    """!demo reset — Reset the counter."""
    kv_del("counter")
    msg_id = send(channel_id, "🔄 Counter has been reset to zero.")
    if msg_id:
        react(channel_id, msg_id, "🔄")


def cmd_help(channel_id: str) -> None:
    """!demo help — Show all commands."""
    send(channel_id, "\n".join([
        "**Demo Counter Commands**",
        "",
        "`!demo` — Increment counter and greet",
        "`!demo info` — Show channel, member, and role info",
        "`!demo edit` — Send a message then edit it",
        "`!demo react` — Send a message with multiple reactions",
        "`!demo embed` — Send a rich embed message",
        "`!demo stats` — Show per-user usage leaderboard",
        "`!demo reset` — Reset the counter to zero",
        "`!demo help` — This message",
    ]))


# ── Event router ──────────────────────────────────────────────────────────────

def handle_event(msg: Dict[str, Any]) -> None:
    method = str(msg.get("method") or "")
    params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
    event_id = params.get("event_id")

    if method == "event.message_create":
        event = params.get("event") if isinstance(params.get("event"), dict) else {}
        channel_id = str(event.get("channel_id") or "")
        content = str(event.get("content") or "").strip()
        author = event.get("author") if isinstance(event.get("author"), dict) else {}
        user_id = str(author.get("id") or "")
        username = author.get("username") or "someone"

        # CRITICAL: Skip bot messages to prevent infinite loops
        if author.get("bot"):
            _ack(event_id)
            return

        lower = content.lower()
        if lower == "!demo" or lower == "!demo count":
            cmd_count(channel_id, user_id, username)
        elif lower == "!demo info":
            cmd_info(channel_id, user_id)
        elif lower == "!demo edit":
            cmd_edit(channel_id)
        elif lower == "!demo react":
            cmd_react(channel_id)
        elif lower == "!demo embed":
            cmd_embed(channel_id, username)
        elif lower == "!demo stats":
            cmd_stats(channel_id)
        elif lower == "!demo reset":
            cmd_reset(channel_id)
        elif lower == "!demo help":
            cmd_help(channel_id)

    _ack(event_id)


def _ack(event_id) -> None:
    if event_id is not None:
        try:
            rpc.call("event.ack", {"event_id": event_id})
        except Exception:
            pass


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    rpc.log("demo_counter v2.0 started")

    while True:
        # Process any notifications that arrived while waiting for RPC responses
        while _pending_notifications:
            handle_event(_pending_notifications.pop(0))

        msg = _read_line()
        if msg is None:
            return
        if not isinstance(msg, dict):
            continue

        method = str(msg.get("method") or "")
        if method == "host.shutdown":
            rpc.log("shutting down")
            return
        if "method" in msg and "id" not in msg:
            handle_event(msg)


if __name__ == "__main__":
    main()
