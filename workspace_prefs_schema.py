WORKSPACE_PREFS_SQLITE_SCHEMA = """
CREATE TABLE workspace_prefs(
    workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
    timezone TEXT NOT NULL DEFAULT ''
);
"""
