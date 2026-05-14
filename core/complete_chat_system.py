"""
COMPLETE CHAT-CENTRIC MEMORY SYSTEM
===================================

This is the production-ready implementation based on your requirements:
1. Each chat has unique chat_id
2. Post-conversation processing (triggered by checkbox)
3. Intelligent graph deduplication
4. Agentic retrieval with graph traversal
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import psycopg
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool
from neo4j import GraphDatabase

# Mem0 for vector embeddings
if not os.environ.get("MEM0_DIR"):
    mem0_dir = os.path.join(os.path.dirname(__file__), ".mem0")
    os.makedirs(mem0_dir, exist_ok=True)
    os.environ["MEM0_DIR"] = mem0_dir

from mem0.configs.base import MemoryConfig
from mem0.memory.main import Memory
from mem0.vector_stores.chroma import ChromaDB
from core.graph_tools import GraphTools
from core.graph_schema import (
    GraphNode,
    LEVEL_SESSION,
    NODE_TYPES,
    RELATIONSHIP_TYPES,
)
from core.memory_extraction import DSPyMemoryExtractor, ExtractionConfig


logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json_loads(text: str, fallback: Any) -> Any:
    """Parse JSON with fallback"""
    try:
        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
        elif cleaned.startswith("```"):
            cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()
        return json.loads(cleaned)
    except:
        return fallback


def _make_display_name(name: str) -> str:
    # Take first 4 meaningful words, drop filler words
    fillers = {"the", "a", "an", "is", "in", "on", "at", "to", "of", "and", "or", "for", "with"}
    words = [w for w in name.strip().split() if w.lower() not in fillers]
    return " ".join(words[:4]).title() if words else name[:30].title()


def _sanitize_vector_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Chroma metadata only accepts str/int/float/bool.
    Convert lists/dicts to JSON strings and None to empty string.
    """
    sanitized = {}
    for key, value in payload.items():
        if isinstance(value, (dict, list)):
            sanitized[key] = json.dumps(value)
        elif value is None:
            sanitized[key] = ""
        else:
            sanitized[key] = value
    return sanitized


def _maybe_json_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip().startswith(("[", "{")):
        parsed = _safe_json_loads(value, None)
        if isinstance(parsed, list):
            return parsed
    return []


def _coerce_jsonb(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return Json(value)
    return value


def _strip_embedding_fields(value: Any) -> Any:
    """Recursively remove embedding-like fields from context payloads."""
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for key, val in value.items():
            key_str = str(key).lower()
            if key_str in {"embedding", "embeddings", "vector", "vectors"}:
                continue
            cleaned[key] = _strip_embedding_fields(val)
        return cleaned
    if isinstance(value, list):
        return [_strip_embedding_fields(item) for item in value]
    return value


# ================================================================
# EPISODIC STORAGE (PostgreSQL)
# ================================================================

class ChatEpisodicStore:
    """
    Stores raw chat conversations in real-time.
    Uses connection pooling for efficient database access.
    """
    
    def __init__(self, dsn: str, min_pool_size: int = 2, max_pool_size: int = 10):
        if not dsn:
            raise ValueError("PostgreSQL DSN required")
        self.dsn = dsn
        self.pool = ConnectionPool(
            dsn,
            min_size=min_pool_size,
            max_size=max_pool_size,
            open=True,  # Open connections immediately
        )
        self._ensure_schema()
    
    def close(self):
        """Close the connection pool. Call this on shutdown."""
        if self.pool:
            self.pool.close()
    
    def _ensure_schema(self):
        with self.pool.connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    chat_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    is_complete BOOLEAN DEFAULT FALSE,
                    completion_requested_at TIMESTAMP,
                    memory_processed BOOLEAN DEFAULT FALSE,
                    memory_processed_at TIMESTAMP,
                    
                    title TEXT,
                    total_messages INT DEFAULT 0,
                    messages JSONB NOT NULL,
                    
                    query_summary TEXT,
                    response_summary TEXT,
                    extracted_concepts JSONB,
                    importance_score FLOAT,
                    skip_reason TEXT,
                    processing_state TEXT DEFAULT 'pending',
                    processing_started_at TIMESTAMP,
                    processing_error TEXT,
                    memory_request_reason TEXT,
                    memory_request_aspects JSONB,
                    memory_request_count INT DEFAULT 0,
                    memory_extraction_version TEXT
                );
            """)
            conn.execute("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS processing_state TEXT DEFAULT 'pending';")
            conn.execute("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMP;")
            conn.execute("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS processing_error TEXT;")
            conn.execute("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS memory_request_reason TEXT;")
            conn.execute("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS memory_request_aspects JSONB;")
            conn.execute("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS memory_request_count INT DEFAULT 0;")
            conn.execute("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS memory_extraction_version TEXT;")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS extracted_memories (
                    chat_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    extracted_at TIMESTAMP NOT NULL,
                    conversation_metadata JSONB NOT NULL,
                    memory_payload JSONB NOT NULL,
                    extracted_concepts JSONB NOT NULL,
                    relationships JSONB NOT NULL,
                    searchable_summary JSONB NOT NULL,
                    importance_score FLOAT NOT NULL,
                    extraction_confidence FLOAT NOT NULL,
                    extraction_version TEXT NOT NULL,
                    content_hash TEXT,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                );
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_user 
                ON chat_sessions(user_id, created_at DESC);
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_complete 
                ON chat_sessions(is_complete, memory_processed);
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_pending_queue
                ON chat_sessions(is_complete, memory_processed, processing_state, completion_requested_at);
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_extracted_memories_user
                ON extracted_memories(user_id, extracted_at DESC);
            """)
    
    def create_chat(self, user_id: str) -> str:
        """Create new chat session"""
        chat_id = f"chat_{uuid.uuid4().hex[:12]}"
        
        with self.pool.connection() as conn:
            conn.execute("""
                INSERT INTO chat_sessions 
                (chat_id, user_id, created_at, updated_at, messages)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                chat_id,
                user_id,
                datetime.now(timezone.utc),
                datetime.now(timezone.utc),
                json.dumps([])
            ))
        
        return chat_id
    
    def add_message(
        self,
        chat_id: str,
        role: str,
        content: str
    ):
        """Add message to chat"""
        with self.pool.connection() as conn:
            conn.execute("""
                UPDATE chat_sessions
                SET messages = messages || %s::jsonb,
                    total_messages = total_messages + 1,
                    updated_at = %s
                WHERE chat_id = %s
            """, (
                json.dumps([{
                    "role": role,
                    "content": content,
                    "timestamp": _utc_now_iso()
                }]),
                datetime.now(timezone.utc),
                chat_id
            ))
    
    def mark_complete(self, chat_id: str):
        """User marks chat as complete (triggers processing)"""
        with self.pool.connection() as conn:
            conn.execute("""
                UPDATE chat_sessions
                SET is_complete = TRUE,
                    completion_requested_at = %s,
                    processing_state = 'pending',
                    processing_started_at = NULL,
                    processing_error = NULL
                WHERE chat_id = %s
            """, (datetime.now(timezone.utc), chat_id))

    def request_memory_extraction(self, chat_id: str, reason: str, specific_aspects: List[str]):
        with self.pool.connection() as conn:
            conn.execute(
                """
                UPDATE chat_sessions
                SET memory_request_reason = %s,
                    memory_request_aspects = %s,
                    memory_request_count = COALESCE(memory_request_count, 0) + 1,
                    updated_at = %s
                WHERE chat_id = %s
                """,
                (
                    reason,
                    Json(specific_aspects),
                    datetime.now(timezone.utc),
                    chat_id,
                ),
            )
    
    def get_chat(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """Fetch chat by ID"""
        with self.pool.connection() as conn:
            row = conn.execute("""
                SELECT * FROM chat_sessions WHERE chat_id = %s
            """, (chat_id,)).fetchone()
            
            if not row:
                return None

            messages = row[10]
            if isinstance(messages, str):
                messages = _safe_json_loads(messages, [])

            extracted_concepts = row[13]
            if isinstance(extracted_concepts, str):
                extracted_concepts = _safe_json_loads(extracted_concepts, None)
            request_aspects = row[20]
            if isinstance(request_aspects, str):
                request_aspects = _safe_json_loads(request_aspects, [])
            
            return {
                "chat_id": row[0],
                "user_id": row[1],
                "created_at": row[2].isoformat() if row[2] else None,
                "updated_at": row[3].isoformat() if row[3] else None,
                "is_complete": row[4],
                "completion_requested_at": row[5].isoformat() if row[5] else None,
                "memory_processed": row[6],
                "memory_processed_at": row[7].isoformat() if row[7] else None,
                "title": row[8],
                "total_messages": row[9],
                "messages": messages,
                "query_summary": row[11],
                "response_summary": row[12],
                "extracted_concepts": extracted_concepts,
                "importance_score": row[14],
                "skip_reason": row[15],
                "processing_state": row[16] or "pending",
                "processing_started_at": row[17].isoformat() if row[17] else None,
                "processing_error": row[18],
                "memory_request_reason": row[19],
                "memory_request_aspects": request_aspects or [],
                "memory_request_count": row[21] or 0,
                "memory_extraction_version": row[22],
            }
    
    def update_chat(self, chat_id: str, updates: Dict[str, Any]):
        """Update chat fields"""
        set_clauses = []
        values = []
        
        for key, value in updates.items():
            set_clauses.append(f"{key} = %s")
            values.append(_coerce_jsonb(value))
        
        values.append(chat_id)
        
        with self.pool.connection() as conn:
            conn.execute(f"""
                UPDATE chat_sessions
                SET {', '.join(set_clauses)}
                WHERE chat_id = %s
            """, tuple(values))
    
    def get_pending_processing(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get chats that need memory processing"""
        with self.pool.connection() as conn:
            rows = conn.execute("""
                SELECT chat_id FROM chat_sessions
                WHERE is_complete = TRUE
                  AND memory_processed = FALSE
                  AND COALESCE(processing_state, 'pending') IN ('pending', 'failed')
                ORDER BY completion_requested_at ASC
                LIMIT %s
            """, (limit,)).fetchall()
            
            return [self.get_chat(row[0]) for row in rows]

    def claim_pending_processing(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Claim pending chats using FOR UPDATE SKIP LOCKED."""
        with self.pool.connection() as conn:
            with conn.transaction():
                rows = conn.execute(
                    """
                    WITH candidates AS (
                        SELECT chat_id
                        FROM chat_sessions
                        WHERE is_complete = TRUE
                          AND memory_processed = FALSE
                          AND COALESCE(processing_state, 'pending') IN ('pending', 'failed')
                        ORDER BY completion_requested_at ASC
                        FOR UPDATE SKIP LOCKED
                        LIMIT %s
                    )
                    UPDATE chat_sessions cs
                    SET processing_state = 'processing',
                        processing_started_at = %s,
                        processing_error = NULL
                    FROM candidates c
                    WHERE cs.chat_id = c.chat_id
                    RETURNING cs.chat_id
                    """,
                    (limit, datetime.now(timezone.utc)),
                ).fetchall()
            return [self.get_chat(row[0]) for row in rows]

    def upsert_extracted_memory(self, memory: Dict[str, Any]):
        payload_hash = hashlib.md5(
            json.dumps(
                {
                    "memory_payload": memory.get("memory_payload", {}),
                    "searchable_summary": memory.get("searchable_summary", {}),
                    "relationships": memory.get("relationships", []),
                },
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        ).hexdigest()

        with self.pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO extracted_memories (
                    chat_id, user_id, extracted_at, conversation_metadata, memory_payload,
                    extracted_concepts, relationships, searchable_summary, importance_score,
                    extraction_confidence, extraction_version, content_hash, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (chat_id)
                DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    extracted_at = EXCLUDED.extracted_at,
                    conversation_metadata = EXCLUDED.conversation_metadata,
                    memory_payload = EXCLUDED.memory_payload,
                    extracted_concepts = EXCLUDED.extracted_concepts,
                    relationships = EXCLUDED.relationships,
                    searchable_summary = EXCLUDED.searchable_summary,
                    importance_score = EXCLUDED.importance_score,
                    extraction_confidence = EXCLUDED.extraction_confidence,
                    extraction_version = EXCLUDED.extraction_version,
                    content_hash = EXCLUDED.content_hash,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    memory["chat_id"],
                    memory["user_id"],
                    datetime.fromisoformat(memory["extracted_at"].replace("Z", "+00:00")),
                    Json(memory.get("conversation_metadata", {})),
                    Json(memory.get("memory_payload", {})),
                    Json(memory.get("extracted_concepts", [])),
                    Json(memory.get("relationships", [])),
                    Json(memory.get("searchable_summary", {})),
                    memory.get("importance_score", 0.0),
                    memory.get("extraction_confidence", 0.0),
                    memory.get("extraction_version", "unknown"),
                    payload_hash,
                    datetime.now(timezone.utc),
                    datetime.now(timezone.utc),
                ),
            )

    def list_recent_chats(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """List recent chats for a user"""
        with self.pool.connection() as conn:
            rows = conn.execute("""
                SELECT chat_id FROM chat_sessions
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (user_id, limit)).fetchall()
            return [self.get_chat(row[0]) for row in rows]


# ================================================================
# AGENTS
# ================================================================

class SummarizationAgent:
    """Summarizes user queries and assistant responses"""
    
    def __init__(self, llm):
        self.llm = llm
    
    def process(self, chat: Dict[str, Any]) -> Dict[str, Any]:
        messages = chat["messages"]
        user_msgs = [m for m in messages if m["role"] == "user"]
        asst_msgs = [m for m in messages if m["role"] == "assistant"]
        
        user_text = "\n".join([m["content"] for m in user_msgs])
        asst_text = "\n".join([m["content"] for m in asst_msgs])
        
        prompt = f"""
Summarize this conversation:

USER MESSAGES:
{user_text}

ASSISTANT MESSAGES:
{asst_text}

Return JSON:
{{
  "query_summary": "What user wanted (1-2 sentences, searchable)",
  "response_summary": "Solution/answer (2-3 sentences, actionable)",
  "conversation_type": "problem_solution|how_to|explanation|factual_question|general_chat",
  "key_points": ["point1", "point2"],
  "was_successful": true/false
}}
"""
        
        response = self.llm.generate_response(
            messages=[{"role": "user", "content": prompt}]
        )
        
        return _safe_json_loads(response, {
            "query_summary": "Chat conversation",
            "response_summary": "Discussion",
            "conversation_type": "general_chat",
            "key_points": [],
            "was_successful": True
        })


class ImportanceFilterAgent:
    """Decides if conversation is worth storing"""
    
    def __init__(self, llm):
        self.llm = llm
    
    def should_store(
        self,
        chat: Dict[str, Any],
        summaries: Dict[str, Any]
    ) -> Dict[str, Any]:
        
        prompt = f"""
Should this conversation be stored in long-term memory?

Turns: {len(chat['messages']) // 2}
Type: {summaries['conversation_type']}
Query: {summaries['query_summary']}
Response: {summaries['response_summary']}

SKIP if trivial (weather, greetings, pure facts)
STORE if problem-solving, domain knowledge, procedures

Return JSON:
{{
  "should_store": true/false,
  "importance_score": 0.0-1.0,
  "reason": "brief explanation",
  "storage_targets": ["vector", "graph"] or ["vector_only"],
  "tags": ["tag1", "tag2"]
}}
"""
        
        response = self.llm.generate_response(
            messages=[{"role": "user", "content": prompt}]
        )
        
        return _safe_json_loads(response, {
            "should_store": True,
            "importance_score": 0.5,
            "reason": "Default store",
            "storage_targets": ["vector", "graph"],
            "tags": []
        })


class ConceptExtractionAgent:
    """Extracts concepts for graph"""
    
    def __init__(self, llm):
        self.llm = llm
    
    def extract(
        self,
        chat: Dict[str, Any],
        summaries: Dict[str, Any]
    ) -> Dict[str, Any]:
        
        full_chat = "\n".join([
            f"{m['role']}: {m['content']}" for m in chat["messages"]
        ])
        
        prompt = f"""
Extract concepts for knowledge graph:

SUMMARY:
Query: {summaries['query_summary']}
Response: {summaries['response_summary']}

FULL CHAT:
{full_chat[:2000]}

Return JSON:
{{
  "concepts": [
    {{"name": "...", "type": "service|tool|concept", "level": 1, "context": "..."}}
  ],
  "problems": [
    {{"name": "...", "type": "problem", "level": 2, "symptoms": [...], "context": "..."}}
  ],
  "solutions": [
    {{"name": "...", "type": "solution", "level": 3, "steps": [...], "context": "..."}}
  ],
  "relationships": [
    {{"source": "...", "relation": "HAS_PROBLEM|SOLVED_BY|RELATED_TO", "target": "..."}}
  ]
}}
"""
        
        response = self.llm.generate_response(
            messages=[{"role": "user", "content": prompt}]
        )
        
        return _safe_json_loads(response, {
            "concepts": [],
            "problems": [],
            "solutions": [],
            "relationships": []
        })


# ================================================================
# MAIN SYSTEM
# ================================================================

class ChatCentricMemorySystem:
    """
    Main system that orchestrates everything
    """
    
    def __init__(
        self,
        nvidia_api_key: str,
        nvidia_model: str,
        chroma_path: str,
        vector_collection: str,
        memgraph_url: Optional[str],
        memgraph_username: Optional[str],
        memgraph_password: Optional[str],
        postgres_dsn: Optional[str]
    ):
        # Initialize Mem0 for embeddings
        config_dict = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": vector_collection,
                    "path": chroma_path
                }
            },
            "llm": {
                "provider": "openai",
                "config": {
                    "api_key": nvidia_api_key,
                    "model": nvidia_model,
                }
            },
            "embedder": {
                "provider": "huggingface",
                "config": {
                    "model": "all-MiniLM-L6-v2",
                    "embedding_dims": 384
                }
            }
        }
        llm_base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("NVIDIA_BASE_URL")
        if llm_base_url:
            config_dict["llm"]["config"]["openai_base_url"] = llm_base_url
        
        self.memory = Memory(MemoryConfig(**config_dict))
        self.embedding_model = self.memory.embedding_model
        self.llm = self.memory.llm
        
        # Initialize stores
        self.episodic = ChatEpisodicStore(postgres_dsn) if postgres_dsn else None
        self.vector_store = ChromaDB(
            collection_name=f"{vector_collection}_chats",
            path=chroma_path
        )
        
        self.graph_driver = None
        if memgraph_url and memgraph_username and memgraph_password:
            self.graph_driver = GraphDatabase.driver(
                memgraph_url,
                auth=(memgraph_username, memgraph_password)
            )
            self.graph_driver.verify_connectivity()
        
        # Initialize agents
        self.summarization_agent = SummarizationAgent(self.llm)
        self.importance_agent = ImportanceFilterAgent(self.llm)
        self.concept_agent = ConceptExtractionAgent(self.llm)
        self.extraction_config = ExtractionConfig()
        self.memory_extractor = DSPyMemoryExtractor(
            self.llm,
            config=self.extraction_config,
            summarization_agent=self.summarization_agent,
            importance_agent=self.importance_agent,
            concept_agent=self.concept_agent,
        )
        
        # Graph merger (from previous file)
        from core.graph_deduplication import IntelligentGraphMerger
        self.graph_merger = IntelligentGraphMerger(
            self.graph_driver,
            self.embedding_model,
            self.llm
        ) if self.graph_driver else None
        self.graph_tools = GraphTools(
            graph_driver=self.graph_driver,
            graph_merger=self.graph_merger,
            vector_store=self.vector_store,
            embedding_model=self.embedding_model,
            logger=logger,
        )
    
    # ============================================================
    # REAL-TIME CHAT OPERATIONS
    # ============================================================
    
    def create_chat(self, user_id: str) -> str:
        """Create new chat session"""
        if not self.episodic:
            raise ValueError("Episodic store not configured")
        
        return self.episodic.create_chat(user_id)
    
    def add_message(self, chat_id: str, role: str, content: str):
        """Add message to chat (real-time)"""
        if not self.episodic:
            raise ValueError("Episodic store not configured")
        
        self.episodic.add_message(chat_id, role, content)
    
    def mark_complete(self, chat_id: str):
        """
        User marks chat as complete
        
        This triggers the memory processing pipeline
        """
        if not self.episodic:
            raise ValueError("Episodic store not configured")
        
        self.episodic.mark_complete(chat_id)
        
    def request_memory_extraction(
        self,
        chat_id: str,
        reason: str,
        specific_aspects: List[str],
    ):
        """Record explicit memory extraction request from tool call."""
        if not self.episodic:
            raise ValueError("Episodic store not configured")
        self.episodic.request_memory_extraction(chat_id, reason, specific_aspects)
    
    # ============================================================
    # MEMORY PROCESSING (POST-CONVERSATION)
    # ============================================================
    
    def process_chat(self, chat_id: str) -> Dict[str, Any]:
        """DSPy-first processing pipeline with staged fallback controls."""
        chat = self.episodic.get_chat(chat_id)
        if not chat:
            return {"status": "not_found"}
        if chat["memory_processed"]:
            return {"status": "already_processed"}

        self.episodic.update_chat(
            chat_id,
            {
                "processing_state": "processing",
                "processing_started_at": datetime.now(timezone.utc),
                "processing_error": None,
            },
        )

        try:
            extracted = self.memory_extractor.extract_chat_memory(chat)
            if extracted.get("processing_state") == "skipped":
                reason = extracted.get("reason", "classifier_skip")
                self.episodic.update_chat(
                    chat_id,
                    {
                        "memory_processed": True,
                        "memory_processed_at": datetime.now(timezone.utc),
                        "skip_reason": reason,
                        "importance_score": extracted.get("importance_score", 0.0),
                        "processing_state": "skipped",
                        "memory_extraction_version": self.extraction_config.EXTRACTION_VERSION,
                    },
                )
                return {"status": "skipped", "reason": reason}

            self.episodic.upsert_extracted_memory(extracted)

            searchable = extracted.get("searchable_summary", {})
            query_intent = searchable.get("query_intent", "")
            solution_summary = searchable.get("solution_summary", "")
            # H5:REMOVED vec_<chat_id> write path (legacy chat-level vectors)
            # query_embedding = self.embedding_model.embed(query_intent or solution_summary or "memory")
            # vector_payload = {
            #     "chat_id": chat_id,
            #     "user_id": chat["user_id"],
            #     "created_at": chat["created_at"],
            #     "search_query_intent": query_intent,
            #     "search_solution_summary": solution_summary,
            #     "search_keywords": searchable.get("keywords", []),
            #     "graph_node_ids": [],
            #     "graph_concepts": [],
            #     "importance_score": extracted.get("importance_score", 0.0),
            #     "extraction_confidence": extracted.get("extraction_confidence", 0.0),
            #     "conversation_type": (extracted.get("conversation_metadata", {}) or {}).get("type", "unknown"),
            #     "extraction_version": extracted.get("extraction_version", self.extraction_config.EXTRACTION_VERSION),
            #     "context_snippet": solution_summary[:200],
            # }
            # vector_id = f"vec_{chat_id}"
            # try:
            #     self.vector_store.insert(
            #         [query_embedding],
            #         [_sanitize_vector_payload(vector_payload)],
            #         [vector_id],
            #     )
            # except Exception:
            #     self.vector_store.update(
            #         vector_id,
            #         vector=query_embedding,
            #         payload=_sanitize_vector_payload(vector_payload),
            #     )

            graph_node_ids = []
            importance_score = extracted.get("importance_score", 0.0)
            has_explicit_request = bool(chat.get("memory_request_reason"))
            meets_graph_threshold = importance_score >= self.extraction_config.MIN_IMPORTANCE_FOR_GRAPH
            if (
                self.graph_merger
                and (meets_graph_threshold or has_explicit_request)
            ):
                try:
                    graph_result = self._process_graph_concepts(
                        chat,
                        extracted,
                        chat_id,
                        chat["user_id"],
                        force_completed_outcome=True,
                    )
                    graph_node_ids = graph_result.get("node_ids", [])
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "legacy_graph_write_failed_continuing",
                        extra={"chat_id": chat_id, "error": str(exc)},
                    )
                    graph_node_ids = []
                # H5:REMOVED vec_<chat_id> update path after graph augmentation
                # graph_node_names = graph_result.get("node_names", [])
                # vector_payload["graph_node_ids"] = graph_node_ids
                # vector_payload["graph_concepts"] = graph_node_names
                # self.vector_store.update(
                #     vector_id,
                #     vector=query_embedding,
                #     payload=_sanitize_vector_payload(vector_payload),
                # )

            h3_h4_status = {"status": "skipped", "reason": "not_configured"}
            messages = [m for m in (chat.get("messages") or []) if isinstance(m, dict)]
            full_transcript = "\n".join(
                f"{str(m.get('role') or 'unknown').strip().title()}: {(m.get('content') or '').strip()}"
                for m in messages
                if (m.get("content") or "").strip()
            ).strip()

            if self.graph_driver and self.vector_store and full_transcript:
                try:
                    from core.agents.runner import run_extraction
                    from core.graph_schema_v2 import (
                        ConversationType as GraphConversationType,
                        Session,
                        SessionResolutionStatus,
                        SourceType,
                    )
                    from core.graph_upsert.writer import GraphUpsertEngine
                    from core.source_registry import ConversationType as RunnerConversationType

                    conversation_type_map = {
                        RunnerConversationType.DEBUGGING: GraphConversationType.DEBUGGING,
                        RunnerConversationType.BRAINSTORM: GraphConversationType.BRAINSTORMING,
                        RunnerConversationType.QA: GraphConversationType.LEARNING,
                        RunnerConversationType.DECISION: GraphConversationType.DECISION_MAKING,
                        RunnerConversationType.CASUAL: GraphConversationType.GENERAL,
                    }

                    source_for_orange_v2 = (
                        SourceType.SLACK
                        if chat.get("memory_request_reason") == "slack_orange_command"
                        else SourceType.STREAMLIT
                    )

                    extraction = asyncio.run(
                        run_extraction(
                            session_id=chat_id,
                            transcript=full_transcript,
                            source=source_for_orange_v2,
                        )
                    )
                    graph_conversation_type = conversation_type_map.get(
                        extraction.conversation_type,
                        GraphConversationType.GENERAL,
                    )

                    session_node = Session(
                        node_id=chat_id,
                        source=source_for_orange_v2,
                        conversation_type=graph_conversation_type,
                        resolution_status=SessionResolutionStatus.OPEN,
                        message_count=len(messages),
                        title=f"Session {chat_id}",
                        summary="Processed via Streamlit",
                    )

                    chroma_client = getattr(self.vector_store, "client", self.vector_store)
                    engine = GraphUpsertEngine(
                        neo4j=self.graph_driver,
                        chroma=chroma_client,
                        llm=self.llm,
                    )
                    upsert_summary = engine.upsert(
                        session=session_node,
                        user_id=chat["user_id"],
                        debug_result=extraction.debug_result,
                        concept_result=extraction.concept_result,
                    )
                    # New v2 pipeline - runs in separate thread to avoid nested asyncio.run()
                    import threading
                    from core.agents.orchestrator import run_extraction_pipeline

                    v2_transcript = "\n".join(
                        f"Turn {i+1} [{str(m.get('role') or 'unknown').strip().lower()}]: {(m.get('content') or '').strip()}"
                        for i, m in enumerate(messages)
                        if (m.get("content") or "").strip()
                    )

                    v2_result = {"problems_created": 0, "solutions_written": 0, "edges_written": 0, "errors": []}
                    v2_exception = []

                    def _run_v2():
                        import asyncio

                        try:
                            v2_result.update(
                                asyncio.run(
                                    run_extraction_pipeline(
                                        session_id=chat_id,
                                        user_id=chat["user_id"],
                                        transcript=v2_transcript,
                                        neo4j_client=self.graph_driver,
                                        chroma_client=chroma_client,
                                    )
                                )
                            )
                        except Exception as exc:
                            v2_exception.append(exc)

                    t = threading.Thread(target=_run_v2, daemon=True)
                    t.start()
                    t.join(timeout=120)  # 2 min max

                    if v2_exception:
                        logger.warning("v2_pipeline_thread_failed", extra={"error": str(v2_exception[0])})
                    else:
                        logger.info(
                            "v2_pipeline_complete",
                            extra={
                                "chat_id": chat_id,
                                "problems_created": v2_result["problems_created"],
                                "solutions_written": v2_result["solutions_written"],
                                "edges_written": v2_result["edges_written"],
                                "errors": v2_result["errors"],
                            },
                        )
                    h3_h4_status = {
                        "status": "processed",
                        "problems_created": upsert_summary.problems_created,
                        "problems_merged": upsert_summary.problems_merged,
                    }
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "h3_h4_extraction_failed_legacy_still_written",
                        extra={"chat_id": chat_id, "error": str(exc)},
                    )
                    h3_h4_status = {"status": "failed", "error": str(exc)}

            self.episodic.update_chat(
                chat_id,
                {
                    "memory_processed": True,
                    "memory_processed_at": datetime.now(timezone.utc),
                    "query_summary": query_intent,
                    "response_summary": solution_summary,
                    "extracted_concepts": extracted.get("extracted_concepts", []),
                    "importance_score": extracted.get("importance_score", 0.0),
                    "skip_reason": None,
                    "processing_state": "processed",
                    "processing_error": None,
                    "memory_extraction_version": extracted.get("extraction_version", self.extraction_config.EXTRACTION_VERSION),
                },
            )

            return {
                "status": "processed",
                # H5:REMOVED vec_<chat_id> return path kept as None for compatibility.
                "vector_id": None,
                "graph_nodes": len(graph_node_ids),
                "conversation_type": (extracted.get("conversation_metadata", {}) or {}).get("type"),
                "importance_score": extracted.get("importance_score", 0.0),
                "extraction_confidence": extracted.get("extraction_confidence", 0.0),
                "orange_v2_status": h3_h4_status,
            }
        except Exception as exc:  # noqa: BLE001
            self.episodic.update_chat(
                chat_id,
                {
                    "processing_state": "failed",
                    "processing_error": str(exc),
                    "memory_processed": False,
                },
            )
            logger.exception("chat_processing_failed", extra={"chat_id": chat_id})
            return {"status": "failed", "error": str(exc)}

    def process_pending_chats(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Process any completed chats that haven't been processed yet."""
        if not self.episodic:
            raise ValueError("Episodic store not configured")

        pending = self.episodic.claim_pending_processing(limit=limit)
        results = []

        for chat in pending:
            if not chat:
                continue
            results.append(self.process_chat(chat["chat_id"]))

        return results

    def _hash_user_id(self, user_id: str) -> str:
        return hashlib.sha256((user_id or "").encode("utf-8")).hexdigest()[:24]

    def _upsert_node_vector(
        self,
        node_id: str,
        node_type: str,
        session_intent: str,
        outcome: str,
        chat_id: str,
        user_id: str,
        importance: float,
        created_at: str,
        embedding: List[float],
    ) -> str:
        vector_id = f"nodevec_{node_id}"
        payload = {
            "node_id": node_id,
            "node_type": node_type,
            "session_intent": session_intent,
            "outcome": outcome,
            "chat_id": chat_id,
            "user_id": self._hash_user_id(user_id),
            "importance": max(0.0, min(1.0, float(importance))),
            "created_at": created_at,
        }
        try:
            self.vector_store.insert([embedding], [_sanitize_vector_payload(payload)], [vector_id])
        except Exception:
            self.vector_store.update(vector_id, vector=embedding, payload=_sanitize_vector_payload(payload))
        return vector_id

    def _update_node_runtime_metadata(
        self,
        node_id: str,
        user_id: str,
        *,
        session_intent: str,
        source_type: str,
        extraction_version: str,
        outcome: str,
        importance: float,
    ) -> None:
        if not self.graph_driver:
            return
        with self.graph_driver.session() as session:
            session.run(
                """
                MATCH (n {id: $node_id, user_id: $user_id})
                SET n.session_intent = $session_intent,
                    n.source_type = $source_type,
                    n.extraction_version = $extraction_version,
                    n.outcome = $outcome,
                    n.importance =
                        CASE
                            WHEN n.importance < $importance THEN $importance
                            ELSE n.importance
                        END,
                    n.user_ids =
                        CASE
                            WHEN $user_id IN coalesce(n.user_ids, []) THEN coalesce(n.user_ids, [])
                            ELSE coalesce(n.user_ids, []) + [$user_id]
                        END,
                    n.updated_at = $now
                """,
                node_id=node_id,
                user_id=user_id,
                session_intent=session_intent,
                source_type=source_type,
                extraction_version=extraction_version,
                outcome=outcome,
                importance=max(0.0, min(1.0, float(importance))),
                now=_utc_now_iso(),
            )

    def _create_relationship_by_ids(
        self,
        source_id: str,
        relation: str,
        target_id: str,
        user_id: str,
    ) -> None:
        if not self.graph_driver or relation not in RELATIONSHIP_TYPES:
            return
        query = f"""
        MATCH (a {{id: $source_id, user_id: $user_id}})
        MATCH (b {{id: $target_id, user_id: $user_id}})
        MERGE (a)-[r:{relation}]->(b)
        ON CREATE SET r.created_at = $now
        SET r.updated_at = $now
        """
        with self.graph_driver.session() as session:
            session.run(
                query,
                source_id=source_id,
                target_id=target_id,
                user_id=user_id,
                now=_utc_now_iso(),
            )

    def _process_graph_concepts(
        self,
        chat: Dict[str, Any],
        extracted: Dict[str, Any],
        chat_id: str,
        user_id: str,
        force_completed_outcome: bool = False,
    ) -> Dict[str, Any]:
        """Process graph nodes from decomposition and persist node-level vectors."""
        if not self.graph_merger:
            return {"node_ids": [], "node_names": []}

        messages = chat.get("messages", [])
        conversation = "\n".join(
            [
                f"[{idx}] {m.get('role', 'unknown')}: {(m.get('content', '') or '').strip()}"
                for idx, m in enumerate(messages, start=1)
                if isinstance(m, dict)
            ]
        )
        payload = dict(extracted.get("memory_payload", {}) or {})
        payload["chat_id"] = chat_id
        payload["user_id"] = user_id
        payload["extraction_version"] = extracted.get("extraction_version", self.extraction_config.EXTRACTION_VERSION)

        decomposed = self.memory_extractor.concept_graph.decompose_into_nodes(
            conversation_messages=conversation,
            payload=payload,
            chat_id=chat_id,
            user_id=user_id,
            extraction_version=payload["extraction_version"],
        )

        raw_nodes = decomposed.get("nodes", [])
        raw_relationships = decomposed.get("relationships", [])
        session_intent = (decomposed.get("session_intent") or (extracted.get("conversation_metadata", {}) or {}).get("type") or "general")

        validated_nodes: List[Dict[str, Any]] = []
        temp_id_by_name: Dict[str, str] = {}
        for raw in raw_nodes if isinstance(raw_nodes, list) else []:
            if not isinstance(raw, dict):
                continue
            node_type = str(raw.get("node_type") or raw.get("type") or "").strip()
            if node_type not in NODE_TYPES:
                logger.warning("drop_invalid_node_type", extra={"chat_id": chat_id, "node_type": node_type})
                continue
            temp_id = str(raw.get("id") or uuid.uuid4())
            name = str(raw.get("name") or "").strip()[:100]
            if not name:
                logger.warning("drop_empty_node_name", extra={"chat_id": chat_id, "node_type": node_type})
                continue
            node = {
                "id": temp_id,
                "name": name,
                "display_name": _make_display_name(str(raw.get("name") or "")),
                "node_type": node_type,
                "level": int(raw.get("level", LEVEL_SESSION if node_type == "session" else 3)),
                "context": str(raw.get("context", "")).strip()[:300],
                "session_intent": session_intent,
                "source_type": str(raw.get("source_type", "chat")),
                "outcome": str(raw.get("outcome", "unknown")),
                "importance": float(raw.get("importance", extracted.get("importance_score", 0.5))),
                "created_at": str(raw.get("created_at") or _utc_now_iso()),
                "extraction_version": payload["extraction_version"],
            }
            validated_nodes.append(node)
            temp_id_by_name.setdefault(name, temp_id)
        temp_id_by_name_lower = {k.lower(): v for k, v in temp_id_by_name.items()}

        if not validated_nodes:
            logger.info("no_graph_nodes_after_validation", extra={"chat_id": chat_id})
            return {"node_ids": [], "node_names": []}

        session_node = next((n for n in validated_nodes if n["node_type"] == "session"), None)
        if not session_node:
            session_node = {
                "id": str(uuid.uuid4()),
                "name": f"Session {chat_id[:8]}",
                "display_name": f"Session {chat_id[:8]}",
                "node_type": "session",
                "level": LEVEL_SESSION,
                "context": "Root node for this completed chat session.",
                "session_intent": session_intent,
                "source_type": "chat",
                "outcome": "unknown",
                "importance": max(0.4, extracted.get("importance_score", 0.5)),
                "created_at": _utc_now_iso(),
                "extraction_version": payload["extraction_version"],
            }
            validated_nodes.insert(0, session_node)

        if force_completed_outcome:
            for node in validated_nodes:
                node_type = node.get("node_type")
                if node_type == "session":
                    node["outcome"] = "worked"
                elif node_type == "solution":
                    node["outcome"] = "worked"
                elif node_type == "problem":
                    node["outcome"] = "worked"
                elif node_type == "attempt" and str(node.get("outcome", "unknown")) == "unknown":
                    continue

        temp_id_set = {n["id"] for n in validated_nodes}
        validated_relationships: List[Dict[str, str]] = []
        for rel in raw_relationships if isinstance(raw_relationships, list) else []:
            if not isinstance(rel, dict):
                continue
            relation = str(rel.get("relation") or "").strip()
            if relation not in RELATIONSHIP_TYPES:
                logger.warning("drop_invalid_relation", extra={"chat_id": chat_id, "relation": relation})
                continue
            source_ref = str(rel.get("source_id") or rel.get("source") or "").strip()
            target_ref = str(rel.get("target_id") or rel.get("target") or "").strip()
            if source_ref not in temp_id_set:
                source_ref = temp_id_by_name.get(source_ref) or temp_id_by_name_lower.get(source_ref.lower(), "")
            if target_ref not in temp_id_set:
                target_ref = temp_id_by_name.get(target_ref) or temp_id_by_name_lower.get(target_ref.lower(), "")
            if source_ref not in temp_id_set or target_ref not in temp_id_set:
                logger.warning("drop_unresolved_relation", extra={"chat_id": chat_id, "relation": relation})
                continue
            validated_relationships.append(
                {
                    "source_id": source_ref,
                    "relation": relation,
                    "target_id": target_ref,
                }
            )

        graph_nodes: List[GraphNode] = []
        for node in validated_nodes:
            try:
                graph_nodes.append(
                    GraphNode(
                        id=node["id"],
                        name=node["name"],
                        display_name=node["display_name"],
                        node_type=node["node_type"],
                        level=node["level"],
                        context=node["context"],
                        session_intent=node["session_intent"],
                        source_type=node["source_type"],
                        chat_ids=[chat_id],
                        vector_refs=[],
                        user_ids=[user_id],
                        embedding=None,
                        mention_count=1,
                        importance=node["importance"],
                        outcome=node["outcome"],
                        created_at=datetime.fromisoformat(node["created_at"].replace("Z", "+00:00")),
                        updated_at=datetime.now(timezone.utc),
                        extraction_version=node["extraction_version"],
                    )
                )
            except Exception:
                logger.warning("drop_graph_node_after_validation", extra={"chat_id": chat_id, "node_name": node.get("name")})

        write_result = self.graph_tools.write_session_graph(
            nodes=graph_nodes,
            relationships=validated_relationships,
            chat_id=chat_id,
            user_id=user_id,
        )

        return {
            "node_ids": write_result.get("node_ids", []),
            "node_names": [node.name for node in graph_nodes],
        }
    
    # ============================================================
    # RETRIEVAL (FOR NEW CHATS)
    # ============================================================
    
    def retrieve_for_query(
        self,
        query: str,
        user_id: str,
        top_k: int = 3,
        chat_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retrieve node-level memory context for a new query."""
        retrieval_threshold = float(getattr(self.extraction_config, "RETRIEVAL_THRESHOLD", 0.75))
        current_session_node_id: Optional[str] = None
        if chat_id and self.graph_driver:
            try:
                with self.graph_driver.session() as session:
                    row = session.run(
                        """
                        MATCH (n) WHERE $chat_id IN coalesce(n.chat_ids, [])
                        AND (n.node_type = 'session' OR n.type = 'session')
                        RETURN n.id AS id
                        LIMIT 1
                        """,
                        chat_id=chat_id,
                    ).single()
                    if row:
                        current_session_node_id = row.get("id")
            except Exception:
                current_session_node_id = None

        result = self.graph_tools.search_and_fetch(
            query=query,
            top_k=max(1, min(3, int(top_k))),
            max_neighbors=5,
            outcome_filter=None,
            intent_filter=None,
            current_node_id=current_session_node_id,
            user_id=user_id,
            retrieval_threshold=retrieval_threshold,
        )
        matches = result.get("matches", [])
        sanitized_matches = _strip_embedding_fields(matches)
        neo4j_fallback_problems: List[Dict[str, Any]] = []
        fallback_blocks: List[str] = []

        best_score = max((float(m.get("score", 0) or 0) for m in matches), default=0.0)
        if (not matches or best_score > 0.5) and self.graph_driver:
            try:
                keywords = [
                    w.strip(".,!?;:()[]{}\"'").lower()
                    for w in query.split()
                    if len(w.strip(".,!?;:()[]{}\"'")) > 3
                ]
                keywords = [k.replace("'", "''") for k in keywords if k]
                keyword_conditions = " OR ".join(
                    [
                        f"toLower(coalesce(n.canonical_label, n.name, '')) CONTAINS '{k}' "
                        f"OR toLower(coalesce(n.context_brief, n.context, '')) CONTAINS '{k}'"
                        for k in keywords[:5]
                    ]
                )

                if keyword_conditions:
                    cypher = f"""
                        MATCH (n) WHERE n.user_id = $user_id
                        AND any(label IN labels(n) WHERE label IN ['Problem','Concept'])
                        AND ({keyword_conditions})
                        RETURN head(labels(n)) AS type,
                               coalesce(n.canonical_label, n.name, n.id) AS label,
                               coalesce(n.context_brief, n.context, '') AS context,
                               coalesce(n.status, n.outcome, 'unknown') AS status,
                               coalesce(n.recurrence_count, n.mention_count, 0) AS recurrence
                        ORDER BY recurrence DESC
                        LIMIT 5
                    """
                else:
                    cypher = """
                        MATCH (n) WHERE n.user_id = $user_id
                        AND any(label IN labels(n) WHERE label IN ['Problem','Concept'])
                        RETURN head(labels(n)) AS type,
                               coalesce(n.canonical_label, n.name, n.id) AS label,
                               coalesce(n.context_brief, n.context, '') AS context,
                               coalesce(n.status, n.outcome, 'unknown') AS status,
                               coalesce(n.recurrence_count, n.mention_count, 0) AS recurrence
                        ORDER BY recurrence DESC
                        LIMIT 5
                    """

                with self.graph_driver.session() as session:
                    rows = session.run(cypher, user_id=user_id).data()
                for row in rows:
                    node_type = str(row.get("type") or "Problem").upper()
                    label = str(row.get("label") or "").strip()
                    context = str(row.get("context") or "").strip()
                    status = str(row.get("status") or "unknown").strip() or "unknown"
                    recurrence = int(row.get("recurrence") or 0)
                    if not label:
                        continue
                    fallback_blocks.append(
                        f"[{node_type}] {label}\n"
                        f"Context: {context}\n"
                        f"Status: {status} | Recurred: {recurrence} times"
                    )
                    neo4j_fallback_problems.append(
                        {
                            "label": label,
                            "context": context,
                            "status": status,
                            "recurrence": recurrence,
                        }
                    )
            except Exception:
                neo4j_fallback_problems = []
                fallback_blocks = []

        context_blob = {
            "query": query,
            "threshold": retrieval_threshold,
            "matches": sanitized_matches,
        }
        if neo4j_fallback_problems:
            context_blob["neo4j_fallback_problems"] = neo4j_fallback_problems

        if fallback_blocks:
            context_text = (
                "Relevant past context from memory:\n\n"
                + "\n\n".join(fallback_blocks)
                + "\n\nUse this to inform your answer but do not cite users by name."
            )
        else:
            context_text = (
                "Relevant past context retrieved from memory: "
                f"{json.dumps(context_blob, ensure_ascii=True)}. "
                "Use this to inform your answer but do not cite users by name."
            )
        logger.info(f"RETRIEVAL CONTEXT: {context_text}")

        return {
            "similar_chats": sanitized_matches,
            "graph_context": {"matches": sanitized_matches},
            "context_text": context_text,
            "context_blob": context_blob,
        }
    
    def _format_context(
        self,
        similar_chats: List[Dict[str, Any]],
        graph_context: Optional[Dict[str, Any]]
    ) -> str:
        """Format for LLM consumption"""
        
        sections = []
        
        if similar_chats:
            sections.append("## Similar Past Conversations\n")
            for i, chat in enumerate(similar_chats, 1):
                sections.append(
                    f"{i}. Q: {chat['query']}\n"
                    f"   A: {chat['response']}\n"
                )
        
        if graph_context and graph_context.get("nodes"):
            sections.append("\n## Knowledge Graph Context\n")
            for node in graph_context["nodes"][:10]:
                sections.append(f"- {node.get('name')}: {node.get('context', '')}\n")
        
        return "\n".join(sections)


# ================================================================
# USAGE EXAMPLE
# ================================================================

"""
# Initialize system
system = ChatCentricMemorySystem(
    nvidia_api_key="...",
    nvidia_model="meta/llama-3.1-8b-instruct",
    chroma_path="./chroma_db",
    vector_collection="chat_memories",
    memgraph_url="bolt://localhost:7687",
    memgraph_username="memgraph",
    memgraph_password="password",
    postgres_dsn="postgresql://user:pass@localhost/db"
)

# ============================================================
# CHAT SESSION 1
# ============================================================

# User starts chat
chat_id = system.create_chat(user_id="user_123")

# Conversation happens
system.add_message(chat_id, "user", "How do I fix AWS S3 403 error?")
system.add_message(chat_id, "assistant", "Check your bucket policy...")
system.add_message(chat_id, "user", "Still not working")
system.add_message(chat_id, "assistant", "Try adding s3:GetObject permission")
system.add_message(chat_id, "user", "It worked!")

# User marks complete → triggers processing
system.mark_complete(chat_id)
result = system.process_chat(chat_id)
# Background processing creates:
# - Vector embedding of query/response summaries
# - Graph nodes: AWS S3 (concept), S3 403 Error (problem), Update Bucket Policy (solution)
# - Relationships between nodes

# ============================================================
# CHAT SESSION 2 (Later, different user or same user)
# ============================================================

chat_id_2 = system.create_chat(user_id="user_123")
system.add_message(chat_id_2, "user", "Lambda can't access my S3 bucket")

# Before responding, retrieve relevant context
context = system.retrieve_for_query(
    query="Lambda can't access my S3 bucket",
    user_id="user_123"
)

# context contains:
# - similar_chats: [Previous S3 403 conversation]
# - graph_context: {nodes: [AWS S3, S3 403 Error, Bucket Policy], relationships: [...]}
# - context_text: Formatted text for LLM

# Feed context to LLM for response
response_with_context = f'''
{context["context_text"]}

User Question: Lambda can't access my S3 bucket

Based on past conversations and knowledge graph, provide answer...
'''
"""
