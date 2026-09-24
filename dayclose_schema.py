DAYCLOSE_SQLITE_SCHEMA = """
CREATE TABLE day_closes(
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    close_date TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    counted_cash_minor INTEGER NOT NULL,
    difference_minor INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    actor_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(workspace_id, close_date)
);
"""
