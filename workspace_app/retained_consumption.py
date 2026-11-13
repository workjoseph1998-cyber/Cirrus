"""Administrator-only, consistent handover of retired consumption records."""
import hashlib
import io
import json
import zipfile
from flask import Blueprint, current_app, send_file
from . import security, store

bp = Blueprint('retained_consumption', __name__)
TABLES = ('monthly_snapshots', 'monthly_history', 'monthly_drafts', 'consumption', 'consumption_history')


def archive(root):
    """The SQLite write barrier also coordinates attachment capture with app writes."""
    output = io.BytesIO(); files = {}
    with store.connect(root) as db:
        db.execute('BEGIN IMMEDIATE')
        for table in TABLES:
            rows = []
            for row in db.execute('SELECT * FROM ' + table):
                data = dict(row)
                if table == 'monthly_drafts':
                    workbook = data.pop('workbook')
                    if workbook:
                        path = 'staged-workbooks/' + data['id'] + '.xlsx'
                        files[path] = workbook; data['workbook_path'] = path
                rows.append(data)
            files['tables/' + table + '.json'] = json.dumps(rows, ensure_ascii=False, indent=2).encode()
        identities = [dict(r) for r in db.execute("SELECT id,kind,data,created,updated FROM records WHERE kind IN ('customer','project')")]
        # Only customer/project linkage information; exclude unrelated project internals.
        for row in identities:
            d = json.loads(row['data']); row['data'] = {k: d.get(k, '') for k in ('name', 'customer_id', 'customer')}
        files['identities.json'] = json.dumps(identities, ensure_ascii=False, indent=2).encode()
        files['actors.json'] = json.dumps([dict(r) for r in db.execute('SELECT id,username FROM users')], ensure_ascii=False, indent=2).encode()
        for row in db.execute('SELECT DISTINCT a.* FROM attachments a JOIN monthly_history h ON h.attachment_id=a.id'):
            files['original-workbooks/' + row['stored']] = (root / 'attachments' / row['stored']).read_bytes()
            files['original-workbooks/' + row['id'] + '.metadata.json'] = json.dumps(dict(row)).encode()
        files['manifest.json'] = json.dumps(dict(application='Cirrus Workplace', application_version='17', schema=db.execute('PRAGMA user_version').fetchone()[0],
            purpose='Retained consumption handover; reporting months and source Date remain separate. Raw values are authoritative.',
            sha256={name: hashlib.sha256(data).hexdigest() for name, data in files.items()}), indent=2).encode()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
            for name, data in files.items():
                z.writestr(name, data)
    output.seek(0)
    return output


@bp.post('/administration/consumption-handover')
def download():
    security.require_admin()
    return send_file(archive(current_app.config['DATA_DIR']), mimetype='application/zip', as_attachment=True, download_name='Cirrus-retained-consumption-handover.zip')
