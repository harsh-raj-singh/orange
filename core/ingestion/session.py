from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from core.graph_schema_v2 import SourceType

KNOWN_SOURCES = {"mcp", "slack", "cursor", "claude", "gmail", "streamlit"}
ROLE_ALIASES = {
    "agent": "assistant",
    "ai": "assistant",
    "agent": "assistant",
    "assistant": "assistant",
    "bot": "assistant",
    "human": "user",
    "model": "assistant",
    "system": "system",
    "tool": "tool",
    "user": "user",
}


def _clean_string(value: Any) -> str:
    return str(value or "").strip()


def _clean_optional_string(value: Any) -> str | None:
    cleaned = _clean_string(value)
    return cleaned or None


def _coerce_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _normalize_role(value: Any) -> str:
    role = _clean_string(value).lower()
    return ROLE_ALIASES.get(role, role or "unknown")


def _message_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for part in value:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text") or part.get("content")
                if text:
                    parts.append(str(text))
        return "\n".join(parts)
    return _clean_string(value)


@dataclass
class IngestionParticipant:
    participant_id: str
    display_name: str | None = None
    role: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.participant_id == other
        if isinstance(other, IngestionParticipant):
            return (
                self.participant_id,
                self.display_name,
                self.role,
                self.metadata,
            ) == (
                other.participant_id,
                other.display_name,
                other.role,
                other.metadata,
            )
        return False

    @classmethod
    def from_any(cls, value: Any) -> "IngestionParticipant | None":
        if isinstance(value, IngestionParticipant):
            return value
        if isinstance(value, str):
            participant_id = value.strip()
            if not participant_id:
                return None
            return cls(participant_id=participant_id)
        if not isinstance(value, dict):
            return None
        participant_id = _clean_string(
            value.get("participant_id") or value.get("id") or value.get("user_id") or value.get("name")
        )
        if not participant_id:
            return None
        return cls(
            participant_id=participant_id,
            display_name=_clean_optional_string(value.get("display_name") or value.get("name")),
            role=_clean_optional_string(value.get("role")),
            metadata=_coerce_dict(value.get("metadata")),
        )


@dataclass
class IngestionMessage:
    role: str
    content: str
    timestamp: datetime | None = None
    message_id: str | None = None
    participant_id: str | None = None
    participant_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_any(cls, value: Any) -> "IngestionMessage | None":
        if isinstance(value, IngestionMessage):
            return value
        if not isinstance(value, dict):
            return None

        content = _message_content(value.get("content") or value.get("text") or value.get("message"))
        if not content.strip():
            return None

        return cls(
            role=_normalize_role(value.get("role") or value.get("author_role") or value.get("type")),
            content=content.strip(),
            timestamp=_coerce_datetime(value.get("timestamp") or value.get("ts") or value.get("created_at")),
            message_id=_clean_optional_string(value.get("message_id") or value.get("id") or value.get("ts")),
            participant_id=_clean_optional_string(
                value.get("participant_id") or value.get("user_id") or value.get("author_id") or value.get("user")
            ),
            participant_name=_clean_optional_string(
                value.get("participant_name") or value.get("user_name") or value.get("author_name")
            ),
            metadata=_coerce_dict(value.get("metadata")),
            raw=dict(value),
        )


@dataclass
class NormalizedTurn:
    turn_index: int
    role: str
    content: str
    timestamp: datetime | None = None
    message_id: str | None = None
    participant_id: str | None = None
    participant_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def as_message(self) -> dict[str, Any]:
        message: dict[str, Any] = {
            "role": self.role,
            "content": self.content,
        }
        if self.timestamp:
            message["timestamp"] = self.timestamp.isoformat()
        if self.message_id:
            message["message_id"] = self.message_id
        if self.participant_id:
            message["participant_id"] = self.participant_id
        if self.participant_name:
            message["participant_name"] = self.participant_name
        if self.metadata:
            message["metadata"] = self.metadata
        return message


@dataclass
class SessionIngestionRequest:
    source: str
    session_id: str | None = None
    user_id: str | None = None
    external_session_id: str | None = None
    org_id: str | None = None
    started_at: datetime | str | int | float | None = None
    ended_at: datetime | str | int | float | None = None
    participants: list[IngestionParticipant | dict[str, Any]] = field(default_factory=list)
    client_name: str | None = None
    client_version: str | None = None
    source_url: str | None = None
    client_metadata: dict[str, Any] = field(default_factory=dict)
    tool_metadata: dict[str, Any] = field(default_factory=dict)
    raw_transcript: str | None = None
    transcript: str | None = None
    messages: list[IngestionMessage | dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedSession:
    source: SourceType
    session_id: str
    external_session_id: str
    user_id: str | None
    org_id: str | None
    started_at: datetime | None
    ended_at: datetime | None
    participants: list[IngestionParticipant]
    client_metadata: dict[str, Any]
    tool_metadata: dict[str, Any]
    raw_transcript: str
    raw_messages: list[dict[str, Any]]
    turns: list[NormalizedTurn]
    metadata: dict[str, Any] = field(default_factory=dict)
    ingested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def message_count(self) -> int:
        return len(self.turns)

    @property
    def source_id(self) -> str:
        return self.source.value

    @property
    def session_node_id(self) -> str:
        return self.session_id if self.session_id.startswith("session_") else f"session_{self.session_id}"

    @property
    def title(self) -> str:
        return _clean_string(self.metadata.get("title")) or f"Session {self.session_id[:8]}"

    @property
    def participant_ids(self) -> list[str]:
        return [participant.participant_id for participant in self.participants]

    @property
    def client_name(self) -> str | None:
        return _clean_optional_string(
            self.client_metadata.get("name")
            or self.client_metadata.get("client")
            or self.tool_metadata.get("client_name")
        )

    @property
    def client_version(self) -> str | None:
        return _clean_optional_string(
            self.client_metadata.get("version")
            or self.client_metadata.get("client_version")
            or self.tool_metadata.get("client_version")
        )

    @property
    def source_url(self) -> str | None:
        return _clean_optional_string(
            self.metadata.get("source_url")
            or self.metadata.get("url")
            or self.client_metadata.get("source_url")
        )

    @property
    def transcript(self) -> str:
        if self.turns:
            return "\n".join(f"Turn {turn.turn_index} [{turn.role}]: {turn.content}" for turn in self.turns)
        return self.raw_transcript.strip()

    @property
    def normalized_turns(self) -> list[dict[str, Any]]:
        return [
            {
                "turn_index": turn.turn_index,
                **turn.as_message(),
            }
            for turn in self.turns
        ]

    def as_chat(self) -> dict[str, Any]:
        chat = {
            "chat_id": self.session_id,
            "session_id": self.session_id,
            "source": self.source.value,
            "messages": [turn.as_message() for turn in self.turns],
            "metadata": self.metadata,
        }
        if self.user_id:
            chat["user_id"] = self.user_id
        if self.org_id:
            chat["org_id"] = self.org_id
        return chat

    def ingestion_metadata(self) -> dict[str, Any]:
        return {
            "source": self.source.value,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "org_id": self.org_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "participants": [
                {
                    "participant_id": participant.participant_id,
                    "display_name": participant.display_name,
                    "role": participant.role,
                    "metadata": participant.metadata,
                }
                for participant in self.participants
            ],
            "client_metadata": self.client_metadata,
            "tool_metadata": self.tool_metadata,
            "raw_transcript": self.raw_transcript,
            "raw_messages": self.raw_messages,
            "normalized_turns": self.normalized_turns,
            "message_count": self.message_count,
            **self.metadata,
        }


def normalize_session_request(request: SessionIngestionRequest | dict[str, Any] | Any) -> NormalizedSession:
    raw = request if isinstance(request, dict) else vars(request)
    source = _clean_string(raw.get("source")).lower()
    session_id = _clean_string(raw.get("session_id"))
    if not source:
        raise ValueError("source is required")
    if source not in KNOWN_SOURCES:
        raise ValueError(f"source must be one of: {', '.join(sorted(KNOWN_SOURCES))}")
    raw_transcript = _clean_string(raw.get("raw_transcript") or raw.get("transcript"))
    messages = [msg for msg in (IngestionMessage.from_any(item) for item in raw.get("messages") or []) if msg]
    turns = [
        NormalizedTurn(
            turn_index=idx,
            role=message.role,
            content=message.content,
            timestamp=message.timestamp,
            message_id=message.message_id,
            participant_id=message.participant_id,
            participant_name=message.participant_name,
            metadata=message.metadata,
            raw=message.raw,
        )
        for idx, message in enumerate(messages, start=1)
    ]

    participants = [
        participant
        for participant in (IngestionParticipant.from_any(item) for item in raw.get("participants") or [])
        if participant
    ]

    if not turns and not raw_transcript:
        raise ValueError("messages or raw_transcript is required")
    if not session_id:
        basis = "|".join(
            [
                source,
                _clean_string(raw.get("user_id")),
                _clean_string(raw.get("external_session_id")),
                _clean_string(raw.get("started_at")),
                raw_transcript or "\n".join(f"{turn.role}:{turn.content}" for turn in turns)[:1000],
            ]
        )
        session_id = hashlib.sha256((basis or uuid4().hex).encode("utf-8")).hexdigest()[:16]

    client_metadata = _coerce_dict(raw.get("client_metadata"))
    if raw.get("client_name") and "name" not in client_metadata:
        client_metadata["name"] = _clean_string(raw.get("client_name"))
    if raw.get("client_version") and "version" not in client_metadata:
        client_metadata["version"] = _clean_string(raw.get("client_version"))

    metadata = _coerce_dict(raw.get("metadata"))
    if raw.get("source_url") and "source_url" not in metadata:
        metadata["source_url"] = _clean_string(raw.get("source_url"))

    return NormalizedSession(
        source=SourceType(source),
        session_id=session_id,
        external_session_id=_clean_string(raw.get("external_session_id")) or session_id,
        user_id=_clean_optional_string(raw.get("user_id")),
        org_id=_clean_optional_string(raw.get("org_id")),
        started_at=_coerce_datetime(raw.get("started_at")),
        ended_at=_coerce_datetime(raw.get("ended_at")),
        participants=participants,
        client_metadata=client_metadata,
        tool_metadata=_coerce_dict(raw.get("tool_metadata")),
        raw_transcript=raw_transcript,
        raw_messages=[message.raw for message in messages],
        turns=turns,
        metadata=metadata,
    )


def normalize_ingestion_request(request: SessionIngestionRequest | dict[str, Any] | Any) -> NormalizedSession:
    return normalize_session_request(request)
