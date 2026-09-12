import pytest
from helixengine.pricing import HEADER, MODELS, Prices, TTL, estimate, parse


def source():
    return ('### Standard pricing data\n|' + '|'.join(HEADER) + '|\n|' + '|'.join(['---'] * 9) + '|\n' +
            '\n'.join('|' + m + '|' + '|'.join(['$10', '$1', '$12.5', '$50', '$20', '$2', '$25', '$75']) + '|' for m in MODELS)).encode()


def test_parse_exact_tariff_schema():
    assert parse(source())[MODELS[0]]['short'] == [10, 1, 12.5, 50]


@pytest.mark.parametrize('raw', [b'', source().replace(b'### Standard', b'### Priority'),
    source().replace(b'Short context input', b'Input'), source() + source(),
    source().replace(b'$10', b'$nan'), source().replace(b'$10', b'$-1'),
    source().replace(MODELS[0].encode(), b'unknown')])
def test_ambiguous_or_changed_tariff_is_unavailable(raw):
    with pytest.raises(ValueError):
        parse(raw)


def test_failed_refresh_does_not_extend_freshness():
    clock = [0]
    p = Prices(fetcher=source, clock=lambda: clock[0])
    p.refresh()
    assert p.state()['expires_at'] == TTL
    p.fetcher = lambda: (_ for _ in ()).throw(OSError('offline'))
    clock[0] = 299
    p.refresh()
    assert p.state()['fresh'] and p.state()['checked_at'] == 0
    clock[0] = TTL
    assert not p.state()['fresh'] and p.state()['rates'] is None
    clock[0] = -1
    assert not p.state()['fresh']


def test_input_subsets_are_not_double_charged():
    u = dict(input_tokens=100, cached_input_tokens=70, cache_write_input_tokens=10, output_tokens=5)
    assert estimate(u, {'short': [10, 1, 12.5, 50]})['short'] == (20*10 + 70 + 10*12.5 + 5*50)/1e6
    assert estimate({**u, 'cached_input_tokens': 95}, {'short': [10,1,12.5,50]}) is None
    assert estimate({**u, 'output_tokens': True}, {'short': [10,1,12.5,50]}) is None
