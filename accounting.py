"""Accounting core for Mosaic ERP.

Amounts are stored as integer minor units. Posted journals are immutable: fixes are
new reversing/correcting journals. Billing documents post through the same journal
engine, so the general ledger remains the single source for all reports.
"""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
import csv, io, json, secrets, threading
from store import Conflict, NotFound, utcnow, canon, sha256

SQLITE_SCHEMA = r'''
CREATE TABLE accounting_settings(workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,base_currency TEXT NOT NULL DEFAULT 'USD',fiscal_year_start TEXT NOT NULL DEFAULT '01-01',config_version INTEGER NOT NULL DEFAULT 1,config_hash TEXT NOT NULL,verification_state TEXT NOT NULL DEFAULT 'unverified',verified_by TEXT,verified_at TEXT,verification_note TEXT,invalidated_at TEXT,invalidation_reason TEXT);
CREATE TABLE accounts(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,code TEXT NOT NULL,name TEXT NOT NULL,type TEXT NOT NULL CHECK(type IN ('asset','liability','equity','income','expense')),currency TEXT,active INTEGER NOT NULL DEFAULT 1,system_key TEXT,UNIQUE(workspace_id,code),UNIQUE(workspace_id,system_key));
CREATE TABLE fiscal_periods(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,name TEXT NOT NULL,starts_on TEXT NOT NULL,ends_on TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','locked')),UNIQUE(workspace_id,starts_on,ends_on));
CREATE TABLE parties(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,kind TEXT NOT NULL CHECK(kind IN ('customer','vendor','both')),name TEXT NOT NULL,email TEXT,tax_id TEXT,currency TEXT,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
CREATE TABLE items(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,sku TEXT NOT NULL,name TEXT NOT NULL,kind TEXT NOT NULL DEFAULT 'goods',income_account_id TEXT REFERENCES accounts(id),expense_account_id TEXT REFERENCES accounts(id),inventory_account_id TEXT REFERENCES accounts(id),tax_code TEXT,active INTEGER NOT NULL DEFAULT 1,UNIQUE(workspace_id,sku));
CREATE TABLE tax_codes(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,code TEXT NOT NULL,name TEXT NOT NULL,rate_bps INTEGER NOT NULL CHECK(rate_bps BETWEEN 0 AND 100000),sales_account_id TEXT REFERENCES accounts(id),purchase_account_id TEXT REFERENCES accounts(id),rounding TEXT NOT NULL DEFAULT 'half_up',verified INTEGER NOT NULL DEFAULT 0,UNIQUE(workspace_id,code));
CREATE TABLE document_sequences(workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,kind TEXT NOT NULL,prefix TEXT NOT NULL,next_number INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(workspace_id,kind));
CREATE TABLE documents(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,kind TEXT NOT NULL CHECK(kind IN ('sales_invoice','purchase_bill','credit_note','debit_note','payment','refund','opening_balance','inventory_adjustment')),number TEXT NOT NULL,party_id TEXT REFERENCES parties(id),currency TEXT NOT NULL,exchange_rate TEXT NOT NULL DEFAULT '1',issue_date TEXT NOT NULL,due_date TEXT,status TEXT NOT NULL CHECK(status IN ('draft','approved','posted','voided')),subtotal_minor INTEGER NOT NULL,total_tax_minor INTEGER NOT NULL,total_minor INTEGER NOT NULL,balance_minor INTEGER NOT NULL,memo TEXT,source_document_id TEXT REFERENCES documents(id),journal_id TEXT,created_by TEXT NOT NULL,approved_by TEXT,created_at TEXT NOT NULL,posted_at TEXT,UNIQUE(workspace_id,kind,number));
CREATE TABLE document_lines(id TEXT PRIMARY KEY,document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE RESTRICT,position INTEGER NOT NULL,item_id TEXT REFERENCES items(id),description TEXT NOT NULL,quantity TEXT NOT NULL,unit_price_minor INTEGER NOT NULL,discount_minor INTEGER NOT NULL DEFAULT 0,tax_code_id TEXT REFERENCES tax_codes(id),net_minor INTEGER NOT NULL,tax_minor INTEGER NOT NULL,total_minor INTEGER NOT NULL,account_id TEXT REFERENCES accounts(id),UNIQUE(document_id,position));
CREATE TABLE journals(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,number TEXT NOT NULL,effective_date TEXT NOT NULL,description TEXT NOT NULL,source_type TEXT NOT NULL,source_id TEXT,reference TEXT,currency TEXT NOT NULL,exchange_rate TEXT NOT NULL DEFAULT '1',reverses_journal_id TEXT REFERENCES journals(id),reversed_by_journal_id TEXT REFERENCES journals(id),created_by TEXT NOT NULL,approved_by TEXT,posted_at TEXT NOT NULL,checksum TEXT NOT NULL,UNIQUE(workspace_id,number),UNIQUE(workspace_id,source_type,source_id));
CREATE TABLE journal_lines(id TEXT PRIMARY KEY,journal_id TEXT NOT NULL REFERENCES journals(id) ON DELETE RESTRICT,workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,position INTEGER NOT NULL,account_id TEXT NOT NULL REFERENCES accounts(id),party_id TEXT REFERENCES parties(id),item_id TEXT REFERENCES items(id),debit_minor INTEGER NOT NULL DEFAULT 0 CHECK(debit_minor>=0),credit_minor INTEGER NOT NULL DEFAULT 0 CHECK(credit_minor>=0),base_debit_minor INTEGER NOT NULL DEFAULT 0,base_credit_minor INTEGER NOT NULL DEFAULT 0,memo TEXT,UNIQUE(journal_id,position),CHECK((debit_minor=0)!=(credit_minor=0)));
CREATE INDEX idx_journal_lines_ws_account ON journal_lines(workspace_id,account_id);
CREATE TABLE settlements(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,payment_document_id TEXT NOT NULL REFERENCES documents(id),target_document_id TEXT NOT NULL REFERENCES documents(id),amount_minor INTEGER NOT NULL CHECK(amount_minor>0),created_at TEXT NOT NULL,UNIQUE(payment_document_id,target_document_id));
CREATE TABLE bank_transactions(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,account_id TEXT NOT NULL REFERENCES accounts(id),posted_on TEXT NOT NULL,description TEXT NOT NULL,amount_minor INTEGER NOT NULL,external_id TEXT,status TEXT NOT NULL DEFAULT 'unmatched',matched_journal_id TEXT REFERENCES journals(id),UNIQUE(workspace_id,account_id,external_id));
CREATE TRIGGER journals_no_update BEFORE UPDATE ON journals BEGIN SELECT RAISE(ABORT,'posted journals are immutable'); END;
CREATE TRIGGER journals_no_delete BEFORE DELETE ON journals BEGIN SELECT RAISE(ABORT,'posted journals are immutable'); END;
CREATE TRIGGER journal_lines_no_update BEFORE UPDATE ON journal_lines BEGIN SELECT RAISE(ABORT,'posted journal lines are immutable'); END;
CREATE TRIGGER journal_lines_no_delete BEFORE DELETE ON journal_lines BEGIN SELECT RAISE(ABORT,'posted journal lines are immutable'); END;
'''

DEFAULT_ACCOUNTS=(('1000','Cash','asset','cash'),('1010','Bank','asset','bank'),('1100','Accounts receivable','asset','receivable'),('1200','Inventory','asset','inventory'),('2000','Accounts payable','liability','payable'),('2100','Sales tax payable','liability','sales_tax'),('2110','Purchase tax recoverable','asset','purchase_tax'),('3000','Owner equity','equity','equity'),('3100','Opening balance equity','equity','opening'),('4000','Sales','income','sales'),('4100','Sales returns','income','sales_returns'),('5000','Cost of goods sold','expense','cogs'),('6000','General expenses','expense','expense'),('6999','Rounding','expense','rounding'),('7900','Foreign exchange gain/loss','income','fx_gain_loss'))
MATERIAL_KEYS={'base_currency','fiscal_year_start','chart_of_accounts','tax_registration','tax_codes','invoice_numbering','legal_name','legal_address','country','jurisdiction'}

def minor(value):
    return int((Decimal(str(value))*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
def ident(prefix): return prefix+'_'+secrets.token_hex(8)

class Accounting:
    def __init__(self, store): self.s=store; self._sequence_lock=threading.RLock()
    def setup(self,wid,actor,base_currency='USD',fiscal_year_start='01-01'):
        currency=(base_currency or '').upper()
        if len(currency)!=3: raise ValueError('base_currency must be a 3-letter code')
        now=utcnow(); cfg={'base_currency':currency,'fiscal_year_start':fiscal_year_start}
        with self.s.tx():
            self.s._db.execute('INSERT INTO accounting_settings(workspace_id,base_currency,fiscal_year_start,config_hash) VALUES(?,?,?,?)',(wid,currency,fiscal_year_start,sha256(canon(cfg))))
            for code,name,typ,key in DEFAULT_ACCOUNTS:
                self.s._db.execute('INSERT INTO accounts(id,workspace_id,code,name,type,system_key) VALUES(?,?,?,?,?,?)',(ident('acc'),wid,code,name,typ,key))
            for kind,prefix in [('journal','JRN-'),('sales_invoice','INV-'),('purchase_bill','BILL-'),('credit_note','CN-'),('debit_note','DN-'),('payment','PAY-'),('refund','REF-'),('opening_balance','OPEN-'),('inventory_adjustment','STK-')]:
                self.s._db.execute('INSERT INTO document_sequences(workspace_id,kind,prefix) VALUES(?,?,?)',(wid,kind,prefix))
            self.s._audit(wid,actor,'accounting.setup',cfg)
        return self.status(wid)
    def status(self,wid):
        row=self.s._db.execute('SELECT * FROM accounting_settings WHERE workspace_id=?',(wid,)).fetchone()
        if not row: raise NotFound('Accounting is not set up')
        return dict(row)
    def verify(self,wid,actor,professional,note=''):
        if not professional.strip(): raise ValueError('professional name or firm is required')
        with self.s.tx():
            self.s._db.execute("UPDATE accounting_settings SET verification_state='verified',verified_by=?,verified_at=?,verification_note=?,invalidated_at=NULL,invalidation_reason=NULL WHERE workspace_id=?",(professional[:200],utcnow(),note[:1000],wid))
            self.s._audit(wid,actor,'accounting.verify',{'professional':professional,'note':note})
        return self.status(wid)
    def change_settings(self,wid,actor,changes):
        allowed={'base_currency','fiscal_year_start'}
        if not changes or not set(changes)<=allowed: raise ValueError('supported settings: base_currency, fiscal_year_start')
        old=self.status(wid); merged={k:changes.get(k,old[k]) for k in allowed}; reason=', '.join(sorted(set(changes)&MATERIAL_KEYS))
        with self.s.tx():
            self.s._db.execute("UPDATE accounting_settings SET base_currency=?,fiscal_year_start=?,config_version=config_version+1,config_hash=?,verification_state='invalidated',invalidated_at=?,invalidation_reason=? WHERE workspace_id=?",(merged['base_currency'],merged['fiscal_year_start'],sha256(canon(merged)),utcnow(),reason,wid))
            self.s._audit(wid,actor,'accounting.material_change',{'changes':changes,'verification_invalidated':True})
        return self.status(wid)
    def _next(self,wid,kind):
        with self._sequence_lock:
            row=self.s._db.execute('SELECT prefix,next_number FROM document_sequences WHERE workspace_id=? AND kind=?',(wid,kind)).fetchone()
            if not row: raise Conflict('document sequence is not configured')
            self.s._db.execute('UPDATE document_sequences SET next_number=next_number+1 WHERE workspace_id=? AND kind=?',(wid,kind))
            return f"{row['prefix']}{int(row['next_number']):06d}"
    def create_account(self,wid,actor,code,name,typ,system_key=None):
        if typ not in ('asset','liability','equity','income','expense'): raise ValueError('invalid account type')
        aid=ident('acc')
        with self.s.tx():
            self.s._db.execute('INSERT INTO accounts(id,workspace_id,code,name,type,system_key) VALUES(?,?,?,?,?,?)',(aid,wid,code,name,typ,system_key))
            self._invalidate(wid,actor,'chart of accounts changed')
        return {'id':aid,'code':code,'name':name,'type':typ}
    def _invalidate(self,wid,actor,reason):
        self.s._db.execute("UPDATE accounting_settings SET config_version=config_version+1,verification_state='invalidated',invalidated_at=?,invalidation_reason=? WHERE workspace_id=?",(utcnow(),reason,wid))
        self.s._audit(wid,actor,'accounting.verification.invalidate',{'reason':reason})
    def create_party(self,wid,actor,kind,name,**fields):
        if kind not in ('customer','vendor','both'): raise ValueError('invalid party kind')
        pid=ident('pty')
        with self.s.tx():
            self.s._db.execute('INSERT INTO parties(id,workspace_id,kind,name,email,tax_id,currency,created_at) VALUES(?,?,?,?,?,?,?,?)',(pid,wid,kind,name,fields.get('email'),fields.get('tax_id'),fields.get('currency'),utcnow()))
            self.s._audit(wid,actor,'party.create',{'party_id':pid,'kind':kind,'name':name})
        return {'id':pid,'kind':kind,'name':name}
    def add_tax_code(self,wid,actor,code,name,rate_percent,sales_account_id=None,purchase_account_id=None,verified=False):
        tid=ident('tax'); bps=int((Decimal(str(rate_percent))*100).quantize(Decimal('1')))
        with self.s.tx():
            self.s._db.execute('INSERT INTO tax_codes(id,workspace_id,code,name,rate_bps,sales_account_id,purchase_account_id,verified) VALUES(?,?,?,?,?,?,?,?)',(tid,wid,code,name,bps,sales_account_id,purchase_account_id,int(bool(verified))))
            self._invalidate(wid,actor,'tax configuration changed')
        return {'id':tid,'code':code,'rate_percent':str(rate_percent),'verified':bool(verified)}
    def add_period(self,wid,actor,name,starts_on,ends_on):
        if starts_on>ends_on: raise ValueError('period start must not follow end')
        pid=ident('per')
        with self.s.tx():
            self.s._db.execute('INSERT INTO fiscal_periods(id,workspace_id,name,starts_on,ends_on) VALUES(?,?,?,?,?)',(pid,wid,name,starts_on,ends_on))
            self.s._audit(wid,actor,'period.create',{'period_id':pid,'starts_on':starts_on,'ends_on':ends_on})
        return {'id':pid,'name':name,'starts_on':starts_on,'ends_on':ends_on,'status':'open'}
    def lock_period(self,wid,actor,period_id):
        with self.s.tx():
            self.s.accounting_lock(wid,'period')
            row=self.s._db.execute('SELECT status FROM fiscal_periods WHERE id=? AND workspace_id=?',(period_id,wid)).fetchone()
            if not row: raise NotFound('Period not found')
            if self.s._db.execute("UPDATE fiscal_periods SET status='locked' WHERE id=? AND workspace_id=? AND status='open'",(period_id,wid)).rowcount!=1: raise Conflict('fiscal period was not open')
            self.s._audit(wid,actor,'period.lock',{'period_id':period_id})
    def _period_open(self,wid,date):
        row=self.s._db.execute('SELECT status FROM fiscal_periods WHERE workspace_id=? AND ? BETWEEN starts_on AND ends_on ORDER BY starts_on DESC LIMIT 1',(wid,date)).fetchone()
        if row and row['status']=='locked': raise Conflict('fiscal period is locked')
    def post_journal(self,wid,actor,effective_date,description,lines,source_type='manual',source_id=None,reference=None,currency=None,exchange_rate='1',approved_by=None,reverses=None):
        with self.s.tx():
            self.s.accounting_lock(wid,'period')
            return self._post_journal(wid,actor,effective_date,description,lines,source_type,source_id,reference,currency,exchange_rate,approved_by,reverses)
    def _post_journal(self,wid,actor,effective_date,description,lines,source_type='manual',source_id=None,reference=None,currency=None,exchange_rate='1',approved_by=None,reverses=None):
        if len(lines)<2: raise ValueError('journal requires at least two lines')
        self._period_open(wid,effective_date); rate=Decimal(str(exchange_rate)); debit=sum(int(x.get('debit_minor',0)) for x in lines); credit=sum(int(x.get('credit_minor',0)) for x in lines)
        if debit!=credit or debit<=0: raise ValueError('journal debits and credits must be positive and equal')
        settings=self.status(wid); cur=currency or settings['base_currency']; jid=ident('jrn'); now=utcnow()
        with self.s.tx():
            number=self._next(wid,'journal'); payload={'number':number,'date':effective_date,'description':description,'lines':lines,'currency':cur,'rate':str(rate)}
            self.s._db.execute('INSERT INTO journals(id,workspace_id,number,effective_date,description,source_type,source_id,reference,currency,exchange_rate,reverses_journal_id,created_by,approved_by,posted_at,checksum) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(jid,wid,number,effective_date,description,source_type,source_id,reference,cur,str(rate),reverses,actor,approved_by,now,sha256(canon(payload))))
            for pos,line in enumerate(lines,1):
                d=int(line.get('debit_minor',0)); c=int(line.get('credit_minor',0))
                self.s._db.execute('INSERT INTO journal_lines(id,journal_id,workspace_id,position,account_id,party_id,item_id,debit_minor,credit_minor,base_debit_minor,base_credit_minor,memo) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(ident('jln'),jid,wid,pos,line['account_id'],line.get('party_id'),line.get('item_id'),d,c,int((Decimal(d)*rate).quantize(Decimal('1'))),int((Decimal(c)*rate).quantize(Decimal('1'))),line.get('memo')))
            if reverses:
                self.s._db.execute('INSERT INTO journal_reversals(original_journal_id,reversal_journal_id,created_at) VALUES(?,?,?)',(reverses,jid,now))
            self.s._audit(wid,actor,'journal.post',{'journal_id':jid,'number':number,'debit_minor':debit,'source_type':source_type})
        return {'id':jid,'number':number,'debit_minor':debit,'credit_minor':credit,'checksum':sha256(canon(payload))}
    def reverse_journal(self,wid,actor,journal_id,effective_date,reason):
        j=self.s._db.execute('SELECT * FROM journals WHERE id=? AND workspace_id=?',(journal_id,wid)).fetchone()
        if not j: raise NotFound('Journal not found')
        if self.s._db.execute('SELECT 1 FROM journal_reversals WHERE original_journal_id=?',(journal_id,)).fetchone(): raise Conflict('Journal already reversed')
        rows=self.s._db.execute('SELECT * FROM journal_lines WHERE journal_id=? ORDER BY position',(journal_id,)).fetchall()
        lines=[{'account_id':r['account_id'],'party_id':r['party_id'],'item_id':r['item_id'],'debit_minor':r['credit_minor'],'credit_minor':r['debit_minor'],'memo':reason} for r in rows]
        return self.post_journal(wid,actor,effective_date,'Reversal: '+reason,lines,'reversal',journal_id,currency=j['currency'],exchange_rate=j['exchange_rate'],reverses=journal_id)
    def create_document(self,wid,actor,kind,issue_date,lines,party_id=None,currency=None,due_date=None,memo=None,source_document_id=None,exchange_rate='1'):
        if kind not in ('sales_invoice','purchase_bill','credit_note','debit_note','opening_balance','inventory_adjustment'): raise ValueError('unsupported document kind')
        if not lines: raise ValueError('document requires lines')
        settings=self.status(wid); did=ident('doc'); computed=[]; sub=tax=0
        for i,x in enumerate(lines,1):
            qty=Decimal(str(x.get('quantity','1'))); unit=int(x['unit_price_minor']); discount=int(x.get('discount_minor',0)); net=int((qty*unit).quantize(Decimal('1')))-discount
            tr=0
            if x.get('tax_code_id'):
                row=self.s._db.execute('SELECT rate_bps FROM tax_codes WHERE id=? AND workspace_id=?',(x['tax_code_id'],wid)).fetchone()
                if not row: raise NotFound('Tax code not found')
                tr=int((Decimal(net)*Decimal(row['rate_bps'])/Decimal(10000)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
            computed.append((i,x,net,tr,net+tr)); sub+=net; tax+=tr
        with self.s.tx():
            number=self._next(wid,kind)
            self.s._db.execute('INSERT INTO documents(id,workspace_id,kind,number,party_id,currency,exchange_rate,issue_date,due_date,status,subtotal_minor,total_tax_minor,total_minor,balance_minor,memo,source_document_id,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(did,wid,kind,number,party_id,currency or settings['base_currency'],str(exchange_rate),issue_date,due_date,'draft',sub,tax,sub+tax,sub+tax,memo,source_document_id,actor,utcnow()))
            for pos,x,net,tr,total in computed:
                self.s._db.execute('INSERT INTO document_lines(id,document_id,position,item_id,description,quantity,unit_price_minor,discount_minor,tax_code_id,net_minor,tax_minor,total_minor,account_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(ident('dln'),did,pos,x.get('item_id'),x.get('description','Line'),str(x.get('quantity','1')),x['unit_price_minor'],x.get('discount_minor',0),x.get('tax_code_id'),net,tr,total,x.get('account_id')))
            self.s._audit(wid,actor,'document.create',{'document_id':did,'kind':kind,'number':number,'total_minor':sub+tax})
        return {'id':did,'kind':kind,'number':number,'status':'draft','subtotal_minor':sub,'tax_minor':tax,'total_minor':sub+tax}
    def approve_document(self,wid,actor,document_id):
        with self.s.tx():
            n=self.s._db.execute("UPDATE documents SET status='approved',approved_by=? WHERE id=? AND workspace_id=? AND status='draft'",(actor,document_id,wid)).rowcount
            if n!=1: raise Conflict('document must be an existing draft')
            self.s._audit(wid,actor,'document.approve',{'document_id':document_id})
    def _system(self,wid,key):
        r=self.s._db.execute('SELECT id FROM accounts WHERE workspace_id=? AND system_key=?',(wid,key)).fetchone()
        if not r: raise Conflict('required system account is missing: '+key)
        return r['id']
    def post_document(self,wid,actor,document_id):
        with self.s.tx():
            self.s.accounting_lock(wid,'document:'+document_id)
            return self._post_document(wid,actor,document_id)
    def _post_document(self,wid,actor,document_id):
        d=self.s._db.execute('SELECT * FROM documents WHERE id=? AND workspace_id=?',(document_id,wid)).fetchone()
        if not d or d['status']!='approved': raise Conflict('document must be approved before posting')
        lines=self.s._db.execute('SELECT * FROM document_lines WHERE document_id=? ORDER BY position',(document_id,)).fetchall(); out=[]
        sales=d['kind'] in ('sales_invoice','debit_note'); purchase=d['kind']=='purchase_bill'; credit=d['kind']=='credit_note'
        if not (sales or purchase or credit): raise ValueError('use a manual journal for this document kind')
        if sales:
            out.append({'account_id':self._system(wid,'receivable'),'party_id':d['party_id'],'debit_minor':d['total_minor']})
            for x in lines: out.append({'account_id':x['account_id'] or self._system(wid,'sales'),'credit_minor':x['net_minor']})
            if d['total_tax_minor']: out.append({'account_id':self._system(wid,'sales_tax'),'credit_minor':d['total_tax_minor']})
        elif purchase:
            for x in lines: out.append({'account_id':x['account_id'] or self._system(wid,'expense'),'debit_minor':x['net_minor']})
            if d['total_tax_minor']: out.append({'account_id':self._system(wid,'purchase_tax'),'debit_minor':d['total_tax_minor']})
            out.append({'account_id':self._system(wid,'payable'),'party_id':d['party_id'],'credit_minor':d['total_minor']})
        else:
            for x in lines: out.append({'account_id':x['account_id'] or self._system(wid,'sales_returns'),'debit_minor':x['net_minor']})
            if d['total_tax_minor']: out.append({'account_id':self._system(wid,'sales_tax'),'debit_minor':d['total_tax_minor']})
            out.append({'account_id':self._system(wid,'receivable'),'party_id':d['party_id'],'credit_minor':d['total_minor']})
        j=self.post_journal(wid,actor,d['issue_date'],f"{d['kind']} {d['number']}",out,d['kind'],d['id'],d['number'],d['currency'],d['exchange_rate'],d['approved_by'])
        with self.s.tx():
            if self.s._db.execute("UPDATE documents SET status='posted',journal_id=?,posted_at=? WHERE id=? AND workspace_id=? AND status='approved'",(j['id'],utcnow(),document_id,wid)).rowcount!=1: raise Conflict('approved document was not posted')
            self.s._audit(wid,actor,'document.post',{'document_id':document_id,'journal_id':j['id']})
        return j
    def trial_balance(self,wid,as_of=None):
        where='l.workspace_id=?'; args=[wid]
        if as_of: where+=' AND j.effective_date<=?'; args.append(as_of)
        rows=self.s._db.execute(f'''SELECT a.code,a.name,a.type,SUM(l.base_debit_minor) debit_minor,SUM(l.base_credit_minor) credit_minor FROM journal_lines l JOIN journals j ON j.id=l.journal_id JOIN accounts a ON a.id=l.account_id WHERE {where} GROUP BY a.id,a.code,a.name,a.type ORDER BY a.code''',tuple(args)).fetchall()
        result=[dict(r)|{'debit_minor':int(r['debit_minor'] or 0),'credit_minor':int(r['credit_minor'] or 0)} for r in rows]; return {'accounts':result,'total_debit_minor':sum(r['debit_minor'] for r in result),'total_credit_minor':sum(r['credit_minor'] for r in result)}
    def general_ledger(self,wid,account_id,from_date=None,to_date=None):
        q='''SELECT j.number,j.effective_date,j.description,j.reference,l.debit_minor,l.credit_minor,l.base_debit_minor,l.base_credit_minor,l.party_id,l.memo FROM journal_lines l JOIN journals j ON j.id=l.journal_id WHERE l.workspace_id=? AND l.account_id=?'''; args=[wid,account_id]
        if from_date:q+=' AND j.effective_date>=?';args.append(from_date)
        if to_date:q+=' AND j.effective_date<=?';args.append(to_date)
        q+=' ORDER BY j.effective_date,j.number,l.position'; rows=[dict(r) for r in self.s._db.execute(q,tuple(args)).fetchall()]; bal=0
        for r in rows: bal+=r['base_debit_minor']-r['base_credit_minor'];r['running_balance_minor']=bal
        return {'account_id':account_id,'entries':rows,'ending_balance_minor':bal}
    def financial_statements(self,wid,from_date=None,to_date=None):
        tb=self.trial_balance(wid,to_date)['accounts']; pnl=[]; bs=[]
        for r in tb:
            bal=r['debit_minor']-r['credit_minor']; item={'code':r['code'],'name':r['name'],'type':r['type'],'amount_minor': -bal if r['type'] in ('income','liability','equity') else bal}
            (pnl if r['type'] in ('income','expense') else bs).append(item)
        income=sum(x['amount_minor'] for x in pnl if next(r for r in tb if r['code']==x['code'])['type']=='income'); expense=sum(x['amount_minor'] for x in pnl if next(r for r in tb if r['code']==x['code'])['type']=='expense')
        return {'profit_and_loss':pnl,'net_profit_minor':income-expense,'balance_sheet':bs,'as_of':to_date}
    def import_csv(self,wid,actor,entity,text,dry_run=True):
        if entity not in ('customers','vendors','accounts'): raise ValueError('supported imports: customers, vendors, accounts')
        rows=list(csv.DictReader(io.StringIO(text))); errors=[]
        required={'customers':{'name'},'vendors':{'name'},'accounts':{'code','name','type'}}[entity]
        for n,r in enumerate(rows,2):
            miss=[x for x in required if not (r.get(x) or '').strip()]
            if miss: errors.append({'row':n,'error':'missing '+', '.join(miss)})
            if entity=='accounts' and r.get('type') not in ('asset','liability','equity','income','expense'): errors.append({'row':n,'error':'invalid account type'})
        if errors or dry_run:return {'valid':not errors,'dry_run':True,'rows':len(rows),'errors':errors}
        for r in rows:
            if entity=='accounts':self.create_account(wid,actor,r['code'],r['name'],r['type'])
            else:self.create_party(wid,actor,'customer' if entity=='customers' else 'vendor',r['name'],email=r.get('email'),tax_id=r.get('tax_id'),currency=r.get('currency'))
        return {'valid':True,'dry_run':False,'imported':len(rows),'errors':[]}

    def opening_balance(self,wid,actor,effective_date,balances,approved_by):
        """Post reconciled opening balances against opening-balance equity."""
        if not approved_by: raise ValueError('opening balances require approval')
        lines=[]; net=0
        for x in balances:
            amount=int(x['balance_minor']); normal=x.get('normal','debit')
            if amount<0: amount=-amount; normal='credit' if normal=='debit' else 'debit'
            line={'account_id':x['account_id'],'debit_minor':amount if normal=='debit' else 0,'credit_minor':amount if normal=='credit' else 0,'memo':'Opening balance'}
            lines.append(line); net+=line['debit_minor']-line['credit_minor']
        if net: lines.append({'account_id':self._system(wid,'opening'),'debit_minor':max(-net,0),'credit_minor':max(net,0),'memo':'Opening balance offset'})
        return self.post_journal(wid,actor,effective_date,'Approved opening balances',lines,'opening_balance',ident('open'),approved_by=approved_by)

    def record_payment(self,wid,actor,target_document_id,amount_minor,paid_on,bank_account_id=None,currency=None,exchange_rate='1',refund=False):
        with self.s.tx():
            self.s.accounting_lock(wid,'document:'+target_document_id)
            return self._record_payment(wid,actor,target_document_id,amount_minor,paid_on,bank_account_id,currency,exchange_rate,refund)
    def _record_payment(self,wid,actor,target_document_id,amount_minor,paid_on,bank_account_id=None,currency=None,exchange_rate='1',refund=False):
        d=self.s._db.execute('SELECT * FROM documents WHERE id=? AND workspace_id=?',(target_document_id,wid)).fetchone()
        if not d or d['status']!='posted': raise Conflict('payment target must be posted')
        amount=int(amount_minor)
        if amount<=0: raise ValueError('payment must be positive')
        if amount>d['balance_minor']: raise Conflict('payment exceeds outstanding balance')
        cash=bank_account_id or self._system(wid,'bank'); control=self._system(wid,'payable' if d['kind']=='purchase_bill' else 'receivable')
        incoming=d['kind'] in ('sales_invoice','debit_note')
        lines=[{'account_id':cash,('credit_minor' if refund or not incoming else 'debit_minor'):amount},{'account_id':control,'party_id':d['party_id'],('debit_minor' if refund or not incoming else 'credit_minor'):amount}]
        kind='refund' if refund else 'payment'; pid=ident('doc'); settings=self.status(wid)
        with self.s.tx():
            number=self._next(wid,kind)
            self.s._db.execute('INSERT INTO documents(id,workspace_id,kind,number,party_id,currency,exchange_rate,issue_date,status,subtotal_minor,total_tax_minor,total_minor,balance_minor,memo,created_by,approved_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(pid,wid,kind,number,d['party_id'],currency or d['currency'],str(exchange_rate),paid_on,'posted',amount,0,amount,0,'Settlement for '+d['number'],actor,actor,utcnow()))
        j=self.post_journal(wid,actor,paid_on,f'{kind} {number}',lines,kind,pid,number,currency or d['currency'],exchange_rate,actor)
        base_settled=int((Decimal(amount)*Decimal(str(exchange_rate))).quantize(Decimal('1'))); historic=int((Decimal(amount)*Decimal(str(d['exchange_rate']))).quantize(Decimal('1'))); fx=base_settled-historic
        if fx:
            fxid=self._system(wid,'fx_gain_loss')
            self.post_journal(wid,actor,paid_on,'Realized foreign exchange difference',[{'account_id':control,'debit_minor':max(fx,0),'credit_minor':max(-fx,0)},{'account_id':fxid,'debit_minor':max(-fx,0),'credit_minor':max(fx,0)}],'fx_settlement',pid+'-fx')
        with self.s.tx():
            if self.s._db.execute("UPDATE documents SET balance_minor=balance_minor-? WHERE id=? AND workspace_id=? AND status='posted' AND balance_minor>=?",(amount,target_document_id,wid,amount)).rowcount!=1: raise Conflict('payment target balance was not updated')
            self.s._db.execute('INSERT INTO settlements(id,workspace_id,payment_document_id,target_document_id,amount_minor,created_at) VALUES(?,?,?,?,?,?)',(ident('set'),wid,pid,target_document_id,amount,utcnow()))
            self.s._audit(wid,actor,'settlement.create',{'payment_document_id':pid,'target_document_id':target_document_id,'amount_minor':amount,'realized_fx_minor':fx})
        return {'payment_document_id':pid,'journal_id':j['id'],'remaining_minor':d['balance_minor']-amount,'realized_fx_minor':fx}

    def aging(self,wid,as_of,kind='receivable'):
        kinds=('sales_invoice','debit_note') if kind=='receivable' else ('purchase_bill',)
        marks=','.join('?' for _ in kinds); rows=self.s._db.execute(f"SELECT id,number,party_id,due_date,currency,balance_minor FROM documents WHERE workspace_id=? AND kind IN ({marks}) AND status='posted' AND balance_minor>0",(wid,*kinds)).fetchall(); buckets={'current':0,'1_30':0,'31_60':0,'61_90':0,'over_90':0}; detail=[]
        from datetime import date
        anchor=date.fromisoformat(as_of)
        for r in rows:
            days=max(0,(anchor-date.fromisoformat(r['due_date'] or as_of)).days); b='current' if days==0 else '1_30' if days<=30 else '31_60' if days<=60 else '61_90' if days<=90 else 'over_90'; buckets[b]+=r['balance_minor']; detail.append(dict(r)|{'days_overdue':days,'bucket':b})
        return {'kind':kind,'as_of':as_of,'buckets':buckets,'documents':detail}


    DOCUMENT_KINDS = ('sales_invoice', 'purchase_bill', 'credit_note', 'debit_note', 'payment', 'refund', 'opening_balance', 'inventory_adjustment')

    def list_documents(self, wid, kind=None, limit=50):
        """Newest documents first, with the party name for display. Read-only."""
        if kind and kind not in self.DOCUMENT_KINDS:
            raise ValueError('unsupported document kind')
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 50
        limit = min(max(limit, 1), 200)
        sql = "SELECT d.id,d.kind,d.number,d.issue_date,d.due_date,d.status,d.currency,d.total_minor,d.balance_minor,p.name AS party_name FROM documents d LEFT JOIN parties p ON p.id=d.party_id WHERE d.workspace_id=?"
        args = [wid]
        if kind:
            sql += " AND d.kind=?"
            args.append(kind)
        sql += " ORDER BY d.issue_date DESC,d.created_at DESC LIMIT ?"
        args.append(limit)
        rows = self.s._db.execute(sql, args).fetchall()
        return {'documents': [dict(r) for r in rows]}

    def get_document(self, wid, document_id):
        """One document with its lines and recorded payments. Read-only."""
        d = self.s._db.execute("SELECT d.*,p.name AS party_name FROM documents d LEFT JOIN parties p ON p.id=d.party_id WHERE d.id=? AND d.workspace_id=?", (document_id, wid)).fetchone()
        if not d:
            raise NotFound('document not found')
        lines = self.s._db.execute("SELECT position,description,quantity,unit_price_minor,discount_minor,net_minor,tax_minor,total_minor FROM document_lines WHERE document_id=? ORDER BY position", (document_id,)).fetchall()
        payments = self.s._db.execute("SELECT s.amount_minor,pay.number,pay.issue_date AS paid_on FROM settlements s JOIN documents pay ON pay.id=s.payment_document_id WHERE s.target_document_id=? AND s.workspace_id=? ORDER BY s.created_at", (document_id, wid)).fetchall()
        out = dict(d)
        out['lines'] = [dict(x) for x in lines]
        out['payments'] = [dict(x) for x in payments]
        return out

    def import_bank_transactions(self,wid,actor,account_id,rows):
        results=[]
        with self.s.tx():
            for x in rows:
                bid=ident('bnk')
                try:self.s._db.execute('INSERT INTO bank_transactions(id,workspace_id,account_id,posted_on,description,amount_minor,external_id) VALUES(?,?,?,?,?,?,?)',(bid,wid,account_id,x['posted_on'],x['description'],int(x['amount_minor']),x.get('external_id')));results.append({'id':bid,'status':'unmatched'})
                except Exception as e: results.append({'external_id':x.get('external_id'),'error':str(e)})
            self.s._audit(wid,actor,'bank.import',{'rows':len(rows),'accepted':sum('id' in x for x in results)})
        return results

    def match_bank_transaction(self,wid,actor,bank_transaction_id,journal_id):
        with self.s.tx():
            b=self.s._db.execute('SELECT amount_minor FROM bank_transactions WHERE id=? AND workspace_id=? AND status=?',(bank_transaction_id,wid,'unmatched')).fetchone(); j=self.s._db.execute('SELECT id FROM journals WHERE id=? AND workspace_id=?',(journal_id,wid)).fetchone()
            if not b or not j: raise Conflict('unmatched bank transaction and journal are required')
            if self.s._db.execute("UPDATE bank_transactions SET status='matched',matched_journal_id=? WHERE id=? AND workspace_id=? AND status='unmatched'",(journal_id,bank_transaction_id,wid)).rowcount!=1: raise Conflict('bank transaction was not matched')
            self.s._audit(wid,actor,'bank.match',{'bank_transaction_id':bank_transaction_id,'journal_id':journal_id})
        return {'matched':True}

    def record_inventory_movement(self,wid,actor,item_id,effective_date,quantity,unit_cost_minor,kind,warehouse='main',source_document_id=None):
        qty=Decimal(str(quantity)); total=int((qty*int(unit_cost_minor)).quantize(Decimal('1'))); iid=ident('mov')
        with self.s.tx():
            self.s._db.execute('INSERT INTO inventory_movements(id,workspace_id,item_id,warehouse,effective_date,quantity,unit_cost_minor,total_cost_minor,kind,source_document_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(iid,wid,item_id,warehouse,effective_date,str(qty),int(unit_cost_minor),total,kind,source_document_id,utcnow())); self.s._audit(wid,actor,'inventory.movement',{'movement_id':iid,'item_id':item_id,'quantity':str(qty),'total_cost_minor':total})
        return {'id':iid,'quantity':str(qty),'total_cost_minor':total}

    def inventory_valuation(self,wid,as_of=None):
        q='SELECT item_id,warehouse,SUM(CAST(quantity AS REAL)) quantity,SUM(total_cost_minor) value_minor FROM inventory_movements WHERE workspace_id=?';args=[wid]
        if as_of:q+=' AND effective_date<=?';args.append(as_of)
        q+=' GROUP BY item_id,warehouse'; rows=[dict(r)|{'quantity':str(r['quantity'] or 0),'value_minor':int(r['value_minor'] or 0)} for r in self.s._db.execute(q,tuple(args)).fetchall()]
        return {'method':'movement-cost totals; costing policy must be verified','as_of':as_of,'positions':rows,'total_value_minor':sum(r['value_minor'] for r in rows)}

    def configure_statutory_adapter(self,wid,actor,jurisdiction,capability,rules_version,verified_by=None,notes=''):
        status='verified' if verified_by else 'disabled'; aid=ident('adp')
        with self.s.tx():
            self.s._db.execute('INSERT INTO statutory_adapters(id,workspace_id,jurisdiction,capability,status,rules_version,verified_by,verified_at,notes) VALUES(?,?,?,?,?,?,?,?,?)',(aid,wid,jurisdiction,capability,status,rules_version,verified_by,utcnow() if verified_by else None,notes)); self._invalidate(wid,actor,'statutory adapter changed')
        return {'id':aid,'status':status,'jurisdiction':jurisdiction,'capability':capability}

    def migration_reconciliation(self,wid,actor,source_system,row_count,control_total_minor,posted_total_minor,detail=None):
        variance=int(posted_total_minor)-int(control_total_minor); bid=ident('mig'); status='reconciled' if variance==0 else 'variance'
        with self.s.tx():
            self.s._db.execute('INSERT INTO migration_batches(id,workspace_id,source_system,imported_at,row_count,control_total_minor,posted_total_minor,status,variance_minor,detail_json) VALUES(?,?,?,?,?,?,?,?,?,?)',(bid,wid,source_system,utcnow(),int(row_count),int(control_total_minor),int(posted_total_minor),status,variance,canon(detail or {}))); self.s._audit(wid,actor,'migration.reconcile',{'batch_id':bid,'status':status,'variance_minor':variance})
        return {'id':bid,'status':status,'variance_minor':variance}

    def run_acceptance(self,wid,actor,sample_name,expected):
        actual={'trial_balance':self.trial_balance(wid),'statements':self.financial_statements(wid)}; differences={k:{'expected':v,'actual':actual.get(k)} for k,v in expected.items() if actual.get(k)!=v}; status='passed' if not differences else 'failed'; rid=ident('accpt'); payload={'sample':sample_name,'expected':expected,'actual':actual}
        with self.s.tx():
            self.s._db.execute('INSERT INTO acceptance_runs(id,workspace_id,run_at,actor_id,sample_name,expected_json,actual_json,status,difference_json,checksum) VALUES(?,?,?,?,?,?,?,?,?,?)',(rid,wid,utcnow(),actor,sample_name,canon(expected),canon(actual),status,canon(differences),sha256(canon(payload)))); self.s._audit(wid,actor,'acceptance.run',{'run_id':rid,'status':status})
        return {'id':rid,'status':status,'differences':differences,'checksum':sha256(canon(payload))}

    def import_transactions(self,wid,actor,rows,dry_run=True):
        """Validation-first journal import with source control totals."""
        errors=[]; debit=credit=0
        for n,row in enumerate(rows,1):
            lines=row.get('lines',[]);d=sum(int(x.get('debit_minor',0)) for x in lines);c=sum(int(x.get('credit_minor',0)) for x in lines)
            if len(lines)<2 or d!=c or d<=0:errors.append({'row':n,'error':'journal is not positive and balanced'})
            debit+=d;credit+=c
        if errors or dry_run:return {'valid':not errors,'dry_run':True,'rows':len(rows),'debit_control_minor':debit,'credit_control_minor':credit,'errors':errors}
        results=[self.post_journal(wid,actor,x['effective_date'],x['description'],x['lines'],'import',x.get('source_id',ident('imp')),x.get('reference')) for x in rows]
        recon=self.migration_reconciliation(wid,actor,'journal-import',len(rows),debit,sum(x['debit_minor'] for x in results),{'journals':[x['id'] for x in results]})
        return {'valid':True,'dry_run':False,'imported':len(results),'reconciliation':recon}
