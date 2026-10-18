"""Watch-officer runs: evidence check -> deterministic draft -> human approval.

A run never publishes. It produces a bilingual status draft plus the agent's
tool trace and rationale; an officer approves or rejects it in the console or
in Telegram. The deterministic draft is the source of truth, so a provider
outage still leaves an actionable approval task.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from .adk_agent import AdvisorCall, AdvisorUnavailable, StepLLM, answer_detailed
from .adk_tools import AdvisorToolContext, AdvisorTools
from .logging_utils import log_event
from .models import AgentRun, AgentRunStatus, Commune, CommuneRisk, RiskTier
from .pipeline import AssessmentUnavailable, CommuneNotFound, Pipeline

log = logging.getLogger("mekongpulse.watch")


def _watch_prompt(
    commune: Commune,
    risk: CommuneRisk,
    draft: dict,
    previous_tier: RiskTier | None,
) -> str:
    previous = previous_tier.value if previous_tier else "none"
    return (
        "You are the MekongPulse watch officer. A watch run was triggered for "
        f"commune {commune.code} ({commune.name_en or commune.name_kh}). "
        f"Current risk tier: {risk.tier.value}; previous tier: {previous}; "
        f"lead time: {risk.lead_time_hours if risk.lead_time_hours is not None else 'unknown'} hours.\n\n"
        "Use the tools to verify the evidence pack and the nearest station reading. "
        "Then explain in 3-4 short sentences why an officer should review the draft: "
        "what changed, what it means for this commune, and what action is recommended. "
        "Do not publish, do not invent readings, and do not change the deterministic draft.\n\n"
        f"Deterministic draft (Khmer):\n{draft.get('khmer', '')}\n\n"
        f"Deterministic draft (English):\n{draft.get('english', '')}"
    )


async def pick_watch_commune(pipeline: Pipeline) -> str:
    """Highest-severity commune for a manual run without an explicit code."""
    risks = await pipeline.repo.risk_map()
    if not risks:
        raise AssessmentUnavailable("no commune risk rows available")
    worst = max(risks, key=lambda risk: (risk.tier.severity, risk.score))
    return worst.commune_code


async def run_watch(
    pipeline: Pipeline,
    commune_code: str,
    *,
    trigger: str = "manual",
    previous_tier: RiskTier | None = None,
    llm: StepLLM | None = None,
) -> AgentRun:
    """Build one pending approval task for a commune. Never publishes."""
    commune = pipeline.gazetteer.get(commune_code) or await pipeline.repo.get_commune(commune_code)
    if commune is None:
        raise CommuneNotFound(commune_code)

    risks = {risk.commune_code: risk for risk in await pipeline.repo.risk_map()}
    risk = risks.get(commune_code)
    if risk is None:
        raise AssessmentUnavailable(f"commune {commune_code} has no current risk row")

    tools = AdvisorTools(AdvisorToolContext(pipeline, authorized=False, publisher=None))
    draft = await tools.draft_status_update([commune_code])
    if not str(draft.get("khmer") or "").strip():
        raise AssessmentUnavailable(f"could not build a draft for commune {commune_code}")

    rationale = ""
    calls: list[AdvisorCall] = []
    error: str | None = None
    try:
        outcome = await answer_detailed(
            tools,
            [],
            _watch_prompt(commune, risk, draft, previous_tier),
            pipeline.settings,
            llm=llm,
        )
        rationale = outcome.text
        calls = outcome.calls
    except AdvisorUnavailable as exc:
        # Keep the deterministic draft reviewable even when the provider is down.
        error = str(exc)[:500]
        rationale = "Agent narration unavailable; review the deterministic draft below."
        log_event(log, "WATCH_AGENT_UNAVAILABLE", commune=commune_code, error=error)

    run = AgentRun(
        id=uuid4().hex,
        commune_code=commune_code,
        commune_name_kh=commune.name_kh,
        commune_name_en=commune.name_en,
        trigger=trigger,
        previous_tier=previous_tier,
        current_tier=risk.tier,
        status=AgentRunStatus.PENDING_APPROVAL,
        rationale=rationale,
        draft_khmer=str(draft["khmer"]).strip(),
        draft_english=str(draft.get("english") or "").strip() or None,
        tool_calls=[
            {"name": call.name, "status": call.status, "summary": call.summary}
            for call in calls
        ],
        created_at=datetime.now(timezone.utc),
        error=error,
    )
    await pipeline.repo.add_agent_run(run)
    log_event(
        log,
        "WATCH_RUN_CREATED",
        run_id=run.id,
        commune=commune_code,
        trigger=trigger,
        tier=risk.tier.value,
        tools=len(run.tool_calls),
        agent_ok=error is None,
    )
    return run
