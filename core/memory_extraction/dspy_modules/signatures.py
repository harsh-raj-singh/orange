from __future__ import annotations

from typing import Any

try:
    import dspy
except Exception:  # pragma: no cover - optional dependency guard
    dspy = None


if dspy:
    class ConversationTypeClassifier(dspy.Signature):
        """Classify conversation type and extraction need."""

        conversation_messages: str = dspy.InputField(desc="Formatted conversation transcript")
        context_metadata: str = dspy.InputField(desc="Metadata JSON string")

        conversation_type: str = dspy.OutputField(desc="debugging|brainstorming|code_review|learning|casual")
        should_extract: bool = dspy.OutputField(desc="Whether to extract memory")
        extraction_depth: str = dspy.OutputField(desc="shallow|medium|deep")
        reasoning: str = dspy.OutputField(desc="Brief reason")


    class GenericTypeExtractor(dspy.Signature):
        """Extract type-specific payload as JSON."""

        conversation_messages: str = dspy.InputField(desc="Conversation transcript")
        conversation_type: str = dspy.InputField(desc="Classified type")
        context_metadata: str = dspy.InputField(desc="Metadata JSON")

        payload_json: str = dspy.OutputField(desc="JSON payload for the type")


    class NegativePathSignature(dspy.Signature):
        """Extract failed assistant suggestions and outcomes."""

        conversation_messages: str = dspy.InputField(desc="Conversation transcript")
        payload_json: str = dspy.InputField(desc="Current extracted payload JSON")

        failed_solutions_json: str = dspy.OutputField(desc="JSON array of failed solutions")


    class ConceptGraphSignature(dspy.Signature):
        """Extract concepts and relationships."""

        conversation_messages: str = dspy.InputField(desc="Conversation transcript")
        payload_json: str = dspy.InputField(desc="Extracted payload JSON")

        concepts_json: str = dspy.OutputField(desc="JSON array of concepts")
        relationships_json: str = dspy.OutputField(desc="JSON array of relationships")


    class SearchableSummarySignature(dspy.Signature):
        """Extract searchable summary fields."""

        conversation_messages: str = dspy.InputField(desc="Conversation transcript")
        payload_json: str = dspy.InputField(desc="Extracted payload JSON")

        query_intent: str = dspy.OutputField(desc="User query intent")
        solution_summary: str = dspy.OutputField(desc="Solution summary")
        keywords_json: str = dspy.OutputField(desc="JSON array of keywords")


    class ImportanceConfidenceSignature(dspy.Signature):
        """Predict importance and confidence."""

        conversation_messages: str = dspy.InputField(desc="Conversation transcript")
        payload_json: str = dspy.InputField(desc="Extracted payload JSON")

        importance_score: float = dspy.OutputField(desc="0-1")
        extraction_confidence: float = dspy.OutputField(desc="0-1")


else:
    class ConversationTypeClassifier:  # pragma: no cover - only used if dspy missing
        pass


    class GenericTypeExtractor:  # pragma: no cover
        pass


    class NegativePathSignature:  # pragma: no cover
        pass


    class ConceptGraphSignature:  # pragma: no cover
        pass


    class SearchableSummarySignature:  # pragma: no cover
        pass


    class ImportanceConfidenceSignature:  # pragma: no cover
        pass


def dspy_available() -> bool:
    return dspy is not None


def get_dspy_module() -> Any:
    return dspy
