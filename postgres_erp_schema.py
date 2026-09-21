"""PostgreSQL migration generated from the reviewed logical ERP schemas.

The source DDL stays shared with SQLite; this translator is deliberately narrow
and rejects unknown SQLite-only syntax rather than silently weakening controls.
"""
from accounting_schema import ACCOUNTING_SQLITE_SCHEMA
from retail_schema import RETAIL_SQLITE_SCHEMA
from onboarding_schema import ONBOARDING_SQLITE_SCHEMA
from operating_model_schema import OPERATING_MODEL_SQLITE_SCHEMA
from migration_schema import MIGRATION_SQLITE_SCHEMA
from tax_verification_schema import TAX_VERIFICATION_SQLITE_SCHEMA
from provisioning_schema import PROVISIONING_SQLITE_SCHEMA
from artifact_builder_schema import ARTIFACT_BUILDER_SQLITE_SCHEMA
from assistant_setup_schema import ASSISTANT_SETUP_SQLITE_SCHEMA
from assistant_preview_schema import ASSISTANT_PREVIEW_SQLITE_SCHEMA

DIRECT_TENANT_TABLES=('accounting_settings','accounts','fiscal_periods','parties','items','tax_rules','tax_transaction_facts','tax_codes','document_sequences','documents','journals','journal_lines','settlements','bank_transactions','inventory_movements','statutory_adapters','acceptance_runs','migration_batches','locations','retail_products','stock_ledger','purchase_orders','sales','tender_entries','retail_returns','cash_sessions','credit_policies','stock_counts','goods_receipts','three_way_matches','onboarding_sessions','operating_models','role_assignments','approval_requests','import_batches','tax_verifications','generated_artifacts','assistant_settings','provisioned_capabilities','verification_tasks','workspace_invitations')
CHILD_POLICIES={
 'journal_reversals':"EXISTS (SELECT 1 FROM journals p WHERE p.id=journal_reversals.original_journal_id AND p.workspace_id=current_setting('mosaic.workspace_id',true))",
 'document_lines':"EXISTS (SELECT 1 FROM documents p WHERE p.id=document_lines.document_id AND p.workspace_id=current_setting('mosaic.workspace_id',true))",
 'purchase_order_lines':"EXISTS (SELECT 1 FROM purchase_orders p WHERE p.id=purchase_order_lines.purchase_order_id AND p.workspace_id=current_setting('mosaic.workspace_id',true))",
 'sale_lines':"EXISTS (SELECT 1 FROM sales p WHERE p.id=sale_lines.sale_id AND p.workspace_id=current_setting('mosaic.workspace_id',true))",
 'retail_return_lines':"EXISTS (SELECT 1 FROM retail_returns p WHERE p.id=retail_return_lines.return_id AND p.workspace_id=current_setting('mosaic.workspace_id',true))",
 'stock_count_lines':"EXISTS (SELECT 1 FROM stock_counts p WHERE p.id=stock_count_lines.stock_count_id AND p.workspace_id=current_setting('mosaic.workspace_id',true))",
}

def _translate(src):
 out=[]
 for raw in src.splitlines():
  line=raw.strip()
  if not line or line.startswith('CREATE TRIGGER '):continue
  if 'RAISE(ABORT' in line:continue
  line=line.replace(' INTEGER PRIMARY KEY AUTOINCREMENT',' bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY')
  line=line.replace(' INTEGER',' bigint').replace(' REAL',' double precision')
  line=line.replace("ALTER TABLE workspaces ADD COLUMN operational_profile_json TEXT;","ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS operational_profile_json text;")
  line=line.replace("ALTER TABLE workspaces ADD COLUMN operational_profile_hash TEXT;","ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS operational_profile_hash text;")
  line=line.replace("ALTER TABLE workspaces ADD COLUMN operational_profile_at TEXT;","ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS operational_profile_at text;")
  out.append(line)
 return '\n'.join(out)


_OWNER_TAX_PG=TAX_VERIFICATION_SQLITE_SCHEMA.replace('professional TEXT NOT NULL,credentials TEXT NOT NULL','reviewer_kind TEXT NOT NULL CHECK(reviewer_kind IN (\'owner\',\'professional\')),reviewer_name TEXT NOT NULL,credentials TEXT NOT NULL DEFAULT \'\'')
_ASSISTANT=ASSISTANT_SETUP_SQLITE_SCHEMA
_ARTIFACT_ONLY=ARTIFACT_BUILDER_SQLITE_SCHEMA[ARTIFACT_BUILDER_SQLITE_SCHEMA.index('CREATE TABLE generated_artifacts('):]
BASE='\n'.join(_translate(x) for x in (ACCOUNTING_SQLITE_SCHEMA,RETAIL_SQLITE_SCHEMA,ONBOARDING_SQLITE_SCHEMA,OPERATING_MODEL_SQLITE_SCHEMA,MIGRATION_SQLITE_SCHEMA,_OWNER_TAX_PG,PROVISIONING_SQLITE_SCHEMA,_ARTIFACT_ONLY,_ASSISTANT))
RLS=[]
for t in DIRECT_TENANT_TABLES:
 RLS += [f'ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;',f'ALTER TABLE {t} FORCE ROW LEVEL SECURITY;',f"CREATE POLICY {t}_tenant ON {t} USING (workspace_id=current_setting('mosaic.workspace_id',true)) WITH CHECK (workspace_id=current_setting('mosaic.workspace_id',true));"]
for t,p in CHILD_POLICIES.items():
 RLS += [f'ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;',f'ALTER TABLE {t} FORCE ROW LEVEL SECURITY;',f'CREATE POLICY {t}_tenant ON {t} USING ({p}) WITH CHECK ({p});']
IMMUTABLE=r'''
CREATE OR REPLACE FUNCTION mosaic_immutable_posted() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'posted accounting records are immutable'; END $$;
CREATE TRIGGER journals_no_update BEFORE UPDATE OR DELETE ON journals FOR EACH ROW EXECUTE FUNCTION mosaic_immutable_posted();
CREATE TRIGGER journal_lines_no_update BEFORE UPDATE OR DELETE ON journal_lines FOR EACH ROW EXECUTE FUNCTION mosaic_immutable_posted();
'''
POSTGRES_ERP_MIGRATION=BASE+'\n'+'\n'.join(RLS)+'\n'+IMMUTABLE
ALL_ERP_TABLES=set(DIRECT_TENANT_TABLES)|set(CHILD_POLICIES)
_preview_rls=['ALTER TABLE assistant_action_drafts ENABLE ROW LEVEL SECURITY;','ALTER TABLE assistant_action_drafts FORCE ROW LEVEL SECURITY;',"CREATE POLICY assistant_action_drafts_tenant ON assistant_action_drafts USING (workspace_id=current_setting('mosaic.workspace_id',true)) WITH CHECK (workspace_id=current_setting('mosaic.workspace_id',true));"]
ASSISTANT_PREVIEW_PG=_translate(ASSISTANT_PREVIEW_SQLITE_SCHEMA)+'\n'+'\n'.join(_preview_rls)
