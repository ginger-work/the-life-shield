"""Phase 2 — Credit Bureau Integration & Dispute System

Creates all tables needed for:
- Credit reports (credit_reports, credit_report_snapshots)
- Tradelines and inquiries
- Dispute cases, letters, bureau responses
- Audit trail (FCRA compliance)
- Compliance events (escalation, human takeover)
- Documents
- Appointments and group sessions

Revision ID: 002_phase2
Revises: None (base schema assumed already applied via docker/postgres/init.sql)
Create Date: 2026-04-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_phase2"
down_revision: Union[str, None] = None  # Update to "001_..." if a prior migration exists
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ──────────────────────────────────────────────────────
    # ENUMS
    # ──────────────────────────────────────────────────────
    # Create all enums first (PostgreSQL requires them before table creation)

    op.execute("CREATE TYPE IF NOT EXISTS bureau_name_enum AS ENUM ('equifax', 'experian', 'transunion', 'innovis')")
    op.execute("CREATE TYPE IF NOT EXISTS tradeline_status_enum AS ENUM ('current', 'late_30', 'late_60', 'late_90', 'charge_off', 'collection', 'paid', 'closed', 'transferred', 'disputed')")
    op.execute("CREATE TYPE IF NOT EXISTS dispute_reason_enum AS ENUM ('inaccurate', 'incomplete', 'unverifiable', 'obsolete', 'fraudulent', 'not_mine', 'wrong_balance', 'wrong_status', 'duplicate')")
    op.execute("CREATE TYPE IF NOT EXISTS dispute_status_enum AS ENUM ('pending_approval', 'approved', 'pending_filing', 'filed', 'investigating', 'responded', 'resolved', 'rejected', 'withdrawn')")
    op.execute("CREATE TYPE IF NOT EXISTS bureau_response_type_enum AS ENUM ('removed', 'updated', 'verified', 'reinvestigation', 'deleted', 'no_response')")
    op.execute("CREATE TYPE IF NOT EXISTS bureau_response_type_enum2 AS ENUM ('removed', 'updated', 'verified', 'reinvestigation', 'deleted', 'no_response')")
    op.execute("CREATE TYPE IF NOT EXISTS letter_status_enum AS ENUM ('draft', 'pending_compliance', 'pending_human_approval', 'approved', 'revision_requested', 'filed', 'archived')")
    op.execute("CREATE TYPE IF NOT EXISTS audit_action_enum AS ENUM ("
               "'auth.login', 'auth.logout', 'auth.failed', 'auth.token_refresh', "
               "'client.created', 'client.updated', 'client.deleted', 'client.viewed', "
               "'credit.report.pull_requested', 'credit.report.pulled', 'credit.report.stored', "
               "'credit.report.viewed', 'credit.report.failed', "
               "'dispute.created', 'dispute.letter.generated', 'dispute.letter.compliance_checked', "
               "'dispute.letter.approved', 'dispute.letter.rejected', 'dispute.filed', "
               "'dispute.status_updated', 'dispute.response_received', 'dispute.resolved', 'dispute.withdrawn', "
               "'webhook.received', 'webhook.processed', 'webhook.failed', "
               "'admin.viewed_client', 'admin.override', "
               "'compliance.flag_raised', 'compliance.cleared')")
    op.execute("CREATE TYPE IF NOT EXISTS escalation_reason_enum AS ENUM ('compliance_flag', 'human_requested', 'sensitive_topic', 'dispute_review', 'fraud_suspected', 'system_error', 'high_value_decision', 'complaint_received')")
    op.execute("CREATE TYPE IF NOT EXISTS escalation_status_enum AS ENUM ('open', 'assigned', 'in_review', 'resolved', 'dismissed')")
    op.execute("CREATE TYPE IF NOT EXISTS document_type_enum AS ENUM ('credit_report', 'dispute_letter', 'bureau_response', 'id_verification', 'proof_of_filing', 'contract', 'consent_form', 'other')")
    op.execute("CREATE TYPE IF NOT EXISTS appointment_type_enum AS ENUM ('onboarding', 'credit_review', 'dispute_review', 'progress_update', 'goal_setting', 'followup')")
    op.execute("CREATE TYPE IF NOT EXISTS appointment_status_enum AS ENUM ('scheduled', 'confirmed', 'in_progress', 'completed', 'cancelled', 'no_show', 'rescheduled')")

    # ──────────────────────────────────────────────────────
    # AUDIT TRAIL (create early — other tables reference it)
    # ──────────────────────────────────────────────────────
    op.create_table(
        "audit_trail",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_type", sa.String(20), nullable=False, server_default="system"),
        sa.Column("subject_type", sa.String(50), nullable=True),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.Enum(name="audit_action_enum"), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("event_data", postgresql.JSON, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("correlation_id", sa.String(36), nullable=True),
        sa.Column("success", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
    )
    op.create_index("ix_audit_trail_client_action", "audit_trail", ["client_id", "action"])
    op.create_index("ix_audit_trail_subject", "audit_trail", ["subject_type", "subject_id"])
    op.create_index("ix_audit_trail_actor_user", "audit_trail", ["actor_user_id", "created_at"])
    op.create_index("ix_audit_trail_created_at", "audit_trail", ["created_at"])

    # ──────────────────────────────────────────────────────
    # CLIENT PROFILES (add credit fields if not exist)
    # ──────────────────────────────────────────────────────
    # Note: client_profiles table created in Phase 1 init.sql
    # We add credit-specific columns here
    op.execute("""
        ALTER TABLE client_profiles
        ADD COLUMN IF NOT EXISTS current_score_equifax INTEGER,
        ADD COLUMN IF NOT EXISTS current_score_experian INTEGER,
        ADD COLUMN IF NOT EXISTS current_score_transunion INTEGER,
        ADD COLUMN IF NOT EXISTS score_goal INTEGER,
        ADD COLUMN IF NOT EXISTS score_updated_at TIMESTAMPTZ
    """)

    # ──────────────────────────────────────────────────────
    # CREDIT REPORTS
    # ──────────────────────────────────────────────────────
    op.create_table(
        "credit_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), onupdate=sa.text("now()"), nullable=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("client_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bureau", sa.Enum(name="bureau_name_enum"), nullable=False),
        sa.Column("pull_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pull_type", sa.String(20), nullable=False, server_default="full"),
        sa.Column("score", sa.Integer, nullable=True),
        sa.Column("score_model", sa.String(50), nullable=True),
        sa.Column("score_range_min", sa.Integer, nullable=True),
        sa.Column("score_range_max", sa.Integer, nullable=True),
        sa.Column("report_reference_number", sa.String(100), nullable=True),
        sa.Column("raw_data_url", sa.String(500), nullable=True),
        sa.Column("parsed_data", postgresql.JSON, nullable=True),
        sa.Column("negative_items_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("inquiries_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tradelines_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("collections_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("api_response_code", sa.String(20), nullable=True),
        sa.Column("api_error_message", sa.Text, nullable=True),
    )
    op.create_index("ix_credit_reports_client_id", "credit_reports", ["client_id"])
    op.create_index("ix_credit_reports_bureau", "credit_reports", ["bureau"])
    op.create_index("ix_credit_reports_pull_date", "credit_reports", ["pull_date"])
    op.create_index("ix_credit_reports_client_bureau_date", "credit_reports", ["client_id", "bureau", "pull_date"])

    # ──────────────────────────────────────────────────────
    # CREDIT REPORT SNAPSHOTS
    # ──────────────────────────────────────────────────────
    op.create_table(
        "credit_report_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("client_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("score_equifax", sa.Integer, nullable=True),
        sa.Column("score_experian", sa.Integer, nullable=True),
        sa.Column("score_transunion", sa.Integer, nullable=True),
        sa.Column("negative_items_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("inquiries_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("collections_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_debt", sa.Numeric(12, 2), nullable=True),
        sa.Column("utilization_percent", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_credit_report_snapshots_client_id", "credit_report_snapshots", ["client_id"])
    op.create_index("ix_credit_report_snapshots_snapshot_date", "credit_report_snapshots", ["snapshot_date"])

    # ──────────────────────────────────────────────────────
    # TRADELINES
    # ──────────────────────────────────────────────────────
    op.create_table(
        "tradelines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("client_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("credit_reports.id", ondelete="SET NULL"), nullable=True),
        sa.Column("bureau", sa.Enum(name="bureau_name_enum"), nullable=False),
        sa.Column("creditor_name", sa.String(255), nullable=False),
        sa.Column("account_number_masked", sa.String(50), nullable=True),
        sa.Column("account_type", sa.String(50), nullable=True),
        sa.Column("balance", sa.Numeric(12, 2), nullable=True),
        sa.Column("credit_limit", sa.Numeric(12, 2), nullable=True),
        sa.Column("original_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("monthly_payment", sa.Numeric(10, 2), nullable=True),
        sa.Column("utilization", sa.Float, nullable=True),
        sa.Column("status", sa.Enum(name="tradeline_status_enum"), nullable=False, server_default="current"),
        sa.Column("payment_history", postgresql.JSON, nullable=True),
        sa.Column("date_opened", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_reported", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_last_active", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_closed", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_disputable", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("dispute_reason", sa.String(200), nullable=True),
        sa.Column("analyst_notes", sa.Text, nullable=True),
    )
    op.create_index("ix_tradelines_client_id", "tradelines", ["client_id"])
    op.create_index("ix_tradelines_report_id", "tradelines", ["report_id"])
    op.create_index("ix_tradelines_client_status", "tradelines", ["client_id", "status"])
    op.create_index("ix_tradelines_disputable", "tradelines", ["client_id", "is_disputable"])

    # ──────────────────────────────────────────────────────
    # INQUIRIES
    # ──────────────────────────────────────────────────────
    op.create_table(
        "inquiries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("client_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("credit_reports.id", ondelete="SET NULL"), nullable=True),
        sa.Column("bureau", sa.Enum(name="bureau_name_enum"), nullable=False),
        sa.Column("inquirer_name", sa.String(255), nullable=False),
        sa.Column("inquiry_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_hard_inquiry", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_disputable", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_duplicate", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_inquiries_client_id", "inquiries", ["client_id"])
    op.create_index("ix_inquiries_inquiry_date", "inquiries", ["inquiry_date"])

    # ──────────────────────────────────────────────────────
    # DISPUTE CASES
    # ──────────────────────────────────────────────────────
    op.create_table(
        "dispute_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("client_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filing_agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tradeline_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tradelines.id", ondelete="SET NULL"), nullable=True),
        sa.Column("bureau", sa.String(20), nullable=False),
        sa.Column("dispute_reason", sa.Enum(name="dispute_reason_enum"), nullable=False),
        sa.Column("item_description", sa.Text, nullable=True),
        sa.Column("creditor_name", sa.String(255), nullable=True),
        sa.Column("account_number_masked", sa.String(50), nullable=True),
        sa.Column("status", sa.Enum(name="dispute_status_enum"), nullable=False, server_default="pending_approval"),
        sa.Column("filed_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expected_response_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_received_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.Enum(name="bureau_response_type_enum"), nullable=True),
        sa.Column("outcome_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("score_impact_points", sa.Integer, nullable=True),
        sa.Column("dispute_letter_url", sa.String(500), nullable=True),
        sa.Column("proof_of_filing_url", sa.String(500), nullable=True),
        sa.Column("priority_score", sa.Integer, nullable=False, server_default="5"),
        sa.Column("analyst_notes", sa.Text, nullable=True),
        sa.Column("admin_notes", sa.Text, nullable=True),
    )
    op.create_index("ix_dispute_cases_client_id", "dispute_cases", ["client_id"])
    op.create_index("ix_dispute_cases_filing_agent_id", "dispute_cases", ["filing_agent_id"])
    op.create_index("ix_dispute_cases_tradeline_id", "dispute_cases", ["tradeline_id"])
    op.create_index("ix_dispute_cases_status", "dispute_cases", ["status"])
    op.create_index("ix_dispute_cases_bureau", "dispute_cases", ["bureau"])
    op.create_index("ix_dispute_cases_client_status", "dispute_cases", ["client_id", "status"])
    op.create_index("ix_dispute_cases_bureau_status", "dispute_cases", ["bureau", "status"])
    op.create_index("ix_dispute_cases_filed_date", "dispute_cases", ["filed_date"])

    # ──────────────────────────────────────────────────────
    # DISPUTE LETTERS
    # ──────────────────────────────────────────────────────
    op.create_table(
        "dispute_letters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("dispute_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("dispute_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("client_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("drafting_agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("letter_content", sa.Text, nullable=False),
        sa.Column("letter_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("compliance_status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("compliance_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("compliance_flags", postgresql.JSON, nullable=True),
        sa.Column("human_approval_required", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("approved_by_admin_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approval_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        sa.Column("status", sa.Enum(name="letter_status_enum"), nullable=False, server_default="draft"),
        sa.Column("ai_model_used", sa.String(100), nullable=True),
        sa.Column("generation_prompt_hash", sa.String(64), nullable=True),
    )
    op.create_index("ix_dispute_letters_dispute_id", "dispute_letters", ["dispute_id"])
    op.create_index("ix_dispute_letters_client_id", "dispute_letters", ["client_id"])
    op.create_index("ix_dispute_letters_status", "dispute_letters", ["status"])
    op.create_index("ix_dispute_letters_compliance", "dispute_letters", ["compliance_status"])

    # ──────────────────────────────────────────────────────
    # BUREAU RESPONSES
    # ──────────────────────────────────────────────────────
    op.create_table(
        "bureau_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("dispute_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("dispute_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("received_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response_type", sa.Enum(name="bureau_response_type_enum2"), nullable=False),
        sa.Column("response_content", sa.Text, nullable=True),
        sa.Column("response_url", sa.String(500), nullable=True),
        sa.Column("score_impact", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_bureau_responses_dispute_id", "bureau_responses", ["dispute_id"])

    # ──────────────────────────────────────────────────────
    # ESCALATION EVENTS
    # ──────────────────────────────────────────────────────
    op.create_table(
        "escalation_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("client_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("triggered_by_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_to_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.Enum(name="escalation_reason_enum"), nullable=False),
        sa.Column("status", sa.Enum(name="escalation_status_enum"), nullable=False, server_default="open"),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("context_data", postgresql.JSON, nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_notes", sa.Text, nullable=True),
    )
    op.create_index("ix_escalation_events_client_id", "escalation_events", ["client_id"])
    op.create_index("ix_escalation_events_status", "escalation_events", ["status"])
    op.create_index("ix_escalation_events_client_status", "escalation_events", ["client_id", "status"])

    # ──────────────────────────────────────────────────────
    # HUMAN TAKEOVERS
    # ──────────────────────────────────────────────────────
    op.create_table(
        "human_takeovers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("client_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("human_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("handback_notes", sa.Text, nullable=True),
    )
    op.create_index("ix_human_takeovers_client_id", "human_takeovers", ["client_id"])
    op.create_index("ix_human_takeovers_is_active", "human_takeovers", ["is_active"])

    # ──────────────────────────────────────────────────────
    # DOCUMENTS
    # ──────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("client_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("document_type", sa.Enum(name="document_type_enum"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("s3_key", sa.String(1000), nullable=False),
        sa.Column("s3_bucket", sa.String(255), nullable=False),
        sa.Column("s3_url", sa.String(2000), nullable=False),
        sa.Column("file_size_bytes", sa.Integer, nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("file_hash", sa.String(64), nullable=True),
        sa.Column("is_encrypted", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_confidential", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_documents_client_id", "documents", ["client_id"])
    op.create_index("ix_documents_client_type", "documents", ["client_id", "document_type"])

    # ──────────────────────────────────────────────────────
    # APPOINTMENTS
    # ──────────────────────────────────────────────────────
    op.create_table(
        "appointments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("client_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("specialist_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("appointment_type", sa.Enum(name="appointment_type_enum"), nullable=False),
        sa.Column("status", sa.Enum(name="appointment_status_enum"), nullable=False, server_default="scheduled"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer, nullable=False, server_default="30"),
        sa.Column("meeting_url", sa.String(500), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
    )
    op.create_index("ix_appointments_client_id", "appointments", ["client_id"])
    op.create_index("ix_appointments_scheduled_at", "appointments", ["scheduled_at"])
    op.create_index("ix_appointments_status", "appointments", ["status"])

    # ──────────────────────────────────────────────────────
    # GROUP SESSIONS
    # ──────────────────────────────────────────────────────
    op.create_table(
        "group_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("session_type", sa.String(50), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer, nullable=False, server_default="60"),
        sa.Column("max_attendees", sa.Integer, nullable=True),
        sa.Column("meeting_url", sa.String(500), nullable=True),
        sa.Column("recording_url", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
    )
    op.create_index("ix_group_sessions_scheduled_at", "group_sessions", ["scheduled_at"])

    # ──────────────────────────────────────────────────────
    # GROUP SESSION ENROLLMENTS
    # ──────────────────────────────────────────────────────
    op.create_table(
        "group_session_enrollments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("client_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("group_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("attended", sa.Boolean, nullable=False, server_default="false"),
    )
    op.create_index("ix_group_session_enrollments_client_id", "group_session_enrollments", ["client_id"])
    op.create_index("ix_group_session_enrollments_session_id", "group_session_enrollments", ["session_id"])


def downgrade() -> None:
    """Drop all Phase 2 tables and enums."""
    # Drop tables in reverse dependency order
    op.drop_table("group_session_enrollments")
    op.drop_table("group_sessions")
    op.drop_table("appointments")
    op.drop_table("documents")
    op.drop_table("human_takeovers")
    op.drop_table("escalation_events")
    op.drop_table("bureau_responses")
    op.drop_table("dispute_letters")
    op.drop_table("dispute_cases")
    op.drop_table("inquiries")
    op.drop_table("tradelines")
    op.drop_table("credit_report_snapshots")
    op.drop_table("credit_reports")
    op.drop_table("audit_trail")

    # Drop enums
    for enum_name in [
        "appointment_status_enum", "appointment_type_enum", "document_type_enum",
        "escalation_status_enum", "escalation_reason_enum", "audit_action_enum",
        "letter_status_enum", "bureau_response_type_enum2", "bureau_response_type_enum",
        "dispute_status_enum", "dispute_reason_enum", "tradeline_status_enum",
        "bureau_name_enum",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
