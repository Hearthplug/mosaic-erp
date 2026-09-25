import base64, io, json, os, tempfile, unittest

import build_intake
from byok_clients import ChatProviderClient, ProviderError
from store import Store
from artifact_builder import ArtifactBuilder


def b64(raw):
    return base64.b64encode(raw).decode()


def minimal_pdf(text):
    stream = 'BT /F1 24 Tf 100 700 Td (%s) Tj ET' % text
    objs = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        ('<< /Length %d >>\nstream\n%s\nendstream' % (len(stream), stream)).encode(),
    ]
    out = io.BytesIO()
    out.write(b'%PDF-1.4\n')
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(('%d 0 obj\n' % i).encode())
        out.write(body)
        out.write(b'\nendobj\n')
    xref = out.tell()
    out.write(('xref\n0 %d\n0000000000 65535 f \n' % (len(objs) + 1)).encode())
    for off in offsets:
        out.write(('%010d 00000 n \n' % off).encode())
    out.write(('trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(objs) + 1, xref)).encode())
    return out.getvalue()


class ReadFileTest(unittest.TestCase):
    def test_txt_document_hints(self):
        out = build_intake.read_file('note.txt', '', b64(b'Invoice summary report for March'))
        self.assertEqual(out['kind'], 'text')
        self.assertEqual(out['detected']['type'], 'document')
        self.assertIn('invoice', out['detected']['hints'])
        self.assertIn('Invoice', out['excerpt'])

    def test_csv_detects_products_pack(self):
        text = 'sku,name,selling_price_minor,cost_minor\nP1,Tea,150,90\n'
        out = build_intake.read_file('products.csv', '', b64(text.encode()))
        self.assertEqual(out['kind'], 'sheet')
        self.assertEqual(out['detected']['type'], 'migration')
        self.assertEqual(out['detected']['pack'], 'products')
        self.assertIn('P1', out['detected']['csv'])

    def test_xlsx_roundtrip_detects_products(self):
        from openpyxl import Workbook
        wb = Workbook(); ws = wb.active
        ws.append(['sku', 'name', 'selling_price_minor', 'cost_minor']); ws.append(['P1', 'Tea', 150, 90])
        buf = io.BytesIO(); wb.save(buf)
        out = build_intake.read_file('products.xlsx', '', b64(buf.getvalue()))
        self.assertEqual(out['kind'], 'sheet')
        self.assertEqual(out['detected']['type'], 'migration')
        self.assertEqual(out['detected']['pack'], 'products')
        self.assertIn('Tea', out['detected']['csv'])

    def test_bare_name_sheet_is_flagged_but_owner_confirms_the_pack(self):
        # customers and vendors share required columns, so either label is
        # possible; the UI shows the guess and the owner confirms it, and
        # staging validation still catches wrong rows.
        out = build_intake.read_file('list.csv', '', b64(b'name,external_id\nAcme,C1\n'))
        self.assertEqual(out['detected']['type'], 'migration')
        self.assertIn(out['detected']['pack'], ('customers', 'vendors'))

    def test_unknown_sheet_not_forced_into_a_pack(self):
        out = build_intake.read_file('random.csv', '', b64(b'alpha,beta\n1,2\n'))
        self.assertEqual(out['detected']['type'], 'unknown')

    def test_empty_and_oversize_rejected(self):
        with self.assertRaises(ValueError):
            build_intake.read_file('x.txt', '', b64(b''))
        with self.assertRaises(ValueError):
            build_intake.read_file('x.txt', '', b64(b'x' * (build_intake.MAX_BYTES + 1)))

    def test_pdf_text_extracted(self):
        out = build_intake.read_file('doc.pdf', '', b64(minimal_pdf('Invoice summary report')))
        self.assertEqual(out['kind'], 'pdf')
        self.assertIn('Invoice', out['excerpt'])
        self.assertEqual(out['detected']['type'], 'document')

    def test_unsupported_type_rejected(self):
        with self.assertRaises(ValueError):
            build_intake.read_file('archive.zip', 'application/zip', b64(b'PK\x03\x04junk'))


class PhotoExtractionTest(unittest.TestCase):
    def test_non_vision_provider_fails_closed(self):
        c = ChatProviderClient('deepseek', 'k')
        with self.assertRaises(ProviderError) as ctx:
            c.extract_image(b64(b'jpeg-bytes'), 'image/jpeg')
        self.assertIn('cannot read photos', str(ctx.exception))
        self.assertIn('OpenAI, Claude or a custom server with a vision model', str(ctx.exception))

    def test_openai_extraction_shape_and_confidence(self):
        payload = {'choices': [{'message': {'content': json.dumps({
            'document_type': 'supplier bill', 'summary': 'Fresh Farms bill',
            'fields': [{'name': 'vendor', 'value': 'Fresh Farms', 'confidence': 0.92},
                       {'name': 'total', 'value': '42.50', 'confidence': 0.4}]})}}]}
        c = ChatProviderClient('openai', 'k')
        c._request = lambda body: payload
        out = c.extract_image(b64(b'jpeg-bytes'), 'image/jpeg')
        self.assertEqual(out['document_type'], 'supplier bill')
        self.assertEqual(out['fields'][0]['name'], 'vendor')
        self.assertAlmostEqual(out['fields'][0]['confidence'], 0.92)
        self.assertAlmostEqual(out['fields'][1]['confidence'], 0.4)

    def test_unreadable_answer_fails_closed(self):
        c = ChatProviderClient('openai', 'k')
        c._request = lambda body: {'choices': [{'message': {'content': 'not json at all'}}]}
        with self.assertRaises(ProviderError):
            c.extract_image(b64(b'jpeg-bytes'), 'image/jpeg')

    def test_fields_must_be_a_list(self):
        c = ChatProviderClient('openai', 'k')
        c._request = lambda body: {'choices': [{'message': {'content': json.dumps({'document_type': 'bill', 'summary': 'x', 'fields': 'vendor'})}}]}
        with self.assertRaises(ProviderError):
            c.extract_image(b64(b'jpeg-bytes'), 'image/jpeg')


class DraftFromExtractionTest(unittest.TestCase):
    def setUp(self):
        self.f = tempfile.NamedTemporaryFile(delete=False); self.f.close()
        self.s = Store(self.f.name)
        self.w, _ = self.s.create_workspace('Intake Co')
        self.b = ArtifactBuilder(self.s, None, None)

    def tearDown(self):
        self.s.close(); os.unlink(self.f.name)

    def test_report_draft_and_unmapped_fields_reported(self):
        extraction = {'document_type': 'sales summary', 'summary': 'weekly sales by product',
                      'fields': [{'name': 'zodiac sign', 'value': 'leo', 'confidence': 0.9}]}
        out = self.b.draft_from_extraction(self.w, 'owner', 'report', extraction, hint='sales.pdf')
        self.assertEqual(out['draft']['kind'], 'report')
        self.assertEqual(out['draft']['status'], 'draft')
        self.assertIn('zodiac sign', out['unmapped'])


    def test_report_without_type_asks_owner_to_choose(self):
        extraction = {'document_type': 'supplier bill', 'summary': 'Fresh Farms bill FF-1042',
                      'fields': [{'name': 'total', 'value': '48.30', 'confidence': 0.9}]}
        out = self.b.draft_from_extraction(self.w, 'owner', 'report', extraction, hint='bill.pdf')
        self.assertTrue(out['needs_choice'])
        self.assertIn('payables_aging', out['choices'])

    def test_report_type_in_hint_drafts_normally(self):
        extraction = {'document_type': 'supplier bill', 'summary': 'Fresh Farms bill FF-1042', 'fields': []}
        out = self.b.draft_from_extraction(self.w, 'owner', 'report', extraction, hint='bill.pdf payables aging')
        self.assertEqual(out['draft']['kind'], 'report')
        self.assertEqual(out['draft']['specification']['report_type'], 'payables_aging')

    def test_same_document_twice_gets_distinct_names(self):
        extraction = {'document_type': 'supplier bill', 'summary': 'Fresh Farms bill', 'fields': []}
        one = self.b.draft_from_extraction(self.w, 'owner', 'report', extraction, hint='bill.pdf payables aging')
        two = self.b.draft_from_extraction(self.w, 'owner', 'report', extraction, hint='bill.pdf payables aging')
        self.assertNotEqual(one['draft']['name'], two['draft']['name'])
        self.assertEqual(one['draft']['name'], 'Supplier bill - payables aging report')

    def test_invalid_target_rejected(self):
        with self.assertRaises(ValueError):
            self.b.draft_from_extraction(self.w, 'owner', 'delete_everything', {'summary': 'x'}, hint='y')

    def test_empty_extraction_rejected(self):
        with self.assertRaises(ValueError):
            self.b.draft_from_extraction(self.w, 'owner', 'report', {}, hint='')


if __name__ == '__main__':
    unittest.main()
