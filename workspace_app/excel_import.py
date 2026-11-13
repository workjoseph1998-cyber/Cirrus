"""Conservative Cirrus-layout reader: parses whitelisted formulas, never evaluates Excel."""
import copy,hashlib,io,json,re,zipfile
from defusedxml.ElementTree import iterparse
from datetime import date,datetime
from decimal import Decimal
from openpyxl import load_workbook
from openpyxl.utils.cell import column_index_from_string,get_column_letter
from .model import FIELDS,ValidationError
from .quotation import default_document,new_row,new_section,calculate,validate_document

MAX_BYTES=10*1024*1024
HEADERS={'service':'service','sub service':'sub_service','type':'type','pricing model':'pricing_model','comments':'comments'}
TOPS=('Production','Disaster Recovery','Monitoring','Cyber Security','Connectivity Services','Connectivity Setup')


def load(raw):
    if len(raw)>MAX_BYTES:raise ValidationError('Workbook exceeds 10 MiB.')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            infos=z.infolist()
            if len(infos)>3000 or sum(i.file_size for i in infos)>50*1024*1024 or any(i.file_size>20*1024*1024 for i in infos):raise ValidationError('Workbook archive expansion exceeds limits.')
            if len({i.filename for i in infos})!=len(infos):raise ValidationError('Duplicate ZIP entries.')
            if any('vbaproject' in i.filename.casefold() or 'externallinks/' in i.filename.casefold() or '/embeddings/' in i.filename.casefold() or '/activex/' in i.filename.casefold() or '/macrosheets/' in i.filename.casefold() for i in infos):raise ValidationError('Macros and external workbook links are not supported.')
            if any(i.file_size>1000*max(i.compress_size,1) for i in infos):raise ValidationError('Suspicious workbook compression ratio.')
            # Bound worksheet objects before openpyxl allocates them. Declared
            # dimensions alone are insufficient: malformed files can understate them.
            cells=0;merged_cells=0
            sheets=[i for i in infos if re.fullmatch(r'xl/worksheets/[^/]+\.xml',i.filename)]
            if len(sheets)>20:raise ValidationError('Workbook exceeds 20 worksheets.')
            for info in sheets:
                merges=0
                with z.open(info) as stream:
                    for _,element in iterparse(stream,events=('end',)):
                        tag=element.tag.rsplit('}',1)[-1]
                        if tag=='c':
                            cells+=1
                            address=element.get('r','')
                            if cells>100000:raise ValidationError('Workbook exceeds 100,000 cells.')
                            match=re.fullmatch(r'([A-Z]+)([1-9][0-9]*)',address)
                            if not match or len(match[1])>2 or column_index_from_string(match[1])>64 or int(match[2])>5000:raise ValidationError('Worksheet cell address exceeds limits.')
                        elif tag=='mergeCell':
                            merges+=1
                            if merges>2000:raise ValidationError('Worksheet exceeds 2,000 merges.')
                            span=element.get('ref','')
                            endpoints=[]
                            for address in span.split(':'):
                                match=re.fullmatch(r'([A-Z]+)([1-9][0-9]*)',address)
                                if not match or len(match[1])>2 or column_index_from_string(match[1])>64 or int(match[2])>5000:raise ValidationError('Merged range exceeds worksheet limits.')
                                endpoints.append((column_index_from_string(match[1]),int(match[2])))
                            if len(endpoints) not in (1,2):raise ValidationError('Invalid merged range.')
                            merged_cells+=(abs(endpoints[-1][0]-endpoints[0][0])+1)*(abs(endpoints[-1][1]-endpoints[0][1])+1)
                            if merged_cells>100000:raise ValidationError('Expanded merged cells exceed 100,000.')
                        element.clear()

        book=load_workbook(io.BytesIO(raw),data_only=False,keep_links=False)
        cached=load_workbook(io.BytesIO(raw),data_only=True,keep_links=False)
        if len(book.worksheets)>20 or sum(s.max_row*s.max_column for s in book)>100000:raise ValidationError('Workbook exceeds worksheet/cell-count limits.')
        if any(s.max_row>5000 or s.max_column>64 or len(s.merged_cells.ranges)>2000 for s in book):raise ValidationError('Worksheet dimensions exceed 5000 rows / 64 columns.')
        text_size=0
        for sheet in book:
            for row in sheet.iter_rows():
                for cell in row:
                    if isinstance(cell.value,str):
                        if len(cell.value)>100000:raise ValidationError('A workbook text cell exceeds 100,000 characters.')
                        text_size+=len(cell.value)
                        if text_size>5000000:raise ValidationError('Expanded workbook text exceeds 5 million characters.')
        return book,cached
    except ValidationError:raise
    except Exception:raise ValidationError('Not a supported .xlsx workbook.') from None


def mapping_for(sheet):
    columns={};header=None
    for row in sheet.iter_rows(max_row=min(sheet.max_row,100)):
        found={}
        for cell in row:
            value=str(cell.value or '').strip().casefold()
            if value in HEADERS:found[HEADERS[value]]=cell.column_letter
            elif 'unit price' in value:found['unit_price']=cell.column_letter
            elif 'monthly fee' in value or 'one-time fee' in value or 'one time fee' in value:found['amount']=cell.column_letter
            elif value.startswith(('number of','quantity')):found['quantity']=cell.column_letter
        if {'service','sub_service','type','unit_price','amount','quantity'}<=found.keys():columns=found;header=row[0].row;break
    if not columns:raise ValidationError('Unsupported layout: Cirrus service columns were not detected. Supply a supported Cirrus-layout workbook.')
    columns.setdefault('comments','H');columns.setdefault('pricing_model','E')
    return {'columns':columns,'header_row':header,'headers':{'customer':'C2','contact':'C3','project':'C4','date':'H2','reference':'H3'},
            'section_rows':{},'group_rows':{},'skip_rows':[]}


def scalar(value):
    if isinstance(value,(int,float,Decimal)) and not isinstance(value,bool):return str(value)
    return ''


def parse(raw,sheet_name=None,mapping=None):
    book,cached=load(raw)
    if sheet_name is None:sheet_name=book.sheetnames[0]
    if sheet_name not in book.sheetnames:raise ValidationError('Worksheet does not exist.')
    sheet=book[sheet_name];cache=cached[sheet_name]
    mapping=copy.deepcopy(mapping or mapping_for(sheet))
    if not isinstance(mapping,dict) or set(mapping)!={'columns','header_row','headers','section_rows','group_rows','skip_rows'}:raise ValidationError('Invalid mapping fields.')
    cols=mapping['columns']
    if not isinstance(cols,dict) or set(cols)!={'service','sub_service','type','quantity','pricing_model','unit_price','amount','comments'}:raise ValidationError('Map all eight service columns.')
    if any(not isinstance(v,str) or not re.fullmatch('[A-Z]{1,2}',v) or column_index_from_string(v)>sheet.max_column for v in cols.values()) or len(set(cols.values()))!=8:raise ValidationError('Column mapping must use eight distinct A–BL columns.')
    if type(mapping['header_row']) is not int or not 1<=mapping['header_row']<=sheet.max_row:raise ValidationError('Invalid first header row.')
    for key in ('section_rows','group_rows'):
        if not isinstance(mapping[key],dict) or any(not str(k).isdigit() or not isinstance(v,str) or not v.strip() for k,v in mapping[key].items()):raise ValidationError('Invalid section/group row mapping.')
    if not isinstance(mapping['skip_rows'],list) or any(type(x) is not int for x in mapping['skip_rows']):raise ValidationError('Invalid skipped rows.')
    if not isinstance(mapping['headers'],dict) or set(mapping['headers'])!={'customer','contact','project','date','reference'}:raise ValidationError('Invalid header mapping.')
    for cell in mapping['headers'].values():
        if not isinstance(cell,str) or not re.fullmatch('[A-Z]{1,2}[1-9][0-9]{0,3}',cell) or column_index_from_string(re.sub('[0-9]','',cell))>sheet.max_column or int(re.sub('[A-Z]','',cell))>sheet.max_row:raise ValidationError('Invalid header cell.')
    doc=default_document();doc['sections']=[]
    q={k:'' for k,_,_ in FIELDS['quote']};q.update(title='Imported quotation',customer='',date=date.today().isoformat(),currency='USD',status='Draft',tax='0',number='IMPORT-PREVIEW',revision=1,lines=[],document=doc)
    issues=[];source_rows={};source_parents={};fee_formulas=[];top=None;group=None;zero_rows=[];summary_rows=[]
    def issue(text,rowid='',kind='review',source=''):
        issues.append({'id':str(len(issues)), 'text':text,'row_id':rowid,'kind':kind,'source':source})
    def value(row,key,merged=False):
        coordinate=cols[key]+str(row);v=sheet[coordinate].value
        if merged and v is None:
            for region in sheet.merged_cells.ranges:
                if coordinate in region and region.min_col==region.max_col:v=sheet.cell(region.min_row,region.min_col).value;break
        return v
    for field,cell in mapping['headers'].items():
        v=sheet[cell].value
        if isinstance(v,str) and v.startswith('='):
            v=cache[cell].value
            if v is None:issue('Header formula has no cached value: review '+field,source=cell)
        if field=='date':
            if isinstance(v,(date,datetime)):q['date']=v.date().isoformat() if isinstance(v,datetime) else v.isoformat()
            elif v:issue('Review imported date manually.',source=cell)
        elif field=='project':doc['project_name']=str(v or '')
        elif field=='reference':q['number']=str(v or 'IMPORT-PREVIEW')
        else:q[field]=str(v or '')
    for prior in range(1,mapping['header_row']):
        name=mapping['section_rows'].get(str(prior)) or str(sheet.cell(prior,column_index_from_string(cols['service'])).value or '').strip()
        if any(name.casefold().startswith(t.casefold()) for t in TOPS):
            top=new_section(name);doc['sections']=[top];group=top
    if top and top['name'].casefold().startswith(('production','disaster')):
        group=new_section('Compute and storage',top['id']);doc['sections'].append(group)
    for n in range(mapping['header_row']+1,sheet.max_row+1):
        if n in mapping['skip_rows']:continue
        vals={k:value(n,k,merged=k=='service') for k in cols};first=str(vals['service'] or '').strip()
        if first.casefold().startswith('cost summary'):summary_rows.append(n);break
        if first.casefold()=='service' or not any(v is not None for v in vals.values()):continue
        custom=mapping['section_rows'].get(str(n))
        numeric=scalar(vals['quantity'])
        is_top=custom or (first and not vals['sub_service'] and not vals['type'] and any(first.casefold().startswith(t.casefold()) for t in TOPS))
        if is_top:
            top=new_section(custom or first);doc['sections'].append(top);group=top
            if top['name'].casefold().startswith(('production','disaster')):
                group=new_section('Compute and storage',top['id']);doc['sections'].append(group)
            continue
        custom_group=mapping['group_rows'].get(str(n))
        if custom_group or (first and not vals['sub_service'] and not vals['type'] and not numeric and not str(vals['amount'] or '').startswith('=')):
            if not top:issue('Unmapped section/group before the first category; adjust section_rows mapping.',source='A'+str(n));continue
            group=new_section(custom_group or first,top['id']);doc['sections'].append(group);continue
        # Subtotals often put their label in D:F, not A. Never import those as services.
        if not first or (not vals['sub_service'] and not vals['type'] and not numeric):continue
        if not top:
            top=new_section('Imported services');doc['sections'].append(top);group=top
        billing='one_time' if 'one' in top['name'].casefold() and 'fee' in top['name'].casefold() else 'monthly'
        pricing=str(vals['pricing_model'] or '')
        unit='unit'
        for candidate in ('VM','TB','EPS','IP','agent','user','node','Mbps','collector','environment'):
            if re.search(r'\b'+candidate+r'\b',pricing,re.I):unit=candidate;break
        row=new_row(first,sub_service=str(vals['sub_service'] or ''),type=str(vals['type'] or ''),quantity=numeric or '1',
                    pricing_model=pricing if pricing not in ('-','x') else '',unit=unit,billing=billing,
                    unit_price=scalar(vals['unit_price']),comments=str(vals['comments'] or ''))
        group['rows'].append(row);source_rows[n]=row;source_parents[n]=top['id']
        if row['unit_price']=='0':zero_rows.append(row['id'])
        amount=vals['amount'];formula=str(amount).replace('$','').replace(' ','') if isinstance(amount,str) and amount.startswith('=') else None
        if formula:
            unit_pattern=re.fullmatch(r'=([A-Z]+)(\d+)\*([A-Z]+)(\d+)',formula)
            percent_pattern=re.fullmatch(r'=SUM\(([A-Z]+)(\d+):\1(\d+)\)\*((?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))',formula,re.I)
            if unit_pattern and unit_pattern[1] in (cols['quantity'],cols['unit_price']) and unit_pattern[3] in (cols['quantity'],cols['unit_price']) and unit_pattern[1]!=unit_pattern[3] and int(unit_pattern[2])==n and int(unit_pattern[4])==n:
                if row['unit_price']=='':issue('Unit formula has no literal unit price; resolve pricing.',row['id'],'price',cols['amount']+str(n))
            elif percent_pattern and percent_pattern[1].upper()==cols['amount']:
                rate=Decimal(percent_pattern[4])*100
                if not 0<=rate<=100:raise ValidationError('Unsupported percentage outside 0–100.')
                row.update(method='percent',percent=str(rate),quantity='1',unit_price='')
                fee_formulas.append((row,int(percent_pattern[2]),int(percent_pattern[3])))
            else:
                row.update(method='fixed',fixed_fee='',unit_price='')
                issue('Unsupported formula is not executed: '+formula,row['id'],'price',cols['amount']+str(n))
        elif scalar(amount)!='':
            # A hardcoded amount is treated as fixed, visibly flagged if pricing language suggests per-unit.
            row.update(method='fixed',fixed_fee=scalar(amount))
            if row['unit_price']!='' and numeric and Decimal(row['unit_price'])*Decimal(numeric)!=Decimal(str(amount)):
                issue('Hardcoded monthly fee disagrees with quantity × unit price; choose fixed or unit pricing.',row['id'],'price',cols['amount']+str(n))
            elif 'per ' in pricing.casefold():issue('Hardcoded fee with per-unit pricing wording: review calculation method.',row['id'],'review',cols['amount']+str(n))
        elif row['unit_price']=='':issue('Missing price; explicitly keep unpriced or resolve.',row['id'],'price',cols['unit_price']+str(n))
        if numeric=='':issue('Non-numeric quantity: review quantity (default activation 1 for fee rows).',row['id'],'review',cols['quantity']+str(n))
    if not doc['sections'] or not source_rows:raise ValidationError('No supported service rows detected. Review mapping or use a Cirrus quotation layout.')
    for row,start,end in fee_formulas:
        if not 1<=start<=end<=sheet.max_row:raise ValidationError('Unsupported formula range.')
        row['targets']=['r:'+r['id'] for n,r in source_rows.items() if start<=n<=end and r['id']!=row['id']]
    # Infer only the known temporary discount pattern; wording/duration is reviewed explicitly.
    discounted_sections=[s for s in doc['sections'] if not s['parent'] and s['name'].casefold().startswith(('production','disaster','monitoring'))]
    doc['discount']['targets']=['s:'+s['id'] for s in discounted_sections]
    doc['discount']['enabled']=False;doc['discount']['months']=0
    for row in sheet.iter_rows():
        label=str(row[0].value or '')
        if 'discount' in label.casefold() and ('six' in label.casefold() or '6 month' in label.casefold()):
            percent=re.search(r'(\d+(?:\.\d+)?)\s*%',label)
            if percent:doc['discount'].update(enabled=True,percent=percent[1],months=6)
    # Preserve terms/signatures in the new private draft, never in the global catalog.
    for n in range(1,sheet.max_row+1):
        a=str(sheet.cell(n,1).value or '')
        if 'prices provided' in a.casefold() or 'agreement' in a.casefold():
            doc['terms']=[{'id':'imported-terms','title':'Imported terms — review dates and conditions','text':a,'visible':True}]
            doc['bottom_order']=['imported-terms','company_signature','customer_signature','footer']
            issue('Imported legal/date-specific terms require review; they are not company-template updates.',source='A'+str(n))
            if sheet.cell(n,5).value:doc['company_signature']['fields']=str(sheet.cell(n,5).value)
            if sheet.cell(n,7).value:doc['customer_signature']['fields']=str(sheet.cell(n,7).value)
    calc=calculate(validate_document(doc))
    for n in range(mapping['header_row']+1,sheet.max_row+1):
        label=' '.join(str(sheet.cell(n,col).value or '') for col in range(1,7)).casefold()
        subtotal=str(value(n,'amount') or '').replace('$','').replace(' ','')
        match=re.fullmatch(r'=SUM\(([A-Z]+)([0-9]+):\1([0-9]+)\)',subtotal,re.I)
        before=[i for i in source_rows if i<n]
        if 'total monthly fee' in label and match and before:
            parent=source_parents[max(before)]
            missing=[i for i in before if source_parents[i]==parent and not int(match[2])<=i<=int(match[3])]
            if missing:issue('Spreadsheet subtotal omits service rows '+', '.join(map(str,missing))+'. Application category totals include every eligible row.',kind='summary',source=cols['amount']+str(n))
    if summary_rows:
        for n in range(summary_rows[0]+1,sheet.max_row+1):
            text=str(sheet.cell(n,1).value or '').casefold()
            if text.startswith('payment terms'):break
            if 'total monthly fee' in text:
                cached_total=cache.cell(n,4).value
                if isinstance(cached_total,(int,float)) and calc['discounted'] is not None and abs(Decimal(str(cached_total))-Decimal(calc['discounted']))>Decimal('.01'):
                    issue('Workbook monthly summary differs from recomputed totals. Application totals will be used.',kind='summary',source='D'+str(n))
                elif cached_total is None:issue('Workbook summary has no reliable cached monthly total; use recomputed application totals.',kind='summary',source='D'+str(n))
                if isinstance(sheet.cell(n,5).value,str) and sheet.cell(n,5).value.startswith('='):issue('Annual spreadsheet formulas are replaced by period-aware application totals. Review the discrepancy/discount period.',kind='summary',source='E'+str(n))
                yearly=cache.cell(n,5).value
                if isinstance(yearly,(int,float)) and calc['yearly'] is not None and abs(Decimal(str(yearly))-Decimal(calc['yearly']))>Decimal('.01'):
                    issue('Workbook yearly summary disagrees with the configured discount periods/application totals.',kind='summary',source='E'+str(n))
    semantic=hashlib.sha256(sheet.title.encode())
    for record in sheet.iter_rows():
        for cell in record:
            if cell.value is not None:semantic.update(json.dumps([cell.coordinate,cell.value],default=str,ensure_ascii=False).encode())
    semantic.update(str(sorted(str(x) for x in sheet.merged_cells.ranges)).encode())
    return {'quotation':q,'mapping':mapping,'issues':issues,'zero_rows':zero_rows,'sheet':sheet_name,'sheets':book.sheetnames,'fingerprint':semantic.hexdigest(),
            'source_preview':[{'row':i,'values':[str(sheet.cell(i,j).value or '')[:300] for j in range(1,min(sheet.max_column,12)+1)]} for i in range(1,min(sheet.max_row,120)+1)]}
