import asyncio
import time

from core.agents.extraction_outputs import ExtractedSolution, SolutionAgentOutput
from core.agents.solution_agent.detail_extractor import run_detail_extractor
from core.agents.solution_agent.outcome_extractor import run_outcome_extractor
from core.agents.solution_agent.relationship_agent import _run_solution_relationship_agent
from core.agents.solution_agent.segmenter import run_solution_segmenter
from core.agents.solution_agent.summary_extractor import run_summary_extractor
from core.graph_schema_v2 import ConfidenceLevel, SolutionOutcome


def _get_followup_text(segment: dict, transcript: str) -> str:
    """Extract the conversation text that follows this solution's last turn."""
    relevant_turns = segment.get("relevant_turns", [])
    if not relevant_turns:
        return ""
    last_turn = max(relevant_turns)
    lines = transcript.split("\n")
    followup_lines = []
    for line in lines:
        # Find lines with turn numbers greater than last_turn
        for turn_num in range(last_turn + 1, last_turn + 6):
            if line.startswith(f"Turn {turn_num} ["):
                followup_lines.append(line)
    return "\n".join(followup_lines)


async def _enrich_segment(segment: dict, transcript: str) -> ExtractedSolution:
    """Run all sub-agents for one solution segment in parallel where possible."""
    followup_text = _get_followup_text(segment, transcript)

    # Wave 1 - detail and outcome run in parallel
    print(
        f"[AGENT] gather wave1(solution segment={segment.get('segment_id', 'unknown')}) starting",
        flush=True,
    )
    t_wave1 = time.time()
    detail, outcome = await asyncio.gather(
        run_detail_extractor(segment),
        run_outcome_extractor(segment, followup_text),
    )
    print(
        f"[AGENT] gather wave1(solution segment={segment.get('segment_id', 'unknown')}) done in {time.time()-t_wave1:.1f}s",
        flush=True,
    )

    # Wave 2 - summary needs detail + outcome
    summary = await run_summary_extractor(segment, detail, outcome)

    # Map outcome string to enum
    outcome_map = {
        "success": SolutionOutcome.SUCCESS,
        "partial": SolutionOutcome.PARTIAL,
        "failed": SolutionOutcome.FAILED,
        "caused_new_problem": SolutionOutcome.CAUSED_NEW_PROBLEM,
        "untried": SolutionOutcome.UNTRIED,
    }
    outcome_enum = outcome_map.get(outcome.get("outcome", "untried"), SolutionOutcome.UNTRIED)

    turns = sorted(segment.get("relevant_turns", []))

    return ExtractedSolution(
        canonical_label=detail.get("canonical_label", segment.get("raw_description", "")[:80]),
        description=summary.get("description", ""),
        in_depth_summary=summary.get("in_depth_summary", ""),
        outcome=outcome_enum,
        failure_reason=outcome.get("failure_reason"),
        failure_error_code=outcome.get("failure_error_code"),
        partial_fix_description=outcome.get("partial_fix_description"),
        steps=detail.get("steps", []),
        code_snippets=detail.get("code_snippets", []),
        tools_used=detail.get("tools_used", []),
        attempt_number=0,
        parent_solution_label=segment.get("parent_solution_label"),
        addresses_problem_label=segment.get("addresses_problem_description", ""),
        applied_turn=turns[0] if turns else None,
        turn_sequence=turns,
        confidence=ConfidenceLevel.MEDIUM,
    )


async def run_solution_agent(session_id: str, transcript: str) -> SolutionAgentOutput:
    print("[AGENT] run_solution_agent starting", flush=True)
    segments = await run_solution_segmenter(transcript)

    if not segments:
        return SolutionAgentOutput(session_id=session_id, solutions=[])

    # All segments enriched in parallel
    print(f"[AGENT] gather enrich_solutions starting for {len(segments)} segments", flush=True)
    t_enrich = time.time()
    solutions = await asyncio.gather(*[_enrich_segment(seg, transcript) for seg in segments])
    print(f"[AGENT] gather enrich_solutions done in {time.time()-t_enrich:.1f}s", flush=True)

    # Sort by applied_turn
    sorted_solutions = sorted(solutions, key=lambda s: s.applied_turn or 0)
    sorted_solutions = await _run_solution_relationship_agent(sorted_solutions)

    return SolutionAgentOutput(session_id=session_id, solutions=list(sorted_solutions))
