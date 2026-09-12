"""Caller-pinned copy handles: short selections expand to exact existing plans.

The catalog reference is caller authority, never taken from a model selection.
Catalog construction and source verification are explicit, metered setup work.
"""
import json
import hashlib
import re
import time

from . import renderer

MAX_HANDLES = 1024
MAX_CATALOG_BYTES = 1_000_000


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def copy_op(op):
    if not isinstance(op, dict) or set(op) != {'source_sha256', 'start_byte', 'end_byte'}:
        raise ValueError('Catalog entries must be exact source ranges')
    key, start, end = op['source_sha256'], op['start_byte'], op['end_byte']
    if not isinstance(key, str) or not re.fullmatch('[0-9a-f]{64}', key):
        raise ValueError('Invalid source hash')
    if type(start) is not int or type(end) is not int or start < 0 or end < start:
        raise ValueError('Invalid source range')
    return dict(op)


def entries(mapping):
    if not isinstance(mapping, dict) or not mapping or len(mapping) > MAX_HANDLES:
        raise ValueError('Invalid catalog size')
    for name, op in mapping.items():
        if not isinstance(name, str) or not re.fullmatch('[A-Za-z0-9_-]{1,32}', name):
            raise ValueError('Invalid handle')
        copy_op(op)


def freeze(store, mapping):
    """Verify every source/range once and archive an immutable catalog."""
    started = time.perf_counter()
    before = dict(store.metrics)
    entries(mapping)
    mapping = {name: copy_op(op) for name, op in mapping.items()}
    raw = encode({'schema': 'helix.copy_catalog.v1', 'entries': mapping})
    if len(raw) > MAX_CATALOG_BYTES:
        raise ValueError('Catalog byte limit exceeded')
    cache = {}
    for op in mapping.values():
        key = op['source_sha256']
        if key not in cache:
            cache[key] = store.get(key)
        if op['end_byte'] > len(cache[key]):
            raise ValueError('Range exceeds exact source')
    digest = store.put(raw)['sha256']
    reference = {'schema': 'helix.copy_catalog.ref.v1', 'sha256': digest}
    receipt = {'schema': 'helix.copy_catalog.creation.v1', 'reference': reference,
        'catalog_bytes': len(raw), 'handles': len(mapping),
        'elapsed_seconds': time.perf_counter() - started,
        'store_io': {k: store.metrics[k] - before[k] for k in before},
        'limits': 'Model setup/discovery, physical I/O and upstream ingestion excluded.'}
    return reference, receipt


def expand(store, reference, selection, max_operations=1024):
    """No inference, execution or publication; unknown handles fail explicitly."""
    if (not isinstance(reference, dict) or set(reference) != {'schema', 'sha256'}
            or reference['schema'] != 'helix.copy_catalog.ref.v1'
            or not isinstance(reference['sha256'], str)
            or not re.fullmatch('[0-9a-f]{64}', reference['sha256'])):
        raise ValueError('Invalid caller catalog reference')
    if not isinstance(selection, list) or len(selection) > max_operations:
        raise ValueError('Selection operation limit exceeded')
    raw = store.get(reference['sha256'])
    if len(raw) > MAX_CATALOG_BYTES:
        raise ValueError('Catalog byte limit exceeded')
    catalog = json.loads(raw)
    if (not isinstance(catalog, dict) or set(catalog) != {'schema', 'entries'}
            or catalog['schema'] != 'helix.copy_catalog.v1'):
        raise ValueError('Invalid catalog schema')
    entries(catalog['entries'])
    operations = []
    for item in selection:
        if isinstance(item, str):
            if item not in catalog['entries']:
                raise ValueError('Unknown handle; exact selection required')
            operations.append(copy_op(catalog['entries'][item]))
        elif isinstance(item, dict) and set(item) == {'literal_utf8'} and isinstance(item['literal_utf8'], str):
            operations.append(dict(item))
        else:
            raise ValueError('Selection accepts handles or explicit UTF-8 literals only')
    return {'schema': 'helix.copy.v1', 'operations': operations}


def assemble(store, reference, selection, **limits):
    before = dict(store.metrics)
    plan = expand(store, reference, selection, limits.get('max_operations', 1024))
    raw, receipt = renderer.assemble(store, plan, **limits)
    receipt['catalog'] = dict(reference)
    receipt['selection_io'] = {k: store.metrics[k] - before[k] for k in before}
    return raw, receipt


def publish(store, reference, selection, destination, expected_sha256=None, **limits):
    before = dict(store.metrics)
    plan = expand(store, reference, selection, limits.get('max_operations', 1024))
    receipt = renderer.publish(store, plan, destination, expected_sha256, **limits)
    receipt['catalog'] = dict(reference)
    receipt['selection_io'] = {k: store.metrics[k] - before[k] for k in before}
    return receipt


def complete_response(store, reference, response, destination, expected_sha256=None,
                      max_response_bytes=100_000, **limits):
    """Caller-side completion: model selects; caller validates and copies bytes.

    A failed response is not repaired silently. The caller must count any return
    to the model for correction. Successful copy is not semantic certification.
    """
    if not isinstance(response, str):
        raise ValueError('Text response required')
    raw = response.encode('utf-8')
    if len(raw) > max_response_bytes:
        raise ValueError('Response byte limit exceeded')
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate response key')
            result[key] = value
        return result
    def invalid_constant(value):
        raise ValueError('Nonstandard JSON constant')
    selection = json.loads(response, object_pairs_hook=unique_pairs, parse_constant=invalid_constant)
    receipt = publish(store, reference, selection, destination, expected_sha256, **limits)
    receipt['response_sha256'] = hashlib.sha256(raw).hexdigest()
    receipt['response_bytes'] = len(raw)
    receipt['semantic_success'] = None
    return receipt
