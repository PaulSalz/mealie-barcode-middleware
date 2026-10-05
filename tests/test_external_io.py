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


def test_live_mealie_food_search_returns_ranked_matches_and_units(monkeypatch):
    from app.services import mealie

    calls = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"items": [
                {"id": "food-other", "name": "Soy Dessert", "unitId": "unit-ml", "unit": {"name": "Milliliter", "abbreviation": "ml"}},
                {"id": "food-exact", "name": "Soy Yogurt", "unitId": "unit-g", "unit": {"name": "Gram", "abbreviation": "g"}},
            ]}

    def fake_get(path, **kwargs):
        calls.append((path, kwargs))
        return Response()

    monkeypatch.setattr(mealie.mealie_http, "get", fake_get)
    results = mealie.search_foods("Soy Yogurt", limit=6)

    assert calls[0][0] == "/api/foods"
    assert calls[0][1]["params"]["search"] == "Soy Yogurt"
    assert results[0]["id"] == "food-exact"
    assert results[0]["exact"] is True
    assert results[0]["score"] == 100
    assert results[0]["default_unit_id"] == "unit-g"
    assert results[0]["default_unit_name"] == "Gram"


def test_barcode_food_search_combines_and_ranks_live_and_local_results(monkeypatch):
    from app.routers import barcodes

    monkeypatch.setattr(
        barcodes,
        "fuzzy_match",
        lambda _query, _brand, _db: [
            {
                "item_id": "food-local",
                "item_name": "Mozzarella gerieben",
                "source": "mealie",
                "score": 88,
                "exact": False,
                "default_unit_id": "unit-g",
                "default_unit_name": "Gram",
            },
            {
                "item_id": "food-shared",
                "item_name": "Mozzarella (old name)",
                "source": "mealie",
                "score": 91,
                "exact": False,
                "default_unit_id": "unit-old",
                "default_unit_name": "Old unit",
            },
        ],
    )
    monkeypatch.setattr(
        barcodes,
        "search_foods",
        lambda _query, limit: [
            {"id": "food-live", "name": "Melone", "score": 62, "exact": False},
            {
                "id": "food-shared",
                "name": "Mozzarella",
                "score": 74,
                "exact": False,
                "default_unit_id": "unit-current",
                "default_unit_name": "Gram",
            },
        ],
    )

    results = barcodes.barcodes_search(q="mozz", db=None)

    assert [result["id"] for result in results] == ["food-shared", "food-local", "food-live"]
    assert results[0]["name"] == "Mozzarella"
    assert results[0]["score"] == 91
    assert results[0]["default_unit_id"] == "unit-current"


def test_barcode_food_search_prefers_full_name_starting_with_partial_query(monkeypatch):
    from app.routers import barcodes

    monkeypatch.setattr(
        barcodes,
        "fuzzy_match",
        lambda _query, _brand, _db: [
            {
                "item_id": "food-orange",
                "item_name": "Orange",
                "source": "mealie",
                "score": 100,
                "exact": False,
            },
            {
                "item_id": "food-orange-juice",
                "item_name": "Orangensaft",
                "source": "mealie",
                "score": 96,
                "exact": False,
            },
        ],
    )
    monkeypatch.setattr(
        barcodes,
        "search_foods",
        lambda _query, limit: [
            {"id": "food-orange", "name": "Orange", "score": 100, "exact": False},
            {"id": "food-orange-juice", "name": "Orangensaft", "score": 96, "exact": False},
        ],
    )

    results = barcodes.barcodes_search(q="orangensaf", db=None)

    assert results[0]["id"] == "food-orange-juice"
    assert results[1]["id"] == "food-orange"
