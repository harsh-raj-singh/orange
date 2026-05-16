USER_SCOPE_EXTRACTION_PROMPT = """
You are extracting memory for a private user session. Include all relevant context,
including personal details, environment specifics, and team/project references.
These are private to this user only.
""".strip()


GLOBAL_SCOPE_EXTRACTION_PREAMBLE = """
You are extracting memory for a shared global knowledge base. The transcript has
already been PII-scrubbed. Do not add any personal, organizational, or location
details back in.
""".strip()


def global_scope_extraction_prompt(subject: str) -> str:
    return f"""
{GLOBAL_SCOPE_EXTRACTION_PREAMBLE} Extract only technical {subject} patterns that would be useful to
any engineer facing the same problem, regardless of their team or company.
""".strip()
