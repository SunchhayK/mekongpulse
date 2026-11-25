"""Durable task queue abstraction for async watch runs and alert fan-out (IMP-02).

Uses Google Cloud Tasks in production when `cloud_tasks_queue` is configured,
with an idempotent in-process `LocalTaskQueue` fallback for dev/tests.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

from .config import Settings
from .logging_utils import log_event

log = logging.getLogger("mekongpulse.tasks")

_SAFE_TASK_ID_RE = re.compile(r"[^A-Za-z0-9_-]+")


def _task_id_from_dedup_key(prefix: str, dedup_key: str) -> str:
    """Deterministic Cloud Tasks-compatible task id (letters, digits, _, -)."""
    digest = hashlib.sha256(dedup_key.encode("utf-8")).hexdigest()[:24]
    clean_prefix = _SAFE_TASK_ID_RE.sub("-", prefix).strip("-") or "task"
    return f"{clean_prefix}-{digest}"


@dataclass(frozen=True)
class EnqueuedTask:
    task_id: str
    queue: str
    url: str
    payload: dict[str, Any]
    deduplicated: bool = False


class TaskQueue(Protocol):
    async def enqueue_watch_run(
        self,
        commune_code: str,
        trigger: str,
        previous_tier: str | None,
        dedup_key: str,
    ) -> EnqueuedTask: ...

    async def enqueue_dispatch_batch(
        self,
        alert_payload: dict[str, Any],
        chat_ids: list[str],
        dedup_key: str,
    ) -> EnqueuedTask: ...


WatchHandler = Callable[[str, str, str | None], Awaitable[Any]]
DispatchBatchHandler = Callable[[dict[str, Any], list[str]], Awaitable[Any]]


@dataclass
class LocalTaskQueue:
    """In-process fallback queue with deduplication and optional immediate handlers."""

    watch_handler: WatchHandler | None = None
    dispatch_handler: DispatchBatchHandler | None = None
    enqueued: list[EnqueuedTask] = field(default_factory=list)
    _seen_ids: set[str] = field(default_factory=set, init=False, repr=False)

    async def enqueue_watch_run(
        self,
        commune_code: str,
        trigger: str,
        previous_tier: str | None,
        dedup_key: str,
    ) -> EnqueuedTask:
        task_id = _task_id_from_dedup_key("watch", dedup_key)
        payload = {
            "commune_code": commune_code,
            "trigger": trigger,
            "previous_tier": previous_tier,
            "dedup_key": dedup_key,
        }
        if task_id in self._seen_ids:
            return EnqueuedTask(
                task_id=task_id,
                queue="local-watch",
                url="/internal/tasks/watch-run",
                payload=payload,
                deduplicated=True,
            )
        self._seen_ids.add(task_id)
        task = EnqueuedTask(
            task_id=task_id,
            queue="local-watch",
            url="/internal/tasks/watch-run",
            payload=payload,
            deduplicated=False,
        )
        self.enqueued.append(task)
        if self.watch_handler is not None:
            await self.watch_handler(commune_code, trigger, previous_tier)
        return task

    async def enqueue_dispatch_batch(
        self,
        alert_payload: dict[str, Any],
        chat_ids: list[str],
        dedup_key: str,
    ) -> EnqueuedTask:
        task_id = _task_id_from_dedup_key("dispatch", dedup_key)
        payload = {
            "alert": alert_payload,
            "chat_ids": list(chat_ids),
            "dedup_key": dedup_key,
        }
        if task_id in self._seen_ids:
            return EnqueuedTask(
                task_id=task_id,
                queue="local-dispatch",
                url="/internal/tasks/dispatch-batch",
                payload=payload,
                deduplicated=True,
            )
        self._seen_ids.add(task_id)
        task = EnqueuedTask(
            task_id=task_id,
            queue="local-dispatch",
            url="/internal/tasks/dispatch-batch",
            payload=payload,
            deduplicated=False,
        )
        self.enqueued.append(task)
        if self.dispatch_handler is not None:
            await self.dispatch_handler(alert_payload, list(chat_ids))
        return task


class CloudTasksQueue:
    """Google Cloud Tasks HTTP queue with idempotent task names and OIDC auth."""

    def __init__(
        self,
        *,
        project: str,
        location: str,
        watch_queue: str,
        dispatch_queue: str,
        target_base_url: str,
        service_account_email: str | None = None,
        audience: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._project = project
        self._location = location
        self._watch_queue = watch_queue
        self._dispatch_queue = dispatch_queue
        self._target_base_url = target_base_url.rstrip("/")
        self._service_account_email = service_account_email
        self._audience = audience or self._target_base_url
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            from google.cloud import tasks_v2  # type: ignore[import-untyped]

            self._client = tasks_v2.CloudTasksClient()
        return self._client

    def _queue_path(self, queue_name: str) -> str:
        if queue_name.startswith("projects/"):
            return queue_name
        return f"projects/{self._project}/locations/{self._location}/queues/{queue_name}"

    async def _create_http_task(
        self,
        *,
        queue_name: str,
        path: str,
        task_id: str,
        payload: dict[str, Any],
    ) -> EnqueuedTask:
        parent = self._queue_path(queue_name)
        url = f"{self._target_base_url}/{path.lstrip('/')}"
        http_request: dict[str, Any] = {
            "http_method": "POST",
            "url": url,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        }
        if self._service_account_email:
            http_request["oidc_token"] = {
                "service_account_email": self._service_account_email,
                "audience": self._audience,
            }
        task_spec = {
            "name": f"{parent}/tasks/{task_id}",
            "http_request": http_request,
        }

        def _submit() -> bool:
            client = self._get_client()
            try:
                client.create_task(request={"parent": parent, "task": task_spec})
                return False
            except Exception as exc:  # noqa: BLE001 - AlreadyExists means idempotent dedup
                if type(exc).__name__ == "AlreadyExists" or "ALREADY_EXISTS" in str(exc).upper():
                    return True
                raise

        deduplicated = await asyncio.to_thread(_submit)
        log_event(
            log,
            "CLOUD_TASK_ENQUEUED",
            queue=queue_name,
            task_id=task_id,
            url=url,
            deduplicated=deduplicated,
        )
        return EnqueuedTask(
            task_id=task_id,
            queue=queue_name,
            url=url,
            payload=payload,
            deduplicated=deduplicated,
        )

    async def enqueue_watch_run(
        self,
        commune_code: str,
        trigger: str,
        previous_tier: str | None,
        dedup_key: str,
    ) -> EnqueuedTask:
        task_id = _task_id_from_dedup_key("watch", dedup_key)
        payload = {
            "commune_code": commune_code,
            "trigger": trigger,
            "previous_tier": previous_tier,
            "dedup_key": dedup_key,
        }
        return await self._create_http_task(
            queue_name=self._watch_queue,
            path="/internal/tasks/watch-run",
            task_id=task_id,
            payload=payload,
        )

    async def enqueue_dispatch_batch(
        self,
        alert_payload: dict[str, Any],
        chat_ids: list[str],
        dedup_key: str,
    ) -> EnqueuedTask:
        task_id = _task_id_from_dedup_key("dispatch", dedup_key)
        payload = {
            "alert": alert_payload,
            "chat_ids": list(chat_ids),
            "dedup_key": dedup_key,
        }
        return await self._create_http_task(
            queue_name=self._dispatch_queue,
            path="/internal/tasks/dispatch-batch",
            task_id=task_id,
            payload=payload,
        )


def create_task_queue(
    settings: Settings,
    *,
    watch_handler: WatchHandler | None = None,
    dispatch_handler: DispatchBatchHandler | None = None,
) -> TaskQueue:
    """Return CloudTasksQueue when configured, otherwise LocalTaskQueue."""
    watch_queue = getattr(settings, "cloud_tasks_queue", None)
    project = (
        getattr(settings, "cloud_tasks_project", None)
        or settings.vertex_project
        or settings.firestore_project
    )
    location = getattr(settings, "cloud_tasks_location", None) or settings.vertex_location
    if watch_queue and project:
        dispatch_queue = getattr(settings, "cloud_tasks_dispatch_queue", None) or watch_queue
        return CloudTasksQueue(
            project=project,
            location=location,
            watch_queue=watch_queue,
            dispatch_queue=dispatch_queue,
            target_base_url=settings.public_base_url,
            service_account_email=getattr(settings, "cloud_tasks_service_account", None),
            audience=getattr(settings, "oidc_audience", None) or settings.public_base_url,
        )
    return LocalTaskQueue(
        watch_handler=watch_handler,
        dispatch_handler=dispatch_handler,
    )
