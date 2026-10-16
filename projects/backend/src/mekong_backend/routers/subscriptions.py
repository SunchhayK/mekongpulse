"""Subscription management (dashboard/admin surface over FR-06 records)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from mekong_shared.models import CropStage, Subscription
from mekong_shared.pipeline import CommuneNotFound

router = APIRouter(prefix="/api/v1/subscriptions", tags=["subscriptions"])


class SubscriptionRequest(BaseModel):
    chat_id: str
    commune_code: str
    crop_stage: CropStage | None = None


@router.get("")
async def list_subscriptions(request: Request, chat_id: str) -> list[Subscription]:
    repo = request.app.state.repo
    return await repo.subscriptions_for_chat(chat_id)


@router.post("", status_code=201)
async def create_subscription(body: SubscriptionRequest, request: Request) -> Subscription:
    repo = request.app.state.repo
    commune = await repo.get_commune(body.commune_code)
    if commune is None:
        raise CommuneNotFound(body.commune_code)
    return await repo.upsert_subscription(
        body.chat_id, body.commune_code, body.crop_stage.value if body.crop_stage else None
    )


@router.delete("/{chat_id}/{commune_code}")
async def delete_subscription(chat_id: str, commune_code: str, request: Request) -> dict:
    repo = request.app.state.repo
    removed = await repo.remove_subscription(chat_id, commune_code)
    if not removed:
        return {"removed": False}
    return {"removed": True}
