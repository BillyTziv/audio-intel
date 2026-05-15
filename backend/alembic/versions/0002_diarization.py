"""diarization toggle, speakers, and diarizing status

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE job_status ADD VALUE IF NOT EXISTS 'diarizing' BEFORE 'summarizing'")

    op.add_column(
        "audio_jobs",
        sa.Column("diarize", sa.Boolean, nullable=False, server_default=sa.false()),
    )

    op.add_column(
        "transcripts",
        sa.Column("speakers", postgresql.JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transcripts", "speakers")
    op.drop_column("audio_jobs", "diarize")
    # Postgres does not support removing enum values without rebuilding the type;
    # leaving 'diarizing' in place is harmless.
