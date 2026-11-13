"""Optional independent formula verification with LibreOffice installed.
No LibreOffice runtime dependency for the application.
"""
import copy
from decimal import Decimal
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from openpyxl import load_workbook
from workspace_app.quote_excel import export_excel
from workspace_app.quotation import calculate,new_row,public_document,validate_document
from quotation_fixture import fixture


def run():
    executable=shutil.which('soffice') or shutil.which('libreoffice')
    if not executable:raise SystemExit('Install LibreOffice to run this optional test.')
    with tempfile.TemporaryDirectory() as td:
        td=Path(td);output=td/'out';output.mkdir();expected={}
        cases={}
        cases['baseline']=fixture()
        cases['twelve-month-hidden']=fixture();cases['twelve-month-hidden']['document']['show_12_month']=False
        cases['unpriced']=fixture();cases['unpriced']['document']['sections'][1]['rows'][0]['unit_price']=''
        cases['zero']=fixture();cases['zero']['document']['sections'][1]['rows'][0]['unit_price']='0'
        cases['included-tax']=fixture();cases['included-tax']['document']['tax']['mode']='included'
        cases['changed-quantity']=fixture()
        cases['long-text']=fixture();cases['long-text']['document']['sections'][1]['rows'][0]['comments']='\n'.join('Specification line '+str(i) for i in range(100))+'\nEND-LONG-XLSX'
        cases['many-rows']=fixture()
        cases['many-rows']['document']['sections'][1]['rows'].extend(new_row('Synthetic extra '+str(i),quantity='1',unit_price='1') for i in range(120))
        selected=os.environ.get('EXCEL_CASES','')
        if selected:
            names=selected.split(',')
            if any(name not in cases for name in names):raise SystemExit('Unknown EXCEL_CASES selection.')
            cases={name:cases[name] for name in names}
        for name,q in cases.items():
            content=export_excel(q).getvalue()
            if name=='changed-quantity':
                # Edit actual Excel input, not the server result/cache, before recalculation.
                workbook=load_workbook(io.BytesIO(content));sheet=workbook['Quotation']
                row=next(row[0].row for row in sheet if row[0].value=='Synthetic VM')
                sheet.cell(row,4,3);stream=io.BytesIO();workbook.save(stream);content=stream.getvalue()
                q['document']=public_document(validate_document(q['document']),retain_schema=True)
                q['document']['sections'][1]['rows'][0]['quantity']='3'
            (td/(name+'.xlsx')).write_bytes(content);expected[name]=calculate(q['document'])
        (td/'cache').mkdir()
        subprocess.run([executable,'-env:UserInstallation='+ (td/'profile').as_uri(),'--headless','--convert-to','xlsx','--outdir',str(output),*[str(p) for p in td.glob('*.xlsx')]],check=True,timeout=300,env={**os.environ,'XDG_CACHE_HOME':str(td/'cache')})
        for name,q in cases.items():
            workbook=load_workbook(output/(name+'.xlsx'),data_only=True)
            if name=='twelve-month-hidden':
                sheet=workbook['Quotation'];header=next(row[0].row for row in sheet if row[0].value=='Category');assert sheet.cell(header,6).value=='One-time (USD)';assert not any(cell.value=='12 months' for row in sheet for cell in row)
            for key in ('regular','discount','discounted','yearly','one_time','term','tax','combined'):
                # Stable summary order includes hidden technical dependency rows;
                # V5 deliberately omits their old customer-facing labels.
                labels=[x for x in q['document']['summary'] if x['key']!='sections']
                regular=next(row[0].row for row in workbook['Quotation'] if row[0].value=='Total monthly fee')
                first=regular-next(i for i,x in enumerate(labels) if x['key']=='regular')
                index=first+next(i for i,x in enumerate(labels) if x['key']==key)
                actual=workbook['Quotation'].cell(index,7).value
                wanted=expected[name][key]
                assert (actual in (None,'') if wanted is None else Decimal(str(actual))==Decimal(wanted)),(name,key,actual,wanted)
            print('PASS independent Excel recalculation:',name)


if __name__=='__main__':run()
