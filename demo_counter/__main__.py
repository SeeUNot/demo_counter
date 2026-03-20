"""
demo_counter — Full SDK showcase plugin for MMO Maid.

Demonstrates every SDK feature:
  @plugin.on_ready             Boot handler
  @plugin.on_event()           Raw event handling (legacy text commands)
  @plugin.on_slash_command()   Slash command handlers
  @plugin.on_component()       Button / select menu interactions
  @plugin.on_modal_submit()    Modal form submissions
  @plugin.schedule()           Background scheduled tasks
  @plugin.on_dashboard()       Web dashboard data handlers

Slash commands:
  /demo           Increment counter and show count
  /demo-board     Post a live counter board with buttons
  /demo-stats     Show the leaderboard (uses defer + followup)
  /demo-goal      Set a custom counter goal (opens modal)
  /demo-info      Show server info (channel, member, roles)
  /demo-help      Show all available commands

Legacy text commands:
  !demo           Increment counter
  !demo board     Post the counter board
  !demo help      Show commands

Dashboard:
  Overview page — stat cards (total clicks, unique users) + leaderboard table
  Settings page — configurable goal and log channel

Capabilities used:
  storage:kv, discord:send_message, discord:edit_message,
  discord:delete_message, discord:add_reaction, discord:read,
  interaction:respond, events:message_content
"""
from __future__ import annotations

import time

from mmo_maid_sdk import (
    Plugin, Context,
    ActionRow, Button, SelectMenu, SelectOption, TextInput,
)

plugin = Plugin()

# ─── Constants ────────────────────────────────────────────────────────────────

DEFAULT_GOAL = 50
THEMES = {
    "blue":   0x58A6FF,
    "green":  0x2ECC71,
    "purple": 0x9B59B6,
    "red":    0xE74C3C,
    "gold":   0xF1C40F,
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_counter(ctx: Context) -> dict:
    """Load counter data from KV with safe defaults."""
    data = ctx.kv.get("counter")
    if not isinstance(data, dict):
        data = {}
    data.setdefault("total", 0)
    data.setdefault("users", {})
    data.setdefault("goal", DEFAULT_GOAL)
    return data


def _get_settings(ctx: Context) -> dict:
    """Load plugin settings from KV."""
    settings = ctx.kv.get("settings")
    if not isinstance(settings, dict):
        settings = {}
    settings.setdefault("goal", DEFAULT_GOAL)
    settings.setdefault("theme", "blue")
    settings.setdefault("log_channel_id", "")
    return settings


def _theme_color(ctx: Context) -> int:
    """Get the current theme color."""
    settings = _get_settings(ctx)
    return THEMES.get(settings.get("theme", "blue"), THEMES["blue"])


def _build_board_embed(data: dict, color: int = 0x58A6FF) -> dict:
    """Build the counter board embed from current data."""
    total = data.get("total", 0)
    users = data.get("users", {})
    goal = data.get("goal", DEFAULT_GOAL)

    filled = min(int((total / max(goal, 1)) * 20), 20)
    bar = "\u2588" * filled + "\u2591" * (20 - filled)

    sorted_users = sorted(users.items(), key=lambda x: x[1], reverse=True)
    medals = ["\U0001f947", "\U0001f948", "\U0001f949"]
    contrib_lines = []
    for i, (uid, count) in enumerate(sorted_users[:5]):
        medal = medals[i] if i < 3 else "\u2022"
        contrib_lines.append(f"{medal} <@{uid}> \u2014 **{count}** clicks")

    fields = [
        {"name": "Progress", "value": f"`{bar}` **{total}** / {goal}", "inline": False},
    ]
    if contrib_lines:
        fields.append({"name": "Top Contributors", "value": "\n".join(contrib_lines), "inline": False})
    fields.append({"name": "Participants", "value": str(len(users)), "inline": True})
    fields.append({"name": "Remaining", "value": str(max(0, goal - total)), "inline": True})

    done = total >= goal
    return {
        "title": "\U0001f3c6 Goal Reached!" if done else "\U0001f4ca Counter Board",
        "description": "Click the buttons below to add to the counter!",
        "color": 0x2ECC71 if done else color,
        "fields": fields,
        "footer": {"text": "MMO Maid Demo Counter \u2022 Live updating"},
    }


def _board_components() -> list:
    """Build the button + select rows for the counter board."""
    return [
        ActionRow(
            Button("+1", custom_id="demo_increment", style="primary", emoji="\U0001f44d"),
            Button("+5", custom_id="demo_increment_5", style="secondary", emoji="\U0001f525"),
            Button("Stats", custom_id="demo_show_stats", style="secondary", emoji="\U0001f4ca"),
            Button("Set Goal", custom_id="demo_set_goal", style="success", emoji="\U0001f3af"),
            Button("Reset", custom_id="demo_board_reset", style="danger", emoji="\U0001f504"),
        ).to_dict(),
        ActionRow(
            SelectMenu("demo_theme_select", options=[
                SelectOption("Blue",   "blue",   emoji="\U0001f535"),
                SelectOption("Green",  "green",  emoji="\U0001f7e2"),
                SelectOption("Purple", "purple", emoji="\U0001f7e3"),
                SelectOption("Red",    "red",    emoji="\U0001f534"),
                SelectOption("Gold",   "gold",   emoji="\U0001f7e1"),
            ], placeholder="\U0001f3a8 Choose board theme"),
        ).to_dict(),
    ]


def _update_board(ctx: Context):
    """Re-render and edit the board message with current data."""
    board = ctx.kv.get("board")
    if not board or not isinstance(board, dict):
        return
    channel_id = str(board.get("channel_id") or "")
    message_id = str(board.get("message_id") or "")
    if not channel_id or not message_id:
        return

    data = _get_counter(ctx)
    embed = _build_board_embed(data, _theme_color(ctx))
    try:
        ctx.discord.edit_message(channel_id=channel_id, message_id=message_id, embeds=[embed])
    except Exception as e:
        ctx.log(f"Board update failed: {e}", level="warning")


def _increment(ctx: Context, user_id: str, amount: int = 1) -> dict:
    """Increment counter for a user. Returns updated data."""
    data = _get_counter(ctx)
    data["total"] = data.get("total", 0) + amount
    users = data.get("users", {})
    users[user_id] = users.get(user_id, 0) + amount
    data["users"] = users

    # Track activity timestamps for the dashboard chart
    activity = ctx.kv.get("activity") or []
    if not isinstance(activity, list):
        activity = []
    activity.append({"ts": int(time.time()), "amount": amount, "user_id": user_id})
    # Keep last 500 events
    if len(activity) > 500:
        activity = activity[-500:]
    ctx.kv.set("activity", activity)

    ctx.kv.set("counter", data)
    return data


# ═══════════════════════════════════════════════════════════════════════════════
#  on_ready — Boot handler
# ═══════════════════════════════════════════════════════════════════════════════

@plugin.on_ready
def ready(ctx: Context):
    ctx.log("demo_counter v4.0 started \u2014 full SDK showcase")


# ═══════════════════════════════════════════════════════════════════════════════
#  Scheduled task — Background heartbeat every 5 minutes
# ═══════════════════════════════════════════════════════════════════════════════

@plugin.schedule(300)
def heartbeat(ctx: Context):
    """Record a periodic heartbeat with current stats."""
    data = _get_counter(ctx)
    ctx.kv.set("heartbeat", {
        "ts": int(time.time()),
        "total": data.get("total", 0),
        "users": len(data.get("users", {})),
    })
    ctx.log(f"Heartbeat: total={data.get('total', 0)}, users={len(data.get('users', {}))}")


# ═══════════════════════════════════════════════════════════════════════════════
#  Slash commands
# ═══════════════════════════════════════════════════════════════════════════════

@plugin.on_slash_command("demo")
def slash_demo(ctx: Context, event: dict):
    """/demo — Increment counter and show current count."""
    user_id = str(event.get("user_id") or event.get("author_id") or "")
    username = str(event.get("author_username") or event.get("username") or "someone")

    data = _increment(ctx, user_id)
    user_count = data["users"].get(user_id, 0)

    ctx.interaction.respond(
        content=f"Hey **{username}**! Counter is now at **{data['total']}** (you: **{user_count}** times).",
    )
    _update_board(ctx)


@plugin.on_slash_command("demo-board")
def slash_board(ctx: Context, event: dict):
    """/demo-board — Post the interactive counter board."""
    channel_id = str(event.get("channel_id") or "")
    if not channel_id:
        ctx.interaction.respond(content="Could not determine channel.", ephemeral=True)
        return

    data = _get_counter(ctx)
    embed = _build_board_embed(data, _theme_color(ctx))

    result = ctx.discord.send_message(
        channel_id=channel_id,
        embeds=[embed],
        components=_board_components(),
    )
    msg_id = result.get("message_id")
    if msg_id:
        ctx.kv.set("board", {"channel_id": channel_id, "message_id": str(msg_id)})
        ctx.interaction.respond(content="\U0001f4ca Board posted! Use the buttons to interact.", ephemeral=True)
    else:
        ctx.interaction.respond(content="Failed to post the board.", ephemeral=True)


@plugin.on_slash_command("demo-stats")
def slash_stats(ctx: Context, event: dict):
    """/demo-stats — Show leaderboard. Demonstrates defer() + followup()."""
    # Defer so we have time to build the response
    ctx.interaction.defer(ephemeral=False)

    data = _get_counter(ctx)
    total = data.get("total", 0)
    users = data.get("users", {})

    if not users:
        ctx.interaction.followup(content=f"Counter is at **{total}** but no per-user data yet.")
        return

    sorted_users = sorted(users.items(), key=lambda x: x[1], reverse=True)
    medals = ["\U0001f947", "\U0001f948", "\U0001f949"]
    lines = [f"**\U0001f4ca Counter Leaderboard** (total: **{total}**)\n"]
    for i, (uid, count) in enumerate(sorted_users[:10]):
        medal = medals[i] if i < 3 else f"`{i+1}.`"
        pct = round((count / max(total, 1)) * 100, 1)
        lines.append(f"{medal} <@{uid}> \u2014 **{count}** click(s) ({pct}%)")

    ctx.interaction.followup(
        embeds=[{
            "title": "\U0001f4ca Counter Leaderboard",
            "description": "\n".join(lines),
            "color": _theme_color(ctx),
            "footer": {"text": f"{len(users)} participants \u2022 {total} total clicks"},
        }],
    )


@plugin.on_slash_command("demo-goal")
def slash_goal(ctx: Context, event: dict):
    """/demo-goal — Open a modal to set a custom counter goal."""
    data = _get_counter(ctx)
    current_goal = str(data.get("goal", DEFAULT_GOAL))

    ctx.interaction.send_modal(
        title="Set Counter Goal",
        custom_id="demo_goal_form",
        fields=[
            TextInput("Goal Number", "goal_value", placeholder="e.g. 100", value=current_goal),
            TextInput("Announcement (optional)", "goal_message",
                      style="paragraph", required=False,
                      placeholder="Message to post when goal is reached"),
        ],
    )


@plugin.on_slash_command("demo-info")
def slash_info(ctx: Context, event: dict):
    """/demo-info — Show server info using discord:read capability."""
    channel_id = str(event.get("channel_id") or "")
    user_id = str(event.get("user_id") or event.get("author_id") or "")

    lines = ["**\U0001f50d Server Info**\n"]

    if channel_id:
        ch = ctx.discord.get_channel(channel_id=channel_id)
        if ch:
            lines.append(f"\U0001f4dd Channel: **{ch.get('name', '?')}** (type: {ch.get('type', '?')})")
            if ch.get("topic"):
                lines.append(f"   Topic: {ch['topic']}")

    if user_id:
        member = ctx.discord.get_member(user_id=user_id)
        if member:
            display = member.get("display_name") or member.get("nick") or member.get("username") or "?"
            role_count = len(member.get("roles", []))
            joined = str(member.get("joined_at") or "?")[:10]
            lines.append(f"\U0001f464 You: **{display}** ({role_count} roles, joined {joined})")

    roles = ctx.discord.list_roles()
    if roles:
        named = [r for r in roles if r.get("name") != "@everyone"]
        named.sort(key=lambda r: r.get("position", 0), reverse=True)
        role_names = ", ".join(f"**{r.get('name', '?')}**" for r in named[:5])
        lines.append(f"\U0001f3ad Top roles ({len(named)} total): {role_names}")

    ctx.interaction.respond(content="\n".join(lines))


@plugin.on_slash_command("demo-help")
def slash_help(ctx: Context, event: dict):
    """/demo-help — Show all available commands."""
    ctx.interaction.respond(
        embeds=[{
            "title": "\U0001f4d6 Demo Counter \u2014 Commands",
            "color": _theme_color(ctx),
            "fields": [
                {"name": "Slash Commands", "value": "\n".join([
                    "`/demo` \u2014 Increment counter",
                    "`/demo-board` \u2014 Post the interactive board",
                    "`/demo-stats` \u2014 Show leaderboard",
                    "`/demo-goal` \u2014 Set a custom goal (modal)",
                    "`/demo-info` \u2014 Server info",
                    "`/demo-help` \u2014 This message",
                ]), "inline": False},
                {"name": "Board Buttons", "value": "\n".join([
                    "**+1 / +5** \u2014 Increment counter",
                    "**Stats** \u2014 View leaderboard (ephemeral)",
                    "**Set Goal** \u2014 Change the goal target (modal)",
                    "**Reset** \u2014 Reset counter to zero",
                    "**Theme** \u2014 Change board color scheme",
                ]), "inline": False},
                {"name": "Text Commands", "value": "\n".join([
                    "`!demo` \u2014 Increment counter",
                    "`!demo board` \u2014 Post the board",
                    "`!demo help` \u2014 Show this message",
                ]), "inline": False},
            ],
            "footer": {"text": "MMO Maid SDK v0.2.0 \u2022 Full feature showcase"},
        }],
        ephemeral=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Component handlers — Buttons
# ═══════════════════════════════════════════════════════════════════════════════

@plugin.on_component("demo_increment")
def on_increment(ctx: Context, event: dict):
    """Handle +1 button click."""
    user_id = str(event.get("user_id") or event.get("author_id") or "")
    data = _increment(ctx, user_id, 1)
    ctx.interaction.respond(
        content=f"**+1!** Counter is now at **{data['total']}**",
        ephemeral=True,
    )
    _update_board(ctx)


@plugin.on_component("demo_increment_5")
def on_increment_5(ctx: Context, event: dict):
    """Handle +5 button click."""
    user_id = str(event.get("user_id") or event.get("author_id") or "")
    data = _increment(ctx, user_id, 5)
    ctx.interaction.respond(
        content=f"**+5!** Counter is now at **{data['total']}**",
        ephemeral=True,
    )
    _update_board(ctx)


@plugin.on_component("demo_show_stats")
def on_show_stats(ctx: Context, event: dict):
    """Handle Stats button — show stats as ephemeral embed."""
    data = _get_counter(ctx)
    total = data.get("total", 0)
    users = data.get("users", {})

    sorted_users = sorted(users.items(), key=lambda x: x[1], reverse=True)
    medals = ["\U0001f947", "\U0001f948", "\U0001f949"]
    lines = []
    for i, (uid, count) in enumerate(sorted_users[:10]):
        medal = medals[i] if i < 3 else f"`{i+1}.`"
        lines.append(f"{medal} <@{uid}> \u2014 {count} click(s)")
    if not lines:
        lines.append("No clicks yet!")

    ctx.interaction.respond(
        embeds=[{
            "title": "\U0001f4ca Counter Stats",
            "description": "\n".join(lines),
            "color": _theme_color(ctx),
            "footer": {"text": f"Total: {total} \u2022 Participants: {len(users)}"},
        }],
        ephemeral=True,
    )


@plugin.on_component("demo_set_goal")
def on_set_goal_button(ctx: Context, event: dict):
    """Handle Set Goal button — open the goal modal."""
    data = _get_counter(ctx)
    current_goal = str(data.get("goal", DEFAULT_GOAL))

    ctx.interaction.send_modal(
        title="Set Counter Goal",
        custom_id="demo_goal_form",
        fields=[
            TextInput("Goal Number", "goal_value", placeholder="e.g. 100", value=current_goal),
            TextInput("Announcement (optional)", "goal_message",
                      style="paragraph", required=False,
                      placeholder="Message to post when goal is reached"),
        ],
    )


@plugin.on_component("demo_board_reset")
def on_board_reset(ctx: Context, event: dict):
    """Handle Reset button click."""
    settings = _get_settings(ctx)
    data = {"total": 0, "users": {}, "goal": settings.get("goal", DEFAULT_GOAL)}
    ctx.kv.set("counter", data)
    ctx.interaction.respond(content="\U0001f504 Counter has been reset to zero!", ephemeral=True)
    _update_board(ctx)


# ═══════════════════════════════════════════════════════════════════════════════
#  Component handlers — Select menu
# ═══════════════════════════════════════════════════════════════════════════════

@plugin.on_component("demo_theme_select")
def on_theme_select(ctx: Context, event: dict):
    """Handle theme select menu — change board color."""
    values = event.get("values") or []
    theme = values[0] if values else "blue"
    if theme not in THEMES:
        theme = "blue"

    settings = _get_settings(ctx)
    settings["theme"] = theme
    ctx.kv.set("settings", settings)

    ctx.interaction.respond(
        content=f"\U0001f3a8 Board theme changed to **{theme}**!",
        ephemeral=True,
    )
    _update_board(ctx)


# ═══════════════════════════════════════════════════════════════════════════════
#  Modal submit handler
# ═══════════════════════════════════════════════════════════════════════════════

@plugin.on_modal_submit("demo_goal_form")
def on_goal_submit(ctx: Context, event: dict):
    """Handle goal modal submission."""
    modal_values = event.get("modal_values") or {}
    raw_goal = modal_values.get("goal_value", "")
    announcement = modal_values.get("goal_message", "").strip()

    try:
        goal = max(1, min(1_000_000, int(raw_goal)))
    except (ValueError, TypeError):
        ctx.interaction.respond(content="Invalid goal number. Please enter a whole number.", ephemeral=True)
        return

    # Update counter data with new goal
    data = _get_counter(ctx)
    data["goal"] = goal
    ctx.kv.set("counter", data)

    # Also persist in settings
    settings = _get_settings(ctx)
    settings["goal"] = goal
    if announcement:
        settings["goal_message"] = announcement
    ctx.kv.set("settings", settings)

    ctx.interaction.respond(
        content=f"\U0001f3af Goal updated to **{goal}**!"
                + (f"\nAnnouncement: {announcement}" if announcement else ""),
        ephemeral=True,
    )
    _update_board(ctx)


# ═══════════════════════════════════════════════════════════════════════════════
#  Legacy text commands (backward compatibility)
# ═══════════════════════════════════════════════════════════════════════════════

@plugin.on_event("message_create")
def on_message(ctx: Context, event: dict):
    """Handle legacy !demo text commands."""
    author = event.get("author") if isinstance(event.get("author"), dict) else {}
    if author.get("bot"):
        return

    content = str(event.get("content") or "").strip().lower()
    if not content.startswith("!demo"):
        return

    channel_id = str(event.get("channel_id") or "")
    user_id = str(event.get("author_id") or "") or str(author.get("id") or "")
    username = str(event.get("author_username") or "") or author.get("username") or "someone"

    if content in ("!demo", "!demo count"):
        data = _increment(ctx, user_id)
        user_count = data["users"].get(user_id, 0)
        result = ctx.discord.send_message(
            channel_id=channel_id,
            content=f"Hey **{username}**! Counter is now at **{data['total']}** (you: **{user_count}** times).",
        )
        msg_id = result.get("message_id")
        if msg_id:
            try:
                ctx.discord.add_reaction(channel_id=channel_id, message_id=str(msg_id), emoji="\U0001f44b")
            except Exception:
                pass
        _update_board(ctx)

    elif content == "!demo board":
        data = _get_counter(ctx)
        embed = _build_board_embed(data, _theme_color(ctx))
        result = ctx.discord.send_message(
            channel_id=channel_id, embeds=[embed], components=_board_components(),
        )
        msg_id = result.get("message_id")
        if msg_id:
            ctx.kv.set("board", {"channel_id": channel_id, "message_id": str(msg_id)})

    elif content == "!demo help":
        ctx.discord.send_message(channel_id=channel_id, embeds=[{
            "title": "\U0001f4d6 Demo Counter \u2014 Commands",
            "color": _theme_color(ctx),
            "description": "\n".join([
                "`/demo` \u2014 Increment counter",
                "`/demo-board` \u2014 Post the interactive board",
                "`/demo-stats` \u2014 Show leaderboard",
                "`/demo-goal` \u2014 Set a custom goal (modal)",
                "`/demo-info` \u2014 Server info",
                "`/demo-help` \u2014 This message",
                "",
                "**Text commands:** `!demo`, `!demo board`, `!demo help`",
            ]),
            "footer": {"text": "MMO Maid SDK v0.2.0"},
        }])


# ═══════════════════════════════════════════════════════════════════════════════
#  Dashboard data handlers
# ═══════════════════════════════════════════════════════════════════════════════

@plugin.on_dashboard("get_total_stat")
def dash_total_stat(ctx: Context, params: dict):
    """Return total clicks as a stat card."""
    data = _get_counter(ctx)
    total = data.get("total", 0)
    goal = data.get("goal", DEFAULT_GOAL)
    pct = round((total / max(goal, 1)) * 100, 1)
    return {"value": total, "change": f"{pct}% of goal"}


@plugin.on_dashboard("get_users_stat")
def dash_users_stat(ctx: Context, params: dict):
    """Return unique user count as a stat card."""
    data = _get_counter(ctx)
    users = data.get("users", {})
    return {"value": len(users)}


@plugin.on_dashboard("get_goal_stat")
def dash_goal_stat(ctx: Context, params: dict):
    """Return current goal as a stat card."""
    data = _get_counter(ctx)
    goal = data.get("goal", DEFAULT_GOAL)
    total = data.get("total", 0)
    remaining = max(0, goal - total)
    return {"value": goal, "change": f"{remaining} remaining"}


@plugin.on_dashboard("get_leaderboard")
def dash_leaderboard(ctx: Context, params: dict):
    """Return top users as a table."""
    data = _get_counter(ctx)
    users = data.get("users", {})
    total = data.get("total", 0)
    sorted_users = sorted(users.items(), key=lambda x: x[1], reverse=True)

    rows = []
    for i, (uid, count) in enumerate(sorted_users[:25], 1):
        pct = round((count / max(total, 1)) * 100, 1)
        rows.append({
            "rank": i,
            "user_id": uid,
            "clicks": count,
            "share": f"{pct}%",
        })

    return {"rows": rows, "total": len(users)}


@plugin.on_dashboard("get_activity_chart")
def dash_activity_chart(ctx: Context, params: dict):
    """Return click activity over time as a chart."""
    activity = ctx.kv.get("activity") or []
    if not isinstance(activity, list):
        activity = []

    # Bucket activity into hourly bins
    buckets: dict = {}
    for entry in activity:
        if not isinstance(entry, dict):
            continue
        ts = entry.get("ts", 0)
        hour = (ts // 3600) * 3600
        buckets[hour] = buckets.get(hour, 0) + entry.get("amount", 1)

    sorted_hours = sorted(buckets.keys())[-24:]  # Last 24 buckets
    labels = []
    values = []
    for h in sorted_hours:
        t = time.gmtime(h)
        labels.append(f"{t.tm_mon}/{t.tm_mday} {t.tm_hour:02d}:00")
        values.append(buckets[h])

    return {
        "labels": labels,
        "series": [{"name": "Clicks", "data": values}],
    }


@plugin.on_dashboard("get_settings")
def dash_get_settings(ctx: Context, params: dict):
    """Return current plugin settings for the settings form."""
    settings = _get_settings(ctx)
    return {
        "values": {
            "goal": str(settings.get("goal", DEFAULT_GOAL)),
            "theme": settings.get("theme", "blue"),
            "log_channel_id": settings.get("log_channel_id", ""),
        },
    }


@plugin.on_dashboard("save_settings")
def dash_save_settings(ctx: Context, params: dict):
    """Save plugin settings from the settings form."""
    values = params.get("values") or {}
    settings = _get_settings(ctx)

    raw_goal = values.get("goal", "")
    try:
        settings["goal"] = max(1, min(1_000_000, int(raw_goal)))
    except (ValueError, TypeError):
        return {"ok": False, "error": "Invalid goal number"}

    theme = values.get("theme", "blue")
    if theme in THEMES:
        settings["theme"] = theme

    settings["log_channel_id"] = str(values.get("log_channel_id", "")).strip()

    ctx.kv.set("settings", settings)

    # Also update the counter goal to match
    data = _get_counter(ctx)
    data["goal"] = settings["goal"]
    ctx.kv.set("counter", data)

    ctx.log(f"Settings updated: goal={settings['goal']}, theme={settings['theme']}")
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
#  Run
# ═══════════════════════════════════════════════════════════════════════════════

plugin.run()
