MIGRATION_SQLITE_SCHEMA=r'''
CREATE TABLE import_batches(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,kind TEXT NOT NULL,pack_version INTEGER NOT NULL,source_system TEXT NOT NULL,source_hash TEXT NOT NULL,row_count INTEGER NOT NULL,control_total_minor INTEGER NOT NULL,status TEXT NOT NULL CHECK(status IN ('validated','rejected','imported','reconciled','variance')),errors_json TEXT NOT NULL,created_by TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(workspace_id,kind,source_hash));
'''
