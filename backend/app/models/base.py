from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPk:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# NOTE: deletion in this codebase is hard-delete by design — the GDPR erasure
# path in gdpr_service really removes rows, which is the behaviour that policy
# requires. The two exceptions (User.deleted_at, Course.deleted_at) are
# deliberate per-model deactivation flags, not a general soft-delete scheme, and
# they declare their own column.
#
# A SoftDeleteMixin used to live here but was inherited by nothing, which
# implied a repo-wide soft-delete convention that does not exist and invited new
# models to opt into a filter no query applies. It was removed rather than
# retrofitted; reintroduce it only alongside a query-level filter that actually
# excludes deleted rows, otherwise "deleted" records stay visible.
