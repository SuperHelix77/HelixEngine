"""Compile exact simultaneous text edits into the existing immutable copy plan.

Model owns every old/new choice. Caller owns the source version and destination.
No fuzzy matching, cascade replacement, semantic repair, execution or new DSL.
"""
import hashlib
import json
import time
from . import renderer


def parse(text):
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate edit key')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('Nonstandard JSON constant')
    return json.loads(text, object_pairs_hook=unique, parse_constant=invalid)


def compile_edits(raw, expected_sha256, response):
    if not isinstance(raw, bytes) or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Caller source version changed')
    if not isinstance(response, dict) or set(response) != {'edits'} or not isinstance(response['edits'], list):
        raise ValueError('Expected exact old/new edits')
    spans = []
    for edit in response['edits']:
        if (not isinstance(edit, dict) or set(edit) != {'old', 'new'}
                or not isinstance(edit['old'], str) or not edit['old'] or not isinstance(edit['new'], str)):
            raise ValueError('Invalid literal edit')
        old = edit['old'].encode('utf-8'); new = edit['new'].encode('utf-8')
        start = raw.find(old)
        if start < 0 or raw.find(old, start + 1) >= 0:
            raise ValueError('Old text must identify exactly one original span')
        spans.append((start, start + len(old), edit['new'], len(new)))
    operations = []; cursor = 0; copied = 0; inserted = 0
    for start, end, text, size in sorted(spans):
        if start < cursor:
            raise ValueError('Overlapping edits are ambiguous')
        if cursor < start:
            operations.append(dict(source_sha256=expected_sha256, start_byte=cursor, end_byte=start))
            copied += start - cursor
        operations.append({'literal_utf8': text}); inserted += size; cursor = end
    if cursor < len(raw):
        operations.append(dict(source_sha256=expected_sha256, start_byte=cursor, end_byte=len(raw)))
        copied += len(raw) - cursor
    return {'schema': 'helix.copy.v1', 'operations': operations}, {
        'source_sha256': expected_sha256, 'source_bytes': len(raw), 'edits': len(spans),
        'copied_bytes': copied, 'literal_bytes': inserted,
        'semantics': 'Not checked by exact matching or assembly'}


def assemble(store, source_sha256, text, **limits):
    started = time.perf_counter(); before = dict(store.metrics)
    raw = store.get(source_sha256)
    plan, receipt = compile_edits(raw, source_sha256, parse(text))
    output, assembly = renderer.assemble(store, plan, **limits)
    return output, {**receipt, 'response_bytes': len(text.encode('utf-8')),
                    'seconds': time.perf_counter()-started, 'assembly': assembly,
                    'store_io': {k: store.metrics[k]-before[k] for k in before}}
