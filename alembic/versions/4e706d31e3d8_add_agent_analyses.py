"""add agent analyses

Revision ID: 4e706d31e3d8
Revises: 2d2cf1d3f3e2
Create Date: 2026-05-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4e706d31e3d8"
down_revision: Union[str, None] = "2d2cf1d3f3e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "agent_analyses" not in inspector.get_table_names():
        op.create_table(
            "agent_analyses",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("profile_id", sa.Integer(), nullable=False),
            sa.Column("provider", sa.String(length=50), nullable=False),
            sa.Column("overall_score", sa.Integer(), nullable=False),
            sa.Column("result_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    indexes = {item["name"] for item in inspector.get_indexes("agent_analyses")}
    if op.f("ix_agent_analyses_id") not in indexes:
        op.create_index(op.f("ix_agent_analyses_id"), "agent_analyses", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_analyses_id"), table_name="agent_analyses")
    op.drop_table("agent_analyses")
