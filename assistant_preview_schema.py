ASSISTANT_PREVIEW_SQLITE_SCHEMA=r'''
CREATE TABLE assistant_action_drafts(
 id TEXT PRIMARY KEY,
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 kind TEXT NOT NULL,
 payload_json TEXT NOT NULL,
 payload_hash TEXT NOT NULL,
 rendered_text TEXT NOT NULL,
 risk TEXT NOT NULL CHECK(risk IN ('standard','high')),
 approval_mode TEXT NOT NULL CHECK(approval_mode IN ('confirm','approve_once')) DEFAULT 'confirm',
 status TEXT NOT NULL CHECK(status IN ('pending','executed','cancelled','expired')) DEFAULT 'pending',
 created_by TEXT NOT NULL,
 created_at TEXT NOT NULL,
 expires_at TEXT NOT NULL,
 resolved_by TEXT NOT NULL DEFAULT '',
 resolved_at TEXT NOT NULL DEFAULT '',
 result_json TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_assistant_drafts_ws ON assistant_action_drafts(workspace_id,status);
'''
