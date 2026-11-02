"""A spent search key must rotate, not silently disable live pricing.

Both search providers are free-tier and quota-capped (Serper 2,500 searches
lifetime, Tavily 1,000/month) while one investigation spends 20-50 of them, so
running a key dry mid-demo is an ordinary event, not an exotic one. It is also
an invisible one: live web is the only source of part prices, so an exhausted
key produces unpriced parts, `pricing_coverage` below the floor, abstaining
fair-value bands and a completed investigation that decided nothing about the
number it was asked to audit.

These tests pin the distinction the rotation rests on: a refused KEY is not a
dead PROVIDER.
"""
import httpx
import pytest

from services import price_lookup


@pytest.fixture(autouse=True)
def _clean_key_state():
    price_lookup._key_blocked_until.clear()
    price_lookup.reset()
    yield
    price_lookup._key_blocked_until.clear()
    price_lookup.reset()


def _http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://google.serper.dev/search")
    return httpx.HTTPStatusError(
        f"{status}", request=request, response=httpx.Response(status, request=request)
    )


def _chain(monkeypatch, serper=("k1", "k2"), tavily=()):
    monkeypatch.setattr(price_lookup, "SERPER_API_KEYS", list(serper))
    monkeypatch.setattr(price_lookup, "TAVILY_API_KEYS", list(tavily))


# ── Rotation ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("status", [401, 402, 403, 429, 432, 433])
def test_quota_refusal_rotates_to_the_next_key(monkeypatch, status):
    """Every status that means "this key" must reach the spare on the SAME query.

    Rotating on the next query instead would lose the part that was in flight,
    and a part lost at the top of the waterfall is a part reported unpriced.
    """
    _chain(monkeypatch)
    seen = []

    def fake_serper(query, api_key):
        seen.append(api_key)
        if api_key == "k1":
            raise _http_error(status)
        return [{"text": "bonnet Rs.18,500", "url": "https://boodmo.com/x"}]

    monkeypatch.setattr(price_lookup, "_serper", fake_serper)
    results = price_lookup._search("kia seltos bonnet price")

    assert seen == ["k1", "k2"]
    assert results and results[0]["provider"] == "serper"


def test_spent_key_is_never_tried_again(monkeypatch):
    """403 is permanent. Re-testing it once per part is 20-50 wasted round-trips
    per claim, each one delaying the price it is meant to fetch."""
    _chain(monkeypatch)
    seen = []

    def fake_serper(query, api_key):
        seen.append(api_key)
        if api_key == "k1":
            raise _http_error(403)
        return [{"text": "Rs.18,500", "url": "https://boodmo.com/x"}]

    monkeypatch.setattr(price_lookup, "_serper", fake_serper)
    for _ in range(3):
        price_lookup._search("q")

    assert seen == ["k1", "k2", "k2", "k2"]


def test_spent_key_survives_reset(monkeypatch):
    """reset() re-arms the per-investigation circuit breaker. A quota that ran
    out during claim N has not refilled by claim N+1, so the key state is
    process-lifetime and deliberately outlives it."""
    _chain(monkeypatch)
    monkeypatch.setattr(
        price_lookup, "_serper",
        lambda query, api_key: (_ for _ in ()).throw(_http_error(403)))
    price_lookup._search("q")
    price_lookup.reset()

    assert price_lookup._live_keys(["k1", "k2"]) == []


def test_rate_limit_rests_the_key_rather_than_spending_it(monkeypatch):
    """pricing_engine prices 6-20 parts concurrently, so a 429 is as likely to
    be a two-second burst as a monthly cap. Burning a spare on a burst would
    spend the fallback on the one failure mode that fixes itself."""
    _chain(monkeypatch)
    monkeypatch.setattr(
        price_lookup, "_serper",
        lambda query, api_key: (_ for _ in ()).throw(_http_error(429)))
    price_lookup._search("q")

    blocked = price_lookup._key_blocked_until["k1"]
    assert blocked != float("inf")
    assert price_lookup._key_blocked_until["k2"] != float("inf")


# ── A key fault is not a provider fault (and vice versa) ──────────────────────

def test_network_failure_trips_the_provider_not_the_chain(monkeypatch):
    """A TLS block or a 5xx says nothing about the key. Rotating through the
    whole chain against a host that is down just multiplies the timeout by the
    number of keys before reaching the provider that still works."""
    _chain(monkeypatch, serper=("k1", "k2"), tavily=("t1",))
    serper_calls, tavily_calls = [], []

    def fake_serper(query, api_key):
        serper_calls.append(api_key)
        raise httpx.ConnectTimeout("tls blocked")

    def fake_tavily(query, api_key):
        tavily_calls.append(api_key)
        return [{"text": "Rs.18,500", "url": "https://boodmo.com/x"}]

    monkeypatch.setattr(price_lookup, "_serper", fake_serper)
    monkeypatch.setattr(price_lookup, "_tavily", fake_tavily)
    results = price_lookup._search("q")

    assert serper_calls == ["k1"]          # one key, not the whole chain
    assert tavily_calls == ["t1"]
    assert results[0]["provider"] == "tavily"
    assert "k1" not in price_lookup._key_blocked_until


def test_exhausted_serper_chain_falls_through_to_tavily(monkeypatch):
    _chain(monkeypatch, serper=("k1", "k2"), tavily=("t1",))
    monkeypatch.setattr(
        price_lookup, "_serper",
        lambda query, api_key: (_ for _ in ()).throw(_http_error(403)))
    monkeypatch.setattr(
        price_lookup, "_tavily",
        lambda query, api_key: [{"text": "Rs.18,500", "url": "https://boodmo.com/x"}])

    assert price_lookup._search("q")[0]["provider"] == "tavily"


def test_every_key_spent_returns_empty_rather_than_raising(monkeypatch):
    """The designed end state: no price, no exception. pricing_coverage then
    drops below PRICING_MIN_COVERAGE and the bands abstain, which is the honest
    outcome — not a crashed investigation, and not an invented number."""
    _chain(monkeypatch, serper=("k1",), tavily=("t1",))
    for name in ("_serper", "_tavily"):
        monkeypatch.setattr(
            price_lookup, name,
            lambda query, api_key: (_ for _ in ()).throw(_http_error(403)))

    assert price_lookup._search("q") == []


def test_masking_never_prints_a_whole_key():
    assert price_lookup._mask("abcd1234efgh5678") == "...5678"
    assert "abcd" not in price_lookup._mask("abcd1234efgh5678")


# ── Chain construction ────────────────────────────────────────────────────────

def test_key_chain_reads_numbered_slots_in_order(monkeypatch):
    import config
    monkeypatch.setenv("SERPER_API_KEY", " primary ")
    monkeypatch.setenv("SERPER_API_KEY_2", "friend")
    monkeypatch.setenv("SERPER_API_KEY_3", "")
    monkeypatch.setenv("SERPER_API_KEY_4", "friend")      # duplicate, ignored
    monkeypatch.setenv("SERPER_API_KEY_5", "third")

    assert config._key_chain("SERPER_API_KEY") == ["primary", "friend", "third"]


def test_key_chain_is_empty_when_nothing_is_configured(monkeypatch):
    import config
    for i in [""] + [f"_{n}" for n in range(2, 10)]:
        monkeypatch.delenv(f"SERPER_API_KEY{i}", raising=False)

    assert config._key_chain("SERPER_API_KEY") == []
