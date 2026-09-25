"""Sandbox billing ledger. No checkout, prices, or live entitlements are defined here."""
SQLITE_BILLING_SCHEMA = """
CREATE TABLE billing_subscriptions(
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 provider TEXT NOT NULL, external_id TEXT NOT NULL,
 plan_ref TEXT NOT NULL, status TEXT NOT NULL,
 period_end TEXT, last_event_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 PRIMARY KEY(provider,external_id),
 UNIQUE(workspace_id,provider,external_id)
);
CREATE INDEX idx_billing_subscriptions_workspace ON billing_subscriptions(workspace_id);
CREATE TABLE billing_events(
 provider TEXT NOT NULL, event_id TEXT NOT NULL,
 workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 subscription_id TEXT NOT NULL, received_at TEXT NOT NULL,
 PRIMARY KEY(provider,event_id)
);
CREATE INDEX idx_billing_events_workspace ON billing_events(workspace_id);
"""
POSTGRES_BILLING_SCHEMA = """
CREATE TABLE billing_subscriptions(
 workspace_id text NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 provider text NOT NULL, external_id text NOT NULL,
 plan_ref text NOT NULL, status text NOT NULL,
 period_end text, last_event_at text NOT NULL,
 updated_at text NOT NULL,
 PRIMARY KEY(provider,external_id),
 UNIQUE(workspace_id,provider,external_id)
);
CREATE INDEX idx_billing_subscriptions_workspace ON billing_subscriptions(workspace_id);
CREATE TABLE billing_events(
 provider text NOT NULL, event_id text NOT NULL,
 workspace_id text NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 subscription_id text NOT NULL, received_at text NOT NULL,
 PRIMARY KEY(provider,event_id)
);
CREATE INDEX idx_billing_events_workspace ON billing_events(workspace_id);
ALTER TABLE billing_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing_subscriptions FORCE ROW LEVEL SECURITY;
CREATE POLICY billing_subscriptions_tenant ON billing_subscriptions
 USING (workspace_id=current_setting('mosaic.workspace_id',true))
 WITH CHECK (workspace_id=current_setting('mosaic.workspace_id',true));
ALTER TABLE billing_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing_events FORCE ROW LEVEL SECURITY;
CREATE POLICY billing_events_tenant ON billing_events
 USING (workspace_id=current_setting('mosaic.workspace_id',true))
 WITH CHECK (workspace_id=current_setting('mosaic.workspace_id',true));
"""
