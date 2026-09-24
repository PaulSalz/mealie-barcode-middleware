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

        def wait_until(predicate, message: str, timeout_ms: int = 5_000, step_ms: int = 100) -> None:
            elapsed = 0
            while elapsed < timeout_ms:
                if predicate():
                    return
                page.wait_for_timeout(step_ms)
                elapsed += step_ms
            raise AssertionError(message)

        def css_var(name: str) -> str:
            return page.evaluate(
                "name => getComputedStyle(document.documentElement).getPropertyValue(name).trim()",
                name,
            )

        def computed(selector: str, prop: str) -> str:
            return page.locator(selector).first.evaluate(
                "(el, prop) => getComputedStyle(el)[prop]",
                prop,
            )

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

        # Navbar mode is one personal-state path: complete immediately, then persist.
        legacy_theme_hits = {"count": 0}

        def handle_legacy_theme(route):
            legacy_theme_hits["count"] += 1
            route.abort()

        page.route("**/api/theme/mode", handle_legacy_theme)
        page.goto(f"{BASE_URL}/", wait_until="domcontentloaded", timeout=20_000)
        html = page.locator("html")
        light_body_bg = css_var("--tblr-body-bg")
        light_surface = css_var("--tblr-bg-surface")
        with page.expect_response(lambda r: r.url.endswith("/api/appearance-v24/mode") and r.request.method == "POST", timeout=5_000) as dark_response:
            page.locator("#theme-toggle-dark").click(force=True)
        assert dark_response.value.ok
        assert html.get_attribute("data-bs-theme") == "dark"
        assert css_var("--tblr-body-bg") != light_body_bg
        assert css_var("--tblr-bg-surface") != light_surface
        assert legacy_theme_hits["count"] == 0

        page.reload(wait_until="domcontentloaded")
        html = page.locator("html")
        assert html.get_attribute("data-bs-theme") == "dark"

        with page.expect_response(lambda r: r.url.endswith("/api/appearance-v24/mode") and r.request.method == "POST", timeout=5_000) as light_response:
            page.locator("#theme-toggle-light").click(force=True)
        assert light_response.value.ok
        assert html.get_attribute("data-bs-theme") == "light"
        assert legacy_theme_hits["count"] == 0

        # Appearance must be exact before Save: no network preview and no partial mode.
        preview_api_hits = {"count": 0}

        def handle_preview_api(route):
            preview_api_hits["count"] += 1
            route.abort()

        page.route("**/api/appearance-v24/preview", handle_preview_api)
        page.goto(f"{BASE_URL}/profile/appearance", wait_until="domcontentloaded", timeout=20_000)
        form = page.locator('form[action="/profile/appearance"]')
        form.wait_for(state="visible", timeout=5_000)
        html = page.locator("html")

        background = page.locator('select[name="theme_base"]')
        background.select_option("slate")
        assert html.get_attribute("data-b2m-base") == "slate"
        assert css_var("--tblr-body-bg") == "#f1f5f9"
        assert css_var("--tblr-bg-surface") == "#f8fafc"

        radius = page.locator('select[name="theme_radius"]')
        radius.select_option("2")
        assert html.get_attribute("data-b2m-radius") == "2"
        assert css_var("--tblr-border-radius") == "1.1rem"
        assert computed(".card", "borderRadius") != "0px"

        epaper = page.locator('input[name="theme_epaper"]')
        epaper.check()
        assert "b2m-epaper" in (html.get_attribute("class") or "").split()
        assert computed("html", "filter") == "grayscale(1)"
        assert css_var("--tblr-body-bg") == "#fff"
        assert css_var("--tblr-primary") == "#000"
        assert "rgb" in css_var("--tblr-border-color")
        epaper_border_before = css_var("--tblr-border-color")
        assert computed(".navbar", "backgroundColor") != "rgba(0, 0, 0, 0)"
        assert computed(".card", "backgroundColor") != "rgba(0, 0, 0, 0)"

        contrast = page.locator('input[name="theme_contrast"]')
        contrast.fill("95")
        assert "b2m-epaper" in (html.get_attribute("class") or "").split()
        assert computed("html", "filter") == "grayscale(1)"
        assert css_var("--tblr-body-bg") == "#fff"
        assert css_var("--tblr-border-color") != epaper_border_before
        assert page.locator("#profile-contrast-value").text_content() == "95"

        # Leaving e-paper must restore the selected palette synchronously.
        epaper.uncheck()
        assert "b2m-epaper" not in (html.get_attribute("class") or "").split()
        assert computed("html", "filter") == "none"
        assert css_var("--tblr-body-bg") == "#f1f5f9"
        assert css_var("--tblr-bg-surface") == "#f8fafc"

        page.locator('input[name="theme_mode"][value="dark"]').check(force=True)
        assert html.get_attribute("data-bs-theme") == "dark"
        assert css_var("--tblr-body-bg") == "#020617"
        assert css_var("--tblr-bg-surface") == "#0f172a"
        dark_nav = computed(".navbar", "backgroundColor")
        dark_card = computed(".card", "backgroundColor")

        page.locator('input[name="theme_mode"][value="light"]').check(force=True)
        assert html.get_attribute("data-bs-theme") == "light"
        assert css_var("--tblr-body-bg") == "#f1f5f9"
        assert css_var("--tblr-bg-surface") == "#f8fafc"
        assert computed(".navbar", "backgroundColor") != dark_nav
        assert computed(".card", "backgroundColor") != dark_card
        assert preview_api_hits["count"] == 0

        # Save is persistence only. Save a visible non-default combination and
        # verify the server-rendered HTML + render-blocking CSS already contain it.
        epaper.check()
        contrast.fill("90")
        assert computed("html", "filter") == "grayscale(1)"
        page.get_by_role("button", name="Save appearance").click()
        page.wait_for_url("**/profile/appearance?saved=1", timeout=10_000)
        html = page.locator("html")
        assert html.get_attribute("data-bs-theme") == "light"
        assert html.get_attribute("data-b2m-base") == "slate"
        assert html.get_attribute("data-b2m-radius") == "2"
        assert "b2m-epaper" in (html.get_attribute("class") or "").split()
        assert css_var("--tblr-border-radius") == "1.1rem"
        assert css_var("--tblr-body-bg") == "#fff"
        assert computed("html", "filter") == "grayscale(1)"

        user_css = page.evaluate("() => fetch('/user-theme.css', {cache:'no-store'}).then(r => r.text())")
        assert "--tblr-border-radius:1.1rem" in user_css
        assert "--tblr-gray-950:#020617" in user_css
        assert "html{filter:grayscale(1)}" in user_css

        # Navigation must keep the saved first-paint markers; no default cache flash.
        page.goto(f"{BASE_URL}/", wait_until="domcontentloaded", timeout=20_000)
        html = page.locator("html")
        assert html.get_attribute("data-b2m-base") == "slate"
        assert html.get_attribute("data-b2m-radius") == "2"
        assert "b2m-epaper" in (html.get_attribute("class") or "").split()
        assert css_var("--tblr-border-radius") == "1.1rem"
        assert computed("html", "filter") == "grayscale(1)"

        # Build a deterministic two-label queue for editor/live-layer tests.
        page.goto(f"{BASE_URL}/labels", wait_until="domcontentloaded", timeout=20_000)
        queue_payload = {
            "queue": [
                {"_id": "ci-label-1", "code": "12345678", "label": "CI Label One", "kind": "code128", "qty": 1},
                {"_id": "ci-label-2", "code": "87654321", "label": "CI Label Two", "kind": "code128", "qty": 1},
            ]
        }
        page.evaluate("payload => localStorage.setItem('b2m-label-generator-v2', JSON.stringify(payload))", queue_payload)
        page.reload(wait_until="domcontentloaded")
        page.locator("#label-queue").wait_for(state="attached", timeout=5_000)
        b21_output = page.locator('input[name="label-output"][value="b21"]')
        b21_output.wait_for(state="attached", timeout=5_000)
        b21_output.check(force=True)
        page.locator("#b21-layout-body").wait_for(state="visible", timeout=5_000)
        page.locator("#b21-v24-layer-list").wait_for(state="visible", timeout=5_000)
        label_element = page.locator('#b21-label-stage [data-element-id="label"]')
        label_element.wait_for(state="attached", timeout=5_000)

        layer_switch = page.locator('[data-layer-visible="label"]')
        assert layer_switch.is_checked()
        layer_switch.uncheck()
        label_element.wait_for(state="detached", timeout=3_000)
        assert not page.get_by_text("Label / calibration", exact=True).is_visible()

        # Current label only must use the canonical job endpoint, never v30 batch queue.
        label_hits = {"batch": 0, "jobs_post": 0}

        def handle_batch(route):
            label_hits["batch"] += 1
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "quantity": 2}))

        def handle_job_create(route):
            label_hits["jobs_post"] += 1
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"id": "ci-label-job"}))

        def handle_job_status(route):
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"id": "ci-label-job", "status": "completed", "completed_pages": 1, "page_count": 1, "printed_labels": 1, "error": ""}),
            )

        page.route("**/labels/b21/print-batch-v30", handle_batch)
        page.route("**/labels/b21/jobs", lambda route: handle_job_create(route) if route.request.method == "POST" else route.continue_())
        page.route("**/labels/b21/jobs/ci-label-job", handle_job_status)
        page.locator("#b21-v2-print-scope").select_option("current")
        try:
            with page.expect_request(lambda request: request.url.endswith("/labels/b21/jobs") and request.method == "POST", timeout=7_000):
                page.locator("#label-niim-print").dispatch_event("click")
        except PlaywrightTimeoutError as exc:
            raise AssertionError(f"Current-label print did not reach canonical job endpoint; hits={label_hits!r}") from exc
        wait_until(
            lambda: label_hits["jobs_post"] == 1,
            f"Current-label job route callback did not complete; hits={label_hits!r}",
            timeout_ms=2_000,
            step_ms=25,
        )
        assert label_hits["batch"] == 0, label_hits

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
        status = page.locator("#shopping-print-status")
        try:
            select.wait_for(state="attached", timeout=2_000)
            wait_until(
                lambda: not select.is_disabled() and "Preview uses" in (status.text_content() or ""),
                "Shopping Print did not settle.",
                timeout_ms=3_000,
            )
        except (PlaywrightTimeoutError, AssertionError) as exc:
            try:
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
            except Exception as eval_error:
                state = {"evaluate_error": str(eval_error)}
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
