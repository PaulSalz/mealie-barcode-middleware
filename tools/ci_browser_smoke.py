#!/usr/bin/env python3
from __future__ import annotations

import json
import os

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


BASE_URL = os.environ.get("B2M_BROWSER_URL", "http://127.0.0.1:8001")


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page_errors: list[str] = []
        console_messages: list[str] = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on("console", lambda message: console_messages.append(f"{message.type}: {message.text}"))

        page.goto(f"{BASE_URL}/setup", wait_until="domcontentloaded", timeout=20_000)
        page.get_by_role("heading", name="Welcome").wait_for(timeout=5_000)
        assert page.get_by_role("button", name="Create account").is_visible()
        assert page.locator('input[name="username"]').is_visible()
        assert page.locator('input[name="password"]').is_visible()
        assert page.locator('input[name="password_confirm"]').is_visible()

        page.locator('input[name="username"]').fill("ci-admin")
        page.locator('input[name="password"]').fill("ci-browser-smoke-password")
        page.locator('input[name="password_confirm"]').fill("ci-browser-smoke-password")
        page.get_by_role("button", name="Create account").click()
        page.wait_for_load_state("domcontentloaded")

        page.goto(f"{BASE_URL}/labels", wait_until="domcontentloaded", timeout=20_000)
        page.locator("#label-queue").wait_for(state="attached", timeout=5_000)
        page.locator("#label-editor-mode").wait_for(state="visible", timeout=5_000)
        assert page.locator("#label-editor-mode").is_visible()

        page.goto(f"{BASE_URL}/actions/new", wait_until="domcontentloaded", timeout=20_000)
        page.get_by_role("heading", name="New action").wait_for(timeout=5_000)
        page.locator('input[name="name"]').fill("CI action")
        page.locator("#action-v22-builder").wait_for(state="visible", timeout=5_000)
        assert page.locator("#action-v22-builder").is_visible()

        local_advanced = page.locator("#action-advanced-toggle")
        local_advanced.wait_for(state="attached", timeout=5_000)
        assert not local_advanced.is_visible()

        tools = page.locator('.d-none.d-md-flex a[data-bs-toggle="dropdown"]').first
        tools.wait_for(state="visible", timeout=5_000)
        tools.click()
        global_advanced = page.locator("#b2m-global-advanced-toggle")
        global_advanced.wait_for(state="visible", timeout=5_000)
        assert global_advanced.is_visible()

        # Shopping Print historically accumulated multiple controller layers. Mock
        # external data so CI can assert the page itself settles promptly and does
        # not enter a bootstrap/list-request loop.
        shopping_hits = {"bootstrap_v31": 0, "lists": 0, "legacy_bootstrap": 0}
        bootstrap_payload = {
            "lists": [{"id": "ci-list", "name": "CI Shopping"}],
            "default_list_id": "ci-list",
            "settings": {
                "paper_width_mm": 50.0,
                "margin_mm": 2.2,
                "top_margin_mm": 2.2,
                "body_font_mm": 3.0,
                "line_gap_mm": 0.8,
                "category_gap_mm": 1.6,
                "bottom_margin_mm": 3.0,
                "density": 3,
                "threshold": 145,
                "dpi": 300,
                "label_type": 3,
                "show_checkboxes": True,
                "show_items": True,
                "show_quantities": True,
                "show_item_dividers": False,
                "show_category_dividers": True,
                "category_divider_style": "solid",
                "item_marker_style": "checkbox",
            },
            "printer": {"configured": True, "connected": False, "status_mode": "fast"},
            "poll_interval_seconds": 60,
            "label_types": [{"value": 1, "name": "With gaps"}, {"value": 3, "name": "Continuous"}],
        }
        list_payload = {
            "id": "ci-list",
            "name": "CI Shopping",
            "items": [{
                "id": "ci-item",
                "name": "Milk",
                "original_name": "Milk",
                "quantity": 1,
                "quantity_value_text": "1",
                "original_quantity_value_text": "1",
                "unit_text": "l",
                "original_unit_text": "l",
                "quantity_text": "1 l",
                "category": "Dairy",
                "override_key": "ci-item",
            }],
            "mealie_count": 1,
            "local_count": 0,
            "count": 1,
            "categories": ["Dairy"],
            "category_order": ["Dairy"],
            "category_aliases": {},
            "local_comment": "",
            "local_entries": [],
            "item_overrides": [],
        }

        def fulfill_json(route, payload):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

        def handle_bootstrap_v31(route):
            shopping_hits["bootstrap_v31"] += 1
            fulfill_json(route, bootstrap_payload)

        def handle_list(route):
            shopping_hits["lists"] += 1
            fulfill_json(route, list_payload)

        def handle_legacy_bootstrap(route):
            shopping_hits["legacy_bootstrap"] += 1
            route.abort()

        page.route("**/api/shopping-print/bootstrap-v31", handle_bootstrap_v31)
        page.route("**/api/shopping-print/bootstrap-v31?*", handle_bootstrap_v31)
        page.route("**/api/shopping-print/bootstrap", handle_legacy_bootstrap)
        page.route("**/api/shopping-print/bootstrap?*", handle_legacy_bootstrap)
        page.route("**/api/access/me*", lambda route: fulfill_json(route, {"is_admin": True, "permissions": {"printer": True}}))
        page.route("**/api/shopping-print/lists/ci-list*", handle_list)

        page.goto(f"{BASE_URL}/shopping-print", wait_until="domcontentloaded", timeout=20_000)
        select = page.locator("#shopping-print-list")
        select.wait_for(state="attached", timeout=5_000)
        try:
            page.wait_for_function(
                """() => {
                    const el = document.querySelector('#shopping-print-list');
                    const status = document.querySelector('#shopping-print-status');
                    return !!el && !el.disabled && !!status && status.textContent.includes('Preview uses');
                }""",
                timeout=5_000,
            )
        except PlaywrightTimeoutError as exc:
            state = page.evaluate(
                """() => {
                    const list = document.querySelector('#shopping-print-list');
                    const status = document.querySelector('#shopping-print-status');
                    return {
                        pathname: location.pathname,
                        v31Loaded: !!window.__b2mShoppingV31Loaded,
                        v30Loaded: !!window.__b2mShoppingV30Loaded,
                        listDisabled: list ? list.disabled : null,
                        listValue: list ? list.value : null,
                        listOptions: list ? Array.from(list.options).map(o => ({value:o.value,text:o.textContent})) : [],
                        status: status ? status.textContent : null,
                    };
                }"""
            )
            raise AssertionError(
                "Shopping Print did not settle. "
                f"state={state!r} hits={shopping_hits!r} "
                f"page_errors={page_errors!r} console={console_messages[-12:]!r}"
            ) from exc

        assert select.input_value() == "ci-list"
        assert page.locator("#shopping-print-canvas").get_attribute("data-height-mm")
        page.wait_for_timeout(700)
        assert shopping_hits["bootstrap_v31"] == 1, shopping_hits
        assert shopping_hits["legacy_bootstrap"] == 0, shopping_hits
        assert 1 <= shopping_hits["lists"] <= 3, shopping_hits

        if page_errors:
            raise AssertionError("Browser JavaScript errors: " + " | ".join(page_errors))

        browser.close()
    print("browser smoke ok")


if __name__ == "__main__":
    main()
