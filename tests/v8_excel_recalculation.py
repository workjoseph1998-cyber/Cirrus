"""Independent Version 8 percentage/fixed-budget formulas; synthetic data only."""
import copy
from decimal import Decimal
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from openpyxl import load_workbook
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace_app.quote_excel import export_excel
from workspace_app.quotation import calculate
from test_v8 import discount_quote


def run():
    cases={}
    for kind,value in [('percent','10'),('fixed','50'),('fixed','9999')]:
        for billing in ('monthly','one_time','both'):
            for duration in ('full','temporary'):
                q=discount_quote(kind,value);q['document']['discount'].update(billing=billing,duration=duration);cases[f'{kind}-{value}-{billing}-{duration}']=q
    cases['disabled']=discount_quote();cases['disabled']['document']['discount'].update(enabled=False,wording='HIDDEN-DISCOUNT-WORDING')
    cases['included-tax']=discount_quote('fixed','50');cases['included-tax']['document']['tax'].update(mode='included',rate='11')
    cases['unpriced-fixed']=discount_quote('fixed','50');cases['unpriced-fixed']['document']['sections'][0]['rows'][0]['unit_price']=''
    cases['unpriced-percent-zero']=discount_quote('percent','0');cases['unpriced-percent-zero']['document']['sections'][0]['rows'][1]['unit_price']=''
    if os.environ.get('V8_EXCEL_CASES'):
        selected=set(os.environ['V8_EXCEL_CASES'].split(','));cases={k:v for k,v in cases.items() if k in selected}
    with tempfile.TemporaryDirectory() as td:
        td=Path(td);out=td/'out';out.mkdir();expected={};positions={}
        keys=('regular','discount','discounted','yearly','run_rate','one_time','term','tax','combined','original_one_time','one_time_discount','recurring_discount_total','discount_final','discounted_final','discount_months','discount_extra_months')
        for name,q in cases.items():
            content=export_excel(q).getvalue();expected[name]=calculate(q['document'])
            # The original nine dependencies keep their order before extra helpers.
            w=load_workbook(io.BytesIO(content));sheet=w['Quotation'];header=next(row[0].row for row in sheet if row[0].value=='Cost Summary');first=header+2+len([s for s in q['document']['sections'] if not s['parent']])
            positions[name]={key:first+i for i,key in enumerate(keys)}
            # Invalidate every formula cache: verification must evaluate formulas,
            # not accept the server's cached numbers.
            w.save(td/(name+'.xlsx'))
        exe=shutil.which('soffice') or shutil.which('libreoffice')
        if not exe:raise RuntimeError('LibreOffice required for independent verification.')
        (td/'cache').mkdir()
        # Small sequential batches keep conversion memory bounded.
        for offset in range(0,len(cases),6):
            names=list(cases)[offset:offset+6]
            subprocess.run([exe,'-env:UserInstallation='+(td/'profile').as_uri(),'--headless','--convert-to','xlsx','--outdir',str(out),*[str(td/(n+'.xlsx')) for n in names]],check=True,timeout=180,stdout=subprocess.DEVNULL,env={**os.environ,'XDG_CACHE_HOME':str(td/'cache')})
        for name in cases:
            w=load_workbook(out/(name+'.xlsx'),data_only=True)
            for key,index in positions[name].items():
                actual=w['Quotation'].cell(index,7).value;wanted=expected[name][key]
                assert (actual in ('',None) if wanted is None else actual is not None and Decimal(str(actual))==Decimal(wanted)),(name,key,actual,wanted)
            print('PASS Version 8 independent formulas:',name)

if __name__=='__main__':run()
