"""recording metadata: title, project, description, meeting_date, participants

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audio_jobs", sa.Column("title", sa.String(length=512), nullable=True))
    op.add_column("audio_jobs", sa.Column("project", sa.String(length=255), nullable=True))
    op.add_column("audio_jobs", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("audio_jobs", sa.Column("meeting_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "audio_jobs",
        sa.Column("participants", postgresql.ARRAY(sa.Text()), nullable=True),
    )
    op.create_index("ix_audio_jobs_project", "audio_jobs", ["project"])


def downgrade() -> None:
    op.drop_index("ix_audio_jobs_project", table_name="audio_jobs")
    op.drop_column("audio_jobs", "participants")
    op.drop_column("audio_jobs", "meeting_date")
    op.drop_column("audio_jobs", "description")
    op.drop_column("audio_jobs", "project")
    op.drop_column("audio_jobs", "title")
