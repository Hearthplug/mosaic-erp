AI_PREFS_SQLITE_SCHEMA=r'''
CREATE TABLE ai_answer_prefs(
 workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
 provider TEXT NOT NULL CHECK(provider IN ('standard','jev','openai','claude','deepseek')) DEFAULT 'standard',
 key_ref TEXT NOT NULL DEFAULT '',
 updated_by TEXT NOT NULL, updated_at TEXT NOT NULL
);
'''
