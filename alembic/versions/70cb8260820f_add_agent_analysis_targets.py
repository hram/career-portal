"""add agent analysis targets

Revision ID: 70cb8260820f
Revises: 4e706d31e3d8
Create Date: 2026-05-16 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "70cb8260820f"
down_revision: Union[str, None] = "4e706d31e3d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {item["name"] for item in inspector.get_columns("agent_analyses")}
    if "target_type" not in columns:
        op.add_column(
            "agent_analyses",
            sa.Column("target_type", sa.String(length=50), server_default="profile", nullable=False),
        )
    if "target_id" not in columns:
        op.add_column("agent_analyses", sa.Column("target_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {item["name"] for item in inspector.get_columns("agent_analyses")}
    if "target_id" in columns:
        op.drop_column("agent_analyses", "target_id")
    if "target_type" in columns:
        op.drop_column("agent_analyses", "target_type")
