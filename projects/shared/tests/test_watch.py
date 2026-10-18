"""Watch-officer runs: deterministic draft, tool trace, pending approval."""

from __future__ import annotations

from mekong_shared.adk_agent import AdvisorUnavailable, ScriptedLLM, StepResult
from mekong_shared.models import AgentRunStatus
from mekong_shared.watch import pick_watch_commune, run_watch

from support import healthy_handlers

COMMUNE = "030502"


async def _synced(repo, make_pipeline):
    pipeline = make_pipeline(repo, healthy_handlers())
    await pipeline.sync()
    return pipeline


async def test_watch_run_creates_pending_approval_with_tool_trace(repo, make_pipeline):
    pipeline = await _synced(repo, make_pipeline)
    scripted = ScriptedLLM(
        [
            StepResult(calls=[("get_commune_evidence", {"commune_id": COMMUNE})]),
            StepResult(text="The station is above the alarm stage; review the flood draft."),
        ]
    )

    run = await run_watch(pipeline, COMMUNE, llm=scripted)

    assert run.status is AgentRunStatus.PENDING_APPROVAL
    assert run.draft_khmer
    assert "review" in run.rationale.lower()
    assert any(call["name"] == "get_commune_evidence" for call in run.tool_calls)
    assert run.published_at is None and run.published_message_id is None

    stored = await repo.get_agent_run(run.id)
    assert stored is not None and stored.id == run.id
    assert (await repo.list_agent_runs())[0].id == run.id


async def test_watch_run_keeps_draft_when_agent_is_unavailable(repo, make_pipeline):
    pipeline = await _synced(repo, make_pipeline)

    class FailingLLM:
        async def step(self, contents):
            raise AdvisorUnavailable("provider unavailable")

    run = await run_watch(pipeline, COMMUNE, llm=FailingLLM())

    assert run.status is AgentRunStatus.PENDING_APPROVAL
    assert "provider unavailable" in (run.error or "")
    assert run.draft_khmer  # deterministic draft remains reviewable
    assert run.tool_calls == []


async def test_pick_watch_commune_returns_a_scored_commune(repo, make_pipeline):
    pipeline = await _synced(repo, make_pipeline)
    code = await pick_watch_commune(pipeline)
    assert code in {risk.commune_code for risk in await repo.risk_map()}
