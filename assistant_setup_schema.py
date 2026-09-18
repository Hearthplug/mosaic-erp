ASSISTANT_SETUP_SQLITE_SCHEMA=r'''
CREATE TABLE assistant_settings(
 workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
 mode TEXT NOT NULL CHECK(mode IN ('deterministic','remote','local')) DEFAULT 'deterministic',
 endpoint TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '', secret_ref TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL CHECK(status IN ('ready','needs_secret','needs_download','unhealthy')) DEFAULT 'ready',
 pending_json TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 1,
 updated_by TEXT NOT NULL, updated_at TEXT NOT NULL
);
'''
