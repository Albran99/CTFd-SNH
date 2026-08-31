"""Retain reviewed writeups when students submit a revision

Revision ID: 0004_writeup_revisions
Revises: 0003_normalize_discussion_post_type
Create Date: 2026-08-31 00:00:00.000000
"""
import sqlalchemy as sa

from CTFd.plugins.migrations import get_all_tables


revision = "0004_writeup_revisions"
down_revision = "0003_normalize_discussion_post_type"
branch_labels = None
depends_on = None


def upgrade(op=None):
    tables = get_all_tables(op)
    if "writeup_revisions" in tables:
        return

    op.create_table(
        "writeup_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("submission_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("review_snapshot", sa.JSON(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["submission_id"], ["writeup_submissions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_writeup_revisions_submission_id",
        "writeup_revisions",
        ["submission_id"],
    )


def downgrade(op=None):
    op.drop_index("ix_writeup_revisions_submission_id", table_name="writeup_revisions")
    op.drop_table("writeup_revisions")
