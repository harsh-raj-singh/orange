"""
Chat-Centric Memory Debug Console
Streamlit app for the post-conversation memory pipeline
"""

import os
import sys
import json
from datetime import datetime
from datetime import timezone
from typing import Any, Dict, List

import streamlit as st
import pandas as pd
from dotenv import load_dotenv
import streamlit.components.v1 as components
from openai import OpenAI

from core.complete_chat_system import ChatCentricMemorySystem
from core.graph_schema import NODE_TYPES, SESSION_INTENTS
from core.graph_tools import SEARCH_AND_FETCH_TOOL
from core.memory_extraction.tools import REQUEST_MEMORY_EXTRACTION_TOOL

load_dotenv()

# ------------------------------------------------------------------
# Session state
# ------------------------------------------------------------------
if "system" not in st.session_state:
    st.session_state.system = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "active_chat_id" not in st.session_state:
    st.session_state.active_chat_id = None
if "last_processing_result" not in st.session_state:
    st.session_state.last_processing_result = None
if "last_retrieval" not in st.session_state:
    st.session_state.last_retrieval = None
if "user_id" not in st.session_state:
    st.session_state.user_id = "test_user"
if "completion_notice" not in st.session_state:
    st.session_state.completion_notice = ""
if "queued_single_run_chat_id" not in st.session_state:
    st.session_state.queued_single_run_chat_id = ""
if "queued_batch_run" not in st.session_state:
    st.session_state.queued_batch_run = False
if "last_extraction_result" not in st.session_state:
    st.session_state.last_extraction_result = None

# ------------------------------------------------------------------
# Page config
# ------------------------------------------------------------------
st.set_page_config(
    page_title="orange1",
    layout="wide",
)

# ------------------------------------------------------------------
# Sidebar config
# ------------------------------------------------------------------
st.sidebar.title("Configuration")
st.sidebar.caption(f"Python: {sys.executable}")

nvidia_api_key = st.sidebar.text_input(
    "NVIDIA API Key",
    type="password",
    value=os.getenv("NVIDIA_API_KEY", ""),
)
nvidia_model = st.sidebar.text_input(
    "NVIDIA Model",
    value=os.getenv("NVIDIA_MODEL", "meta/llama-3.1-8b-instruct"),
)

chroma_path = st.sidebar.text_input(
    "Chroma Path",
    value=os.getenv("CHROMA_PATH", "./chroma_db"),
)
vector_collection = st.sidebar.text_input(
    "Vector Collection",
    value=os.getenv("VECTOR_COLLECTION", "chat_memories"),
)

st.sidebar.markdown("---")
st.sidebar.subheader("Memgraph / Neo4j")
memgraph_host = st.sidebar.text_input(
    "Host",
    value=os.getenv("MEMGRAPH_HOST", "localhost"),
)
memgraph_port = st.sidebar.text_input(
    "Port",
    value=os.getenv("MEMGRAPH_PORT", "7687"),
)
memgraph_username = st.sidebar.text_input(
    "Username",
    value=os.getenv("MEMGRAPH_USERNAME", ""),
)
memgraph_password = st.sidebar.text_input(
    "Password",
    type="password",
    value=os.getenv("MEMGRAPH_PASSWORD", ""),
)
memgraph_ssl = st.sidebar.checkbox(
    "Use SSL",
    value=os.getenv("MEMGRAPH_SSL", "false").lower() in ("1", "true", "yes"),
)

st.sidebar.markdown("---")
st.sidebar.subheader("Postgres (Episodic)")
postgres_dsn = st.sidebar.text_input(
    "Postgres DSN",
    value=os.getenv(
        "POSTGRES_DSN",
        "postgresql://neuralchat:neuralchat@127.0.0.1:5432/neuralchat",
    ),
)

st.sidebar.markdown("---")
user_id = st.sidebar.text_input("User ID", value=st.session_state.user_id)
st.session_state.user_id = user_id

use_llm_response = st.sidebar.checkbox("Generate assistant response", value=True)
stream_responses = st.sidebar.checkbox("Stream responses", value=True)


def build_memgraph_url(host: str, port: str, use_ssl: bool) -> str:
    scheme = os.getenv("MEMGRAPH_SCHEME")
    if not scheme:
        scheme = "bolt+ssc" if use_ssl else "bolt"
    return f"{scheme}://{host}:{port}"


if st.sidebar.button("Initialize System"):
    if not nvidia_api_key:
        st.sidebar.error("NVIDIA API key is required.")
    elif not postgres_dsn:
        st.sidebar.error("Postgres DSN is required for episodic storage.")
    else:
        with st.spinner("Initializing chat-centric system..."):
            memgraph_url = (
                build_memgraph_url(memgraph_host, memgraph_port, memgraph_ssl)
                if memgraph_username and memgraph_password
                else None
            )
            st.session_state.system = ChatCentricMemorySystem(
                nvidia_api_key=nvidia_api_key,
                nvidia_model=nvidia_model,
                chroma_path=chroma_path,
                vector_collection=vector_collection,
                memgraph_url=memgraph_url,
                memgraph_username=memgraph_username or None,
                memgraph_password=memgraph_password or None,
                postgres_dsn=postgres_dsn,
            )
        st.sidebar.success("System initialized")

# ------------------------------------------------------------------
# Main UI
# ------------------------------------------------------------------
st.title("orange1")
st.caption("Post-conversation memory processing with vector + graph retrieval")

if st.session_state.system is None:
    st.warning("Initialize the system from the sidebar to begin.")
    st.stop()

system = st.session_state.system

# Ensure an active chat exists
if st.session_state.active_chat_id is None:
    st.session_state.active_chat_id = system.create_chat(user_id=st.session_state.user_id)


def _render_chat_history():
    for msg in st.session_state.chat_history:
        role = msg.get("role")
        if role == "user":
            st.markdown(f"**You:** {msg['content']}")
        else:
            st.markdown(f"**Assistant:** {msg['content']}")
            if msg.get("context_used"):
                with st.expander("Context used"):
                    st.text(msg["context_used"])
        st.markdown("")


def _build_prompt(user_message: str, context_text: str) -> str:
    return f"""
You are a helpful assistant. Use the provided context when it is relevant.
Do NOT reveal your chain-of-thought or hidden reasoning. Provide the final answer only.

Context:
{context_text or "(no prior context)"}

User question:
{user_message}

Answer clearly and concisely. If the context is empty, answer from general knowledge.
"""


def _generate_response(user_message: str, context_text: str) -> str:
    prompt = f"""
{_build_prompt(user_message, context_text)}
"""
    tools = [
        {"type": "function", "function": REQUEST_MEMORY_EXTRACTION_TOOL},
        {"type": "function", "function": SEARCH_AND_FETCH_TOOL},
    ]
    response = system.llm.generate_response(
        messages=[{"role": "user", "content": prompt}],
        tools=tools,
        tool_choice="auto",
    )

    extra_context_blobs = []
    if isinstance(response, dict):
        for tool_call in response.get("tool_calls", []):
            name = tool_call.get("name")
            args = tool_call.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}

            if name == "request_memory_extraction":
                reason = str(args.get("reason", "assistant_requested_memory"))
                aspects = args.get("specific_aspects", [])
                if not isinstance(aspects, list):
                    aspects = [str(aspects)]
                system.request_memory_extraction(
                    chat_id=st.session_state.active_chat_id,
                    reason=reason,
                    specific_aspects=[str(item) for item in aspects],
                )
                st.caption("Memory extraction request captured.")
            elif name == "search_and_fetch":
                current_session_node_id = None
                if system.graph_driver and st.session_state.get("active_chat_id"):
                    try:
                        with system.graph_driver.session() as session:
                            row = session.run(
                                """
                                MATCH (n:session)
                                WHERE $chat_id IN n.chat_ids
                                RETURN n.id AS id
                                LIMIT 1
                                """,
                                chat_id=st.session_state["active_chat_id"],
                            ).single()
                            if row:
                                current_session_node_id = row.get("id")
                    except Exception:
                        current_session_node_id = None
                result = system.graph_tools.search_and_fetch(
                    query=str(args.get("query") or user_message),
                    top_k=int(args.get("top_k", 3)),
                    max_neighbors=int(args.get("max_neighbors", 5)),
                    outcome_filter=args.get("outcome_filter"),
                    intent_filter=args.get("intent_filter"),
                    current_node_id=current_session_node_id,
                    user_id=st.session_state.user_id,
                    retrieval_threshold=float(getattr(system.extraction_config, "RETRIEVAL_THRESHOLD", 0.75)),
                )
                extra_context_blobs.append(result)
                st.caption("Additional memory context retrieved.")
        content = response.get("content", "")
        if extra_context_blobs:
            extra = json.dumps(extra_context_blobs, ensure_ascii=True)
            if content:
                content = f"{content}\n\n[Additional retrieved context]\n{extra}"
            else:
                followup = system.llm.generate_response(
                    messages=[{"role": "user", "content": _build_prompt(user_message, f'{context_text}\n{extra}')}]
                )
                if isinstance(followup, dict):
                    content = followup.get("content", "")
                else:
                    content = str(followup)
        return (content or "").strip() or "I can help with that."

    return (response or "").strip() or "I can help with that."


def _generate_response_streaming(user_message: str, context_text: str) -> str:
    prompt = _build_prompt(user_message, context_text)
    placeholder = st.empty()
    full_text = ""

    config = system.llm.config
    client = OpenAI(
        api_key=getattr(config, "api_key", None) or os.getenv("NVIDIA_API_KEY"),
        base_url=getattr(config, "openai_base_url", None) or os.getenv("OPENAI_BASE_URL"),
    )

    stream = client.chat.completions.create(
        model=getattr(config, "model", None) or os.getenv("NVIDIA_MODEL"),
        messages=[{"role": "user", "content": prompt}],
        temperature=getattr(config, "temperature", 0.2),
        max_tokens=getattr(config, "max_tokens", 1200),
        stream=True,
    )

    in_think = False

    for event in stream:
        if not event.choices:
            continue
        delta = event.choices[0].delta
        if not delta or not getattr(delta, "content", None):
            continue

        text = delta.content

        # Strip any <think>...</think> blocks if present
        while text:
            if in_think:
                end_idx = text.find("</think>")
                if end_idx == -1:
                    text = ""
                else:
                    text = text[end_idx + len("</think>"):]
                    in_think = False
            else:
                start_idx = text.find("<think>")
                if start_idx == -1:
                    full_text += text
                    text = ""
                else:
                    full_text += text[:start_idx]
                    text = text[start_idx + len("<think>"):]
                    in_think = True

        placeholder.markdown(full_text)

    return full_text.strip() or "I can help with that."


def _render_json(value, fallback_label: str = "Value"):
    if isinstance(value, (dict, list)):
        st.json(value)
    elif value is None:
        st.text(f"{fallback_label}: (none)")
    else:
        st.text(f"{fallback_label}: {value}")


def _display_processing_state(raw_state: str) -> str:
    state = (raw_state or "pending").strip().lower()
    return "completed" if state == "processed" else state


def _state_badge(state: str) -> str:
    state = _display_processing_state(state)
    if state == "pending":
        return "🟡 pending"
    if state == "processing":
        return "🔵 processing"
    if state == "completed":
        return "🟢 completed"
    if state == "failed":
        return "🔴 failed"
    if state == "skipped":
        return "⚪ skipped"
    return state


def _load_chat_rows(limit: int = 500) -> List[Dict[str, Any]]:
    if not system.episodic:
        return []
    with system.episodic.pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT
                chat_id,
                created_at,
                total_messages,
                COALESCE(processing_state, 'pending') AS processing_state,
                importance_score
            FROM chat_sessions
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
    result = []
    for row in rows:
        result.append(
            {
                "chat_id": row[0],
                "created_at": row[1].isoformat() if row[1] else None,
                "message_count": int(row[2] or 0),
                "processing_state": _display_processing_state(row[3]),
                "importance_score": float(row[4]) if row[4] is not None else None,
            }
        )
    return result


def _load_extraction_log(limit: int = 10) -> List[Dict[str, Any]]:
    if not system.episodic:
        return []
    with system.episodic.pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT
                cs.chat_id,
                COALESCE(cs.processing_state, 'pending') AS processing_state,
                cs.importance_score,
                em.extraction_confidence,
                em.conversation_metadata->>'type' AS conversation_type,
                em.conversation_metadata->>'success_outcome' AS success_outcome,
                COALESCE(cs.memory_processed_at, cs.updated_at) AS processed_at
            FROM chat_sessions cs
            LEFT JOIN extracted_memories em ON em.chat_id = cs.chat_id
            WHERE COALESCE(cs.processing_state, 'pending') IN ('processed', 'failed', 'skipped')
            ORDER BY COALESCE(cs.memory_processed_at, cs.updated_at) DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

    result = []
    for row in rows:
        success_raw = (row[5] or "").lower()
        if success_raw == "true":
            outcome = "worked"
        elif success_raw == "false":
            outcome = "failed"
        else:
            outcome = "unknown"
        result.append(
            {
                "chat_id": row[0],
                "outcome": outcome,
                "importance_score": float(row[2]) if row[2] is not None else None,
                "extraction_confidence": float(row[3]) if row[3] is not None else None,
                "conversation_type": row[4] or "unknown",
                "processed_at": row[6].isoformat() if row[6] else None,
                "processing_state": _display_processing_state(row[1]),
            }
        )
    return result


# Tabs
chat_tab, processing_tab, graph_tab = st.tabs([
    "Chat",
    "Processing",
    "Graph Inspector",
])

# ------------------------------------------------------------------
# Chat tab
# ------------------------------------------------------------------
with chat_tab:
    st.subheader("Conversation")
    if st.session_state.get("completion_notice"):
        st.success(st.session_state["completion_notice"])

    col_left, col_right = st.columns([2, 1])

    with col_left:
        user_message = st.text_area("Your message", height=120)
        col_send, col_complete, col_new = st.columns([1, 1, 1])

        with col_send:
            if st.button("Send", use_container_width=True) and user_message.strip():
                chat_id = st.session_state.active_chat_id
                system.add_message(chat_id, "user", user_message.strip())

                retrieval = system.retrieve_for_query(
                    query=user_message,
                    user_id=st.session_state.user_id,
                    top_k=3,
                    chat_id=chat_id,
                )
                context_text = retrieval.get("context_text") or ""

                if use_llm_response:
                    if stream_responses:
                        response = _generate_response_streaming(user_message, context_text)
                    else:
                        response = _generate_response(user_message, context_text)
                else:
                    response = "Message stored. Enable response generation in the sidebar."

                system.add_message(chat_id, "assistant", response)

                st.session_state.chat_history.append({
                    "role": "user",
                    "content": user_message.strip(),
                    "timestamp": datetime.now().isoformat(),
                })
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": response,
                    "timestamp": datetime.now().isoformat(),
                    "context_used": context_text,
                })

                st.session_state.last_retrieval = retrieval

        with col_complete:
            if st.button("Mark Complete", use_container_width=True):
                chat_id = st.session_state.active_chat_id
                system.mark_complete(chat_id)
                st.session_state["completion_notice"] = (
                    "Chat marked complete. Trigger memory extraction from the Processing tab."
                )

        with col_new:
            if st.button("New Chat", use_container_width=True):
                st.session_state.chat_history = []
                st.session_state.active_chat_id = system.create_chat(user_id=st.session_state.user_id)
                st.session_state.last_processing_result = None
                st.session_state.last_retrieval = None
                st.session_state["completion_notice"] = ""
                st.rerun()

        st.markdown("---")
        _render_chat_history()

    with col_right:
        st.subheader("Chat Status")
        st.code(st.session_state.active_chat_id, language="text")

        if st.session_state.last_processing_result:
            st.markdown("**Last Processing Result**")
            _render_json(st.session_state.last_processing_result, "Processing result")

        if st.session_state.last_retrieval:
            st.markdown("**Last Retrieval Summary**")
            _render_json({
                "similar_chats": st.session_state.last_retrieval.get("similar_chats"),
                "graph_context": st.session_state.last_retrieval.get("graph_context"),
            }, "Retrieval summary")

# ------------------------------------------------------------------
# Processing tab
# ------------------------------------------------------------------
with processing_tab:
    queue_left, queue_right = st.columns([6, 1])
    with queue_left:
        st.subheader("Queue Status")
    with queue_right:
        if st.button("Refresh", key="refresh_processing_queue", use_container_width=True):
            st.rerun()

    chat_rows = _load_chat_rows(limit=500)
    queue_df = pd.DataFrame(chat_rows)
    if not queue_df.empty:
        queue_df["chat_id"] = queue_df["chat_id"].apply(lambda x: str(x)[:8])
        queue_df["processing_state"] = queue_df["processing_state"].apply(_state_badge)
        queue_df = queue_df[["chat_id", "created_at", "message_count", "processing_state", "importance_score"]]
        st.dataframe(queue_df, use_container_width=True)
    else:
        st.info("No chats available yet.")

    st.markdown("---")
    st.subheader("Trigger Panel")

    pending_rows = [row for row in chat_rows if row["processing_state"] == "pending"]
    pending_options = {
        f"{row['chat_id'][:8]} | {row['created_at']}": row["chat_id"]
        for row in pending_rows
    }

    selected_pending_label = st.selectbox(
        "Pending chat",
        options=list(pending_options.keys()) if pending_options else ["(none)"],
        index=0,
        key="pending_chat_selector",
    )

    if st.button("Run Memory Extraction", use_container_width=True, disabled=not pending_options):
        selected_chat_id = pending_options.get(selected_pending_label, "")
        if selected_chat_id:
            system.episodic.update_chat(
                selected_chat_id,
                {
                    "processing_state": "processing",
                    "processing_started_at": datetime.now(timezone.utc),
                    "processing_error": None,
                },
            )
            st.session_state.queued_single_run_chat_id = selected_chat_id
            st.rerun()

    if st.session_state.get("queued_single_run_chat_id"):
        run_chat_id = st.session_state["queued_single_run_chat_id"]
        st.info(f"Running extraction for `{run_chat_id[:8]}`...")
        try:
            result = system.process_chat(run_chat_id)
            st.session_state.last_extraction_result = {"chat_id": run_chat_id, "result": result}
            status = str(result.get("status", "")).lower()
            if status == "processed":
                st.success(f"Extraction completed for `{run_chat_id[:8]}`.")
            elif status in {"skipped", "already_processed"}:
                st.info(f"Extraction result for `{run_chat_id[:8]}`: {status}.")
            else:
                st.error(f"Extraction returned status `{status}` for `{run_chat_id[:8]}`.")
        except Exception as exc:  # noqa: BLE001
            system.episodic.update_chat(
                run_chat_id,
                {
                    "processing_state": "failed",
                    "processing_error": str(exc),
                    "memory_processed": False,
                },
            )
            st.error(f"Failed to process `{run_chat_id[:8]}`: {exc}")
        finally:
            st.session_state.queued_single_run_chat_id = ""

    if st.session_state.get("last_extraction_result"):
        with st.expander("Extraction Result", expanded=False):
            st.json(st.session_state["last_extraction_result"])

    if st.button("Process All Pending", use_container_width=True, disabled=not pending_rows):
        total = len(pending_rows)
        progress = st.progress(0.0)
        status_box = st.empty()
        batch_results = []
        for idx, row in enumerate(pending_rows, start=1):
            chat_id = row["chat_id"]
            system.episodic.update_chat(
                chat_id,
                {
                    "processing_state": "processing",
                    "processing_started_at": datetime.now(timezone.utc),
                    "processing_error": None,
                },
            )
            status_box.info(f"[{idx}/{total}] Processing `{chat_id[:8]}`")
            try:
                result = system.process_chat(chat_id)
                batch_results.append({"chat_id": chat_id, "result": result})
            except Exception as exc:  # noqa: BLE001
                system.episodic.update_chat(
                    chat_id,
                    {
                        "processing_state": "failed",
                        "processing_error": str(exc),
                        "memory_processed": False,
                    },
                )
                batch_results.append({"chat_id": chat_id, "result": {"status": "failed", "error": str(exc)}})
            progress.progress(idx / total)

        status_box.success(f"Processed {total} pending chats.")
        st.session_state.last_processing_result = {"batch": batch_results}
        with st.expander("Extraction Result", expanded=False):
            st.json(st.session_state.last_processing_result)

    st.markdown("---")
    st.subheader("Extraction Log")
    log_rows = _load_extraction_log(limit=10)
    if log_rows:
        log_df = pd.DataFrame(log_rows)
        log_df["chat_id"] = log_df["chat_id"].apply(lambda x: str(x)[:8])
        log_df = log_df[
            [
                "chat_id",
                "outcome",
                "importance_score",
                "extraction_confidence",
                "conversation_type",
                "processing_state",
                "processed_at",
            ]
        ]
        st.dataframe(log_df, use_container_width=True)
    else:
        st.info("No processed chats yet.")

# ------------------------------------------------------------------
# Graph Inspector tab
# ------------------------------------------------------------------
with graph_tab:
    st.subheader("Graph Inspector")

    if system.graph_driver is None:
        st.info("Graph database not configured. Add Memgraph/Neo4j credentials in the sidebar.")
    else:
        selected_from_query = st.query_params.get("selected_node")
        if selected_from_query:
            if isinstance(selected_from_query, list):
                selected_from_query = selected_from_query[0]
            st.session_state["selected_graph_node_id"] = str(selected_from_query)

        left_col, right_col = st.columns([3, 7])

        with left_col:
            st.markdown("**Controls**")
            with system.episodic.pool.connection() as conn:
                completed_rows = conn.execute(
                    """
                    SELECT
                        cs.chat_id,
                        cs.created_at,
                        COALESCE(em.conversation_metadata->>'type', 'unknown') AS conversation_type
                    FROM chat_sessions cs
                    LEFT JOIN extracted_memories em ON em.chat_id = cs.chat_id
                    WHERE COALESCE(cs.processing_state, 'pending') IN ('processed', 'completed')
                    ORDER BY cs.created_at DESC
                    """
                ).fetchall()

            completed_options = {
                f"{row[0][:8]} | {row[1].isoformat() if row[1] else ''} | {row[2]}": row[0]
                for row in completed_rows
            }
            selected_chat_label = st.selectbox(
                "Chat",
                options=list(completed_options.keys()) if completed_options else ["(none)"],
                key="graph_chat_selector",
            )
            selected_chat_id = completed_options.get(selected_chat_label, "")

            show_full_graph = st.checkbox("Show Full Graph", value=False)

            selected_node_types: List[str] = []
            selected_intents: List[str] = []
            selected_outcome = "All"
            if show_full_graph:
                selected_node_types = st.multiselect("node_type", options=NODE_TYPES, default=[])
                selected_intents = st.multiselect("session_intent", options=SESSION_INTENTS, default=[])
                selected_outcome = st.selectbox(
                    "outcome",
                    options=["All", "worked", "failed", "partial", "unknown"],
                    index=0,
                )

            st.markdown("---")
            st.markdown("**Node Details**")

        try:
            if show_full_graph:
                with system.graph_driver.session() as session:
                    row = session.run(
                        """
                        MATCH (n {user_id: $user_id})
                        WITH collect(n) AS scoped_nodes
                        UNWIND scoped_nodes AS src
                        OPTIONAL MATCH (src)-[r]->(dst {user_id: $user_id})
                        WITH scoped_nodes,
                             collect(
                                 CASE
                                     WHEN r IS NULL THEN NULL
                                     ELSE {
                                         source_id: src.id,
                                         relation: type(r),
                                         target_id: dst.id,
                                         properties: properties(r)
                                     }
                                 END
                             ) AS rels
                        RETURN
                            [node IN scoped_nodes | properties(node)] AS nodes,
                            [rel IN rels WHERE rel IS NOT NULL] AS edges
                        """,
                        user_id=st.session_state.user_id,
                    ).single()
                nodes = row["nodes"] if row else []
                edges = row["edges"] if row else []
            else:
                if selected_chat_id:
                    graph_data = system.graph_tools.get_graph_for_chat(
                        chat_id=selected_chat_id,
                        user_id=st.session_state.user_id,
                    )
                    nodes = graph_data.get("nodes", [])
                    edges = graph_data.get("edges", [])
                else:
                    nodes = []
                    edges = []

            normalized_nodes = []
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                node_type = node.get("node_type") or node.get("type") or "concept"
                session_intent = node.get("session_intent") or "general"
                outcome = node.get("outcome") or "unknown"
                normalized_nodes.append(
                    {
                        "id": node.get("id"),
                        "name": node.get("name") or node.get("id"),
                        "display_name": (node.get("display_name") or node.get("name") or node.get("id") or "")[:80],
                        "node_type": node_type,
                        "level": int(node.get("level") or 4),
                        "context": node.get("context") or "",
                        "outcome": outcome,
                        "importance": float(node.get("importance") or 0.0),
                        "mention_count": int(node.get("mention_count") or 0),
                        "session_intent": session_intent,
                        "chat_ids": node.get("chat_ids") or [],
                        "created_at": node.get("created_at"),
                    }
                )

            nodes_by_id = {n["id"]: n for n in normalized_nodes if n.get("id")}

            node_payload = []
            for node in normalized_nodes:
                node_type = node.get("node_type") or "concept"
                session_intent = node.get("session_intent") or "general"
                outcome = node.get("outcome") or "unknown"
                if node_type == "session":
                    continue
                if show_full_graph:
                    if selected_node_types and node_type not in selected_node_types:
                        continue
                    if selected_intents and session_intent not in selected_intents:
                        continue
                    if selected_outcome != "All" and outcome != selected_outcome:
                        continue
                node_payload.append(node)

            node_ids = {n["id"] for n in node_payload if n.get("id")}
            edge_payload = []
            for edge in edges:
                if not isinstance(edge, dict):
                    continue
                source_id = edge.get("source_id")
                target_id = edge.get("target_id")
                if source_id not in node_ids or target_id not in node_ids:
                    continue
                edge_payload.append(
                    {
                        "source_id": source_id,
                        "target_id": target_id,
                        "relation": edge.get("relation") or "RELATED_TO",
                        "properties": edge.get("properties") or {},
                    }
                )

            selected_node_id = st.session_state.get("selected_graph_node_id", "")
            selected_node = nodes_by_id.get(selected_node_id)

            with left_col:
                if selected_node:
                    outcome = (selected_node.get("outcome") or "unknown").lower()
                    outcome_color = {
                        "worked": "#2ECC71",
                        "failed": "#E74C3C",
                        "partial": "#F39C12",
                        "unknown": "#95A5A6",
                    }.get(outcome, "#95A5A6")
                    st.markdown(f"### {selected_node.get('display_name') or selected_node.get('name')}")
                    st.write(f"**node_type**: {selected_node.get('node_type')}")
                    st.markdown(
                        f"**outcome**: <span style='color:{outcome_color};font-weight:600'>{outcome}</span>",
                        unsafe_allow_html=True,
                    )
                    st.write(f"**level**: {selected_node.get('level')}")
                    st.write(f"**context**: {selected_node.get('context')}")
                    st.write(f"**importance**: {selected_node.get('importance')}")
                    st.write(f"**mention_count**: {selected_node.get('mention_count')}")
                    chat_ids = selected_node.get("chat_ids") or []
                    st.write(f"**chat_ids**: {len(chat_ids)}")
                    st.write(chat_ids)
                    st.write(f"**created_at**: {selected_node.get('created_at')}")
                else:
                    st.info("Click a node in the graph to view details.")

            with right_col:
                graph_height = st.number_input("Graph height", min_value=300, max_value=1200, value=700, step=50)
                if node_payload:
                    graph_html = f"""
                    <div id="graph-wrap" style="width:100%;">
                      <div id="graph" style="width:100%; height:{int(graph_height)}px; border:1px solid #e5e7eb; background:#ffffff;"></div>
                    </div>
                    <script src="https://d3js.org/d3.v7.min.js"></script>
                    <script>
                    const nodes = {json.dumps(node_payload)};
                    const links = {json.dumps(edge_payload)};

                    const nodeColors = {{
                      session: "#4A90D9",
                      problem: "#E74C3C",
                      solution: "#2ECC71",
                      attempt: "#F39C12",
                      concept: "#9B59B6",
                      context: "#95A5A6",
                      decision: "#1ABC9C",
                      artifact: "#E67E22",
                      open_question: "#F1C40F",
                    }};

                    function nodeRadius(level) {{
                      if (level === 1) return 18;
                      if (level === 2) return 14;
                      if (level === 3) return 10;
                      return 7;
                    }}

                    function edgeColorByOutcome(outcome) {{
                      if (outcome === "worked") return "#2ECC71";
                      if (outcome === "failed") return "#E74C3C";
                      if (outcome === "partial") return "#F39C12";
                      return "#BDC3C7";
                    }}

                    function notifyNodeClick(nodeId) {{
                      try {{
                        const parentUrl = new URL(window.parent.location.href);
                        parentUrl.searchParams.set("selected_node", nodeId);
                        window.parent.location.href = parentUrl.toString();
                      }} catch (e) {{}}
                    }}

                    const containerEl = document.getElementById("graph");
                    const width = containerEl.clientWidth || 900;
                    const height = {int(graph_height)};

                    const svg = d3.select(containerEl)
                      .append("svg")
                      .attr("width", width)
                      .attr("height", height);

                    const zoomLayer = svg.append("g");
                    svg.call(d3.zoom().scaleExtent([0.2, 3]).on("zoom", (event) => {{
                      zoomLayer.attr("transform", event.transform);
                    }}));

                    const nodeMap = new Map(nodes.map(n => [n.id, n]));

                    const simLinks = links.map(l => ({{
                      source: l.source_id,
                      target: l.target_id,
                      relation: l.relation,
                      properties: l.properties || {{}},
                    }}));

                    const link = zoomLayer.append("g")
                      .attr("stroke-opacity", 0.85)
                      .selectAll("line")
                      .data(simLinks)
                      .join("line")
                      .attr("stroke-width", 1.8)
                      .attr("stroke", d => {{
                        const crossChat = d.properties && (d.properties.cross_chat === true || d.properties.cross_chat === "true" || d.properties.cross_chat === 1);
                        if (crossChat) return "#4A90D9";
                        const src = nodeMap.get(d.source);
                        return edgeColorByOutcome((src && src.outcome) || "unknown");
                      }})
                      .attr("stroke-dasharray", d => {{
                        const crossChat = d.properties && (d.properties.cross_chat === true || d.properties.cross_chat === "true" || d.properties.cross_chat === 1);
                        return crossChat ? "5,5" : null;
                      }});

                    link.append("title")
                      .text(d => d.relation);

                    const node = zoomLayer.append("g")
                      .selectAll("circle")
                      .data(nodes)
                      .join("circle")
                      .attr("r", d => nodeRadius(Number(d.level || 4)))
                      .attr("fill", d => nodeColors[d.node_type] || "#7F8C8D")
                      .attr("stroke", "#ffffff")
                      .attr("stroke-width", 1.2)
                      .style("cursor", "pointer")
                      .on("click", (event, d) => notifyNodeClick(d.id))
                      .call(d3.drag()
                        .on("start", (event, d) => {{
                          if (!event.active) simulation.alphaTarget(0.3).restart();
                          d.fx = d.x;
                          d.fy = d.y;
                        }})
                        .on("drag", (event, d) => {{
                          d.fx = event.x;
                          d.fy = event.y;
                        }})
                        .on("end", (event, d) => {{
                          if (!event.active) simulation.alphaTarget(0);
                          d.fx = null;
                          d.fy = null;
                        }})
                      );

                    node.append("title")
                      .text(d => `${{d.name}}\\n${{d.node_type}}\\n${{d.context}}`);

                    const label = zoomLayer.append("g")
                      .selectAll("text")
                      .data(nodes)
                      .join("text")
                      .attr("font-size", "11px")
                      .attr("dx", 10)
                      .attr("dy", "0.35em")
                      .text(d => d.display_name || d.name);

                    const simulation = d3.forceSimulation(nodes)
                      .force("link", d3.forceLink(simLinks).id(d => d.id).distance(110))
                      .force("charge", d3.forceManyBody().strength(-280))
                      .force("center", d3.forceCenter(width / 2, height / 2))
                      .on("tick", () => {{
                        link
                          .attr("x1", d => d.source.x)
                          .attr("y1", d => d.source.y)
                          .attr("x2", d => d.target.x)
                          .attr("y2", d => d.target.y);

                        node
                          .attr("cx", d => d.x)
                          .attr("cy", d => d.y);

                        label
                          .attr("x", d => d.x)
                          .attr("y", d => d.y);
                      }});
                    </script>
                    """
                    components.html(graph_html, height=int(graph_height) + 20, scrolling=False)

                    st.markdown(
                        """
                        <div style="display:flex; flex-wrap:wrap; gap:12px; margin-top:8px; font-size:12px;">
                          <span><span style="display:inline-block;width:10px;height:10px;background:#4A90D9;margin-right:6px;"></span>session</span>
                          <span><span style="display:inline-block;width:10px;height:10px;background:#E74C3C;margin-right:6px;"></span>problem</span>
                          <span><span style="display:inline-block;width:10px;height:10px;background:#2ECC71;margin-right:6px;"></span>solution</span>
                          <span><span style="display:inline-block;width:10px;height:10px;background:#F39C12;margin-right:6px;"></span>attempt</span>
                          <span><span style="display:inline-block;width:10px;height:10px;background:#9B59B6;margin-right:6px;"></span>concept</span>
                          <span><span style="display:inline-block;width:10px;height:10px;background:#95A5A6;margin-right:6px;"></span>context</span>
                          <span><span style="display:inline-block;width:10px;height:10px;background:#1ABC9C;margin-right:6px;"></span>decision</span>
                          <span><span style="display:inline-block;width:10px;height:10px;background:#E67E22;margin-right:6px;"></span>artifact</span>
                          <span><span style="display:inline-block;width:10px;height:10px;background:#F1C40F;margin-right:6px;"></span>open_question</span>
                          <span><span style="display:inline-block;width:16px;height:0;border-top:2px dashed #4A90D9;margin-right:6px;vertical-align:middle;"></span>Cross-chat connection</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                else:
                    st.info("No graph data available for the selected scope.")

                with st.expander("Nodes Table", expanded=False):
                    st.dataframe(pd.DataFrame(node_payload), use_container_width=True)
                with st.expander("Edges Table", expanded=False):
                    st.dataframe(pd.DataFrame(edge_payload), use_container_width=True)

                st.markdown("---")
                st.subheader("Orange V2 Graph")
                try:
                    with system.graph_driver.session() as session:
                        v2_rows = session.run(
                            """
                            MATCH (n) WHERE n.user_id = $user_id
                            AND any(label IN labels(n) WHERE label IN ['Problem','Solution','Concept','Session'])
                            RETURN
                              head(labels(n)) AS type,
                              coalesce(n.canonical_label, n.title, n.name, n.id) AS label,
                              coalesce(n.context_brief, n.context, '') AS context,
                              coalesce(n.status, n.outcome, '') AS status,
                              coalesce(n.source, 'legacy') AS source
                            ORDER BY type
                            """,
                            user_id=st.session_state.user_id,
                        ).data()

                    if v2_rows:
                        v2_df = pd.DataFrame(v2_rows)
                        st.dataframe(v2_df[["type", "label", "context", "status", "source"]], use_container_width=True)
                    else:
                        st.info("No Orange V2 graph nodes found for this user.")
                except Exception as exc:
                    st.warning(f"Orange V2 graph query failed: {exc}")
        except Exception as exc:
            st.error(f"Graph query failed: {exc}")
