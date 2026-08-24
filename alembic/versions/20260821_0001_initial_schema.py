"""initial schema

Revision ID: 20260821_0001
Revises:
Create Date: 2026-08-21 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260821_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("auth_provider", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "games",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("lobby_id", sa.String(), nullable=False),
        sa.Column("workplace", sa.String(), nullable=True),
        sa.Column("winner", sa.String(), nullable=False),
        sa.Column("spy_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("guessed_workplace", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "game_players",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("game_id", sa.Integer(), sa.ForeignKey("games.id"), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("is_winner", sa.Boolean(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("game_players")
    op.drop_table("games")
    op.drop_table("users")
