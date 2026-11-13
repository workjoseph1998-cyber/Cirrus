"""Small shared, server-side pagination for permission-filtered listing results."""
from math import ceil
from urllib.parse import urlencode
from flask import request
from .model import ValidationError

def paginate(rows):
    try:size=int(request.args.get('per_page','25'));page=int(request.args.get('page','1'))
    except ValueError:raise ValidationError('Use a valid page and 25, 50 or 100 rows.') from None
    if size not in (25,50,100) or page<1:raise ValidationError('Use a valid page and 25, 50 or 100 rows.')
    pages=max(1,ceil(len(rows)/size));page=min(page,pages)
    return rows[(page-1)*size:page*size],dict(total=len(rows),page=page,pages=pages,size=size,links=[dict(page=n,url=request.path+'?'+urlencode(dict(request.args,page=n))) for n in range(max(1,page-2),min(pages,page+2)+1)])
