from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class FollowRequestCreate(BaseModel):
    target_id: uuid.UUID


class FollowRequestOut(BaseModel):
    id: uuid.UUID
    requester_id: uuid.UUID
    requester_name: str
    requester_handle: str | None
    target_id: uuid.UUID
    target_name: str
    target_handle: str | None
    status: str
    created_at: datetime
    responded_at: datetime | None

    model_config = {"from_attributes": True}


class ConnectionOut(BaseModel):
    user_id: uuid.UUID
    full_name: str
    public_handle: str | None
    avatar_url: str | None
    connected_since: datetime


class PersonSearchResultOut(BaseModel):
    user_id: uuid.UUID
    full_name: str
    public_handle: str | None
    avatar_url: str | None
    # From the searching user's point of view: none|pending_outgoing|pending_incoming|connected
    relationship: str
