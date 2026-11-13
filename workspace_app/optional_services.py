"""Monitoring selection uses saved section IDs; included fees exclude optional bases."""
import re

LABEL='Optional: Monitoring - 24×7 NOC Services'


def monitoring_ids(doc):
    saved=set(doc.get('monitoring_ids',[]))
    return [s['id'] for s in doc['sections'] if s['id'] in saved or re.match(r'^monitoring\b',s['name'].strip(),re.I)]


def section_ids(doc):
    if not doc.get('optional_monitoring',False):return set()
    chosen=set(monitoring_ids(doc))
    return chosen|{s['id'] for s in doc['sections'] if s['parent'] in chosen}


def row_ids(doc):
    sections=section_ids(doc)
    return {r['id'] for s in doc['sections'] if s['id'] in sections for r in s['rows']}
