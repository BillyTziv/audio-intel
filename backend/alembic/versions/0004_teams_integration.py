"""teams integration: microsoft_accounts table + teams metadata on audio_jobs

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "microsoft_accounts",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("ms_user_id", sa.String(length=255), nullable=False),
        sa.Column("ms_display_name", sa.String(length=255), nullable=True),
        sa.Column("ms_user_principal_name", sa.String(length=255), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.add_column("audio_jobs", sa.Column("source", sa.String(length=40), nullable=True))
    op.add_column("audio_jobs", sa.Column("source_meeting_id", sa.String(length=255), nullable=True))
    op.add_column("audio_jobs", sa.Column("teams_transcript_vtt", sa.Text(), nullable=True))
    op.create_index("ix_audio_jobs_source_meeting_id", "audio_jobs", ["source_meeting_id"])


def downgrade() -> None:
    op.drop_index("ix_audio_jobs_source_meeting_id", table_name="audio_jobs")
    op.drop_column("audio_jobs", "teams_transcript_vtt")
    op.drop_column("audio_jobs", "source_meeting_id")
    op.drop_column("audio_jobs", "source")
    op.drop_table("microsoft_accounts")
