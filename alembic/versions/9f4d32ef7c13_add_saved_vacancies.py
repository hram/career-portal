"""add saved vacancies

Revision ID: 9f4d32ef7c13
Revises: 70cb8260820f
Create Date: 2026-05-21 14:40:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9f4d32ef7c13"
down_revision: Union[str, None] = "70cb8260820f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "saved_vacancies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("hh_id", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("area_name", sa.String(length=255), nullable=True),
        sa.Column("salary_text", sa.String(length=255), nullable=True),
        sa.Column("vacancy_url", sa.String(length=500), nullable=True),
        sa.Column("api_url", sa.String(length=500), nullable=True),
        sa.Column("published_at", sa.String(length=100), nullable=True),
        sa.Column("description_text", sa.Text(), nullable=True),
        sa.Column("raw_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_saved_vacancies_hh_id"), "saved_vacancies", ["hh_id"], unique=False)
    op.create_index(op.f("ix_saved_vacancies_id"), "saved_vacancies", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_saved_vacancies_id"), table_name="saved_vacancies")
    op.drop_index(op.f("ix_saved_vacancies_hh_id"), table_name="saved_vacancies")
    op.drop_table("saved_vacancies")
