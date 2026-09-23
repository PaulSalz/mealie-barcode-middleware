from __future__ import annotations

from app.frontend_assets import BUNDLES, GENERATED_DIR, build_frontend_assets


def test_frontend_bundles_are_built_in_declared_order():
    result = build_frontend_assets()
    assert set(result["bundles"]) == set(BUNDLES)

    for name, sources in BUNDLES.items():
        path = GENERATED_DIR / name
        assert path.is_file()
        content = path.read_text(encoding="utf-8")
        positions = []
        for source in sources:
            marker = f"/* ---- {source} ---- */"
            assert marker in content
            positions.append(content.index(marker))
        assert positions == sorted(positions)
        assert result["bundles"][name]["sha256"]


def test_frontend_bundle_sources_are_unique():
    for sources in BUNDLES.values():
        assert len(sources) == len(set(sources))
