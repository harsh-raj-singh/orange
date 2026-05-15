SOLUTION_AGENT_USER_SCOPE_PROMPT = """
You are extracting memory for a private user session. Include all relevant context,
including personal details, environment specifics, and team/project references.
These are private to this user only.
""".strip()

SOLUTION_AGENT_GLOBAL_SCOPE_PROMPT = """
You are extracting memory for a shared global knowledge base. The transcript has
already been PII-scrubbed. Do not add any personal, organizational, or location
details back in. Extract only technical solution patterns that would be useful to
any engineer facing the same problem, regardless of their team or company.
""".strip()
