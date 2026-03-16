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

import time

from mmo_maid_sdk import Plugin, Context

plugin = Plugin()


@plugin.on_ready
def ready(ctx: Context):
    ctx.log("demo_counter v2.1 started (SDK)")


@plugin.on_event("message")
def on_message(ctx: Context, event: dict):
    author = event.get("author") if isinstance(event.get("author"), dict) else {}

    # Skip bot messages to prevent infinite loops
    if author.get("bot"):
        return

    content = str(event.get("content") or "").strip().lower()
    channel_id = str(event.get("channel_id") or "")
    user_id = str(author.get("id") or "")
    username = author.get("username") or "someone"

    if content == "!demo" or content == "!demo count":
        cmd_count(ctx, channel_id, user_id, username)
    elif content == "!demo info":
        cmd_info(ctx, channel_id, user_id)
    elif content == "!demo edit":
        cmd_edit(ctx, channel_id)
    elif content == "!demo react":
        cmd_react(ctx, channel_id)
    elif content == "!demo embed":
        cmd_embed(ctx, channel_id, username)
    elif content == "!demo stats":
        cmd_stats(ctx, channel_id)
    elif content == "!demo reset":
        cmd_reset(ctx, channel_id)
    elif content == "!demo help":
        cmd_help(ctx, channel_id)


# ── Command handlers ──────────────────────────────────────────────────────────

def cmd_count(ctx: Context, channel_id: str, user_id: str, username: str):
    """!demo — Increment counter and greet."""
    data = ctx.kv.get("counter") or {"total": 0, "users": {}}
    if not isinstance(data, dict):
        data = {"total": 0, "users": {}}

    data["total"] = data.get("total", 0) + 1
    users = data.get("users", {})
    users[user_id] = users.get(user_id, 0) + 1
    data["users"] = users
    ctx.kv.set("counter", data)

    result = ctx.discord.send_message(
        channel_id=channel_id,
        content=(
            f"Hey **{username}**! Counter is now at **{data['total']}** "
            f"(you: **{users[user_id]}** times)."
        ),
    )
    msg_id = result.get("message_id")
    if msg_id:
        ctx.discord.add_reaction(channel_id=channel_id, message_id=str(msg_id), emoji="👋")


def cmd_info(ctx: Context, channel_id: str, user_id: str):
    """!demo info — Show channel, member, and role info."""
    lines = ["**Server Info**\n"]

    ch = ctx.discord.get_channel(channel_id=channel_id)
    if ch:
        lines.append(f"📝 Channel: **{ch.get('name', '?')}** (type: {ch.get('type', '?')})")
        if ch.get("topic"):
            lines.append(f"   Topic: {ch['topic']}")

    member = ctx.discord.get_member(user_id=user_id)
    if member:
        display = member.get("display_name") or member.get("nick") or member.get("username") or "?"
        role_count = len(member.get("roles", []))
        joined = str(member.get("joined_at") or "?")[:10]
        lines.append(f"👤 You: **{display}** ({role_count} roles, joined {joined})")

    roles = ctx.discord.list_roles()
    if roles:
        named = [r for r in roles if r.get("name") != "@everyone"]
        named.sort(key=lambda r: r.get("position", 0), reverse=True)
        top_5 = named[:5]
        role_names = ", ".join(f"**{r.get('name', '?')}**" for r in top_5)
        lines.append(f"🎭 Top roles ({len(named)} total): {role_names}")

    ctx.discord.send_message(channel_id=channel_id, content="\n".join(lines))


def cmd_edit(ctx: Context, channel_id: str):
    """!demo edit — Send a message, wait, then edit it."""
    result = ctx.discord.send_message(
        channel_id=channel_id,
        content="⏳ This message will be edited in 2 seconds...",
    )
    msg_id = result.get("message_id")
    if not msg_id:
        return
    ctx.log("Sent message, waiting 2s before edit")
    time.sleep(2)
    ctx.discord.edit_message(
        channel_id=channel_id,
        message_id=str(msg_id),
        content="✅ Message edited! The edit_message capability works.",
    )
    ctx.discord.add_reaction(channel_id=channel_id, message_id=str(msg_id), emoji="✏️")


def cmd_react(ctx: Context, channel_id: str):
    """!demo react — Send a message and add multiple reactions."""
    result = ctx.discord.send_message(
        channel_id=channel_id,
        content="React test — watch the reactions appear:",
    )
    msg_id = result.get("message_id")
    if not msg_id:
        return
    for emoji in ["1️⃣", "2️⃣", "3️⃣", "✅", "🎉"]:
        ctx.discord.add_reaction(channel_id=channel_id, message_id=str(msg_id), emoji=emoji)
        time.sleep(0.3)


def cmd_embed(ctx: Context, channel_id: str, username: str):
    """!demo embed — Send a rich embed."""
    data = ctx.kv.get("counter") or {"total": 0, "users": {}}
    total = data.get("total", 0) if isinstance(data, dict) else 0

    ctx.discord.send_message(
        channel_id=channel_id,
        embeds=[{
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
        }],
    )


def cmd_stats(ctx: Context, channel_id: str):
    """!demo stats — Show per-user stats from KV."""
    data = ctx.kv.get("counter") or {"total": 0, "users": {}}
    if not isinstance(data, dict):
        ctx.discord.send_message(channel_id=channel_id, content="No stats yet — use the counter first.")
        return

    total = data.get("total", 0)
    users = data.get("users", {})

    if not users:
        ctx.discord.send_message(channel_id=channel_id, content=f"Counter is at **{total}** but no per-user data yet.")
        return

    sorted_users = sorted(users.items(), key=lambda x: x[1], reverse=True)
    lines = [f"**Counter Stats** (total: **{total}**)\n"]
    for i, (uid, count) in enumerate(sorted_users[:10], 1):
        member = ctx.discord.get_member(user_id=uid)
        name = member.get("display_name") or member.get("nick") or member.get("username") or uid if member else uid
        lines.append(f"{i}. **{name}** — {count} time(s)")

    ctx.discord.send_message(channel_id=channel_id, content="\n".join(lines))


def cmd_reset(ctx: Context, channel_id: str):
    """!demo reset — Reset the counter."""
    ctx.kv.delete("counter")
    result = ctx.discord.send_message(channel_id=channel_id, content="🔄 Counter has been reset to zero.")
    msg_id = result.get("message_id")
    if msg_id:
        ctx.discord.add_reaction(channel_id=channel_id, message_id=str(msg_id), emoji="🔄")


def cmd_help(ctx: Context, channel_id: str):
    """!demo help — Show all commands."""
    ctx.discord.send_message(channel_id=channel_id, content="\n".join([
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


plugin.run()
