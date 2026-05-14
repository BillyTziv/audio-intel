"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

job_status = sa.Enum(
    "pending", "queued", "validating", "converting", "chunking",
    "transcribing", "summarizing", "completed", "failed",
    name="job_status",
)
chunk_status = sa.Enum("pending", "processing", "done", "failed", name="chunk_status")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(120), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("is_admin", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    job_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "audio_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("stored_filename", sa.String(512), nullable=False),
        sa.Column("file_path", sa.String(1024), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=True),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("duration_seconds", sa.Float, nullable=True),
        sa.Column("status", job_status, nullable=False, server_default="pending"),
        sa.Column("progress", sa.Float, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_audio_jobs_user_id", "audio_jobs", ["user_id"])
    op.create_index("ix_audio_jobs_status", "audio_jobs", ["status"])
    op.create_index("ix_audio_jobs_created_at", "audio_jobs", ["created_at"])

    chunk_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "audio_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("audio_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("index", sa.Integer, nullable=False),
        sa.Column("start_seconds", sa.Float, nullable=False),
        sa.Column("end_seconds", sa.Float, nullable=False),
        sa.Column("file_path", sa.String(1024), nullable=False),
        sa.Column("status", chunk_status, nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audio_chunks_job_id", "audio_chunks", ["job_id"])

    op.create_table(
        "transcripts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("audio_jobs.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("language", sa.String(16), nullable=True),
        sa.Column("raw_text", sa.Text, nullable=True),
        sa.Column("cleaned_text", sa.Text, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("key_points", postgresql.JSONB, nullable=True),
        sa.Column("decisions", postgresql.JSONB, nullable=True),
        sa.Column("action_items", postgresql.JSONB, nullable=True),
        sa.Column("segments", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_transcripts_job_id", "transcripts", ["job_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_transcripts_job_id", table_name="transcripts")
    op.drop_table("transcripts")
    op.drop_index("ix_audio_chunks_job_id", table_name="audio_chunks")
    op.drop_table("audio_chunks")
    op.drop_index("ix_audio_jobs_created_at", table_name="audio_jobs")
    op.drop_index("ix_audio_jobs_status", table_name="audio_jobs")
    op.drop_index("ix_audio_jobs_user_id", table_name="audio_jobs")
    op.drop_table("audio_jobs")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
    chunk_status.drop(op.get_bind(), checkfirst=True)
    job_status.drop(op.get_bind(), checkfirst=True)
