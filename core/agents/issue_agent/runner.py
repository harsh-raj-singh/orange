import asyncio
import time

from core.agents.extraction_outputs import (
    EnrichedProblem,
    IssueAgentOutput,
    RawProblemSegment,
    SolutionAgentOutput,
)
from core.agents.issue_agent.canonical_label import run_canonical_label
from core.agents.issue_agent.code_snippet import run_code_snippet
from core.agents.issue_agent.context_stitcher import run_context_stitcher
from core.agents.issue_agent.error_signature import run_error_signature
from core.agents.issue_agent.relationship import run_relationship_agent
from core.agents.issue_agent.segmenter import run_segmenter
from core.agents.issue_agent.tech_context import run_tech_context


def _merge_to_enriched(
    segment: RawProblemSegment,
    wave1: dict,
    wave2: dict,
) -> EnrichedProblem:
    turns = sorted(segment.relevant_turns)
    return EnrichedProblem(
        segment_id=segment.segment_id,
        canonical_label=wave2.get("canonical_label", ""),
        description=wave2.get("description", ""),
        llm_reasoning=wave2.get("llm_reasoning", ""),
        error_code=wave1.get("error_code"),
        error_type=wave1.get("error_type"),
        stack_trace_summary=wave1.get("stack_trace_summary"),
        tech_stack=wave1.get("tech_stack", []),
        affected_file_paths=wave1.get("affected_file_paths", []),
        relevant_code=wave1.get("relevant_code", []),
        turn_sequence=turns,
        first_seen_turn=turns[0] if turns else None,
        last_seen_turn=turns[-1] if turns else None,
    )


async def _run_wave1(segment: RawProblemSegment) -> dict:
    """Run all wave 1 sub-agents in parallel for one segment. Merge results into one dict."""
    print(
        f"[AGENT] gather wave1(issue segment={segment.segment_id}) starting",
        flush=True,
    )
    t_wave1 = time.time()
    error_sig, tech_ctx, code_snip = await asyncio.gather(
        run_error_signature(segment),
        run_tech_context(segment),
        run_code_snippet(segment),
    )
    print(
        f"[AGENT] gather wave1(issue segment={segment.segment_id}) done in {time.time()-t_wave1:.1f}s",
        flush=True,
    )
    return {**error_sig, **tech_ctx, **code_snip}


async def run_issue_agent(
    session_id: str,
    transcript: str,
    solution_output: SolutionAgentOutput,
) -> IssueAgentOutput:
    print("[AGENT] run_issue_agent starting", flush=True)
    # Step 1 - Segment the transcript into distinct problems.
    segments = await run_segmenter(transcript)

    if not segments:
        return IssueAgentOutput(session_id=session_id, problems=[])

    # Step 2 - Wave 1: all three sub-agents in parallel, per segment.
    print(f"[AGENT] gather wave1(all issue segments) starting for {len(segments)} segments", flush=True)
    t_wave1_all = time.time()
    wave1_results = await asyncio.gather(*[_run_wave1(segment) for segment in segments])
    print(
        f"[AGENT] gather wave1(all issue segments) done in {time.time()-t_wave1_all:.1f}s",
        flush=True,
    )

    solution_labels = [s.addresses_problem_label for s in solution_output.solutions if s.addresses_problem_label]

    # Step 3 - Wave 2: canonical label per segment (needs wave 1 output).
    print(f"[AGENT] gather wave2(canonical labels) starting for {len(segments)} segments", flush=True)
    t_wave2 = time.time()
    wave2_results = await asyncio.gather(
        *[
            run_canonical_label(segments[i], wave1_results[i], solution_labels)
            for i in range(len(segments))
        ]
    )
    print(f"[AGENT] gather wave2(canonical labels) done in {time.time()-t_wave2:.1f}s", flush=True)

    # Step 4 - Merge into EnrichedProblem list.
    enriched = [
        _merge_to_enriched(segments[i], wave1_results[i], wave2_results[i])
        for i in range(len(segments))
    ]

    # Step 5 - Relationship agent sees all problems at once.
    enriched = await run_relationship_agent(enriched, transcript)

    # Step 6 - Context stitching (needs solution output).
    enriched = await run_context_stitcher(enriched, solution_output)

    enriched.sort(key=lambda p: p.first_seen_turn or 0)

    return IssueAgentOutput(session_id=session_id, problems=enriched)
