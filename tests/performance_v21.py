"""Comparable synthetic quote open/save timing and SQL counts against a source path."""
import json,os,re,sqlite3,statistics,sys,tempfile,time
from pathlib import Path
source=Path(os.environ.get('CIRRUS_BENCH_SOURCE',str(Path(__file__).resolve().parents[1])))
sys.path[:0]=[str(source),str(source/'tests')]
from workspace_app import create_app,store,security
from workspace_app.commercial import fingerprint
from test_v5 import quote
with tempfile.TemporaryDirectory() as td:
    root=Path(td)/'data';app=create_app(root,True)
    with store.connect(root) as db:
        uid=security.create_user(db,'benchmark','Synthetic-benchmark-password-21!','Administrator',True)
        customer=store.save(db,'customer',dict(name='Synthetic benchmark customer',contact='',notes=''))
        ids=[]
        for i in range(100):
            q=quote('BENCH-'+str(i),status='Draft');q.update(customer_id=customer,valid_until='2026-12-31')
            ids.append(store.save(db,'quote',q))
        db.execute('UPDATE records SET owner_id=?',(uid,))
    client=app.test_client();client.get('/login')
    with client.session_transaction() as session:csrf=session['csrf']
    client.post('/login',data=dict(csrf=csrf,username='benchmark',password='Synthetic-benchmark-password-21!'))
    ident=ids[0];result={};original=sqlite3.connect;queries=[]
    def connection(*args,**kwargs):
        db=original(*args,**kwargs);db.set_trace_callback(queries.append);return db
    from unittest.mock import patch
    for name in ('open','save'):
        samples=[];counts=[]
        for sample in range(6):
            with store.connect(root) as db:data=json.loads(db.execute('SELECT data FROM records WHERE id=?',(ident,)).fetchone()[0])
            data['title']='Synthetic benchmark saved '+str(sample)
            with client.session_transaction() as session:csrf=session['csrf']
            # Fingerprint before the request; exclude fixture/preparation queries.
            with store.connect(root) as db:before=json.loads(db.execute('SELECT data FROM records WHERE id=?',(ident,)).fetchone()[0])
            queries.clear()
            with patch('sqlite3.connect',connection):
                start=time.perf_counter()
                response=client.get('/quotes/'+ident+'/edit') if name=='open' else client.post('/quotes/'+ident+'/edit',data=dict(csrf=csrf,quotation=json.dumps(data),base_hash=fingerprint(before)))
                elapsed=(time.perf_counter()-start)*1000
            assert response.status_code==(200 if name=='open' else 302),response.status_code
            if sample:samples.append(round(elapsed,2));counts.append(len(queries))
        result[name]=dict(median_ms=statistics.median(samples),samples=samples,sql_statements=counts)
    print(json.dumps(dict(source_version='V20' if source.name=='codex-test-lab' else 'V21',fixture='100 quotations; 1 customer; five warm Flask requests; synthetic SQLite; SQL trace includes ACLs; saves change title',results=result),indent=2))
