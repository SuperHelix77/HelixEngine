"""Independent provenance checks and transactional accepted-packet publication.

Checks mechanical integrity, not semantic sufficiency for an unknown future task.
"""
import json, re, sqlite3


def exact_value(a, b):
    """JSON value identity including types; Python False == 0 is insufficient."""
    if type(a) is not type(b):
        return False
    if isinstance(b, dict):
        return a.keys() == b.keys() and all(exact_value(a[k], b[k]) for k in b)
    if isinstance(b, list):
        return len(a) == len(b) and all(exact_value(x, y) for x, y in zip(a, b))
    return a == b


def verify(store, candidate):
    receipt = store.receipt(candidate['receipt'])
    if candidate.get('schema') != 'helix.evidence.v1':
        raise ValueError('Unknown packet schema')
    for field in ('exit_code', 'timed_out', 'wall_seconds', 'environment_id'):
        if not exact_value(candidate.get(field), receipt[field]):
            raise ValueError('Receipt mismatch: ' + field)
    if not exact_value(candidate.get('interrupted'), receipt.get('interrupted', False)):
        raise ValueError('Interruption mismatch')
    for field, source in (('command', 'argv'), ('cwd', 'cwd'), ('changed_watched_files', 'changed_watched_files')):
        if field in candidate:
            if not exact_value(candidate[field], receipt[source]):
                raise ValueError('Receipt mismatch: ' + field)
        elif candidate.get('metadata_in_receipt') is not True:
            raise ValueError('Missing metadata provenance')
    if candidate.get('coverage') != 'partial typed projection; originals retained losslessly; missing detail must be retrieved':
        raise ValueError('Missing partial-coverage declaration')
    if candidate.get('kind') not in ('generic', 'pytest', 'compiler'):
        raise ValueError('Unknown reducer kind')
    for stream in ('stdout', 'stderr'):
        if not exact_value(candidate['raw'][stream], receipt[stream]):
            raise ValueError('Raw reference mismatch')
        raw = store.get(receipt[stream]['sha256'])
        if len(raw) != receipt[stream]['bytes']:
            raise ValueError('Raw byte length mismatch')
        # Separate implementation: no reducer invocation or trust in reducer counts.
        lines = [line.decode('utf-8', errors='replace') for line in raw.splitlines()]
        lines = [re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', line) for line in lines]
        projection = candidate['streams'][stream]
        if not exact_value(projection.get('lines'), len(lines)):
            raise ValueError('Line count mismatch')
        if projection.get('projection_omitted_due_to_budget') is True:
            if candidate.get('retrieval_required') is not True:
                raise ValueError('Omission without retrieval requirement')
            continue
        if projection.get('projection_only') is not True:
            raise ValueError('Projection presented as complete evidence')
        for field in ('diagnostics', 'summary_candidates', 'preview'):
            for record in projection.get(field, []):
                number = record['line']
                if type(number) is not int or not 1 <= number <= len(lines) or record['text'] != lines[number-1]:
                    raise ValueError('Projected text is not source-bound')
        kind = candidate['kind']
        summaries = []
        diagnostic_lines = []
        section_lines = []
        for number, line in enumerate(lines, 1):
            if kind == 'pytest':
                if re.search(r'\b\d+ (passed|failed|error|errors|skipped|xfailed|xpassed)\b', line) and (' in ' in line or line.startswith('=')):
                    summaries.append({'line': number, 'text': line})
                diagnostic = line.startswith(('FAILED ', 'ERROR ')) or bool(re.match(r'^E\s+', line))
                if re.fullmatch(r'_{3,}.+_{3,}', line):
                    section_lines.append(number)
            elif kind == 'compiler':
                diagnostic = bool(re.search(r'(^|\s)(fatal error|error|warning):', line))
            else:
                diagnostic = bool(re.search(r'\b(error|failed|failure|warning|exception|panic)\b', line, re.I))
            if diagnostic:
                diagnostic_lines.append(number)
        if not exact_value(projection.get('summary_candidates'), summaries[-2:]):
            raise ValueError('Summary count evidence mismatch')
        emitted = [entry['line'] for entry in projection.get('diagnostics', [])]
        if not exact_value(emitted, diagnostic_lines[:len(emitted)]) or not exact_value(projection.get('diagnostic_lines_omitted'), len(diagnostic_lines)-len(emitted)):
            raise ValueError('Diagnostic omission accounting mismatch')
        sections = projection.get('failure_section_index', [])
        if not exact_value(projection.get('failure_sections_omitted'), len(section_lines)-len(sections)):
            raise ValueError('Section omission accounting mismatch')
        for index, section in enumerate(sections):
            if index >= len(section_lines):
                raise ValueError('Invented failure section')
            start = section_lines[index]
            end = section_lines[index+1]-1 if index+1 < len(section_lines) else len(lines)
            if not exact_value(section, {'start': start, 'end': end, 'header': lines[start-1]}):
                raise ValueError('Failure span mismatch')
    return {'verified': True, 'scope': 'byte provenance and structural invariants; semantic sufficiency not established'}


def publish(store, name, candidate, expected_revision):
    """Verify first; commit accepted object and revision together, using CAS.

    Rejected objects may remain cold, but never change the accepted pointer.
    SQLite is the sole authoritative pointer, including after process failure.
    """
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError('Invalid expected revision')
    if not re.fullmatch(r'[a-zA-Z0-9_.-]{1,128}', name):
        raise ValueError('Invalid publication name')
    verify(store, candidate)
    blob = json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    obj = store.put(blob)['sha256']
    with sqlite3.connect(store.root / 'accepted.sqlite3', isolation_level=None) as db:
        db.execute('PRAGMA synchronous=FULL')
        db.execute('BEGIN IMMEDIATE')
        try:
            db.execute('CREATE TABLE IF NOT EXISTS accepted(name TEXT PRIMARY KEY, revision INTEGER NOT NULL, object TEXT NOT NULL)')
            row = db.execute('SELECT revision FROM accepted WHERE name=?', (name,)).fetchone()
            revision = row[0] if row else 0
            if revision != expected_revision:
                raise ValueError('Stale accepted-packet revision')
            db.execute('INSERT OR REPLACE INTO accepted VALUES(?,?,?)', (name, revision+1, obj))
            db.execute('COMMIT')
        except BaseException:
            db.execute('ROLLBACK')
            raise
    return {'name': name, 'revision': revision+1, 'packet_sha256': obj}
