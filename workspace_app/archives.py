"""Atomic family-level archiving. Visibility never changes financial history."""
import json
from pathlib import Path
from flask import Blueprint, current_app, flash, redirect, render_template, request
from . import security, statistics, store
from .model import ValidationError
from .references import key
from .relationships import actor, stamp
from .commercial import fingerprint

bp=Blueprint('archives', __name__)


def archived_keys(db):
    return {r['reference_key'] for r in db.execute('SELECT reference_key FROM quotation_archives WHERE archived=1')}


def filtered(db, args):
    from .documents import workspace
    matches,stats,_,_=workspace(db,args)
    return stats,matches


def selection(db, values):
    mode=values.get('selection_mode','individual')
    if mode=='matching':
        try:args=json.loads(values.get('filters','{}'))
        except (ValueError,TypeError):raise ValidationError('Invalid matching filters.') from None
        if not isinstance(args,dict) or any(not isinstance(v,str) for v in args.values()):raise ValidationError('Invalid matching filters.')
        _,matches=filtered(db,args); selected={key(r['data']['number']) for r in matches}
    elif mode=='individual':
        selected={key(s) for s in values.getlist('references')}
    else:raise ValidationError('Choose quotations or explicitly select all matching filters.')
    if not selected:raise ValidationError('Select at least one quotation family.')
    families={ref:[] for ref in selected}
    for r in store.records(db,unrestricted=True):
        if r['kind'] in ('quote','document') and key(r['data']['number']) in families:families[key(r['data']['number'])].append(r)
    result=[]
    for ref,rows in sorted(families.items()):
        # Do not allow arbitrary hidden references to probe existence or ownership.
        readable=[r for r in rows if security.can_read(db,r)]
        if not readable:raise ValidationError('A selected family is no longer accessible. Reload the list.')
        result.append(dict(reference=readable[0]['data']['number'],key=ref,revisions=len(rows),blocked=not all(security.can_read(db,r,write=True) for r in rows),ids=sorted(r['id'] for r in rows)))
    return result


@bp.post('/quotes/bulk')
def bulk():
    with store.connect(current_app.config['DATA_DIR']) as db:
        db.execute('BEGIN IMMEDIATE')
        action=request.form.get('action')
        if action not in ('archive','restore','delete'):raise ValidationError('Choose archive or restore.')
        selected=selection(db,request.form)
        files=[]
        if action=='delete':
            from .relationships import guard_delete,record
            from .outcomes import require_not_accepted
            archived=archived_keys(db)
            all_rows={r['id']:r for r in store.records(db,unrestricted=True)}
            contract_links={ident for row in db.execute('SELECT data FROM contracts') for ident in (json.loads(row['data']).get('initial_quote_id'),json.loads(row['data']).get('accepted_quote_id')) if ident}
            for family in selected:
                family['details']=[];family['reasons']=[]
                if request.form.get('archive_view')!='archived' or family['key'] not in archived:family['reasons'].append('Permanent deletion is available only for archived families.')
                for ident in family['ids']:
                    row=all_rows[ident]
                    if security.can_read(db,row):
                        cost=db.execute('SELECT version FROM quote_costing WHERE quote_id=?',(ident,)).fetchone()
                        files_hash=fingerprint([[dict(f) for f in db.execute('SELECT id,name,stored FROM attachments WHERE record_id=? ORDER BY id',(ident,))],[dict(f) for f in db.execute('SELECT * FROM approval_rounds WHERE quote_id=? ORDER BY id',(ident,))],[dict(f) for f in db.execute('SELECT * FROM pdf_file_owners WHERE record_id=? ORDER BY path_key',(ident,))]])
                        family['details'].append(dict(id=ident,title=row['data']['title'],management=dict(db.execute('SELECT * FROM document_management WHERE record_id=?',(ident,)).fetchone() or {}),links=[tuple(x) for x in db.execute('SELECT source_id,target_id FROM document_links WHERE source_id=? OR target_id=? ORDER BY source_id,target_id',(ident,ident))],revision=row['data']['revision'],snapshot=fingerprint(row['data']),cost_version=cost['version'] if cost else 0,files_hash=files_hash))
                    try:
                        if db.execute('SELECT 1 FROM contract_documents cd JOIN attachments a ON a.id=cd.attachment_id WHERE a.record_id=?',(ident,)).fetchone():raise ValidationError('A document attachment is linked to a contract and must be retained.')
                        require_not_accepted(db,ident)
                        if ident in contract_links:raise ValidationError('This revision is linked to a contract version and must be retained.')
                    except ValidationError as exc:family['reasons'].append(str(exc))
                if family['reasons']:family['blocked']=True
        digest=fingerprint(selected)
        if request.form.get('confirm')=='yes':
            if request.form.get('selection_hash')!=digest:raise ValidationError('Selection or permissions changed. Review the selection again.')
            if any(r['blocked'] for r in selected):raise ValidationError('No changes made. '+'; '.join(dict.fromkeys(reason for r in selected for reason in (r.get('reasons') or ['Edit access is required on every revision.']) if r['blocked'])))
            if action=='delete':
                if request.form.get('delete_phrase')!='DELETE':raise ValidationError('Type DELETE to confirm permanent deletion.')
                from .quotation_deletion import purge
                jobs=[purge(db,family,current_app.config['DATA_DIR']) for family in selected]
            else:
                for r in selected:
                    db.execute('INSERT INTO quotation_archives VALUES (?,?,?,?) ON CONFLICT(reference_key) DO UPDATE SET archived=excluded.archived,at=excluded.at,actor=excluded.actor',(r['key'],int(action=='archive'),stamp(),actor()))
                    db.execute('INSERT INTO archive_history(reference_key,archived,at,actor) VALUES (?,?,?,?)',(r['key'],int(action=='archive'),stamp(),actor()))
            flash(f'{len(selected)} quotation families '+('removed from the database. Review external cleanup results below.' if action=='delete' else 'archived.' if action=='archive' else 'restored.'))
    if request.form.get('confirm')=='yes' and action=='delete':
        from .quotation_deletion import cleanup
        for ident in jobs:cleanup(current_app.config['DATA_DIR'],ident)
        return redirect('/quotation-deletions')
    if request.form.get('confirm')=='yes':
        for name in files:
            try:(Path(current_app.config['DATA_DIR'])/'attachments'/name).unlink(missing_ok=True)
            except OSError:flash('A removed attachment file could not be cleaned up. Ask the server administrator to review orphaned files.')
        return redirect('/list/quote?archive='+('archived' if action in ('archive','delete') else 'active'))
    return render_template('archive_confirm.html',selected=selected,action=action,selection_hash=digest,revision_count=sum(r['revisions'] for r in selected),blocked=any(r['blocked'] for r in selected))
