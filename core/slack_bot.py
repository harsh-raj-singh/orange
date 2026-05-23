"""
Slack recorder for Orange memory.

Flow:
  1. /orange starts recording messages in the current Slack channel.
  2. /orange-stop stops recording and writes the session through the same
     StoreSessionRequest path used by the Vercel demo graph.
  3. /orange-status reports the current recording state.

Run with Socket Mode:
  python -m core.slack_bot
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk import WebClient

from core.mcp_server.handlers import handle_store_session
from core.mcp_server.models import StoreSessionRequest
from core.viz_api.dependencies import get_chroma, get_neo4j, get_postgres_store

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("orange.slack")

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")

DEFAULT_USER_EMAIL = (
    os.getenv("ORANGE_SLACK_DEFAULT_USER_EMAIL")
    or os.getenv("ORANGE_USER_EMAIL")
    or ""
).strip().lower()
DEFAULT_COMPANY = (
    os.getenv("ORANGE_SLACK_COMPANY")
    or os.getenv("ORANGE_COMPANY")
    or ""
).strip()


@dataclass
class RecordedMessage:
    user_id: str
    name: str
    email: str | None
    text: str
    ts: str | None = None
    recorded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class RecordingSession:
    session_id: str
    channel_id: str
    channel_name: str
    team_id: str
    team_domain: str
    started_by: str
    started_by_name: str
    started_by_email: str | None
    started_at: str
    company: str
    messages: list[RecordedMessage] = field(default_factory=list)
    participants: dict[str, dict[str, str | None]] = field(default_factory=dict)

    @property
    def message_count(self) -> int:
        return len(self.messages)


active_sessions: dict[str, RecordingSession] = {}
session_lock = threading.Lock()
slack_client: WebClient | None = None
_user_cache: dict[str, dict[str, str | None]] = {}


def _require_env() -> None:
    missing = [
        name
        for name, value in {
            "SLACK_BOT_TOKEN": SLACK_BOT_TOKEN,
            "SLACK_SIGNING_SECRET": SLACK_SIGNING_SECRET,
            "SLACK_APP_TOKEN": SLACK_APP_TOKEN,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError(f"Missing required Slack environment variables: {', '.join(missing)}")


def _client() -> WebClient:
    global slack_client
    if slack_client is None:
        _require_env()
        slack_client = WebClient(token=SLACK_BOT_TOKEN)
    return slack_client


def _get_user_profile(user_id: str) -> dict[str, str | None]:
    if user_id in _user_cache:
        return _user_cache[user_id]

    profile = {"id": user_id, "name": user_id, "email": None}
    try:
        result = _client().users_info(user=user_id)
        user = result.get("user") or {}
        slack_profile = user.get("profile") or {}
        profile["name"] = (
            slack_profile.get("display_name")
            or slack_profile.get("real_name")
            or user.get("name")
            or user_id
        )
        profile["email"] = (slack_profile.get("email") or "").strip().lower() or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("slack_user_lookup_failed", extra={"user_id": user_id, "error": str(exc)})

    _user_cache[user_id] = profile
    return profile


def _session_id(team_id: str, channel_id: str) -> str:
    now = datetime.now(timezone.utc)
    compact = now.strftime("%Y%m%d%H%M%S")
    team = team_id or "workspace"
    return f"slack_{team}_{channel_id}_{compact}"


def _session_source_url(session: RecordingSession) -> str | None:
    if not session.team_domain:
        return None
    return f"https://{session.team_domain}.slack.com/archives/{session.channel_id}"


def _company_from_command(command: dict[str, Any]) -> str:
    return DEFAULT_COMPANY or (command.get("team_domain") or command.get("team_id") or "Slack workspace")


def _message_content(message: RecordedMessage) -> str:
    return f"[{message.name}]: {' '.join(message.text.split())}"


def build_store_request_from_session(
    session: RecordingSession,
    *,
    ended_at: datetime | None = None,
) -> StoreSessionRequest:
    ended_at = ended_at or datetime.now(timezone.utc)
    user_email = session.started_by_email or DEFAULT_USER_EMAIL or None
    user_id = user_email or f"slack:{session.team_id or 'workspace'}:{session.started_by}"
    participants = [
        {
            "id": participant["id"],
            "name": participant.get("name"),
            "metadata": {"email": participant.get("email")},
        }
        for participant in session.participants.values()
    ]
    messages = [{"role": "user", "content": _message_content(message)} for message in session.messages]
    transcript = "\n".join(
        f"Turn {index} [user]: {message['content']}"
        for index, message in enumerate(messages, start=1)
    )

    return StoreSessionRequest(
        transcript=transcript,
        source="slack",
        user_id=user_id,
        user_email=user_email,
        session_id=session.session_id,
        external_session_id=f"{session.team_id}:{session.channel_id}:{session.started_at}",
        org_id=session.company,
        company=session.company,
        started_at=session.started_at,
        ended_at=ended_at,
        participants=participants,
        source_url=_session_source_url(session),
        client_metadata={
            "name": "orange-slack-bot",
            "trigger": "/orange-stop",
            "channel_id": session.channel_id,
            "channel_name": session.channel_name,
            "team_id": session.team_id,
            "team_domain": session.team_domain,
        },
        messages=messages,
        metadata={
            "title": f"Slack recording in #{session.channel_name or session.channel_id}",
            "company": session.company,
            "slack": {
                "channel_id": session.channel_id,
                "channel_name": session.channel_name,
                "team_id": session.team_id,
                "team_domain": session.team_domain,
                "started_by": session.started_by,
            },
        },
        contribute_to_global=True,
        worth_storing=True,
        session_duration_turns=len(messages),
    )


def _store_session(session: RecordingSession):
    request = build_store_request_from_session(session)
    return asyncio.run(
        handle_store_session(
            request,
            neo4j=get_neo4j(),
            chroma=get_chroma(),
            llm=None,
            postgres_store=get_postgres_store(),
        )
    )


def create_app() -> App:
    _require_env()
    app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)

    @app.command("/orange")
    def handle_orange_start(ack, say, command):
        ack()

        channel_id = command["channel_id"]
        starter = _get_user_profile(command["user_id"])

        with session_lock:
            if channel_id in active_sessions:
                session = active_sessions[channel_id]
                say(
                    "Orange is already recording in this channel.\n"
                    f"Started by <@{session.started_by}>. "
                    f"`{session.message_count}` messages captured so far.\n"
                    "Type `/orange-stop` to stop recording."
                )
                return

            session = RecordingSession(
                session_id=_session_id(command.get("team_id", ""), channel_id),
                channel_id=channel_id,
                channel_name=command.get("channel_name", ""),
                team_id=command.get("team_id", ""),
                team_domain=command.get("team_domain", ""),
                started_by=command["user_id"],
                started_by_name=starter["name"] or command["user_id"],
                started_by_email=starter.get("email") or DEFAULT_USER_EMAIL or None,
                started_at=datetime.now(timezone.utc).isoformat(),
                company=_company_from_command(command),
            )
            session.participants[command["user_id"]] = {
                "id": command["user_id"],
                "name": starter["name"],
                "email": starter.get("email") or DEFAULT_USER_EMAIL or None,
            }
            active_sessions[channel_id] = session

        logger.info(
            "slack_recording_started",
            extra={"channel_id": channel_id, "session_id": session.session_id},
        )
        say(
            "Orange is now recording this conversation.\n\n"
            f"Started by <@{command['user_id']}>.\n"
            f"Company scope: `{session.company}`.\n"
            "Type `/orange-stop` when the useful part is done."
        )

    @app.command("/orange-stop")
    def handle_orange_stop(ack, say, command):
        ack()

        channel_id = command["channel_id"]
        with session_lock:
            session = active_sessions.pop(channel_id, None)

        if session is None:
            say("Orange is not recording in this channel. Type `/orange` to start.")
            return

        if session.message_count == 0:
            say("Recording stopped, but no messages were captured. Nothing was stored.")
            return

        say(
            f"Recording stopped. `{session.message_count}` messages captured.\n"
            "Writing the session into Orange memory now."
        )

        def _run_pipeline() -> None:
            try:
                result = _store_session(session)
                created = result.insights_stored + result.problems_created + result.solutions_written
                status_line = (
                    f"Created `{created}` graph items "
                    f"(`{result.insights_stored}` insights, `{result.problems_created}` problems, "
                    f"`{result.solutions_written}` solutions)."
                )
                if result.skipped_reason:
                    status_line = f"Skipped: `{result.skipped_reason}`."
                if result.errors:
                    status_line += f"\nWarnings: `{'; '.join(result.errors)[:240]}`"

                say(
                    "Orange memory write complete.\n\n"
                    f"{status_line}\n"
                    f"Session: `{result.session_id}`\n"
                    f"Company scope: `{session.company}`\n"
                    f"User email: `{session.started_by_email or DEFAULT_USER_EMAIL or 'not available'}`"
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "slack_memory_write_failed",
                    extra={"session_id": session.session_id, "error": str(exc)},
                    exc_info=True,
                )
                say(
                    "Orange memory write failed.\n"
                    f"Error: `{str(exc)[:220]}`\n"
                    "The recording was not committed to the graph."
                )

        threading.Thread(target=_run_pipeline, daemon=True).start()

    @app.event("message")
    def handle_message(event, say):  # noqa: ARG001
        channel_id = event.get("channel")
        user_id = event.get("user")
        text = (event.get("text") or "").strip()

        if event.get("subtype") is not None or not channel_id or not user_id or not text:
            return

        with session_lock:
            session = active_sessions.get(channel_id)
            if session is None:
                return

        profile = _get_user_profile(user_id)
        recorded = RecordedMessage(
            user_id=user_id,
            name=profile["name"] or user_id,
            email=profile.get("email"),
            text=text,
            ts=event.get("ts"),
        )

        with session_lock:
            session = active_sessions.get(channel_id)
            if session is None:
                return
            session.messages.append(recorded)
            session.participants[user_id] = {
                "id": user_id,
                "name": recorded.name,
                "email": recorded.email,
            }
            count = session.message_count

        logger.info(
            "slack_message_captured",
            extra={"channel_id": channel_id, "session_id": session.session_id, "count": count},
        )

    @app.command("/orange-status")
    def handle_orange_status(ack, say, command):
        ack()

        with session_lock:
            session = active_sessions.get(command["channel_id"])

        if session is None:
            say("Orange is not recording in this channel.")
            return

        say(
            "Orange is recording.\n\n"
            f"Started by: <@{session.started_by}>\n"
            f"Messages captured: `{session.message_count}`\n"
            f"Company scope: `{session.company}`\n"
            f"Session: `{session.session_id}`\n\n"
            "Type `/orange-stop` to stop and store the memory."
        )

    return app


def main() -> None:
    _require_env()
    logger.info("Starting Orange Slack bot in Socket Mode")
    handler = SocketModeHandler(create_app(), SLACK_APP_TOKEN)
    handler.start()


if __name__ == "__main__":
    main()
