"""Durable TaskQueue tests: LocalTaskQueue, CloudTasksQueue, idempotent dedup (IMP-02)."""

from __future__ import annotations

import json

from mekong_shared.config import Settings
from mekong_shared.tasks import CloudTasksQueue, LocalTaskQueue, create_task_queue


async def test_local_task_queue_deduplicates_and_invokes_handlers():
    watched: list[tuple[str, str, str | None]] = []
    dispatched: list[tuple[dict, list[str]]] = []

    async def on_watch(commune_code: str, trigger: str, previous_tier: str | None) -> None:
        watched.append((commune_code, trigger, previous_tier))

    async def on_dispatch(alert_payload: dict, chat_ids: list[str]) -> None:
        dispatched.append((alert_payload, chat_ids))

    queue = LocalTaskQueue(watch_handler=on_watch, dispatch_handler=on_dispatch)

    t1 = await queue.enqueue_watch_run("080404", "transition", "NORMAL", "patrol:1:080404:WARNING")
    t2 = await queue.enqueue_watch_run("080404", "transition", "NORMAL", "patrol:1:080404:WARNING")
    assert t1.deduplicated is False
    assert t2.deduplicated is True
    assert t1.task_id == t2.task_id
    assert watched == [("080404", "transition", "NORMAL")]

    d1 = await queue.enqueue_dispatch_batch(
        {"commune_id": "080404", "risk_tier": "WARNING"},
        ["111", "222"],
        "dispatch:1:080404:batch0",
    )
    d2 = await queue.enqueue_dispatch_batch(
        {"commune_id": "080404", "risk_tier": "WARNING"},
        ["111", "222"],
        "dispatch:1:080404:batch0",
    )
    assert d1.deduplicated is False
    assert d2.deduplicated is True
    assert len(dispatched) == 1
    assert dispatched[0][1] == ["111", "222"]


async def test_cloud_tasks_queue_submits_oidc_http_task_and_handles_already_exists():
    class AlreadyExists(Exception):
        pass

    class FakeCloudTasksClient:
        def __init__(self) -> None:
            self.requests: list[dict] = []
            self._seen: set[str] = set()

        def create_task(self, *, request: dict):
            name = request["task"]["name"]
            if name in self._seen:
                raise AlreadyExists("ALREADY_EXISTS")
            self._seen.add(name)
            self.requests.append(request)
            return request["task"]

    fake = FakeCloudTasksClient()
    queue = CloudTasksQueue(
        project="ai-builder-cup-9f8cd",
        location="asia-southeast1",
        watch_queue="mekongpulse-watch",
        dispatch_queue="mekongpulse-dispatch",
        target_base_url="https://api.mekongpulse.test",
        service_account_email="tasks@ai-builder-cup-9f8cd.iam.gserviceaccount.com",
        client=fake,
    )

    first = await queue.enqueue_watch_run("080404", "transition", "WARNING", "key-1")
    dup = await queue.enqueue_watch_run("080404", "transition", "WARNING", "key-1")
    assert first.deduplicated is False
    assert dup.deduplicated is True
    assert len(fake.requests) == 1

    req = fake.requests[0]
    assert req["parent"] == "projects/ai-builder-cup-9f8cd/locations/asia-southeast1/queues/mekongpulse-watch"
    http_req = req["task"]["http_request"]
    assert http_req["url"] == "https://api.mekongpulse.test/internal/tasks/watch-run"
    assert http_req["oidc_token"]["service_account_email"] == "tasks@ai-builder-cup-9f8cd.iam.gserviceaccount.com"
    assert json.loads(http_req["body"].decode("utf-8"))["commune_code"] == "080404"

    batch = await queue.enqueue_dispatch_batch({"commune_id": "080404"}, ["101", "102"], "batch-1")
    assert batch.deduplicated is False
    assert fake.requests[1]["parent"].endswith("/queues/mekongpulse-dispatch")


def test_create_task_queue_falls_back_to_local_without_config(tmp_path):
    settings = Settings(
        _env_file=None,
        environment="development",
        data_dir=tmp_path,
        audio_dir=tmp_path / "audio",
    )
    queue = create_task_queue(settings)
    assert isinstance(queue, LocalTaskQueue)
