"""Current official tariff scenarios. No inferred Codex billing or cross-task ranking."""
import hashlib
import math
import ssl
import certifi
from urllib.request import urlopen, Request
import threading
import time

SOURCE = 'https://developers.openai.com/api/docs/pricing.md'
MODELS = ('gpt-6-astra', 'gpt-5.6-sol', 'gpt-5.6-terra', 'gpt-5.6-luna')
TTL = 300
HEADER = ['Model', 'Short context input', 'Short context cached input', 'Short context cache writes', 'Short context output', 'Long context input', 'Long context cached input', 'Long context cache writes', 'Long context output']


def parse(raw):
    body = raw.decode('utf-8')
    marker = '### Standard pricing data'
    if body.count(marker) != 1: raise ValueError('Ambiguous Standard pricing section')
    section = body.split(marker, 1)[1].split('\n### ', 1)[0]
    rows = [[c.strip() for c in line.strip().strip('|').split('|')] for line in section.splitlines() if line.startswith('|')]
    if not rows or rows[0] != HEADER: raise ValueError('Official pricing schema changed')
    rates = {}
    for cells in rows[2:]:
        if cells[0] not in MODELS: continue
        if cells[0] in rates or len(cells) != 9: raise ValueError('Ambiguous model tariff')
        values = []
        for value in cells[1:]:
            if not value.startswith('$'): raise ValueError('Unsupported price')
            n = float(value[1:].replace(',', ''))
            if not math.isfinite(n) or n <= 0: raise ValueError('Invalid price')
            values.append(n)
        rates[cells[0]] = {'short': values[:4], 'long': values[4:]}
    if set(rates) != set(MODELS): raise ValueError('Missing model price')
    return rates


def fetch():
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    with urlopen(Request(SOURCE,headers={'User-Agent':'HelixEngine/0.1'}),timeout=15,context=context) as response:
        raw=response.read(1_000_001)
    if len(raw)>1_000_000:raise ValueError('Pricing source exceeds limit')
    return raw


class Prices:
    def __init__(self, fetcher=fetch, clock=time.time):
        self.fetcher=fetcher; self.clock=clock; self.lock=threading.Lock()
        self.rates=None; self.checked=None; self.digest=None; self.error=None

    def refresh(self):
        try:
            raw=self.fetcher(); rates=parse(raw)
            with self.lock:
                self.rates=rates; self.checked=self.clock(); self.digest=hashlib.sha256(raw).hexdigest(); self.error=None
        except Exception as exc:
            with self.lock: self.error=type(exc).__name__

    def state(self):
        with self.lock:
            fresh=self.checked is not None and 0 <= self.clock()-self.checked < TTL
            return {'source':SOURCE,'checked_at':self.checked,'expires_at':self.checked+TTL if self.checked is not None else None,
                'sha256':self.digest,'fresh':fresh,'rates':self.rates if fresh else None,'error':self.error,
                'refresh_seconds':120,'ttl_seconds':TTL}

    def loop(self):
        while True:
            self.refresh(); time.sleep(120)


def estimate(usage, rates):
    if not usage or not rates: return None
    keys=('input_tokens','cached_input_tokens','cache_write_input_tokens','output_tokens')
    if any(type(usage.get(k)) is not int or usage[k]<0 for k in keys): return None
    total,cached,writes,output=(usage[k] for k in keys)
    if cached+writes>total: return None
    counts=(total-cached-writes,cached,writes,output)
    return {tier:sum(n*p for n,p in zip(counts,prices))/1_000_000 for tier,prices in rates.items()}
