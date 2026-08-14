"""add missing performance indexes

Revision ID: c4a91f7d0e2b
Revises: 31e4fc98f4cf
Create Date: 2026-08-14 11:40:00.000000

Real, query-pattern-justified indexes found during a full model-vs-query
audit (this codebase is otherwise already thoroughly indexed — see
aedd5b33915f's composite attempt-lookup indexes and the many index=True
columns already on every model). Every index below is backed by an actual
`.where()`/`.order_by()` clause found in the API/service layer, not a
blanket pass:

- ix_courses_instructor_id (courses.instructor_id): GET /courses with
  published_only=false filters `Course.instructor_id == user.id` for an
  instructor browsing their own drafts (courses.py::list_courses). Was
  entirely unindexed before this.
- ix_courses_published_deleted (courses.is_published, courses.deleted_at):
  the default/public course-catalog query (`published_only=true`, the
  overwhelmingly common case, and the one just wired up with Redis caching
  in this same change) filters on both columns together on every cache
  miss; every other course query also filters `deleted_at IS NULL`.
- ix_chat_messages_room_created (chat_messages.room_id, chat_messages.
  created_at): list_messages (chat.py) filters by room_id, optionally adds
  `created_at < :before` for cursor pagination, and always orders by
  created_at desc — the existing single-column room_id index alone forces
  a sort of every message in a room on each page.
- ix_notifications_user_created (notifications.user_id, notifications.
  created_at): GET /notifications (notifications.py) filters by user_id and
  orders by created_at desc on every load of the notification bell.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c4a91f7d0e2b'
down_revision: Union[str, None] = '31e4fc98f4cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_courses_instructor_id', 'courses', ['instructor_id'], unique=False)
    op.create_index('ix_courses_published_deleted', 'courses', ['is_published', 'deleted_at'], unique=False)
    op.create_index('ix_chat_messages_room_created', 'chat_messages', ['room_id', 'created_at'], unique=False)
    op.create_index('ix_notifications_user_created', 'notifications', ['user_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_notifications_user_created', table_name='notifications')
    op.drop_index('ix_chat_messages_room_created', table_name='chat_messages')
    op.drop_index('ix_courses_published_deleted', table_name='courses')
    op.drop_index('ix_courses_instructor_id', table_name='courses')
