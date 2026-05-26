"""add hh search query to roles

Revision ID: c1a6b9d4e2f0
Revises: 9f4d32ef7c13
Create Date: 2026-05-21 22:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1a6b9d4e2f0"
down_revision: Union[str, None] = "9f4d32ef7c13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("resume_templates", sa.Column("hh_search_query", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("resume_templates", "hh_search_query")
