from types import SimpleNamespace

from app.services import barcode_lookup, mealie_health


def test_mealie_health_cache_reuses_probe(monkeypatch):
    calls = []

    def fake_get(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr(mealie_health.mealie_http, "get", fake_get)
    mealie_health.clear_mealie_health_cache()

    assert mealie_health.mealie_reachable(ttl_seconds=60) is True
    assert mealie_health.mealie_reachable(ttl_seconds=60) is True
    assert len(calls) == 1

    assert mealie_health.mealie_reachable(ttl_seconds=60, force=True) is True
    assert len(calls) == 2


def test_failover_does_not_call_secondary_when_primary_succeeds(monkeypatch):
    calls = []

    def primary(_barcode):
        calls.append("primary")
        return {
            "title": "Primary product",
            "brand": "Brand",
            "quantity": "1 kg",
            "product_type": "food",
            "source": "primary",
        }

    def secondary(_barcode):
        calls.append("secondary")
        return {"title": "Secondary product", "source": "secondary"}

    monkeypatch.setattr(
        barcode_lookup,
        "settings",
        SimpleNamespace(lookup_strategy="failover", lookup_enrich_in_background=False),
    )

    first, second = barcode_lookup._lookup_with_budget("1234567890123", primary, secondary)
    assert first and first["source"] == "primary"
    assert second is None
    assert calls == ["primary"]


def test_background_complement_keeps_secondary_out_of_hot_path(monkeypatch):
    calls = []

    def primary(_barcode):
        calls.append("primary")
        return {
            "title": "Primary product",
            "brand": "",
            "quantity": None,
            "product_type": None,
            "source": "primary",
        }

    def secondary(_barcode):
        calls.append("secondary")
        return {"title": "Secondary product", "brand": "Brand", "source": "secondary"}

    monkeypatch.setattr(
        barcode_lookup,
        "settings",
        SimpleNamespace(lookup_strategy="complement", lookup_enrich_in_background=True),
    )

    first, second = barcode_lookup._lookup_with_budget("1234567890123", primary, secondary)
    assert first and first["source"] == "primary"
    assert second is None
    assert calls == ["primary"]
