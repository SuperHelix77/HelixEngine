"""Optional immutable line index. All index construction and reads use Store metrics.

Raw originals remain authoritative. Indexing duplicates content and is opt-in.
Ranges follow bytes.splitlines(keepends=True), as the original retrieval API does.
"""
import json
from .evidence import digest


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def build(store, source, chunk_bytes=16384, fanout=16):
    if chunk_bytes < 256 or not 2 <= fanout <= 64:
        raise ValueError('Invalid index geometry')
    raw = store.get(source)
    lines = raw.splitlines(keepends=True)
    store.metrics['index_bytes_parsed'] = store.metrics.get('index_bytes_parsed', 0) + len(raw)
    leaves = []
    pending = []
    size = 0
    def flush():
        if pending:
            blob = b''.join(pending)
            leaves.append({'sha256': store.put(blob)['sha256'], 'bytes': len(blob), 'lines': len(pending), 'leaf': True})
    for line in lines:
        if pending and size + len(line) > chunk_bytes:
            flush(); pending = []; size = 0
        pending.append(line); size += len(line)
    flush()
    level = leaves
    while len(level) > 1:
        next_level = []
        for offset in range(0, len(level), fanout):
            children = level[offset:offset+fanout]
            node = {'schema': 'helix.lines.node.v1', 'children': children}
            next_level.append({'sha256': store.put(encode(node))['sha256'], 'bytes': sum(c['bytes'] for c in children), 'lines': sum(c['lines'] for c in children), 'leaf': False})
        level = next_level
    root = {'schema': 'helix.lines.v1', 'source_sha256': source, 'bytes': len(raw), 'lines': len(lines), 'tree': level[0] if level else None, 'chunk_target_bytes': chunk_bytes, 'fanout': fanout}
    key = store.put(encode(root))['sha256']
    verify_index(store, key, source)
    return key


def retrieve(store, index, source, start=1, end=None):
    """Require the expected source digest; never silently follow a different version."""
    root = json.loads(store.get(index))
    if root.get('schema') != 'helix.lines.v1' or root.get('source_sha256') != source:
        raise ValueError('Index version/source mismatch')
    if type(start) is not int or start < 1 or end is not None and (type(end) is not int or end < start):
        raise ValueError('Invalid inclusive line range')
    # Indexed retrieval keeps the historical API's bounded suffix behavior:
    # an end beyond the source is clamped after the source binding is checked.
    stop = root['lines'] if end is None else min(end, root['lines'])
    parts = []
    def visit(ref, first):
        if first > stop or first + ref['lines'] <= start:
            return
        blob = store.get(ref['sha256'])
        if ref['leaf']:
            lines = blob.splitlines(keepends=True)
            if len(blob) != ref['bytes'] or len(lines) != ref['lines']:
                raise ValueError('Leaf dimensions mismatch')
            parts.extend(lines[max(0, start-first):stop-first+1])
        else:
            node = json.loads(blob)
            if node.get('schema') != 'helix.lines.node.v1':
                raise ValueError('Unknown index node')
            children = node['children']
            if not children or sum(c['lines'] for c in children) != ref['lines'] or sum(c['bytes'] for c in children) != ref['bytes']:
                raise ValueError('Node dimensions mismatch')
            for child in children:
                visit(child, first)
                first += child['lines']
    tree = root['tree']
    if tree:
        if tree['bytes'] != root['bytes'] or tree['lines'] != root['lines']:
            raise ValueError('Root dimensions mismatch')
        visit(tree, 1)
    elif root['bytes'] or root['lines']:
        raise ValueError('Nonempty index without tree')
    result = b''.join(parts)
    store.metrics['range_bytes_hashed'] = store.metrics.get('range_bytes_hashed', 0) + len(result)
    return result, {'index': index, 'source_sha256': source, 'range_1based': [start, end], 'bytes': len(result), 'sha256': digest(result), 'io': dict(store.metrics), 'scope': 'application bytes; index construction and retained raw storage must be accounted separately; not physical SSD traffic'}


def verify_index(store, index, source):
    """One-time full reconstruction check before accepting an index binding."""
    raw, _ = retrieve(store, index, source)
    if digest(raw) != source:
        raise ValueError('Index reconstruction does not match original source')
    store.metrics['index_verification_bytes_hashed'] = store.metrics.get('index_verification_bytes_hashed', 0) + len(raw)
    return {'verified_source_sha256': source, 'reconstructed_bytes': len(raw)}
