"""Normalize legacy discussion post_type values

Revision ID: 0003_normalize_discussion_post_type
Revises: 0002_writeup_system
Create Date: 2026-07-06 00:00:00.000000
"""

import sqlalchemy as sa

from CTFd.plugins.migrations import get_all_tables

revision = "0003_normalize_discussion_post_type"
down_revision = "0002_writeup_system"
branch_labels = None
depends_on = None


def upgrade(op=None):
    tables = get_all_tables(op)
    if "challenge_discussion_posts" not in tables:
        return

    op.execute(
        sa.text(
            "UPDATE challenge_discussion_posts "
            "SET post_type = 'general' "
            "WHERE post_type = 'discussion'"
        )
    )


def downgrade(op=None):
    pass
