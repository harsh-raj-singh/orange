"""
ORANGE SLACK BOT
================
Connects Slack conversations to the Orange memory backend.

Flow:
  1. User types /orange in a Slack channel  →  bot starts recording
  2. All messages in that channel are captured and stored
  3. User types /orange-stop                →  bot stops recording
  4. The FULL pipeline runs:
     • PostgreSQL  – raw conversation stored
     • ChromaDB   – vector embeddings for similarity search
     • Neo4j      – knowledge graph nodes and relationships

Requirements:
  - SLACK_BOT_TOKEN   (xoxb-...)
  - SLACK_SIGNING_SECRET
  - SLACK_APP_TOKEN   (xapp-... for Socket Mode)
  - POSTGRES_DSN, NVIDIA_API_KEY, CHROMA_PATH, etc. (already in your .env)

Usage (Socket Mode — no public URL needed):
  $ python -m core.slack_bot
"""

import os
import sys
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, Optional

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk import WebClient

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.complete_chat_system import ChatCentricMemorySystem

load_dotenv()

# ──────────────────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("orange.slack")

# ──────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")  # Required for Socket Mode

# Orange backend config
LLM_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("NVIDIA_API_KEY")
LLM_MODEL = os.getenv("OPENAI_MODEL") or os.getenv("NVIDIA_MODEL") or "gpt-5.4-nano"
CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")
VECTOR_COLLECTION = os.getenv("VECTOR_COLLECTION", "chat_memories")
POSTGRES_DSN = os.getenv("POSTGRES_DSN")

# Graph DB config
MEMGRAPH_HOST = os.getenv("MEMGRAPH_HOST")
MEMGRAPH_PORT = os.getenv("MEMGRAPH_PORT", "7687")
MEMGRAPH_USERNAME = os.getenv("MEMGRAPH_USERNAME")
MEMGRAPH_PASSWORD = os.getenv("MEMGRAPH_PASSWORD")
MEMGRAPH_SSL = os.getenv("MEMGRAPH_SSL", "false").lower() in ("1", "true", "yes")
MEMGRAPH_SCHEME = os.getenv("MEMGRAPH_SCHEME")

if not SLACK_BOT_TOKEN:
    raise ValueError("SLACK_BOT_TOKEN is required. Set it in .env")
if not SLACK_APP_TOKEN:
    raise ValueError("SLACK_APP_TOKEN is required for Socket Mode. Set it in .env")
if not POSTGRES_DSN:
    raise ValueError("POSTGRES_DSN is required. Set it in .env")
if not LLM_API_KEY:
    raise ValueError("OPENAI_API_KEY or NVIDIA_API_KEY is required. Set it in .env")


def _build_memgraph_url() -> Optional[str]:
    """Build Memgraph/Neo4j connection URL from env vars."""
    if not MEMGRAPH_HOST or not MEMGRAPH_USERNAME or not MEMGRAPH_PASSWORD:
        return None
    scheme = MEMGRAPH_SCHEME or ("bolt+ssc" if MEMGRAPH_SSL else "bolt")
    return f"{scheme}://{MEMGRAPH_HOST}:{MEMGRAPH_PORT}"


# ──────────────────────────────────────────────────────────
# ACTIVE RECORDING SESSIONS
# ──────────────────────────────────────────────────────────
# Key: channel_id → { chat_id, user_id, started_at, started_by, message_count }
active_sessions: Dict[str, Dict] = {}
session_lock = threading.Lock()
DEFAULT_STREAMLIT_USER_ID = "test_user"


# ──────────────────────────────────────────────────────────
# INITIALIZE THE FULL ORANGE SYSTEM
# ──────────────────────────────────────────────────────────
logger.info("🍊 Initializing Orange Memory System (all 3 stores)...")

memgraph_url = _build_memgraph_url()
if memgraph_url:
    logger.info(f"   Graph DB: {memgraph_url}")
else:
    logger.warning("   Graph DB: NOT CONFIGURED (skipping graph storage)")

orange_system = ChatCentricMemorySystem(
    nvidia_api_key=LLM_API_KEY,
    nvidia_model=LLM_MODEL,
    chroma_path=CHROMA_PATH,
    vector_collection=VECTOR_COLLECTION,
    memgraph_url=memgraph_url,
    memgraph_username=MEMGRAPH_USERNAME or None,
    memgraph_password=MEMGRAPH_PASSWORD or None,
    postgres_dsn=POSTGRES_DSN,
)

logger.info("   ✅ PostgreSQL: connected")
logger.info(f"   ✅ ChromaDB: {CHROMA_PATH}")
if memgraph_url:
    logger.info("   ✅ Graph DB: connected")
logger.info("🍊 System initialized!")

# Slack app
app = App(
    token=SLACK_BOT_TOKEN,
    signing_secret=SLACK_SIGNING_SECRET,
)

# Slack client for user info lookups
slack_client = WebClient(token=SLACK_BOT_TOKEN)

# Cache for user display names
_user_cache: Dict[str, str] = {}


def _get_user_name(user_id: str) -> str:
    """Resolve Slack user_id to display name (cached)."""
    if user_id in _user_cache:
        return _user_cache[user_id]
    try:
        result = slack_client.users_info(user=user_id)
        name = (
            result["user"]["profile"].get("display_name")
            or result["user"]["profile"].get("real_name")
            or result["user"]["name"]
        )
        _user_cache[user_id] = name
        return name
    except Exception as e:
        logger.warning(f"Could not resolve user {user_id}: {e}")
        _user_cache[user_id] = user_id
        return user_id


# ──────────────────────────────────────────────────────────
# /orange — START RECORDING
# ──────────────────────────────────────────────────────────
@app.command("/orange")
def handle_orange_start(ack, say, command):
    """Start recording messages in this channel."""
    ack()

    channel_id = command["channel_id"]
    user_id = command["user_id"]
    user_name = _get_user_name(user_id)

    with session_lock:
        if channel_id in active_sessions:
            session = active_sessions[channel_id]
            say(
                f"🍊 Orange is already recording in this channel!\n"
                f"Started by <@{session['started_by']}> • "
                f"`{session['message_count']}` messages captured so far.\n"
                f"Type `/orange-stop` to stop recording."
            )
            return

        # Create a new chat session via the FULL system
        chat_id = orange_system.create_chat(
            user_id=DEFAULT_STREAMLIT_USER_ID
        )

        # Mark this chat as explicitly requested for memory storage
        # This bypasses the importance filter in the extraction pipeline
        orange_system.episodic.request_memory_extraction(
            chat_id=chat_id,
            reason="slack_orange_command",
            specific_aspects=["conversation_context", "decisions", "action_items"],
        )

        active_sessions[channel_id] = {
            "chat_id": chat_id,
            "user_id": DEFAULT_STREAMLIT_USER_ID,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "started_by": user_id,
            "message_count": 0,
        }

    logger.info(
        f"🍊 Recording started in channel {channel_id} by {user_name} "
        f"(chat_id={chat_id})"
    )

    say(
        f"🍊 *Orange is now recording this conversation!*\n\n"
        f"Started by <@{user_id}>\n"
        f"All messages in this channel will be captured.\n\n"
        f"When done, type `/orange-stop` to:\n"
        f"  • Save to PostgreSQL\n"
        f"  • Generate vector embeddings (ChromaDB)\n"
        f"  • Extract knowledge graph (Neo4j)\n"
        f"  • Run full memory extraction pipeline 🧠"
    )


# ──────────────────────────────────────────────────────────
# /orange-stop — STOP RECORDING & RUN FULL PIPELINE
# ──────────────────────────────────────────────────────────
@app.command("/orange-stop")
def handle_orange_stop(ack, say, command):
    """Stop recording and trigger the FULL memory extraction pipeline."""
    ack()

    channel_id = command["channel_id"]
    user_id = command["user_id"]

    with session_lock:
        if channel_id not in active_sessions:
            say(
                "🍊 Orange is not recording in this channel.\n"
                "Type `/orange` to start recording."
            )
            return

        session = active_sessions.pop(channel_id)

    chat_id = session["chat_id"]
    msg_count = session["message_count"]
    started_by = session["started_by"]

    if msg_count == 0:
        say(
            f"🍊 Recording stopped, but no messages were captured.\n"
            f"Nothing to process. Type `/orange` to start a new recording."
        )
        return

    logger.info(
        f"🍊 Recording stopped in channel {channel_id}. "
        f"{msg_count} messages captured (chat_id={chat_id})"
    )

    # Mark the chat as complete
    orange_system.mark_complete(chat_id)

    say(
        f"🍊 *Recording stopped!* `{msg_count}` messages captured.\n\n"
        f"🔄 *Running full memory extraction pipeline...*\n"
        f"  • PostgreSQL ✅ (already stored)\n"
        f"  • ChromaDB → generating embeddings...\n"
        f"  • Neo4j → extracting knowledge graph...\n\n"
        f"This may take a moment. I'll post the results here."
    )

    # Run the full pipeline in a background thread so we don't block Slack
    def _run_pipeline():
        try:
            result = orange_system.process_chat(chat_id)
            status = result.get("status", "unknown")

            if status == "processed":
                graph_nodes = result.get("graph_nodes", 0)
                importance = result.get("importance_score", 0)
                conv_type = result.get("conversation_type", "unknown")
                confidence = result.get("extraction_confidence", 0)

                say(
                    f"🍊 *Memory extraction complete!* ✅\n\n"
                    f"📊 *Results:*\n"
                    f"  • Status: `processed`\n"
                    f"  • Conversation type: `{conv_type}`\n"
                    f"  • Importance score: `{importance:.2f}`\n"
                    f"  • Extraction confidence: `{confidence:.2f}`\n"
                    f"  • Graph nodes created: `{graph_nodes}`\n"
                    f"  • Vector ID: `vec_{chat_id}`\n\n"
                    f"💾 *Stored in:*\n"
                    f"  ✅ PostgreSQL (raw conversation + extracted memory)\n"
                    f"  ✅ ChromaDB (vector embeddings for search)\n"
                    f"  {'✅' if graph_nodes > 0 else '⚪'} Neo4j ({graph_nodes} knowledge graph nodes)\n\n"
                    f"Chat ID: `{chat_id}` • Started by <@{started_by}>"
                )
            elif status == "skipped":
                reason = result.get("reason", "unknown")
                say(
                    f"🍊 *Memory extraction skipped.*\n"
                    f"Reason: `{reason}`\n"
                    f"The conversation wasn't deemed important enough to store as a memory.\n"
                    f"Chat ID: `{chat_id}`"
                )
            else:
                say(
                    f"🍊 Processing returned status: `{status}`\n"
                    f"Chat ID: `{chat_id}`"
                )

        except Exception as e:
            logger.error(f"Pipeline failed for chat {chat_id}: {e}", exc_info=True)
            say(
                f"🍊 *Memory extraction failed* ❌\n"
                f"Error: `{str(e)[:200]}`\n\n"
                f"The raw conversation is still saved in PostgreSQL.\n"
                f"You can retry from the Streamlit debug console.\n"
                f"Chat ID: `{chat_id}`"
            )

    thread = threading.Thread(target=_run_pipeline, daemon=True)
    thread.start()


# ──────────────────────────────────────────────────────────
# MESSAGE LISTENER — capture messages during recording
# ──────────────────────────────────────────────────────────
@app.event("message")
def handle_message(event, say):
    """Capture messages from channels where Orange is recording."""

    channel_id = event.get("channel")
    user_id = event.get("user")
    text = event.get("text", "")
    subtype = event.get("subtype")

    # Debug: log ALL message events so we can confirm they arrive
    logger.info(
        f"📨 Message event received: channel={channel_id} user={user_id} "
        f"subtype={subtype} text={text[:50] if text else '(empty)'}..."
    )

    # Skip bot messages, edits, deletes, etc.
    if subtype is not None or not user_id or not text:
        logger.info(f"   ↳ Skipped (subtype={subtype}, user={user_id}, text_empty={not text})")
        return

    with session_lock:
        if channel_id not in active_sessions:
            logger.info(f"   ↳ Channel {channel_id} is not being recorded, ignoring.")
            return
        session = active_sessions[channel_id]

    # Store the message via the full system
    chat_id = session["chat_id"]
    user_name = _get_user_name(user_id)

    try:
        # Store as "user" role with the sender's name prefixed
        orange_system.add_message(
            chat_id=chat_id,
            role="user",
            content=f"[{user_name}]: {text}",
        )

        with session_lock:
            if channel_id in active_sessions:
                active_sessions[channel_id]["message_count"] += 1

        logger.info(
            f"   ✅ Captured message #{active_sessions.get(channel_id, {}).get('message_count', '?')} "
            f"from {user_name}: {text[:80]}"
        )
    except Exception as e:
        logger.error(f"Failed to store message: {e}", exc_info=True)


# ──────────────────────────────────────────────────────────
# /orange-status — CHECK RECORDING STATUS
# ──────────────────────────────────────────────────────────
@app.command("/orange-status")
def handle_orange_status(ack, say, command):
    """Check if Orange is recording in this channel."""
    ack()

    channel_id = command["channel_id"]

    with session_lock:
        if channel_id not in active_sessions:
            say("🍊 Orange is not recording in this channel.")
            return
        session = active_sessions[channel_id]

    stores = []
    stores.append("✅ PostgreSQL")
    stores.append("✅ ChromaDB")
    stores.append("✅ Neo4j" if orange_system.graph_driver else "⚪ Neo4j (not configured)")

    say(
        f"🍊 *Orange is recording!*\n\n"
        f"• Started by: <@{session['started_by']}>\n"
        f"• Started at: `{session['started_at']}`\n"
        f"• Messages captured: `{session['message_count']}`\n"
        f"• Chat ID: `{session['chat_id']}`\n\n"
        f"*Target stores:*\n" + "\n".join(f"  {s}" for s in stores) + "\n\n"
        f"Type `/orange-stop` to stop recording and run extraction."
    )


# ──────────────────────────────────────────────────────────
# ENTRYPOINT
# ──────────────────────────────────────────────────────────
def main():
    """Run Orange Slack bot in Socket Mode (local dev, no public URL needed)."""
    logger.info("🍊 Starting Orange Slack Bot (Socket Mode)...")
    logger.info(f"   PostgreSQL: {POSTGRES_DSN.split('@')[-1] if POSTGRES_DSN else 'NOT SET'}")
    logger.info(f"   ChromaDB:   {CHROMA_PATH}")
    logger.info(f"   Graph DB:   {_build_memgraph_url() or 'NOT CONFIGURED'}")

    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()


if __name__ == "__main__":
    main()
