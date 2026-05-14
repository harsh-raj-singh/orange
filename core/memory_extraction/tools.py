from __future__ import annotations

REQUEST_MEMORY_EXTRACTION_TOOL = {
    "name": "request_memory_extraction",
    "description": (
        "Request extraction of memories from current conversation. "
        "Use when details should be remembered for future conversations."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Why memory extraction should be requested",
            },
            "specific_aspects": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific items to remember, e.g. error messages and fixes",
            },
        },
        "required": ["reason", "specific_aspects"],
    },
}
