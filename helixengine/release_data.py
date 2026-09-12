"""Read-only, hash-bound public evidence capsules. No model calls or promotion."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def project(read_bytes, directory=None):
    root = Path(directory or HERE / 'release_evidence').resolve()
    result = {'version': '0.1.0-preview.1', 'state': 'EVIDENCE_PREVIEW',
              'model_wide_parity': False, 'release_medians': None, 'lanes': [], 'problems': []}
    try:
        index = json.loads(read_bytes(root / 'index.json', 200_000))
        result['version'] = index['version']
        for entry in index['lanes']:
            name = entry['file']
            path = (root / name).resolve()
            if path.parent != root or path.suffix != '.json':
                raise ValueError('Invalid capsule path')
            try:
                raw = read_bytes(path, 200_000)
                if hashlib.sha256(raw).hexdigest() != entry['sha256']:
                    raise ValueError('Evidence capsule changed')
                lane = json.loads(raw)
                if lane['model_wide_parity'] is not False or lane['release_median'] is not None:
                    raise ValueError('Preview cannot promote model qualification')
                for arm in lane.get('arms', []):
                    u = arm['usage']
                    keys = ('input_tokens', 'cached_input_tokens', 'cache_write_input_tokens', 'output_tokens', 'reasoning_output_tokens')
                    if any(type(u.get(k)) is not int or u[k] < 0 for k in keys):
                        raise ValueError('Invalid native counters')
                    if u['cached_input_tokens'] + u['cache_write_input_tokens'] > u['input_tokens'] or u['reasoning_output_tokens'] > u['output_tokens']:
                        raise ValueError('Invalid token subset')
                arms = {a['arm']: a for a in lane.get('arms', [])}
                if len(arms) != len(lane.get('arms', [])):
                    raise ValueError('Duplicate evidence arm')
                if arms:
                    if set(arms) != {'off', 'on'}:
                        raise ValueError('Incomplete pair')
                    a, b = arms['off']['usage'], arms['on']['usage']
                    def delta(x, y): return 100 * (1 - y / x) if x else None
                    lane['savings'] = {k: delta(a[k], b[k]) for k in ('input_tokens', 'output_tokens')}
                    lane['savings']['uncached_input_tokens'] = delta(a['input_tokens'] - a['cached_input_tokens'], b['input_tokens'] - b['cached_input_tokens'])
                lane['capsule_sha256'] = entry['sha256']
                lane['integrity'] = 'VERIFIED_PUBLIC_CAPSULE'
                result['lanes'].append(lane)
            except (ValueError, KeyError, TypeError, OSError) as exc:
                result['problems'].append({'file': name, 'error': str(exc)})
    except (ValueError, KeyError, TypeError, OSError) as exc:
        result['problems'].append({'error': str(exc)})
    return result
