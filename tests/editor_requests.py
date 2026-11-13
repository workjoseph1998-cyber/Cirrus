"""Existing regression clients now submit the same stale-edit token as the editor."""
import re


def fields_for(client,path,fields):
    if re.fullmatch(r'/quotes/[^/]+/edit',path) and 'base_hash' not in fields:
        response=client.get(path)
        token=re.search(rb'name="base_hash" value="([^"]*)"',response.data)
        if token:fields=dict(fields,base_hash=token[1].decode())
    return fields
