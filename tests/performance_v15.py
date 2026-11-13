"""Development-only warm Flask page timings over synthetic data; no live database."""
import json,statistics,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace_app import create_app,store,security
from test_v5 import quote


def measure():
 with tempfile.TemporaryDirectory() as td:
  root=Path(td)/'data';app=create_app(root,True)
  with store.connect(root) as db:
   admin=security.create_user(db,'performance-admin','Synthetic-performance-password!','Administrator',True)
   customers=[store.save(db,'customer',dict(name='Synthetic customer '+str(i),contact='Synthetic contact',notes='')) for i in range(30)]
   for i in range(300):
    q=quote('PERF-'+str(i),status='Draft');q.update(title='Synthetic services '+str(i),customer_id=customers[i%30],customer='Synthetic customer '+str(i%30),date='2026-11-04');store.save(db,'quote',q)
   db.execute('UPDATE records SET owner_id=?',(admin,))
  client=app.test_client();client.get('/login')
  with client.session_transaction() as s:csrf=s['csrf']
  assert client.post('/login',data=dict(csrf=csrf,username='performance-admin',password='Synthetic-performance-password!')).status_code==302
  result={}
  for path in ['/','/list/quote','/customers','/customers/'+customers[0]]:
   durations=[]
   for sample in range(6):
    begin=time.perf_counter();response=client.get(path);elapsed=(time.perf_counter()-begin)*1000;assert response.status_code==200
    if sample:durations.append(round(elapsed,2))
   result[path if not path.startswith('/customers/') else '/customers/:id']=dict(median_ms=round(statistics.median(durations),2),samples=durations,response_bytes=len(response.data))
  return dict(fixture='300 draft quotations / 30 customers; five warm authenticated Flask samples per page; one cold sample excluded; temporary SQLite; no real emails',pages=result)

if __name__=='__main__':print(json.dumps(measure(),indent=2))
