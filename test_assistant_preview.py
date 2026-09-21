import json, os, tempfile, unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from store import Store
from assistant_setup import AssistantSetup
from assistant_preview import AssistantPreview, LocalModelClient, ModelError, BINDINGS, DRAFT_TTL_MINUTES
from accounting import Accounting
from retail import Retail

AVAILABILITY = {'schema': 'mosaic-local-availability-v1', 'available': True,
                'verdicts': [{'architecture': 'amd64', 'passed': True}, {'architecture': 'arm64', 'passed': True}]}

class FakeClient:
    def __init__(self, label='RETAIL_PRODUCT_CREATE', slots=None, error=None):
        self.label, self.slots, self.error = label, slots, error
        self.calls = []
    def classify(self, message):
        self.calls.append(('classify', message))
        if self.error: raise self.error
        return self.label
    def fill_slots(self, message, label):
        self.calls.append(('slots', message, label))
        if self.error: raise self.error
        return self.slots if self.slots is not None else {}

class AssistantPreviewTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.NamedTemporaryFile()
        self.av = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False)
        json.dump(AVAILABILITY, self.av); self.av.close()
        self.env = patch.dict(os.environ, {'MOSAIC_ASSISTANT_LOCAL_AVAILABILITY_FILE': self.av.name})
        self.env.start()
        self.s = Store(self.t.name)
        self.w, self.k = self.s.create_workspace('Preview shop')
        self.books = Accounting(self.s)
        self.retail = Retail(self.s, self.books)
        self.setup = AssistantSetup(self.s)
    def tearDown(self):
        self.s.close(); self.env.stop(); os.unlink(self.av.name)
    def enable_local(self):
        with self.s.tx():
            self.s._db.execute("INSERT INTO assistant_settings(workspace_id,mode,status,updated_by,updated_at) VALUES(?,'local','ready','test','now')",(self.w,))
    def preview(self, client):
        return AssistantPreview(self.s, self.retail, self.setup, client=client)
    def make_editor(self):
        return self.k  # workspace owner key has top role
    def draft(self, label='RETAIL_PRODUCT_CREATE', slots=None, role='owner'):
        p = self.preview(FakeClient(label, slots if slots is not None else {'name': 'Rice 5kg'}))
        out = p.chat(self.w, self.k, role, 'add a product')
        assert 'draft' in out, out
        return p, out['draft']

    def test_unavailable_without_local_mode_or_verdict(self):
        p = self.preview(FakeClient())
        self.assertFalse(p.chat(self.w, self.k, 'owner', 'add product')['preview_available'])
        self.enable_local()
        with patch.dict(os.environ, {'MOSAIC_ASSISTANT_LOCAL_AVAILABILITY_FILE': ''}):
            self.assertFalse(p.chat(self.w, self.k, 'owner', 'add product')['preview_available'])

    def test_product_draft_and_confirm_executes_once(self):
        self.enable_local()
        p, d = self.draft()
        self.assertIn('Rice 5kg', d['rendered'])
        self.assertIn(d['payload']['params']['sku'], d['rendered'])
        self.assertTrue(d['approve_once_allowed'])
        r = p.confirm(self.w, self.k, 'owner', d['id'])
        self.assertEqual(r['status'], 'executed')
        row = self.s._db.execute('SELECT * FROM retail_products WHERE workspace_id=? AND name=?', (self.w, 'Rice 5kg')).fetchone()
        self.assertIsNotNone(row)
        with self.assertRaisesRegex(Exception, 'single-use'):
            p.confirm(self.w, self.k, 'owner', d['id'])

    def test_approve_once_records_mode_and_is_single_use(self):
        self.enable_local()
        p, d = self.draft()
        r = p.confirm(self.w, self.k, 'owner', d['id'], approve_once=True)
        self.assertEqual(r['approval_mode'], 'approve_once')
        with self.assertRaisesRegex(Exception, 'single-use'):
            p.confirm(self.w, self.k, 'owner', d['id'], approve_once=True)

    def test_approve_once_rejected_for_high_risk_draft(self):
        self.enable_local()
        p, d = self.draft()
        with self.s.tx():
            self.s._db.execute("UPDATE assistant_action_drafts SET risk='high' WHERE id=?", (d['id'],))
        with self.assertRaisesRegex(Exception, 'standard actions'):
            p.confirm(self.w, self.k, 'owner', d['id'], approve_once=True)
        row = self.s._db.execute('SELECT status FROM assistant_action_drafts WHERE id=?', (d['id'],)).fetchone()
        self.assertEqual(row['status'], 'pending')

    def test_tampered_payload_fails_closed(self):
        self.enable_local()
        p, d = self.draft()
        payload = d['payload']; payload['params']['name'] = 'Tampered'
        with self.s.tx():
            self.s._db.execute('UPDATE assistant_action_drafts SET payload_json=? WHERE id=?', (json.dumps(payload), d['id']))
        with self.assertRaisesRegex(Exception, 'new approval'):
            p.confirm(self.w, self.k, 'owner', d['id'])
        self.assertIsNone(self.s._db.execute('SELECT id FROM retail_products WHERE workspace_id=?', (self.w,)).fetchone())

    def test_expired_draft_cannot_execute(self):
        self.enable_local()
        p, d = self.draft()
        old = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        with self.s.tx():
            self.s._db.execute('UPDATE assistant_action_drafts SET expires_at=? WHERE id=?', (old, d['id']))
        with self.assertRaisesRegex(Exception, 'expired'):
            p.confirm(self.w, self.k, 'owner', d['id'])

    def test_cancel_then_confirm_rejected(self):
        self.enable_local()
        p, d = self.draft()
        self.assertEqual(p.cancel(self.w, self.k, d['id'])['status'], 'cancelled')
        with self.assertRaisesRegex(Exception, 'cancelled'):
            p.confirm(self.w, self.k, 'owner', d['id'])

    def test_model_error_fails_closed_without_draft(self):
        self.enable_local()
        p = self.preview(FakeClient(error=ModelError('boom')))
        out = p.chat(self.w, self.k, 'owner', 'add product')
        self.assertNotIn('draft', out)
        self.assertIn('safe answer', out['reply'])

    def test_invalid_label_and_slots_fail_closed(self):
        self.enable_local()
        p = self.preview(FakeClient('RETAIL_PRODUCT_CREATE', {'wrong': 1}))
        out = p.chat(self.w, self.k, 'owner', 'add product')
        self.assertNotIn('draft', out)
        p2 = self.preview(FakeClient('NOPE', {}))
        self.assertEqual(p2._infer('x'), ('clarify', {}))
        self.assertRaises(ModelError, LocalModelClient(base='http://127.0.0.1:9').classify, 'x')

    def test_unsupported_kind_explains_without_draft(self):
        self.enable_local()
        p = self.preview(FakeClient('RETAIL_SALE_CREATE', {'location_ref': 'LOC-1'}))
        out = p.chat(self.w, self.k, 'owner', 'sell one rice')
        self.assertNotIn('draft', out)
        self.assertIn('cannot execute', out['reply'])

    def test_reject_and_clarify_paths(self):
        self.enable_local()
        out = self.preview(FakeClient('REJECT', {})).chat(self.w, self.k, 'owner', 'delete everything')
        self.assertIn('never', out['reply'])
        out = self.preview(FakeClient('CLARIFY', {})).chat(self.w, self.k, 'owner', 'hmm')
        self.assertIn('rephrase', out['reply'])

    def test_role_enforcement(self):
        self.enable_local()
        out = self.preview(FakeClient('WORKSPACE_INVITE', {'role': 'cashier'})).chat(self.w, self.k, 'viewer', 'invite a cashier')
        self.assertNotIn('draft', out)
        self.assertIn('role', out['reply'])
        out = self.preview(FakeClient('RETAIL_PRODUCT_CREATE', {'name': 'Oil 1L'})).chat(self.w, self.k, 'viewer', 'add product')
        self.assertNotIn('draft', out)

    def test_invite_binding_executes(self):
        self.enable_local()
        p = self.preview(FakeClient('WORKSPACE_INVITE', {'role': 'cashier'}))
        out = p.chat(self.w, self.k, 'owner', 'invite a cashier')
        r = p.confirm(self.w, self.k, 'owner', out['draft']['id'], approve_once=True)
        self.assertIn('/invite?token=', r['reply'])
        stored = self.s._db.execute('SELECT result_json FROM assistant_action_drafts WHERE id=?', (out['draft']['id'],)).fetchone()['result_json']
        self.assertNotIn('miv_', stored)
        inv = self.s._db.execute('SELECT operational_role FROM workspace_invitations WHERE workspace_id=?', (self.w,)).fetchone()
        self.assertEqual(inv['operational_role'], 'Cashier · sell & return')

    def test_stock_status_binding_reads_across_locations(self):
        self.enable_local()
        self.retail.setup_location(self.w, self.k, 'LOC-1', 'Main')
        loc = self.s._db.execute('SELECT id FROM locations WHERE workspace_id=?', (self.w,)).fetchone()['id']
        prod = self.retail.product(self.w, self.k, 'PROD-1', 'Rice 5kg', 500, 400)
        self.retail.move_stock(self.w, self.k, prod['id'], loc, 7, 400, 'purchase', 'test', 't1')
        p = self.preview(FakeClient('RETAIL_STOCK_STATUS', {'product_ref': 'PROD-1'}))
        out = p.chat(self.w, self.k, 'viewer', 'stock of PROD-1')
        r = p.confirm(self.w, self.k, 'viewer', out['draft']['id'])
        self.assertEqual(r['result']['total'], 7)

    def test_unknown_product_ref_clarifies(self):
        self.enable_local()
        out = self.preview(FakeClient('RETAIL_STOCK_STATUS', {'product_ref': 'PROD-9'})).chat(self.w, self.k, 'viewer', 'stock')
        self.assertNotIn('draft', out)
        self.assertIn('could not find', out['reply'])

    def test_client_rejects_public_endpoint_and_bad_outputs(self):
        with patch.dict(os.environ, {'MOSAIC_ASSISTANT_LOCAL_URL': 'http://8.8.8.8:18080'}):
            self.assertRaises(ModelError, LocalModelClient)
        c = LocalModelClient(base='http://127.0.0.1:9')
        self.assertRaises(ModelError, c.classify, 'hi')

    def test_no_secret_or_content_in_audit(self):
        self.enable_local()
        p, d = self.draft()
        p.confirm(self.w, self.k, 'owner', d['id'], approve_once=True)
        dump = ' '.join(str(x) for x in self.s.audit_trail(self.w))
        self.assertNotIn('Rice 5kg', dump)

if __name__ == '__main__':
    unittest.main()

class AssistantPreviewPGContract(unittest.TestCase):
    def test_preview_table_rls_and_policy(self):
        import postgres_erp_schema as p
        sql = p.ASSISTANT_PREVIEW_PG
        self.assertIn('ALTER TABLE assistant_action_drafts FORCE ROW LEVEL SECURITY;', sql)
        self.assertIn('ALTER TABLE assistant_action_drafts ENABLE ROW LEVEL SECURITY;', sql)
        self.assertIn('CREATE POLICY assistant_action_drafts_tenant', sql)

    def test_preview_migration_appended_incrementally(self):
        import postgres_store as s
        from postgres_erp_schema import ASSISTANT_PREVIEW_PG, POSTGRES_ERP_MIGRATION
        self.assertEqual(s.PG_MIGRATIONS[1], POSTGRES_ERP_MIGRATION)
        self.assertEqual(s.PG_MIGRATIONS[-1], ASSISTANT_PREVIEW_PG)
        self.assertNotIn('assistant_action_drafts', POSTGRES_ERP_MIGRATION)
