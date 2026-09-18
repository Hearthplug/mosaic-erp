ARTIFACT_BUILDER_SQLITE_SCHEMA=r'''
ALTER TABLE tax_verifications RENAME TO tax_verifications_legacy;
CREATE TABLE tax_verifications(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,jurisdiction TEXT NOT NULL,rules_version TEXT NOT NULL,reviewer_kind TEXT NOT NULL CHECK(reviewer_kind IN ('owner','professional')),reviewer_name TEXT NOT NULL,credentials TEXT NOT NULL DEFAULT '',verified_on TEXT NOT NULL,effective_from TEXT NOT NULL,effective_to TEXT,registration_scope TEXT NOT NULL,supply_scope TEXT NOT NULL,item_classification_basis TEXT NOT NULL,price_basis TEXT NOT NULL CHECK(price_basis IN ('inclusive','exclusive')),rounding_basis TEXT NOT NULL,source_urls_json TEXT NOT NULL,limitations TEXT NOT NULL,attestation_hash TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('active','superseded','revoked')),created_by TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(workspace_id,jurisdiction,rules_version));
INSERT INTO tax_verifications SELECT id,workspace_id,jurisdiction,rules_version,'professional',professional,credentials,verified_on,effective_from,effective_to,registration_scope,supply_scope,item_classification_basis,price_basis,rounding_basis,source_urls_json,limitations,attestation_hash,status,created_by,created_at FROM tax_verifications_legacy;
DROP TABLE tax_verifications_legacy;
CREATE TABLE generated_artifacts(
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 kind TEXT NOT NULL CHECK(kind IN ('dashboard','report','statutory_invoice')),
 name TEXT NOT NULL, specification_json TEXT NOT NULL, specification_hash TEXT NOT NULL,
 source_tables_json TEXT NOT NULL, config_version INTEGER,
 status TEXT NOT NULL CHECK(status IN ('draft','active','reverification_required','retired')) DEFAULT 'draft',
 legal_status TEXT NOT NULL CHECK(legal_status IN ('not_applicable','review_required','owner_reviewed','professional_reviewed')),
 rules_version TEXT, tax_verification_id TEXT,
 created_by TEXT NOT NULL, created_at TEXT NOT NULL,
 reviewer_kind TEXT CHECK(reviewer_kind IN ('owner','professional')), reviewed_by TEXT, reviewed_at TEXT, review_note TEXT,
 UNIQUE(workspace_id,kind,name)
);
CREATE INDEX idx_generated_artifacts_ws ON generated_artifacts(workspace_id,kind,status);
'''
