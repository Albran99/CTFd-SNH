"""Create challenge_discussion_posts table

Revision ID: 0001_challenge_discussion
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
import sqlalchemy as sa

from CTFd.plugins.migrations import get_all_tables

revision = "0001_challenge_discussion"
down_revision = None
branch_labels = None
depends_on = None


def upgrade(op=None):
    tables = get_all_tables(op)
    if "challenge_discussion_posts" in tables:
        return

    op.create_table(
        "challenge_discussion_posts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("challenge_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("post_type", sa.String(length=16), nullable=False, server_default="discussion"),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("date", sa.DateTime(), nullable=True),
        sa.Column("hidden", sa.Boolean(), nullable=True, server_default="0"),
        sa.ForeignKeyConstraint(["challenge_id"], ["challenges.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["challenge_discussion_posts.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_challenge_discussion_challenge_id",
        "challenge_discussion_posts",
        ["challenge_id"],
    )
    op.create_index(
        "ix_challenge_discussion_user_id",
        "challenge_discussion_posts",
        ["user_id"],
    )


def downgrade(op=None):
    op.drop_index("ix_challenge_discussion_user_id", table_name="challenge_discussion_posts")
    op.drop_index("ix_challenge_discussion_challenge_id", table_name="challenge_discussion_posts")
    op.drop_table("challenge_discussion_posts")
