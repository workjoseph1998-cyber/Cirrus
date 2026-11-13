"""Customer-only XLSX: formulas, editable drivers and cached exact results.

No internal columns or hidden confidential sheets. Excel recalculates after edits.
"""
import base64
import io
import math
import textwrap
import zipfile
import xml.etree.ElementTree as ET
from decimal import Decimal
from openpyxl import Workbook
from openpyxl.cell.rich_text import CellRichText,TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.drawing.image import Image
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.pagebreak import Break
from openpyxl.worksheet.datavalidation import DataValidation
from .quotation import calculate, validate_document, discount_wording,public_document,is_support
from .model import ValidationError
from .quotation_presentation import EXCEL_DOLLARS,column_heading,fee_heading
from .optional_services import section_ids as optional_sections


def export_excel(q):
    original=validate_document(q['document'], enforce_minimum=True);c=calculate(original)
    support_ids={r['id'] for s in original['sections'] for r in s['rows'] if is_support(r,s)}
    d=public_document(original,c,retain_schema=True)
    for section in d['sections']:
        for row in section['rows']:
            if row.get('dr_mode'):row['comments']+='\n'+('VM Replication' if row['dr_mode']=='replication' else 'Running')
    numeric=[v for key,v in c.items() if key not in ('optional','rows','sections','sections_once','sections_yearly') and v is not None]
    for section in d['sections']:
        for row in section['rows']:
            numeric.extend(row[k] for k in ('quantity','unit_price','fixed_fee','percent','discount') if row[k]!='')
    numeric += [d['tax']['rate'],d['discount']['percent']]+[c['optional'][k] for k in ('monthly','yearly','one_time') if c['optional'][k] is not None]
    if any(len(Decimal(v).normalize().as_tuple().digits)>15 or abs(Decimal(v))>=Decimal('10000000000000') for v in numeric):
        raise ValidationError('Excel cannot faithfully represent these large/high-precision values. Use PDF, or keep inputs within 15 significant digits and totals below 10 trillion.')
    book=Workbook();ws=book.active;ws.title='Quotation';settings=book.create_sheet('Pricing settings')
    book.calculation.fullCalcOnLoad=True
    ws.page_setup.orientation=d['format']['orientation'];ws.page_setup.paperSize=ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0;ws.sheet_properties.pageSetUpPr.fitToPage=True
    ws.print_title_rows='1:8'
    ws.sheet_view.showGridLines=False;ws.freeze_panes='A9'
    widths=[23,29,20,14,24,20,24,45]
    for i,width in enumerate(widths,1): ws.column_dimensions[chr(64+i)].width=width
    ws.merge_cells('A1:H1');ws['A1']='Quotation';ws['A1'].fill=PatternFill('solid',fgColor='5B9BD5');ws.row_dimensions[1].height=20;ws['A1'].font=Font(name=d['format']['font'],bold=True,size=16);ws['A1'].alignment=Alignment(horizontal='center')
    ws.merge_cells('A2:A4')
    for row,label,value in [(2,'Messrs.',q['customer']),(3,'Contact',q['contact']),(4,'Project',d['project_name'])]:
        ws.cell(row,2,label);ws.cell(row,2).fill=PatternFill('solid',fgColor='A6A6A6');ws.cell(row,2).font=Font(bold=True,color='FFFFFF')
        ws.merge_cells(start_row=row,start_column=3,end_row=row,end_column=5);ws.cell(row,3,value)
    for row,label,value in [(2,'Date',q['date']),(3,'Ref',q['number'])]:
        ws.cell(row,6,label);ws.cell(row,6).fill=PatternFill('solid',fgColor='A6A6A6');ws.cell(row,6).font=Font(bold=True,color='FFFFFF')
        ws.merge_cells(start_row=row,start_column=6,end_row=row,end_column=7);ws.cell(row,8,value)
    if d['branding']['logo']:
        image=Image(io.BytesIO(base64.b64decode(d['branding']['logo'].split(',',1)[1])));scale=min(135/image.width,54/image.height);image.width*=scale;image.height*=scale;ws.add_image(image,'A2')
    ws['H5']='Currency: '+q['currency']
    ws.merge_cells('A6:H6');ws['A6']=d['banner'];ws.merge_cells('A7:H7');ws['A7']=q.get('scope','')
    cols={x['key']:x for x in d['columns']}
    keys=['service','sub_service','type','quantity','pricing_model','unit_price','amount','comments']
    for index,key in enumerate(keys,1):
        ws.cell(8,index,column_heading(d,key));ws.column_dimensions[chr(64+index)].hidden=not cols[key]['visible']
    for row in ws.iter_rows(min_row=1,max_row=8):
        for cell in row:
            if isinstance(cell.value,str): cell.data_type='s'
    settings.append(['Customer-visible calculation drivers','Value'])
    for label,value in [('Contract months',d['contract_months']),('Discount months',int(c['discount_months'])),('Discount percent',float(d['discount']['percent']) if d['discount']['enabled'] else 0),('Tax percent',float(d['tax']['rate'])),('Tax mode',d['tax']['mode'])]: settings.append([label,value])
    settings.append(['Discount kind',d['discount']['kind'] if d['discount']['enabled'] else 'percent'])
    settings.append(['Fixed total discount budget',float(d['discount']['amount']) if d['discount']['enabled'] else 0])
    settings.append(['Discount billing scope',d['discount']['billing'] if d['discount']['enabled'] else 'none'])
    settings.append(['Discount basis','Eligible fees after line discounts; fixed amount is one total budget.'])
    settings.append(['Row / description','Line discount %','Method','Billing','State'])
    row_positions={};section_positions={};row_objects={};cache={};current=9;rendered={}
    def segments(value,width):
        lines=[]
        for line in str(value).split('\n'):
            lines.extend(textwrap.wrap(line,width=max(8,int(width)-2),replace_whitespace=False,drop_whitespace=False) or [''])
        return ['\n'.join(lines[i:i+18]) for i in range(0,len(lines),18)] or ['']
    ordered=[];category_headers={};category_footers={};spacers=[]
    for top in d['sections']:
        if top['parent']: continue
        if ordered: spacers.append(current);current+=1
        for section in [top]+[s for s in d['sections'] if s['parent']==top['id']]:
            ordered.append((top,section));section_positions[section['id']]=current;current+=1
            if not section['parent']:category_headers[top['id']]=current;current+=1
            for row in section['rows']:
                row_positions[row['id']]=current;row_objects[row['id']]=(row,section,top)
                values=[row['service'],row['sub_service'],row['type'],'',row['pricing_model'],'','',row['comments']+'\n'+row['billing']+' · '+row['state']+' · '+row['method']]
                chunks=[segments(value,widths[i]) if i in (0,1,2,4,7) else [''] for i,value in enumerate(values)]
                rendered[row['id']]=chunks
                current+=max(len(x) for x in chunks)
        category_footers[top['id']]=(current,current+1);current+=2
    def constant(row,col,value):
        cell=ws.cell(row,col)
        cell.value=value
        if isinstance(value,str): cell.data_type='s' # Never interpret user text as formula.
    for top,s in ordered:
        index=section_positions[s['id']];ws.merge_cells(start_row=index,start_column=1,end_row=index,end_column=8)
        constant(index,1,('Optional: ' if s['id'] in optional_sections(d) else '')+s['name']);ws.cell(index,1).fill=PatternFill('solid',fgColor='2F75B5' if s['parent'] else 'D9D9D9')
        ws.cell(index,1).font=Font(name=d['format']['font'],bold=True,size=12 if not s['parent'] else 10,color='B32222' if not s['parent'] else 'FFFFFF')
        ws.row_dimensions[index].hidden=s['hidden'] or top['hidden']
        if not s['parent']:
            header=category_headers[s['id']]
            for col,key in enumerate(keys,1):
                constant(header,col,column_heading(d,key,top));ws.cell(header,col).fill=PatternFill('solid',fgColor='BDD7EE')
            ws.row_dimensions[header].hidden=s['hidden']
        for r in s['rows']:
            n=row_positions[r['id']];ws.row_dimensions[n].hidden=s['hidden'] or top['hidden']
            driver=r['percent'] if r['method']=='percent' else r['fixed_fee'] if r['method']=='fixed' else r['unit_price']
            chunks=rendered[r['id']]
            for offset in range(max(len(x) for x in chunks)):
                ws.row_dimensions[n+offset].hidden=s['hidden'] or top['hidden']
                for col in range(1,9):
                    value=chunks[col-1][offset] if offset<len(chunks[col-1]) else ''
                    if offset==0 and col==4:value=float(r['quantity'])
                    if offset==0 and col==6:value=None if r['id'] in support_ids else float(driver) if driver!='' else None
                    constant(n+offset,col,value)
            ws.cell(n,6).number_format='0.00"%"' if r['method']=='percent' else EXCEL_DOLLARS
            ws.cell(n,7).number_format=EXCEL_DOLLARS
            settings.append([r['service']+' / '+r['sub_service'],float(r['discount']),r['method'],r['billing'],r['state']])
            r['_excel_discount_row']=settings.max_row
    def eligible(targets):
        result=set()
        for t in targets:
            if t.startswith('r:'): result.add(t[2:]);continue
            sid=t[2:];sids={sid}|{s['id'] for s in d['sections'] if s['parent']==sid}
            result.update(i for i,(r,s,top) in row_objects.items() if s['id'] in sids)
        return result
    helper_cache={}
    def add_refs(ids):
        refs=[f'G{row_positions[i]}' for i in sorted(ids)]
        if not refs:return '0'
        if len(refs)>100:
            signature=tuple(refs)
            if signature not in helper_cache:
                helpers=[]
                for offset in range(0,len(refs),100):
                    part=["'Quotation'!"+r for r in refs[offset:offset+100]]
                    index=settings.max_row+1
                    settings.cell(index,6,'=IF(COUNT('+','.join(part)+')='+str(len(part))+',SUM('+','.join(part)+'),"")')
                    helpers.append(f"'Pricing settings'!F{index}")
                helper_cache[signature]=helpers
            refs=helper_cache[signature]
        # Explicit ISNUMBER tests preserve unpriced versus zero and avoid SUM skipping blanks.
        return 'IF(AND('+','.join('ISNUMBER('+x+')' for x in refs)+'),SUM('+','.join(refs)+'),"")'
    def formula(n,expression,value,col=7):
        ws.cell(n,col,'='+expression);cache[f'{chr(64+col)}{n}']=value
        ws.cell(n,col).number_format=EXCEL_DOLLARS
    for ident,(r,s,top) in row_objects.items():
        n=row_positions[ident]
        if ident in support_ids:
            ws.cell(n,7,None if c['rows'][ident] is None else Decimal(c['rows'][ident]));continue
        discount=f"'Pricing settings'!B{r['_excel_discount_row']}"
        rate=''
        if r.get('dr_mode'):
            rate_row=settings.max_row+1;settings.append(['DR applied percentage: '+r['sub_service'],float(r['dr_percent'])])
            rate="*'Pricing settings'!B"+str(rate_row)+'/100'
            if r.get('dr_link') and not r.get('dr_override'):
                formula(n,'F'+str(row_positions[r['dr_link']]),r['unit_price'],6)
        if Decimal(r.get('minimum_quantity','0'))>0:
            validation=DataValidation(type='decimal',operator='greaterThanOrEqual',formula1=r['minimum_quantity'],allow_blank=False)
            validation.errorTitle='Minimum bundle';validation.error='Minimum quantity: '+r['minimum_quantity'];validation.showErrorMessage=True;validation.errorStyle='stop';ws.add_data_validation(validation);validation.add(ws.cell(n,4))
        if r['state'] in ('excluded','included') or s['excluded'] or top['excluded']: expression='0'
        else:
            if r['method']=='unit': raw=f'IF(ISNUMBER(F{n}),D{n}*F{n}'+rate+',"")'
            elif r['method']=='fixed': raw=f'IF(ISNUMBER(F{n}),F{n},"")'
            else:
                base=add_refs(eligible(r['targets']));raw=f'IF(ISNUMBER({base}),({base})*F{n}/100,"")'
            # Round the row amount once after its optional line discount.
            expression=f'IF(D{n}=0,0,IF(ISNUMBER({raw}),ROUND(({raw})*(1-{discount}/100),2),""))'
        formula(n,expression,c['rows'][ident])
    optional=set(c['optional']['rows'])
    monthly={i for i,(r,_,_) in row_objects.items() if r['billing']=='monthly' and i not in optional};once=set(row_objects)-monthly-optional
    for top in d['sections']:
        if top['parent']:continue
        ids={i for i,(r,s,_) in row_objects.items() if s['id']==top['id'] or s['parent']==top['id']}
        for index,period,selected,value in [(category_footers[top['id']][0],'monthly',ids&monthly,c['sections'][top['id']]),(category_footers[top['id']][1],'one-time',ids&once,c['sections_once'][top['id']])]:
            ws.merge_cells(start_row=index,start_column=1,end_row=index,end_column=6)
            constant(index,1,('Optional: ' if top['id'] in optional_sections(d) else '')+top['name']+' — '+period+' subtotal')
            if top['id'] in optional_sections(d):
                selected=ids&optional&{i for i,(r,_,_) in row_objects.items() if r['billing']==('monthly' if period=='monthly' else 'one_time')}
                value=c['optional']['sections'][top['id']]['monthly' if period=='monthly' else 'one_time']
            formula(index,add_refs(selected),value)
            totals=c['optional']['sections'][top['id']] if top['id'] in optional_sections(d) else dict(monthly=c['sections'][top['id']],one_time=c['sections_once'][top['id']])
            both_zero=all(v is not None and Decimal(v)==0 for v in totals.values())
            hide_zero=(value is not None and Decimal(value)==0 and (not both_zero or period=='one-time'))
            if both_zero and period=='monthly':constant(index,1,top['name']+' — Total')
            ws.row_dimensions[index].hidden=top['hidden'] or hide_zero
            for cell in ws[index]:cell.fill=PatternFill('solid',fgColor='E8EFF4')
    summary_start=current+1;ws.merge_cells(start_row=summary_start,start_column=1,end_row=summary_start,end_column=8);constant(summary_start,1,d['summary_title'])
    ws.cell(summary_start,1).fill=PatternFill('solid',fgColor='5B9BD5')
    positions={};n=summary_start+1
    for col,label in [(1,'Category'),(4,fee_heading(d,'monthly')),*([(5,str(min(12,d['contract_months']))+' months')] if d['show_12_month'] else []),(7 if d['show_12_month'] else 6,fee_heading(d,'one_time'))]:constant(n,col,label)
    if not d['show_12_month']:
        ws.merge_cells(start_row=n,start_column=1,end_row=n,end_column=3);ws.merge_cells(start_row=n,start_column=4,end_row=n,end_column=5);ws.merge_cells(start_row=n,start_column=6,end_row=n,end_column=8)
    n+=1
    # All totals exist for formula dependencies; unselected summary lines are hidden.
    labels={x['key']:x for x in d['summary']}
    section_summary={}
    for s in d['sections']:
        if s['parent'] or s['id'] in optional_sections(d):continue
        constant(n,1,s['name']);section_summary[s['id']]=n
        ids={i for i,(r,section,_) in row_objects.items() if section['id']==s['id'] or section['parent']==s['id']}&monthly
        formula(n,add_refs(ids),c['sections'][s['id']],4)
        if d['show_12_month']:formula(n,f'IF(ISNUMBER(D{n}),D{n}*MIN(12,\'Pricing settings\'!B2),"")' ,c['sections_yearly'][s['id']],5)
        formula(n,add_refs({i for i,(r,section,_) in row_objects.items() if section['id']==s['id'] or section['parent']==s['id']} & once),c['sections_once'][s['id']],7 if d['show_12_month'] else 6)
        if not d['show_12_month']:
            ws.merge_cells(start_row=n,start_column=1,end_row=n,end_column=3);ws.merge_cells(start_row=n,start_column=4,end_row=n,end_column=5);ws.merge_cells(start_row=n,start_column=6,end_row=n,end_column=8)
        ws.row_dimensions[n].hidden=s['hidden'];n+=1
    for x in d['summary']:
        if x['key']=='sections':continue
        positions[x['key']]=n;constant(n,1,x['label'] if x['key'] in ('regular','one_time') else '');ws.row_dimensions[n].hidden=not x['visible'] or x['key'] not in ('regular','one_time');n+=1
    # Retain the original dependency order for older exports; Version 8 helpers
    # follow it. Every technical dependency is hidden, never a displayed contract
    # / tax / combined summary row.
    extras=('original_one_time','one_time_discount','recurring_discount_total','discount_final','discounted_final','discount_months','discount_extra_months','eligible_monthly','eligible_once','discount_basis')
    for name in extras:
        positions[name]=n;ws.row_dimensions[n].hidden=True;n+=1
    ref=lambda key:f'G{positions[key]}'
    rate="'Pricing settings'!B4";months="'Pricing settings'!B2";duration="'Pricing settings'!B3";taxrate="'Pricing settings'!B5"
    kind="'Pricing settings'!B7";budget="'Pricing settings'!B8";billing="'Pricing settings'!B9"
    regular=add_refs(monthly)
    em=add_refs(eligible(d['discount']['targets'])&monthly);eo=add_refs(eligible(d['discount']['targets'])&once)
    E=ref('eligible_monthly');O=ref('eligible_once');B=ref('discount_basis');R=ref('recurring_discount_total')
    expressions={'regular':regular,'original_one_time':add_refs(once),
        'eligible_monthly':f'IF(AND(OR({billing}="monthly",{billing}="both"),{duration}>0),{em},0)',
        'eligible_once':f'IF(OR({billing}="one_time",{billing}="both"),{eo},0)',
        'discount_months':duration,
        'discount_basis':f'IF(AND(ISNUMBER({E}),ISNUMBER({O})),{E}*{duration}+{O},"")'}
    expressions['recurring_discount_total']=f'IF({kind}="fixed",IF({budget}=0,0,IF(ISNUMBER({B}),IF({B}=0,0,ROUND(MIN(ROUND({budget},2),{B})*{E}*{duration}/{B},2)),"")),IF({rate}=0,0,IF(ISNUMBER({E}),ROUND({E}*{rate}/100,2)*{duration},"")))'
    expressions['one_time_discount']=f'IF({kind}="fixed",IF({budget}=0,0,IF(ISNUMBER({B}),MIN(ROUND({budget},2),{B})-{R},"")),IF({rate}=0,0,IF(ISNUMBER({O}),ROUND({O}*{rate}/100,2),"")))'
    expressions['discount_final']=f'IF({duration}=0,0,IF(ISNUMBER({R}),IF({kind}="fixed",ROUNDDOWN({R}/{duration},2),{R}/{duration}),""))'
    expressions['discount_extra_months']=f'IF(AND(ISNUMBER({R}),ISNUMBER({ref("discount_final")})),ROUND(({R}-{ref("discount_final")}*{duration})*100,0),0)'
    expressions['discount']=f'IF(ISNUMBER({ref("discount_final")}),{ref("discount_final")}+IF({ref("discount_extra_months")}>0,0.01,0),"")'
    for name,driver in [('discounted','discount'),('discounted_final','discount_final')]:
        expressions[name]=f'IF(AND(ISNUMBER({ref("regular")}),ISNUMBER({ref(driver)})),{ref("regular")}-{ref(driver)},"")'
    expressions['one_time']=f'IF(AND(ISNUMBER({ref("original_one_time")}),ISNUMBER({ref("one_time_discount")})),{ref("original_one_time")}-{ref("one_time_discount")},"")'
    expressions['run_rate']=f'IF(ISNUMBER({ref("regular")}),{ref("regular")}*12,"")'
    def recurring(m):
        return f'IF(AND(ISNUMBER({ref("regular")}),ISNUMBER({R})),{ref("regular")}*({m})-{ref("discount_final")}*MIN({m},{duration})-MIN(MIN({m},{duration}),{ref("discount_extra_months")})*0.01,"")'
    expressions['term']=recurring(months);expressions['yearly']=recurring(f'MIN(12,{months})')
    base=f'({ref("term")}+{ref("one_time")})';valid=f'AND(ISNUMBER({ref("term")}),ISNUMBER({ref("one_time")}))'
    tax_formula=f'{base}*{taxrate}/100'+(f'/(1+{taxrate}/100)' if d['tax']['mode']=='included' else '')
    expressions['tax']=f'IF({valid},ROUND({tax_formula},2),"")'
    expressions['combined']=f'IF({valid},{base}'+(f'+{ref("tax")}' if d['tax']['mode']=='added' else '')+',"")'
    from .summary_discounts import apply
    raw={i:None if c['rows'][i] is None else Decimal(c['rows'][i]) for i in row_objects}
    policy=apply(d,raw,monthly,once,eligible(d['discount']['targets']))
    def net(ids):return None if any(raw[i] is None for i in ids) else str(sum((raw[i] for i in ids),Decimal(0)))
    helpers={'eligible_monthly':net(policy['recurring_ids']),'eligible_once':net(policy['once_ids'])}
    helpers['discount_basis']=None if helpers['eligible_monthly'] is None or helpers['eligible_once'] is None else str(Decimal(helpers['eligible_monthly'])*policy['months']+Decimal(helpers['eligible_once']))
    for key,index in positions.items():formula(index,expressions[key],c.get(key,helpers.get(key)))
    show=d['discount']['enabled'] and d['discount']['show_summary']
    if show:
        for index in positions.values():ws.row_dimensions[index].hidden=True
        def visible_total(label,key,style=''):
            nonlocal n
            constant(n,1,label);ws.merge_cells(start_row=n,start_column=1,end_row=n,end_column=6)
            formula(n,ref(key),c[key]);ws.cell(n,7).number_format=EXCEL_DOLLARS
            if style=='monthly':
                for cell in ws[n]:
                    cell.fill=PatternFill('solid',fgColor='C00000')
                    cell.font=Font(name=d['format']['font'],size=12.3 if d['format']['size']=='large' else 10.1,bold=True,color='FFFFFF')
            elif style=='once':
                for cell in ws[n]:cell.fill=PatternFill('solid',fgColor='FFF2CC');cell.font=Font(name=d['format']['font'],size=12.3 if d['format']['size']=='large' else 10.1,bold=True,color='172638')
            elif style=='discount':
                for cell in ws[n]:cell.fill=PatternFill('solid',fgColor='FFF1DF');cell.font=Font(name=d['format']['font'],bold=True,color='B54B00')
            n+=1
        if d['discount']['billing'] in ('monthly','both'):
            visible_total('Original monthly fee','regular')
            visible_total('Discount per promotional month (deduction)','discount','discount')
            tier='first '+c['discount_extra_months']+' months' if int(c['discount_extra_months']) else c['discount_months']+' months'
            visible_total('Total monthly fee · promotional · '+tier,'discounted','monthly')
            if int(c['discount_extra_months']):visible_total('Total monthly fee · months '+str(int(c['discount_extra_months'])+1)+'–'+c['discount_months'],'discounted_final','monthly')
            if int(c['discount_months'])<d['contract_months']:visible_total('Regular monthly fee afterward · month '+str(int(c['discount_months'])+1)+' onward','regular','monthly')
        else:visible_total('Total monthly fee','regular','monthly')
        if d['discount']['billing'] in ('one_time','both'):
            visible_total('Original one-time fee','original_one_time');visible_total('One-time discount (deduction)','one_time_discount','discount')
        visible_total('Total one-time fee','one_time','once')
        description=discount_wording(d)
        if description:
            ws.merge_cells(start_row=n,start_column=1,end_row=n,end_column=8);constant(n,1,description);ws.row_dimensions[n].height=max(24,12*math.ceil(len(description)/140));n+=1
    else:
        for key,style in [('regular','monthly'),('one_time','once')]:
            index=positions[key];ws.cell(index,7).number_format=EXCEL_DOLLARS
            for cell in ws[index]:
                cell.font=Font(name=d['format']['font'],size=12.3 if d['format']['size']=='large' else 10.1,bold=True,color='FFFFFF' if style=='monthly' else '172638')
                if style=='monthly':cell.fill=PatternFill('solid',fgColor='C00000')
                if style=='once':cell.fill=PatternFill('solid',fgColor='FFF2CC')
    if optional:
        n+=1;ws.merge_cells(start_row=n,start_column=1,end_row=n,end_column=3);constant(n,1,c['optional']['label'])
        for col,key,suffix in [(4,'monthly',' / month'),(5,'yearly',' / year (12 months)'),(7,'one_time',' one-time')]:
            ids=optional&({i for i,(r,_,_) in row_objects.items() if r['billing']=='monthly'} if key!='one_time' else {i for i,(r,_,_) in row_objects.items() if r['billing']=='one_time'})
            expression=add_refs(ids)
            if key=='yearly':expression=f'IF(ISNUMBER({expression}),({expression})*12,"")'
            formula(n,expression,c['optional'][key],col);ws.cell(n,col).number_format=EXCEL_DOLLARS+'"'+suffix+'"'
        for cell in ws[n]:cell.fill=PatternFill('solid',fgColor='FFF2A8');cell.font=Font(name=d['format']['font'],bold=True,color='172638')
        ws.row_dimensions[n].height=32
    mode=d['tax']['mode'];n+=1
    text='Prices exclude VAT; tax estimate is not added.' if mode=='exclusive' else 'Tax is added to the contract total.' if mode=='added' else 'Prices include tax; tax shown is included.'
    blocks=[]
    for key in d['bottom_order']:
        t=next((t for t in d['terms'] if t['id']==key),None)
        if t and t['visible']:blocks.append((t['title'],t['text']))
        elif key in ('company_signature','customer_signature'):blocks.append((d[key]['heading'],d[key]['fields']))
        elif key=='footer':blocks.append((d['branding']['company'],'\n'.join([d['branding']['address'],d['branding']['contact'],'VAT No. '+d['branding']['vat']])))
    for title,text in blocks:
        if not text:continue
        ws.merge_cells(start_row=n,start_column=1,end_row=n,end_column=8);constant(n,1,title);ws.cell(n,1).font=Font(bold=True);n+=1
        # Split long text into modest rows so Excel does not clip at its 409-point row-height limit.
        for paragraph in text.split('\n'):
            for offset in range(0,max(1,len(paragraph)),900):
                chunk=paragraph[offset:offset+900];ws.merge_cells(start_row=n,start_column=1,end_row=n,end_column=8);constant(n,1,chunk)
                ws.row_dimensions[n].height=max(15,12*math.ceil(len(chunk)/170));n+=1
    border=Border(*[Side(style='thin',color='888888')]*4)
    for row in ws:
        for cell in row:
            cell.alignment=Alignment(vertical='top',wrap_text=True,horizontal='center' if cell.coordinate=='A1' else None)
            cell.border=border
            if not cell.font.bold:cell.font=Font(name=d['format']['font'],size=11 if d['format']['size']=='large' else 9)
            if cell.data_type!='f' and isinstance(cell.value,str):
                cell.data_type='s'
                if cell.column==8 and 'VM Replication' in cell.value:
                    before,label,after=cell.value.partition('VM Replication')
                    cell.value=CellRichText(before,TextBlock(InlineFont(color='C00000'),label),after)
        if row[0].row>=9 and row[0].row<summary_start:
            lines=max([max((math.ceil(len(part)/max(8,int(widths[i])-2)) for part in str(x.value or '').split('\n')),default=1)+str(x.value or '').count('\n') for i,x in enumerate(row[:8])])
            ws.row_dimensions[row[0].row].height=min(400,max(15,lines*12))
    for col in 'ABCDEFGH':ws[f'{col}8'].fill=PatternFill('solid',fgColor='BDD7EE')
    settings.column_dimensions['A'].width=55
    settings.column_dimensions['B'].width=22
    for row in settings:
        for cell in row:
            if isinstance(cell.value,str) and not (cell.column==6 and cell.data_type=='f'):cell.data_type='s'
    settings.append(['Export notes', 'F in Quotation is the row driver: unit price, fixed fee or percentage.'])
    settings.append(['Structure', 'Method, billing, state and eligibility are snapshots. Change them in the app and re-export.'])
    settings.append(['Layout', 'Excel keeps the eight canonical template columns; edited labels and visibility are preserved. Column order follows the app in PDF/print only.'])
    settings.append(['Summary', 'Hidden summary lines remain as hidden formula dependencies.'])
    for row in spacers:
        ws.row_dimensions[row].height=18
        for cell in ws[row]:cell.border=Border()
    ws.print_area=f'A1:H{n}'
    # Cache server's exact results: openpyxl itself cannot evaluate Excel formulas.
    out=io.BytesIO();book.save(out)
    source=zipfile.ZipFile(io.BytesIO(out.getvalue()));result=io.BytesIO()
    ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with source,zipfile.ZipFile(result,'w',zipfile.ZIP_DEFLATED) as archive:
        for entry in source.infolist():
            content=source.read(entry.filename)
            if entry.filename=='xl/worksheets/sheet1.xml':
                root=ET.fromstring(content)
                for cell in root.findall('.//m:c',ns):
                    if cell.attrib.get('r') in cache:
                        val=cache[cell.attrib['r']];v=cell.find('m:v',ns)
                        if v is None:v=ET.SubElement(cell,'{'+ns['m']+'}v')
                        if val is None:cell.set('t','str');v.text=''
                        else:cell.attrib.pop('t',None);v.text=val
                content=ET.tostring(root,encoding='utf-8')
            archive.writestr(entry,content)
    result.seek(0);return result
