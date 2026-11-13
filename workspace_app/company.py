"""Sanitized reference catalog and explicit administrator company templates."""
import copy,json,secrets
from datetime import datetime,timezone
from pathlib import Path
from flask import Blueprint,abort,current_app,flash,redirect,render_template,request,session
from . import store,security
from .model import FIELDS,ValidationError
from .quotation import default_document,new_row,validate_document

bp=Blueprint('company',__name__)
# Business mappings only: no customer identity, quantities, dates or prices.
SERVICES=[
 ('COMPUTE','Cirrus Compute','VM','IaaS','VM','Per VM / month'),
 ('STORAGE','Cirrus Compute','Storage','STaaS','TB','Per TB / month'),
 ('DCFW','Security','Datacenter FW','SecaaS','environment','Per environment / month'),
 ('PERIMETER','Security','Perimeter FW','Perimeter FW','Mbps','Per Mbps / month'),
 ('LB','Security','Load Balancer','SecaaS','Mbps','Per Mbps / month'),
 ('WAF','Security','WAF','SecaaS','Mbps','Per Mbps / month'),
 ('EDR','Security','EDR','CrowdStrike','VM','Per VM / month'),
 ('BACKUP','Backup as a Service','Managed Backup','BkaaS','agent','Per agent / month'),
 ('BACKUP-STORAGE','Backup as a Service','Backup Storage','BkaaS','TB','Per TB / month'),
 ('SUPPORT','Managed Services','Working hours Support','Support','service','Monthly service fee'),
 ('NOC','Performance','NOC','NOC CIR','IP','Per IP / month'),
 ('SIEM-COLLECTOR','Security','SIEM','SIEM Collector VM','collector','Per collector / month'),
 ('SIEM-ABS','Security','SIEM','SIEM ABS','IP','Per IP / month'),
 ('SOC','Security','SOC 24/7 monitoring','SOC','EPS','Per EPS / month'),
 ('VPN-USER','Security','VPN','VPNaaS','user','Per user / month'),
 ('VPN-NODE','Security','VPN','VPNaaS','node','Per node / month'),
 ('INTERNET','Internet as a Service','Protected Internet','Internet','Mbps','Per Mbps / month'),
 ('REPLICATION-LINK','Replication Link','Protected Link','Replication','Mbps','Per Mbps / month'),
 ('SETUP','Connectivity Setup','One-Time fee','CaaS','service','Estimation')]


def catalog_items():
    from .quotation_defaults import default_items
    return default_items()


def standard_template(company='CIRRUS SAL',payment='',delivery=''):
    d=default_document(company,payment,delivery);mapping={x[0]:x for x in SERVICES}
    def row(code):
        _,service,sub,type_,unit,pricing=mapping[code]
        return new_row(service,item_key='code:CIR-'+code,sub_service=sub,type=type_,unit=unit,pricing_model=pricing,
                       quantity='1',method='fixed' if code=='SETUP' else 'unit',billing='one_time' if code=='SETUP' else 'monthly')
    for section in d['sections']:
        if section['parent']:
            parent=next(x for x in d['sections'] if x['id']==section['parent'])
            codes={'Compute and storage':['COMPUTE','STORAGE'],'Security Services':['DCFW','PERIMETER','LB','WAF','EDR'],
                   'Backup Services':['BACKUP','BACKUP-STORAGE']}.get(section['name'])
            if codes:
                section['rows']=[row(code) for code in codes]
                if parent['name']=='Disaster Recovery' and section['name']=='Security Services':section['rows'].append(row('VPN-USER'))
            else:
                for r in section['rows']:
                    r['quantity']='1'
                    if r.get('type')=='Support':r['item_key']='code:CIR-SUPPORT'
        elif section['name'].startswith('Monitoring'):section['rows']=[row('NOC')]
        elif section['name']=='Cyber Security Services':section['rows']=[row(x) for x in ('SIEM-COLLECTOR','SIEM-ABS','SOC','VPN-USER','VPN-NODE')]
        elif section['name']=='Connectivity Services':section['rows']=[row('INTERNET'),row('REPLICATION-LINK')]
        elif section['name'].startswith('Connectivity Setup'):section['rows']=[row('SETUP')]
    for section in d['sections']:
        for r in section['rows']:
            if r.get('type')=='Support':r['item_key']='code:CIR-SUPPORT'
    return d


def load_template(db):
    saved=db.execute('SELECT data FROM company_template WHERE id=1').fetchone()
    if saved:
        from .quotation import customer_cleanup
        doc=customer_cleanup(copy.deepcopy(json.loads(saved['data'])))
        doc['discount'].update(enabled=False,show_summary=False,percent='0',amount='0',months=0,wording='')
        return doc
    cfg=store.settings(db);return standard_template(cfg['company'],cfg['payment_terms'],cfg['delivery_terms'])


@bp.route('/company-template',methods=['GET','POST'])
def template():
    security.require_admin()
    if request.method=='GET' and request.args.get('advanced')!='1':return redirect('/quotation-defaults')
    with store.connect(current_app.config['DATA_DIR']) as db:
        doc=load_template(db)
        if request.method=='POST':
            source=request.form.get('source_quote')
            if source:
                security.require_id(db,source)
                record=next((r for r in store.records(db) if r['id']==source and r['kind']=='quote'),None)
                if not record:raise ValidationError('Choose an accessible quotation.')
                doc=record['data']['document']
            else:
                try:doc=json.loads(request.form.get('document','{}'))
                except ValueError:raise ValidationError('Invalid template JSON.') from None
            doc=validate_document(doc)
            # Template records only structure/branding/terms. Header identity is never copied.
            db.execute('INSERT INTO company_template VALUES (1,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',(json.dumps(doc),))
            flash('Company template saved explicitly. New quotations receive independent copies; existing quotations are unchanged.')
            return redirect('/company-template')
        quotes=[r for r in store.records(db) if r['kind']=='quote']
    return render_template('company_template.html',document=json.dumps(doc,indent=2),quotes=quotes)


@bp.route('/catalog-replacement',methods=['GET','POST'])
def replace_catalog():
    security.require_admin();root=current_app.config['DATA_DIR']
    with store.connect(root) as db:
        done=db.execute('SELECT * FROM upgrade_operations WHERE name=?',('cirrus-catalog-v1',)).fetchone()
        count=db.execute("SELECT COUNT(*) FROM records WHERE kind='catalog'").fetchone()[0]
    if request.method=='POST':
        if request.form.get('confirm')!='REPLACE CATALOG':raise ValidationError('Type REPLACE CATALOG to confirm.')
        if done:flash('Catalog replacement was already applied; no changes made.');return redirect('/catalog-replacement')
        from .backup import online_safety_backup
        backup_dir=Path(root)/'backups';backup_dir.mkdir(exist_ok=True)
        path=backup_dir/('before-catalog-'+secrets.token_hex(8)+'.zip')
        online_safety_backup(root,path,allow_internal=True)
        with store.connect(root) as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM upgrade_operations WHERE name=?',('cirrus-catalog-v1',)).fetchone():raise ValidationError('Replacement already completed.')
            ids=[r[0] for r in db.execute("SELECT id FROM records WHERE kind='catalog'")]
            attached=db.execute("SELECT id FROM attachments WHERE record_id IN (SELECT id FROM records WHERE kind='catalog')").fetchall()
            if attached:
                note={k:'' for k,_,_ in FIELDS['note']}
                note.update(title='Archived service-catalog attachments',content='Preserved during the explicit catalog replacement. Original files are also present in the pre-replacement backup.',type='Reference',status='Open',visibility='Work')
                archive_id=store.save(db,'note',note)
                for f in attached:db.execute('UPDATE attachments SET record_id=? WHERE id=?',(archive_id,f['id']))
                for u in db.execute('SELECT id FROM users WHERE active=1 AND id<>?',(security.current_user()['id'],)):
                    db.execute('INSERT INTO record_acl VALUES (?,?,?)',(archive_id,u['id'],'read'))
            for ident in ids:
                db.execute('DELETE FROM record_acl WHERE record_id=?',(ident,));db.execute('DELETE FROM records WHERE id=?',(ident,))
            from uuid import uuid5,NAMESPACE_URL
            for item in catalog_items():store.save(db,'catalog',item,str(uuid5(NAMESPACE_URL,item['code'])))
            db.execute('INSERT INTO upgrade_operations VALUES (?,?,?)',('cirrus-catalog-v1',datetime.now(timezone.utc).isoformat(),path.name))
        flash('Catalog replaced once. Full-instance safety backup saved; historical quotation snapshots and VM library were not changed.')
        return redirect('/catalog-replacement')
    return render_template('catalog_replacement.html',count=count,done=done,items=catalog_items())
