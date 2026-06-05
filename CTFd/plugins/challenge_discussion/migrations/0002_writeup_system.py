"""Create writeup system tables

Revision ID: 0002_writeup_system
Revises: 0001_challenge_discussion
Create Date: 2026-06-05 00:00:00.000000
"""
import sqlalchemy as sa

from CTFd.plugins.migrations import get_all_tables

revision = "0002_writeup_system"
down_revision = "0001_challenge_discussion"
branch_labels = None
depends_on = None


def upgrade(op=None):
    tables = get_all_tables(op)

    if "writeup_rubric_criteria" not in tables:
        op.create_table(
            "writeup_rubric_criteria",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("max_score", sa.Integer(), nullable=False, server_default="10"),
            sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
            sa.PrimaryKeyConstraint("id"),
        )

    if "writeup_submissions" not in tables:
        op.create_table(
            "writeup_submissions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("challenge_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["challenge_id"], ["challenges.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("challenge_id", "user_id", name="uq_writeup_challenge_user"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_writeup_submissions_challenge_id",
            "writeup_submissions",
            ["challenge_id"],
        )
        op.create_index(
            "ix_writeup_submissions_user_id",
            "writeup_submissions",
            ["user_id"],
        )

    if "writeup_reviews" not in tables:
        op.create_table(
            "writeup_reviews",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("submission_id", sa.Integer(), nullable=False),
            sa.Column("reviewer_id", sa.Integer(), nullable=True),
            sa.Column("scores", sa.JSON(), nullable=False),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("total_score", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_score", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(
                ["submission_id"], ["writeup_submissions.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["reviewer_id"], ["users.id"], ondelete="SET NULL"
            ),
            sa.UniqueConstraint("submission_id", name="uq_writeup_review_submission"),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade(op=None):
    op.drop_table("writeup_reviews")
    op.drop_index("ix_writeup_submissions_user_id", table_name="writeup_submissions")
    op.drop_index("ix_writeup_submissions_challenge_id", table_name="writeup_submissions")
    op.drop_table("writeup_submissions")
    op.drop_table("writeup_rubric_criteria")
