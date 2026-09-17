"""Versioned layperson onboarding sessions."""
ONBOARDING_SQLITE_SCHEMA=r'''
CREATE TABLE onboarding_sessions(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,schema_version INTEGER NOT NULL,status TEXT NOT NULL CHECK(status IN ('in_progress','needs_review','ready','applied')),answers_json TEXT NOT NULL DEFAULT '{}',inference_json TEXT NOT NULL DEFAULT '{}',contradictions_json TEXT NOT NULL DEFAULT '[]',current_question TEXT,created_by TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
'''
