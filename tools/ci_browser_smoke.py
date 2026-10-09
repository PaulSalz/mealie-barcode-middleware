#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


BASE_URL = os.environ.get("B2M_BROWSER_URL", "http://127.0.0.1:8001")


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
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

        # Activity hover must color every cell in the row, including when the
        # pointer sits over one cell. Navigation positions must be stable when
        # Items becomes the active page.
        page.goto(f"{BASE_URL}/activities", wait_until="load", timeout=20_000)
        page.evaluate("""() => {
            document.querySelector('#activity-tbody').innerHTML =
              '<tr data-href="/barcodes/ci" class="cursor-pointer">' +
              '<td>First</td><td>Second</td><td>Third</td><td>Fourth</td><td>Fifth</td></tr>';
        }""")
        cells = page.locator("#activity-tbody tr:first-child > td")
        def cell_paints():
            return cells.evaluate_all("""(elements) => elements.map(el => {
                const style = getComputedStyle(el);
                return [style.backgroundColor, style.backgroundImage, style.boxShadow];
            })""")
        page.locator("#activity-table thead").hover()
        resting = cell_paints()
        cells.first.hover()
        first_hover = cell_paints()
        cells.nth(2).hover()
        middle_hover = cell_paints()
        assert len({tuple(paint) for paint in first_hover}) == 1, (resting, first_hover)
        assert first_hover == middle_hover and first_hover != resting, (resting, first_hover, middle_hover)

        def nav_positions():
            return page.locator("#navbar-menu > .navbar-nav > .nav-item > .nav-link").evaluate_all(
                "(links) => Object.fromEntries(links.filter(a => getComputedStyle(a).display !== 'none').map(a => [a.textContent.trim(), (() => { const r = a.getBoundingClientRect(); return [r.x, r.y, r.width, r.height].map(n => Math.round(n * 10) / 10); })()]))"
            )

        activity_nav = nav_positions()
        for route in ("/", "/barcodes", "/items", "/actions"):
            page.goto(f"{BASE_URL}{route}", wait_until="domcontentloaded", timeout=20_000)
            initial_nav = nav_positions()
            page.wait_for_load_state("load")
            current_nav = nav_positions()
            assert initial_nav == current_nav, (route, "load shift", initial_nav, current_nav)
            assert activity_nav == current_nav, (route, activity_nav, current_nav)

        # Keep several authenticated tabs open and verify the browser shares one
        # long-lived SSE connection instead of exhausting its per-origin slots.
        context.add_init_script(script="""(() => {
            try { Object.defineProperty(navigator, "locks", {configurable: true, value: undefined}); } catch (e) {}
            const NativeEventSource = window.EventSource;
            window.__b2mEventSources = [];
            if (typeof NativeEventSource === "function") {
                window.EventSource = new Proxy(NativeEventSource, {
                    construct(target, args, newTarget) {
                        const source = Reflect.construct(target, args, newTarget);
                        window.__b2mEventSources.push(source);
                        return source;
                    }
                });
            }
        })();""")
        page.reload(wait_until="domcontentloaded", timeout=20_000)
        event_capabilities = page.evaluate("""() => ({
            secure_context: window.isSecureContext,
            web_locks: Boolean(navigator.locks && navigator.locks.request),
            broadcast_channel: typeof BroadcastChannel === "function",
        })""")
        print("B2M multi-tab event capabilities:", event_capabilities)
        assert not event_capabilities["web_locks"], event_capabilities

        def event_lease_is_active(tab):
            return tab.evaluate("""() => {
                try {
                    const lease = JSON.parse(localStorage.getItem("b2m-live-event-lease-v1") || "null");
                    return Boolean(lease && lease.expires > Date.now());
                } catch (error) {
                    return false;
                }
            }""")

        wait_until(lambda: event_lease_is_active(page), "The active B2M tab did not acquire the shared event lease.", timeout_ms=8_000)
        event_tabs = []
        for index in range(3):
            event_tab = context.new_page()
            event_tab.goto(f"{BASE_URL}/api/version", wait_until="load", timeout=20_000)
            wait_until(
                lambda tab=event_tab: event_lease_is_active(tab),
                "A secondary tab could not see the active tab's event lease.",
                timeout_ms=8_000,
            )
            event_tab.evaluate("document.body.innerHTML = '<div id=scan-toasts></div>'")
            event_tab.add_script_tag(url=f"{BASE_URL}/static/js/app.js?multitab-smoke={index}")
            event_tab.evaluate("""() => {
                window.__b2mReceivedMessages = [];
                window.addEventListener('b2m:sse', event => window.__b2mReceivedMessages.push(event.detail));
            }""")
            event_tabs.append(event_tab)
        page.wait_for_timeout(500)
        event_source_states = [page.evaluate("() => window.__b2mEventSources.map(source => source.readyState)")]
        event_source_states.extend(
            tab.evaluate("() => window.__b2mEventSources.map(source => source.readyState)")
            for tab in event_tabs
        )
        active_streams = sum(
            state in (0, 1)
            for states in event_source_states
            for state in states
        )
        print("B2M live event stream states:", event_source_states)
        assert active_streams == 1, {"event_sources": event_source_states}
        page.evaluate("""() => {
            const source = window.__b2mEventSources.find(item => item.readyState === 1);
            if (!source) throw new Error("No active B2M event stream");
            source.dispatchEvent(new MessageEvent("received", {data: JSON.stringify({barcode: "ci-multitab"})}));
        }""")
        wait_until(
            lambda: all(tab.evaluate("() => window.__b2mReceivedMessages.some(message => message.event === 'received' && message.data.includes('ci-multitab'))") for tab in event_tabs),
            "The shared stream did not broadcast received events to every tab.",
            timeout_ms=3_000,
        )
        for event_tab in event_tabs:
            event_tab.close()

        # Simulate a slow post-b21.css request. Navigation must already have
        # its final position from app.css before the late stylesheet loads.
        page.goto(f"{BASE_URL}/items", wait_until="load", timeout=20_000)
        navbar = page.locator("#navbar-menu > .navbar-nav")
        late_css = page.locator('link[href*="/static/css/post-b21.css"]')
        late_css.wait_for(state="attached", timeout=5_000)
        final_x = navbar.evaluate("(el) => el.getBoundingClientRect().x")
        late_css.evaluate("(el) => { el.disabled = true; }")
        early_x = navbar.evaluate("(el) => el.getBoundingClientRect().x")
        assert abs(early_x - final_x) < 1, (early_x, final_x)
        late_css.evaluate("(el) => { el.disabled = false; }")

        # Navbar light/dark must update immediately and persist as the personal mode.
        page.goto(f"{BASE_URL}/", wait_until="domcontentloaded", timeout=20_000)
        html = page.locator("html")
        with page.expect_response(lambda r: r.url.endswith("/api/appearance-v24/mode") and r.request.method == "POST", timeout=5_000) as dark_response:
            page.locator("#theme-toggle-dark").click(force=True)
        assert dark_response.value.ok
        wait_until(
            lambda: html.get_attribute("data-bs-theme") == "dark",
            "Navbar did not switch to dark mode immediately.",
            timeout_ms=3_000,
        )
        page.reload(wait_until="domcontentloaded")
        html = page.locator("html")
        wait_until(
            lambda: html.get_attribute("data-bs-theme") == "dark",
            "Personal dark mode was not retained after reload.",
            timeout_ms=3_000,
        )

        with page.expect_response(lambda r: r.url.endswith("/api/appearance-v24/mode") and r.request.method == "POST", timeout=5_000) as light_response:
            page.locator("#theme-toggle-light").click(force=True)
        assert light_response.value.ok
        wait_until(
            lambda: html.get_attribute("data-bs-theme") == "light",
            "Navbar did not switch back to light mode immediately.",
            timeout_ms=3_000,
        )

        # Appearance preview must apply light/dark and e-paper before Save.
        page.goto(f"{BASE_URL}/profile/appearance", wait_until="domcontentloaded", timeout=20_000)
        page.locator('form[action="/profile/appearance"]').wait_for(state="visible", timeout=5_000)
        html = page.locator("html")
        epaper = page.locator('input[name="theme_epaper"]')
        epaper.check()
        wait_until(
            lambda: "b2m-epaper" in (html.get_attribute("class") or "").split(),
            "E-paper class was not applied before Save.",
            timeout_ms=3_000,
        )
        preview = page.locator("#b2m-theme-v32-preview")
        wait_until(
            lambda: preview.count() == 1 and "grayscale(1)" in (preview.text_content() or ""),
            "E-paper preview CSS was not applied before Save.",
            timeout_ms=5_000,
        )
        page.locator('input[name="theme_mode"][value="dark"]').check(force=True)
        wait_until(
            lambda: html.get_attribute("data-bs-theme") == "dark",
            "Appearance form did not preview dark mode immediately.",
            timeout_ms=3_000,
        )
        page.locator('input[name="theme_mode"][value="light"]').check(force=True)
        wait_until(
            lambda: html.get_attribute("data-bs-theme") == "light",
            "Appearance form did not preview light mode immediately.",
            timeout_ms=3_000,
        )

        # Frequently used can be personalized and directly added to either list type.
        frequent_limit = page.locator("#appearance-frequent-used-limit")
        assert frequent_limit.is_visible()
        frequent_limit.select_option("9")
        appearance_payloads: list[dict] = []

        def handle_appearance_save(route):
            if route.request.method != "POST":
                route.continue_()
                return
            appearance_payloads.append(route.request.post_data_json)
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"ok": True, "frequent_used_limit": 9}),
            )

        page.route("**/api/appearance-v24", handle_appearance_save)
        page.locator("#appearance-save-button").click()
        wait_until(lambda: bool(appearance_payloads), "Appearance form did not submit.")
        assert appearance_payloads[0]["frequent_used_limit"] == 9, appearance_payloads
        page.unroute("**/api/appearance-v24", handle_appearance_save)
        saved_limit = page.evaluate("""async () => {
            const response = await fetch('/api/appearance-v24', {
              method: 'POST',
              headers: {'Content-Type': 'application/json', Accept: 'application/json'},
              body: JSON.stringify({frequent_used_limit: 9})
            });
            return {ok: response.ok, data: await response.json()};
        }""")
        assert saved_limit["ok"] and saved_limit["data"]["frequent_used_limit"] == 9, saved_limit

        page.route(
            re.compile(r".*/api/dashboard(?:\?.*)?$"),
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({
                    "shopping_lists": [
                        {"id": "ci-list-default", "name": "This week", "default": True, "count": 0},
                        {"id": "ci-list-other", "name": "Later", "default": False, "count": 0},
                    ],
                    "recent_items": [
                        {
                            "barcode": "ci-recent-food",
                            "product_name": "Recent milk",
                            "target_type": "food",
                            "target_id": "ci-food-0",
                            "target_name": "Food 0",
                            "target_count": 1,
                            "targets": [{"type": "food", "id": "ci-food-0", "name": "Food 0"}],
                            "title": "Recent milk",
                            "source": "CI",
                            "status": "mapped",
                            "result": "added",
                            "created_at": "just now",
                            "created_at_absolute": "now",
                        },
                        {
                            "barcode": "ci-recent-recipe",
                            "product_name": "Dinner",
                            "target_type": "recipe",
                            "target_id": "ci-recipe-0",
                            "target_name": "Recipe 0",
                            "target_count": 1,
                            "targets": [{"type": "recipe", "id": "ci-recipe-0", "name": "Recipe 0"}],
                            "title": "Recipe 0",
                            "source": "CI",
                            "status": "mapped",
                            "result": "added",
                            "created_at": "just now",
                            "created_at_absolute": "now",
                        },
                        {
                            "barcode": "ci-recent-action",
                            "product_name": "Action scan",
                            "target_type": "action",
                            "target_id": "ci-action",
                            "target_name": "Kitchen light",
                            "target_count": 1,
                            "targets": [{"type": "action", "id": "ci-action", "name": "Kitchen light"}],
                            "title": "Kitchen light",
                            "source": "CI",
                            "status": "mapped",
                            "result": "action_triggered",
                            "created_at": "just now",
                            "created_at_absolute": "now",
                        },
                    ],
                    "total_barcodes": 0, "mapped_count": 0, "pending_count": 0,
                    "queue_depth": 0, "unknown_count": 0, "scanner_online": 0, "scanner_total": 0,
                }),
            ),
        )
        page.route(
            "**/api/dashboard/frequent",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({
                    "foods": [{"id": "ci-food-" + str(i), "name": "Food " + str(i), "uses": 12 - i} for i in range(10)],
                    "recipes": [{"id": "ci-recipe-" + str(i), "name": "Recipe " + str(i), "uses": 10 - i} for i in range(10)],
                    "actions": [{"id": "ci-action", "name": "Kitchen light", "uses": 7}],
                    "limit": 9,
                }),
            ),
        )
        added_targets: list[dict] = []

        def handle_frequent_add(route):
            added_targets.append(route.request.post_data_json)
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"ok": True, "list_name": "This week"}),
            )

        page.route("**/api/dashboard/frequent/add", handle_frequent_add)
        triggered_actions: list[dict] = []

        def handle_frequent_action_trigger(route):
            triggered_actions.append({"url": route.request.url, "method": route.request.method})
            route.fulfill(status=202, content_type="application/json", body=json.dumps({"ok": True, "status": "queued"}))

        page.route("**/api/dashboard/frequent/actions/*/trigger", handle_frequent_action_trigger)
        page.goto(f"{BASE_URL}/", wait_until="domcontentloaded", timeout=20_000)
        page.locator("#recent-scans-card").evaluate("""card => {
            if (card.querySelector("#recent-scans-body")) return;
            const placeholder = card.querySelector(".card-body");
            if (placeholder) placeholder.remove();
            const table = document.createElement("div");
            table.className = "table-responsive";
            table.innerHTML = '<table class="table table-vcenter card-table"><tbody id="recent-scans-body"></tbody></table>';
            card.appendChild(table);
        }""")
        page.evaluate("window.dispatchEvent(new Event('focus'))")
        wait_until(
            lambda: page.locator("#recent-scans-body .b2m-frequent-add").count() == 2,
            "Recent food and recipe quick-add buttons were not rendered.",
        )
        assert page.locator("#recent-scans-body .b2m-frequent-trigger").count() == 1
        wait_until(
            lambda: page.locator("#b2m-frequent-foods .b2m-frequent-add").count() == 9,
            "Dashboard did not apply the personal Frequently used limit.",
        )
        assert page.locator("#b2m-frequent-recipes .b2m-frequent-add").count() == 9
        action_button = page.locator("#b2m-frequent-actions .b2m-frequent-trigger")
        assert action_button.count() == 1
        assert "btn-sm" not in (action_button.get_attribute("class") or "")
        with page.expect_request(
            lambda request: request.url.endswith("/api/dashboard/frequent/actions/ci-action/trigger")
            and request.method == "POST",
            timeout=5_000,
        ):
            action_button.click()
        wait_until(lambda: len(triggered_actions) == 1, "Dashboard action was not triggered.")
        assert triggered_actions[0]["method"] == "POST"

        recent_add = page.locator("#recent-scans-body .b2m-frequent-add").first
        recent_add.click()
        modal = page.locator("#b2m-frequent-add-modal")
        modal.wait_for(state="visible", timeout=3_000)
        assert page.locator("#b2m-frequent-add-name").inner_text() == "Food 0"
        page.locator("#b2m-frequent-add-modal [data-bs-dismiss='modal']").last.click()
        wait_until(lambda: not modal.is_visible(), "Recent scan quick-add dialog did not close.", timeout_ms=2_000)
        with page.expect_request(
            lambda request: request.url.endswith("/api/dashboard/frequent/actions/ci-action/trigger")
            and request.method == "POST",
            timeout=5_000,
        ):
            page.locator("#recent-scans-body .b2m-frequent-trigger").click()
        wait_until(lambda: len(triggered_actions) == 2, "Recent scan action was not triggered.")

        page.locator("#b2m-frequent-foods .b2m-frequent-add").first.click()
        modal = page.locator("#b2m-frequent-add-modal")
        modal.wait_for(state="visible", timeout=3_000)
        modal_name = page.locator("#b2m-frequent-add-name")
        assert "fs-3" in (modal_name.get_attribute("class") or "")
        assert modal_name.inner_text() == "Food 0"
        wait_until(lambda: page.locator("#b2m-frequent-add-list option").count() == 2, "Shopping lists did not load.")
        page.locator("#b2m-frequent-add-list").select_option("ci-list-other")
        page.locator("#b2m-frequent-add-quantity").fill("2.5")
        with page.expect_request(
            lambda request: request.url.endswith("/api/dashboard/frequent/add")
            and request.method == "POST",
            timeout=5_000,
        ):
            page.locator("#b2m-frequent-add-submit").click()
        wait_until(lambda: len(added_targets) == 1, "Food was not added from the dashboard.")
        assert added_targets[0] == {
            "target_type": "food",
            "target_id": "ci-food-0",
            "list_id": "ci-list-other",
            "quantity": 2.5,
        }, added_targets
        wait_until(lambda: not modal.is_visible(), "Food add dialog did not close.", timeout_ms=3_000)

        page.locator("#b2m-frequent-recipes .b2m-frequent-add").first.click()
        modal.wait_for(state="visible", timeout=3_000)
        wait_until(lambda: page.locator("#b2m-frequent-add-list option").count() == 2, "Shopping lists did not reload.")
        page.locator("#b2m-frequent-add-list").select_option("ci-list-default")
        page.locator("#b2m-frequent-add-quantity").fill("3")
        with page.expect_request(
            lambda request: request.url.endswith("/api/dashboard/frequent/add")
            and request.method == "POST",
            timeout=5_000,
        ):
            page.locator("#b2m-frequent-add-submit").click()
        wait_until(lambda: len(added_targets) == 2, "Recipe was not added from the dashboard.")
        assert added_targets[1] == {
            "target_type": "recipe",
            "target_id": "ci-recipe-0",
            "list_id": "ci-list-default",
            "quantity": 3.0,
        }, added_targets
        wait_until(lambda: not modal.is_visible(), "Recipe add dialog did not close.", timeout_ms=3_000)

        # The quick-add dialog also closes from the backdrop and Escape key.
        page.locator("#b2m-frequent-foods .b2m-frequent-add").first.click()
        modal.wait_for(state="visible", timeout=3_000)
        page.locator("#b2m-frequent-add-modal").evaluate("(el) => el.dispatchEvent(new MouseEvent('click', {bubbles:true}))")
        wait_until(lambda: not modal.is_visible(), "Backdrop click did not close the dialog.", timeout_ms=2_000)

        page.locator("#b2m-frequent-foods .b2m-frequent-add").first.click()
        modal.wait_for(state="visible", timeout=3_000)
        page.keyboard.press("Escape")
        wait_until(lambda: not modal.is_visible(), "Escape did not close the dialog.", timeout_ms=2_000)

        page.set_viewport_size({"width": 390, "height": 844})
        for selector in (
            "#shopping-lists-card",
            ".b2m-dashboard-overview",
            ".b2m-dashboard-counts",
            "#b2m-frequent-dashboard",
        ):
            assert page.locator(selector).is_visible(), selector
        assert page.locator("#recent-scans-body .b2m-frequent-trigger").is_visible()
        recent_section = page.locator("#recent-scans-card")
        frequent_section = page.locator("details.b2m-dashboard-frequent")
        assert recent_section.evaluate("(element) => element.open")
        assert frequent_section.evaluate("(element) => element.open")
        recent_section.locator("summary").click()
        wait_until(lambda: not recent_section.evaluate("(element) => element.open"), "Recent scans did not collapse on mobile.")
        frequent_section.locator("summary").click()
        wait_until(lambda: not frequent_section.evaluate("(element) => element.open"), "Frequently used did not collapse on mobile.")
        assert not page.locator("#recent-scans-body").is_visible()
        assert not page.locator("#b2m-frequent-dashboard").is_visible()
        page.set_viewport_size({"width": 1280, "height": 900})
        wait_until(
            lambda: recent_section.evaluate("(element) => element.open") and frequent_section.evaluate("(element) => element.open"),
            "Dashboard sections did not reopen on desktop.",
        )
        page.unroute_all()

        # Build a deterministic two-label queue for editor/live-layer tests.
        page.route(
            "**/labels/b21/status",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({
                    "configured": True,
                    "connected": True,
                    "info": {"modelMetadata": {"model": "CI B21", "dpi": 300}},
                    "dpi": 300,
                }),
            ),
        )
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

        # Printer diagnostics follow the global Basic/Advanced preference.
        tools = page.locator('.d-none.d-md-flex a[data-bs-toggle="dropdown"]').first
        tools.wait_for(state="visible", timeout=5_000)
        tools.click()
        global_advanced = page.locator("#b2m-global-advanced-toggle")
        global_advanced.wait_for(state="visible", timeout=5_000)
        if global_advanced.is_checked():
            with page.expect_response(
                lambda response: response.url.endswith("/api/appearance-v24")
                and response.request.method == "POST",
                timeout=5_000,
            ):
                global_advanced.uncheck(force=True)
        wait_until(
            lambda: not page.locator("html").evaluate("el => el.classList.contains('b2m-advanced-enabled')"),
            "Global Advanced mode did not switch off.",
        )
        printer_card = page.locator("#b21-printer-card")
        printer_card.wait_for(state="attached", timeout=5_000)
        assert not printer_card.is_visible(), "Printer controls should be hidden in browser output mode."
        assert printer_card.evaluate("(el) => el.closest('#b21-output-card') !== null"), "Printer controls should be integrated into the output selection card."
        disconnect_button = page.locator("#b21-connect-button")
        assert not disconnect_button.is_visible(), "The printer connection button should be hidden in browser output mode."
        browser_columns = page.locator("#b21-output-grid").evaluate(
            "(el) => getComputedStyle(el).gridTemplateColumns.split(' ').map(parseFloat)"
        )
        assert browser_columns[0] > browser_columns[1], browser_columns
        b21_toolbar = page.locator("#b21-v2-header")
        b21_toolbar.wait_for(state="attached", timeout=5_000)
        assert not b21_toolbar.is_visible(), "B21-specific print controls should be hidden in browser output mode."
        b21_output = page.locator('input[name="label-output"][value="b21"]')
        b21_output.wait_for(state="attached", timeout=5_000)
        b21_output.check(force=True)
        page.locator("#b21-layout-body").wait_for(state="visible", timeout=5_000)
        wait_until(
            lambda: printer_card.is_visible()
            and disconnect_button.is_visible()
            and "Disconnect" in (disconnect_button.text_content() or ""),
            "B21 printer controls should appear when B21 output is selected.",
            timeout_ms=5_000,
        )
        assert b21_toolbar.is_visible(), "B21 printer controls should remain available in Basic mode."
        assert page.locator("#b21-v2-print-scope").count() == 0
        assert page.locator("#b21-v2-copies").count() == 0
        assert page.locator("#label-print").inner_text().strip() == "Print all"
        b21_columns = page.locator("#b21-output-grid").evaluate(
            "(el) => getComputedStyle(el).gridTemplateColumns.split(' ').map(parseFloat)"
        )
        assert b21_columns[1] > b21_columns[0], b21_columns
        if not global_advanced.is_visible():
            tools.click()
            global_advanced.wait_for(state="visible", timeout=5_000)
        if not global_advanced.is_checked():
            if not global_advanced.is_visible():
                tools.click()
                global_advanced.wait_for(state="visible", timeout=5_000)
            with page.expect_response(
                lambda response: response.url.endswith("/api/appearance-v24")
                and response.request.method == "POST",
                timeout=5_000,
            ):
                global_advanced.check(force=True)
        wait_until(
            lambda: page.locator("html").evaluate("el => el.classList.contains('b2m-advanced-enabled')"),
            "Global Advanced mode did not switch on.",
        )
        b21_toolbar.wait_for(state="visible", timeout=5_000)
        page.locator("#b21-v24-layer-list").wait_for(state="visible", timeout=5_000)
        label_element = page.locator('#b21-label-stage [data-element-id="label"]')
        label_element.wait_for(state="attached", timeout=5_000)
        page.wait_for_function(
            "() => { const link=document.getElementById('b21-designer-stylesheet'); return !!link && !!link.sheet && link.sheet.cssRules.length > 0; }",
            timeout=5_000,
        )

        # Queue edit actions replace the preview dropdown; redundant printer data stays in Settings.
        label_ui = page.evaluate("""() => {
          const preview = document.querySelector('.b21-sticky-preview-card');
          const selector = document.getElementById('b21-preview-selector');
          const entrySelect = document.getElementById('b21-entry-select');
          const kind = document.querySelector('#label-queue .entry-kind');
          const copies = document.querySelector('#label-queue .entry-qty');
          const edit = document.querySelector('#label-queue .entry-edit');
          const entryPrint = document.querySelector('#label-queue .entry-print');
          const printAll = document.getElementById('label-print');
          const quickPrint = document.querySelector('#label-editor-mode [data-label-mode="quick"]');
          const layers = document.getElementById('b21-v2-layers-header');
          const presetHeader = document.getElementById('b21-v13-preset-header');
          const reset = document.getElementById('b21-v2-reset-all');
          const content = document.getElementById('b21-v2-content-row');
          const align = document.getElementById('b21-v22-element-align');
          const divider = document.querySelector('.b21-v22-align-divider');
          const typography = document.getElementById('b21-v22-typography');
          const printerInfo = ['b21-status-dot','b21-status-title','b21-status-detail','b21-v2-printer-data','b21-v4-output-status']
            .filter(id => document.getElementById(id)).length;
          return {
            title: preview?.querySelector('.card-title')?.textContent.trim(),
            selectorRemoved: !selector,
            entrySelectHidden: !!entrySelect && entrySelect.hidden,
            queueEditVisible: !!edit && getComputedStyle(edit).display !== 'none',
            queuePrintVisible: !!entryPrint && getComputedStyle(entryPrint).display !== 'none',
            printButtonsAdjacent: !!edit && !!entryPrint && edit.previousElementSibling === entryPrint,
            printAllAfterQuick: !!printAll && !!quickPrint && printAll.previousElementSibling === quickPrint,
            printAllText: printAll?.textContent.trim(),
            copiesHeight: copies ? parseFloat(getComputedStyle(copies).height) : null,
            kindHeight: kind ? parseFloat(getComputedStyle(kind).height) : null,
            previewMeta: !!document.getElementById('b21-preview-meta'),
            printerInfo, connectVisible: !!document.querySelector('#b21-connect-button'),
            layersTitle: layers?.querySelector('.fw-semibold')?.textContent.trim(),
            layersMargin: parseFloat(getComputedStyle(layers).marginTop),
            resetInPresets: !!reset && reset.parentElement === presetHeader,
            resetInLayers: !!layers?.contains(reset),
            contentBorder: parseFloat(getComputedStyle(content).borderLeftWidth),
            alignTitle: align?.querySelector('.fw-semibold')?.textContent.trim(),
            alignHintCount: align?.querySelectorAll('.form-hint').length,
            duplicateAlignLabel: align?.querySelector('label.form-label')?.textContent.trim() || '',
            dividerWidth: parseFloat(getComputedStyle(divider).borderTopWidth),
            dividerBeforeTypography: !!divider && divider.nextElementSibling === typography
          };
        }""")
        assert label_ui["title"] == "B21 label preview", label_ui
        assert label_ui["selectorRemoved"] and label_ui["entrySelectHidden"], label_ui
        assert label_ui["queueEditVisible"] and label_ui["queuePrintVisible"], label_ui
        assert label_ui["printButtonsAdjacent"] and label_ui["printAllAfterQuick"], label_ui
        assert label_ui["printAllText"] == "Print all", label_ui
        assert abs(label_ui["copiesHeight"] - label_ui["kindHeight"]) < 1, label_ui
        assert not label_ui["previewMeta"], label_ui
        assert label_ui["printerInfo"] == 0 and label_ui["connectVisible"], label_ui
        assert label_ui["layersTitle"] == "Layers" and label_ui["layersMargin"] >= 16, label_ui
        assert label_ui["resetInPresets"] and not label_ui["resetInLayers"], label_ui
        assert label_ui["contentBorder"] >= 1, label_ui
        assert label_ui["alignTitle"] == "Align" and label_ui["alignHintCount"] == 0, label_ui
        assert label_ui["duplicateAlignLabel"] == "", label_ui
        assert label_ui["dividerWidth"] == 1 and label_ui["dividerBeforeTypography"], label_ui

        page.locator("#label-queue .entry-edit").nth(1).click()
        assert page.locator("#b21-entry-select").input_value() == "1"
        page.wait_for_function(
            "() => document.querySelector('#b21-label-stage [data-element-id=label]')?.textContent === 'CI Label Two'",
            timeout=5_000,
        )
        page.wait_for_function(
            "() => { const image=document.querySelector('#b21-label-stage .b21-code'); return !!image && image.complete && image.naturalWidth > 0; }",
            timeout=5_000,
        )
        page.locator('#b21-v24-layer-list [data-layer-select="code"]').click()
        invert_key = page.evaluate("""() => {
          const queue=JSON.parse(localStorage.getItem('b2m-label-generator-v2')||'{}').queue||[];
          return String(queue[Number(document.getElementById('b21-entry-select')?.value||0)]?._id);
        }""")
        page.locator('#b21-v24-layer-list [data-layer-invert="code"]').click()
        page.wait_for_function("""key => {
          const all=JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3')||'{}');
          return all[key]?.elements.find(row=>row.id==='code')?.inverted===true;
        }""", arg=invert_key, timeout=5_000)
        assert page.locator('#b21-label-stage [data-element-id="code"].b21-layer-inverted .b21-code').evaluate("el => getComputedStyle(el).filter") == "invert(1)"
        page.locator('#b21-v24-layer-list [data-layer-invert="code"]').click()
        page.wait_for_function("""key => {
          const all=JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3')||'{}');
          return all[key]?.elements.find(row=>row.id==='code')?.inverted===false;
        }""", arg=invert_key, timeout=5_000)
        for align_mode, edge in (("right", "right"), ("left", "left")):
            page.locator(f'#b21-v2-align [data-align="{align_mode}"]').click()
            page.wait_for_function(
                "edge => { const stage=document.querySelector('#b21-label-stage'), code=stage?.querySelector('.b21-code-content'); if(!stage||!code)return false; const a=stage.getBoundingClientRect(),b=code.getBoundingClientRect(); return Math.abs(a[edge]-b[edge])<2; }",
                arg=edge,
                timeout=5_000,
            )

        code128_resize = page.evaluate("""() => {
          const stage=document.querySelector('#b21-label-stage');
          const widthInput=document.getElementById('b21-v2-w');
          const heightInput=document.getElementById('b21-v2-h');
          const bounds=()=>{const rect=stage.querySelector('.b21-code-content').getBoundingClientRect();return {width:rect.width,height:rect.height};};
          const beforeWidth=bounds();
          widthInput.value=String(Math.min(100,Number(widthInput.value)+5));
          widthInput.dispatchEvent(new Event('input',{bubbles:true}));
          const afterWidth=bounds();
          heightInput.value=String(Math.max(1,Number(heightInput.value)-8));
          heightInput.dispatchEvent(new Event('input',{bubbles:true}));
          return {beforeWidth,afterWidth,afterHeight:bounds()};
        }""")
        assert code128_resize["afterWidth"]["width"] > code128_resize["beforeWidth"]["width"] + 1, code128_resize
        assert abs(code128_resize["afterWidth"]["height"] - code128_resize["beforeWidth"]["height"]) < 1, code128_resize
        assert code128_resize["afterHeight"]["height"] < code128_resize["afterWidth"]["height"] - 1, code128_resize
        size_labels = page.evaluate("""() => ['w','h'].map(key => document.getElementById('b21-v2-'+key+'-value')?.textContent || '')""")
        assert all(value.isdigit() for value in size_labels), size_labels

        # Code 128 handle resize must persist both dimensions without a release snap.
        code_drag_before = page.evaluate("""() => {
          const data=JSON.parse(localStorage.getItem('b2m-label-generator-v2')||'{}').queue||[];
          const index=Number(document.getElementById('b21-entry-select')?.value||0);
          const key=String(data[index]?._id);
          const all=JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3')||'{}');
          const code=all[key]?.elements.find(row=>row.id==='code');
          return {key,w:code.w,h:code.h};
        }""")
        code_handle = page.locator('#b21-v2-code-resize-handle')
        code_handle.wait_for(state='attached', timeout=5_000)
        code_handle_box = code_handle.bounding_box()
        assert code_handle_box is not None
        page.mouse.move(code_handle_box['x']+code_handle_box['width']/2, code_handle_box['y']+code_handle_box['height']/2)
        page.mouse.down()
        page.mouse.move(code_handle_box['x']+code_handle_box['width']/2+14, code_handle_box['y']+code_handle_box['height']/2+10, steps=4)
        page.mouse.up()
        page.wait_for_function("""([key,width,height]) => {
          const all=JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3')||'{}');
          const code=all[key]?.elements.find(row=>row.id==='code');
          return !!code && (code.w!==width || code.h!==height);
        }""", arg=[code_drag_before['key'],code_drag_before['w'],code_drag_before['h']], timeout=5_000)
        code_drag_after = page.evaluate("""key => {
          const all=JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3')||'{}');
          const code=all[key].elements.find(row=>row.id==='code');
          const stage=document.getElementById('b21-label-stage').getBoundingClientRect();
          const box=document.querySelector('#b21-label-stage .b21-code-box').getBoundingClientRect();
          return {w:code.w,h:code.h,boxW:box.width,boxH:box.height,stageW:stage.width,stageH:stage.height};
        }""", code_drag_before['key'])
        assert code_drag_after['w'] != code_drag_before['w'] or code_drag_after['h'] != code_drag_before['h'], (code_drag_before, code_drag_after)
        assert abs(code_drag_after['boxW'] - code_drag_after['stageW']*code_drag_after['w']/100) < 2, code_drag_after
        assert abs(code_drag_after['boxH'] - code_drag_after['stageH']*code_drag_after['h']/100) < 2, code_drag_after

        page.evaluate("""() => {
          const selector=document.querySelectorAll('#label-queue .entry-kind')[1];
          if(!selector) throw new Error('Second queue code-style selector is missing.');
          selector.value='qr';
          selector.dispatchEvent(new Event('change',{bubbles:true}));
        }""")
        page.wait_for_function(
            "() => { const image=document.querySelector('#b21-label-stage .b21-code'); return !!image && image.src.includes('kind=qr') && image.complete && image.naturalWidth > 0; }",
            timeout=5_000,
        )
        page.wait_for_function(
            """() => {
              const all=JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3')||'{}');
              const queue=JSON.parse(localStorage.getItem('b2m-label-generator-v2')||'{}').queue||[];
              const code=all[String(queue[1]._id)]?.elements.find(row=>row.id==='code');
              const dimensions=document.querySelector('#b21-label-stage').style.aspectRatio.split('/').map(value=>Number(value.trim()));
              return !!code && Math.abs(code.w*dimensions[0]-code.h*dimensions[1])<0.01;
            }""",
            timeout=5_000,
        )
        page.evaluate("""() => {
          const widthInput=document.getElementById('b21-v2-w');
          widthInput.value='40';
          widthInput.dispatchEvent(new Event('input',{bubbles:true}));
        }""")
        page.wait_for_function(
            """() => {
              const all=JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3')||'{}');
              const queue=JSON.parse(localStorage.getItem('b2m-label-generator-v2')||'{}').queue||[];
              const code=all[String(queue[1]._id)]?.elements.find(row=>row.id==='code');
              const dimensions=document.querySelector('#b21-label-stage').style.aspectRatio.split('/').map(value=>Number(value.trim()));
              return !!code && Math.abs(code.w-40)<0.01 && Math.abs(code.w*dimensions[0]-code.h*dimensions[1])<0.01;
            }""",
            timeout=5_000,
        )
        qr_resize = page.evaluate("""() => {
          const stage=document.querySelector('#b21-label-stage');
          const widthInput=document.getElementById('b21-v2-w');
          const all=JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3')||'{}');
          const queue=JSON.parse(localStorage.getItem('b2m-label-generator-v2')||'{}').queue||[];
          const code=all[String(queue[1]._id)].elements.find(row=>row.id==='code');
          const rect=stage.querySelector('.b21-code-content').getBoundingClientRect();
          return {code,visualWidth:rect.width,visualHeight:rect.height,dimensions:stage.style.aspectRatio.split('/').map(value=>Number(value.trim())),inputValue:widthInput.value,selectedIndex:document.getElementById('b21-entry-select')?.value,imageSrc:stage.querySelector('.b21-code')?.src};
        }""")
        assert abs(qr_resize["code"]["w"] * qr_resize["dimensions"][0] - qr_resize["code"]["h"] * qr_resize["dimensions"][1]) < 0.01, qr_resize
        assert abs(qr_resize["code"]["w"] - 40) < 0.01, qr_resize
        assert abs(qr_resize["visualWidth"] - qr_resize["visualHeight"]) < 1, qr_resize

        # QR handle drag stays square and its stored dimensions match the final preview.
        qr_drag_before = page.evaluate("""() => {
          const queue=JSON.parse(localStorage.getItem('b2m-label-generator-v2')||'{}').queue||[];
          const key=String(queue[Number(document.getElementById('b21-entry-select')?.value||0)]?._id);
          const all=JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3')||'{}');
          const code=all[key].elements.find(row=>row.id==='code');
          return {key,w:code.w,h:code.h};
        }""")
        qr_handle = page.locator('#b21-v2-code-resize-handle')
        qr_handle.wait_for(state='attached', timeout=5_000)
        qr_handle_box = qr_handle.bounding_box()
        assert qr_handle_box is not None
        page.mouse.move(qr_handle_box['x']+qr_handle_box['width']/2, qr_handle_box['y']+qr_handle_box['height']/2)
        page.mouse.down()
        page.mouse.move(qr_handle_box['x']+qr_handle_box['width']/2+12, qr_handle_box['y']+qr_handle_box['height']/2+12, steps=4)
        page.mouse.up()
        page.wait_for_function("""([key,width,height]) => {
          const all=JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3')||'{}');
          const code=all[key]?.elements.find(row=>row.id==='code');
          return !!code && (Math.abs(code.w-width)>0.001 || Math.abs(code.h-height)>0.001);
        }""", arg=[qr_drag_before['key'],qr_drag_before['w'],qr_drag_before['h']], timeout=5_000)
        qr_drag_after = page.evaluate("""key => {
          const all=JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3')||'{}');
          const code=all[key].elements.find(row=>row.id==='code');
          const stage=document.getElementById('b21-label-stage').getBoundingClientRect();
          const visual=document.querySelector('#b21-label-stage .b21-code-content').getBoundingClientRect();
          return {w:code.w,h:code.h,visualW:visual.width,visualH:visual.height,stageW:stage.width,stageH:stage.height};
        }""", qr_drag_before['key'])
        assert abs(qr_drag_after['w']*qr_resize['dimensions'][0] - qr_drag_after['h']*qr_resize['dimensions'][1]) < 0.01, qr_drag_after
        assert abs(qr_drag_after['visualW'] - qr_drag_after['visualH']) < 1, qr_drag_after
        assert abs(qr_drag_after['visualW'] - qr_drag_after['stageW']*qr_drag_after['w']/100) < 2, qr_drag_after
        assert abs(qr_drag_after['visualH'] - qr_drag_after['stageH']*qr_drag_after['h']/100) < 2, qr_drag_after

        sticky_result = page.evaluate("""() => {
            const preview = document.querySelector('.b21-sticky-preview-card');
            const position = getComputedStyle(preview).position;
            const absoluteTop = preview.getBoundingClientRect().top + window.scrollY;
            window.scrollTo({top: absoluteTop + 168, behavior: 'instant'});
            return {position, top: preview.getBoundingClientRect().top};
        }""")
        assert sticky_result["position"] == "sticky", sticky_result
        assert 12 <= sticky_result["top"] <= 20, sticky_result
        page.evaluate("window.scrollTo(0, 0)")

        assert page.locator("[data-layer-visible]").count() > 0
        assert page.locator("#b21-v2-visible").count() == 0
        page.locator('[data-layer-select="label"]').click()
        page.locator('[data-layer-visible="label"]').click()
        label_element.wait_for(state="detached", timeout=3_000)
        assert not page.get_by_text("Label / calibration", exact=True).is_visible()
        page.locator('[data-layer-visible="label"]').click()
        label_element.wait_for(state="attached", timeout=3_000)

        # Selecting a layer and dragging it immediately must persist its new position.
        page.locator('[data-layer-select="label"]').click()
        page.wait_for_function(
            "() => !!document.querySelector('#b21-label-stage [data-element-id=label] .b21-v2-text-content.b21-v2-element-selected')",
            timeout=5_000,
        )
        label_before = page.evaluate("""() => {
          const all = JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3') || '{}');
          const queue = JSON.parse(localStorage.getItem('b2m-label-generator-v2') || '{}').queue || [];
          const index = Number(document.getElementById('b21-entry-select')?.value || 0);
          const entry = all[String(queue[index]?._id)];
          const element = entry && entry.elements.find(row => row.id === 'label');
          return element && {x: element.x, y: element.y};
        }""")
        label_box = page.locator('#b21-label-stage [data-element-id="label"] .b21-v2-text-content').bounding_box()
        assert label_before is not None and label_box is not None
        drag_x = label_box["x"] + label_box["width"] / 2
        drag_y = label_box["y"] + label_box["height"] / 2
        page.mouse.move(drag_x, drag_y)
        page.mouse.down()
        page.mouse.move(drag_x + 48, drag_y + 30, steps=5)
        page.mouse.up()
        page.wait_for_timeout(150)
        label_after_drag = page.evaluate("""() => {
          const all = JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3') || '{}');
          const queue = JSON.parse(localStorage.getItem('b2m-label-generator-v2') || '{}').queue || [];
          const index = Number(document.getElementById('b21-entry-select')?.value || 0);
          const entry = all[String(queue[index]?._id)];
          const element = entry && entry.elements.find(row => row.id === 'label');
          return element && {x: element.x, y: element.y};
        }""")
        assert label_after_drag is not None
        assert label_after_drag["x"] != label_before["x"] or label_after_drag["y"] != label_before["y"], (label_before, label_after_drag)
        page.locator('[data-layer-select="code"]').click()
        page.locator('[data-layer-select="label"]').click()
        label_after_reselect = page.evaluate("""() => {
          const all = JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3') || '{}');
          const queue = JSON.parse(localStorage.getItem('b2m-label-generator-v2') || '{}').queue || [];
          const index = Number(document.getElementById('b21-entry-select')?.value || 0);
          const entry = all[String(queue[index]?._id)];
          const element = entry && entry.elements.find(row => row.id === 'label');
          return element && {x: element.x, y: element.y};
        }""")
        assert label_after_reselect == label_after_drag, (label_after_drag, label_after_reselect)

        # Layer order remains saved when a different layer is selected.
        page.locator('[data-layer-forward="label"]').click()
        saved_order = page.evaluate("""() => {
          const state = JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3') || '{}');
          const entry = Object.values(state).find(value => value && Array.isArray(value.elements));
          return entry ? entry.elements.map(element => element.id) : [];
        }""")
        page.locator('[data-layer-select="code"]').click()
        reloaded_order = page.evaluate("""() => {
          const state = JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3') || '{}');
          const entry = Object.values(state).find(value => value && Array.isArray(value.elements));
          return entry ? entry.elements.map(element => element.id) : [];
        }""")
        assert saved_order == reloaded_order
        assert saved_order.index("label") > saved_order.index("code")

        # Presets fit label text to the selected roll; copy/paste keeps each code's identity.
        page.locator("#label-queue .entry-edit").nth(0).click()
        page.evaluate("window.__b2mB21LabelEditor.prepareQueue()")
        smallest_profile = page.evaluate("""async () => {
          const data = await (await fetch('/labels/b21/profiles')).json();
          return (data.profiles || []).slice().sort((a, b) => a.width_mm * a.height_mm - b.width_mm * b.height_mm)[0] || null;
        }""")
        assert smallest_profile is not None, "B21 profile list should include a selectable label size."
        page.locator("#b21-profile-select").select_option(str(smallest_profile["id"]))
        entry_keys = page.evaluate("""() => {
          const data = JSON.parse(localStorage.getItem('b2m-label-generator-v2') || '{}');
          const key = (entry, index) => String(entry && entry._id != null ? entry._id : ((entry && entry.code) || 'entry-' + index));
          return {source:key(data.queue[0],0),target:key(data.queue[1],1)};
        }""")
        source_key, target_key = entry_keys["source"], entry_keys["target"]
        page.locator('#b21-v4-presets [data-preset="stacked"]').click()
        preset_geometry = page.evaluate("""key => {
          const all = JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3') || '{}');
          const elements = all[key].elements;
          const label = elements.find(row => row.id === 'label');
          const code = elements.find(row => row.id === 'code');
          return {labelWidth:label.w,labelHeight:label.h,codeWidth:code.w,codeHeight:code.h,fontSize:label.fontSizePt};
        }""", source_key)
        assert preset_geometry == {"labelWidth": 92, "labelHeight": 34, "codeWidth": 92, "codeHeight": 50, "fontSize": preset_geometry["fontSize"]}, preset_geometry
        short_font = preset_geometry["fontSize"]
        page.wait_for_function("""() => {
          const img = document.querySelector('#b21-label-stage .b21-code-box .b21-code');
          return !!img && img.complete && img.naturalWidth > 0;
        }""", timeout=5_000)
        code_frame = page.evaluate("""() => {
          const box = document.querySelector('#b21-label-stage .b21-code-box');
          const visual = box && box.querySelector('.b21-code-content');
          const image = visual && visual.querySelector('img');
          const rect = element => {
            const value = element.getBoundingClientRect();
            return {width:value.width,height:value.height};
          };
          const style = image && getComputedStyle(image);
          const activeOutlines = [box,visual,image].filter(element => {
            const value = getComputedStyle(element);
            return value.outlineStyle !== 'none' && value.outlineWidth !== '0px';
          }).length;
          return {
            box:rect(box),visual:rect(visual),image:rect(image),
            imageRatio:image.naturalWidth/image.naturalHeight,
            visualRatio:visual.getBoundingClientRect().width/visual.getBoundingClientRect().height,
            outline:style.outlineWidth,outlineOffset:style.outlineOffset,
            boxOutline:getComputedStyle(box).outlineStyle,
            visualOutline:getComputedStyle(visual).outlineStyle,
            activeOutlines,
            selected:image.classList.contains('b21-v2-element-selected')
          };
        }""")
        assert code_frame["visual"]["width"] <= code_frame["box"]["width"] + 1, code_frame
        assert code_frame["visual"]["height"] <= code_frame["box"]["height"] + 1, code_frame
        assert abs(code_frame["visualRatio"] - code_frame["box"]["width"] / code_frame["box"]["height"]) < .03, code_frame
        assert code_frame["outline"] == "2px" and code_frame["outlineOffset"] == "0px", code_frame
        assert code_frame["selected"], code_frame
        assert code_frame["activeOutlines"] == 1, code_frame
        assert code_frame["boxOutline"] == "none" and code_frame["visualOutline"] == "none", code_frame
        assert code_frame["imageRatio"] > 1.05, code_frame

        # QR selection follows the square rendered SVG, while a barcode follows its rectangle.
        page.evaluate("""kind => {
          const data = JSON.parse(localStorage.getItem('b2m-label-generator-v2') || '{}');
          data.queue[0].kind = kind;
          localStorage.setItem('b2m-label-generator-v2', JSON.stringify(data));
          document.getElementById('b21-entry-select').dispatchEvent(new Event('change', {bubbles:true}));
        }""", "qr")
        page.wait_for_function("""() => {
          const image = document.querySelector('#b21-label-stage .b21-code-box .b21-code');
          return !!image && image.src.includes('kind=qr') && image.complete && image.naturalWidth > 0;
        }""", timeout=5_000)
        qr_frame = page.evaluate("""() => {
          const box = document.querySelector('#b21-label-stage .b21-code-box');
          const visual = box?.querySelector('.b21-code-content');
          const image = visual?.querySelector('img');
          return {
            svgRatio:image.naturalWidth/image.naturalHeight,
            renderedRatio:visual.getBoundingClientRect().width/visual.getBoundingClientRect().height,
            outline:getComputedStyle(image).outlineWidth,
            boxOutline:getComputedStyle(box).outlineStyle,
            visualOutline:getComputedStyle(visual).outlineStyle
          };
        }""")
        assert abs(qr_frame["svgRatio"] - 1) < .01, qr_frame
        assert abs(qr_frame["renderedRatio"] - 1) < .03, qr_frame
        assert qr_frame["outline"] == "2px", qr_frame
        assert qr_frame["boxOutline"] == "none" and qr_frame["visualOutline"] == "none", qr_frame
        page.evaluate("""kind => {
          const data = JSON.parse(localStorage.getItem('b2m-label-generator-v2') || '{}');
          data.queue[0].kind = kind;
          localStorage.setItem('b2m-label-generator-v2', JSON.stringify(data));
          document.getElementById('b21-entry-select').dispatchEvent(new Event('change', {bubbles:true}));
        }""", "code128")
        page.wait_for_function("""() => {
          const image = document.querySelector('#b21-label-stage .b21-code-box .b21-code');
          return !!image && image.src.includes('kind=code128') && image.complete && image.naturalWidth > 0;
        }""", timeout=5_000)

        page.locator('.b21-v24-layer-select[data-layer-select="label"]').click()
        text_frame = page.evaluate("""() => {
          const box = document.querySelector('#b21-label-stage [data-element-id="label"]');
          const content = box && box.querySelector('.b21-v2-text-content');
          const rect = element => {
            const value = element.getBoundingClientRect();
            return {width:value.width,height:value.height,top:value.top};
          };
          const activeOutlines = [box,content].filter(element => {
            const value = getComputedStyle(element);
            return value.outlineStyle !== 'none' && value.outlineWidth !== '0px';
          }).length;
          return {
            box:rect(box),content:rect(content),
            contentOutline:getComputedStyle(content).outlineWidth,
            contentSelected:content.classList.contains('b21-v2-element-selected'),
            outerOutline:getComputedStyle(box).outlineStyle,
            activeOutlines
          };
        }""")
        assert text_frame["content"]["width"] < text_frame["box"]["width"] * .8, text_frame
        assert text_frame["content"]["height"] < text_frame["box"]["height"] * .8, text_frame
        assert text_frame["contentOutline"] == "2px" and text_frame["contentSelected"], text_frame
        assert text_frame["outerOutline"] == "none" and text_frame["activeOutlines"] == 1, text_frame

        steppers = page.evaluate("""() => {
          const up = document.querySelector('#b21-v2-fontSizePt-step-up');
          const down = document.querySelector('#b21-v2-fontSizePt-step-down');
          const a = up.getBoundingClientRect(), b = down.getBoundingClientRect();
          return {upTop:a.top,downTop:b.top,upWidth:a.width,upHeight:a.height,downWidth:b.width,downHeight:b.height,
            upLabel:up.getAttribute('aria-label'),downLabel:down.getAttribute('aria-label')};
        }""")
        assert steppers["upTop"] < steppers["downTop"], steppers
        assert max(steppers["upWidth"],steppers["downWidth"]) <= 20, steppers
        assert max(steppers["upHeight"],steppers["downHeight"]) <= 15, steppers
        assert steppers["upLabel"].startswith("Increase") and steppers["downLabel"].startswith("Decrease"), steppers

        font_before = page.evaluate("""key => {
          const all = JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3') || '{}');
          return all[key].elements.find(row => row.id === 'label').fontSizePt;
        }""", source_key)
        page.locator("#b21-v2-fontSizePt-step-up").click()
        font_up = page.evaluate("""key => {
          const all = JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3') || '{}');
          return all[key].elements.find(row => row.id === 'label').fontSizePt;
        }""", source_key)
        assert font_up == font_before + .5, {"before":font_before,"after":font_up}
        page.locator("#b21-v2-fontSizePt-step-down").click()
        font_down = page.evaluate("""key => {
          const all = JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3') || '{}');
          return all[key].elements.find(row => row.id === 'label').fontSizePt;
        }""", source_key)
        assert font_down == font_before, {"before":font_before,"after":font_down}

        page.evaluate("""() => {
          const data = JSON.parse(localStorage.getItem('b2m-label-generator-v2') || '{}');
          data.queue[0].label = 'Canned tomatoes with basil and oregano for homemade pasta sauce and hearty vegetable soup all winter long';
          localStorage.setItem('b2m-label-generator-v2', JSON.stringify(data));
        }""")
        page.locator('#b21-v4-presets [data-preset="stacked"]').click()
        long_font = page.evaluate("""key => {
          const all = JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3') || '{}');
          return all[key].elements.find(row => row.id === 'label').fontSizePt;
        }""", source_key)
        font_debug = page.evaluate("""async key => {
          const all = JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3') || '{}');
          const data = JSON.parse(localStorage.getItem('b2m-label-generator-v2') || '{}');
          const bundle = await (await fetch('/static/generated/labels-ui.js')).text();
          return {
            key,queueLabel:data.queue[0].label,stageAspect:document.querySelector('#b21-label-stage')?.style.aspectRatio,
            savedLabel:all[key]?.elements.find(row => row.id === 'label'),
            adaptiveCode:bundle.includes('function fontSizeFor'),newPreset:bundle.includes('h:34')
          };
        }""", source_key)
        assert long_font < short_font, (short_font, long_font, smallest_profile, font_debug)
        page.locator('[data-layer-select="label"]').click()
        handle_geometry = page.evaluate("""() => {
          const stage=document.getElementById('b21-label-stage');
          const node=stage?.querySelector('[data-element-id=label]');
          const handle=stage?.querySelector(':scope > .b21-v2-resize-handle');
          const content=node?.querySelector('.b21-v2-text-content');
          const rect=element=>{const r=element.getBoundingClientRect();return {left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height};};
          return {handle:handle&&rect(handle),content:content&&rect(content),node:node&&rect(node),
            offsetParent:content?.offsetParent?.className,offsetLeft:content?.offsetLeft,offsetTop:content?.offsetTop,
            offsetWidth:content?.offsetWidth,offsetHeight:content?.offsetHeight,nodeOffsetWidth:node?.offsetWidth,nodeOffsetHeight:node?.offsetHeight,
            handleLeft:handle?.style.left,handleTop:handle?.style.top,transform:node&&getComputedStyle(node).transform};
        }""")
        assert handle_geometry["handle"] and handle_geometry["content"], handle_geometry
        assert abs(handle_geometry["handle"]["left"] + handle_geometry["handle"]["width"] / 2 - handle_geometry["content"]["right"]) < 2 and abs(handle_geometry["handle"]["top"] + handle_geometry["handle"]["height"] / 2 - handle_geometry["content"]["bottom"]) < 2, handle_geometry
        text_resize_before = page.evaluate("""key => {
          const all=JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3')||'{}');
          const element=all[key].elements.find(row=>row.id==='label');
          return {w:element.w,h:element.h,text:document.querySelector('#b21-label-stage [data-element-id="label"] .b21-v2-text-content')?.textContent};
        }""", source_key)
        text_handle = page.locator('#b21-label-stage > .b21-v2-resize-handle').bounding_box()
        assert text_handle is not None, "Selected text should expose its resize handle."
        resize_x = text_handle["x"] + text_handle["width"] / 2
        resize_y = text_handle["y"] + text_handle["height"] / 2
        page.mouse.move(resize_x, resize_y)
        page.mouse.down()
        page.mouse.move(resize_x - 60, resize_y + 12, steps=5)
        page.mouse.up()
        page.wait_for_function(
            "([key,width]) => { const all=JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3')||'{}'); const element=all[key]?.elements.find(row=>row.id==='label'); return !!element && element.w !== width; }",
            arg=[source_key, text_resize_before["w"]],
            timeout=5_000,
        )
        text_resize_after = page.evaluate("""key => {
          const all=JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3')||'{}');
          const element=all[key].elements.find(row=>row.id==='label');
          return {w:element.w,h:element.h,text:document.querySelector('#b21-label-stage [data-element-id="label"] .b21-v2-text-content')?.textContent};
        }""", source_key)
        assert text_resize_after["w"] != text_resize_before["w"], (text_resize_before, text_resize_after)
        assert text_resize_after["text"] == text_resize_before["text"], (text_resize_before, text_resize_after)
        page.locator('[data-layer-select="code"]').click()
        page.locator('[data-layer-select="label"]').click()
        text_resize_reloaded = page.evaluate("""key => {
          const all=JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3')||'{}');
          const element=all[key].elements.find(row=>row.id==='label');
          return {w:element.w,h:element.h};
        }""", source_key)
        assert text_resize_reloaded == {"w": text_resize_after["w"], "h": text_resize_after["h"]}, (text_resize_after, text_resize_reloaded)
        page.evaluate("""key => {
          const data = JSON.parse(localStorage.getItem('b2m-label-generator-v2') || '{}');
          data.queue[0].label = 'CI Label One';
          localStorage.setItem('b2m-label-generator-v2', JSON.stringify(data));
          const all = JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3') || '{}');
          const source = all[key];
          source.elements.find(row => row.id === 'label').x = 36;
          source.elements.push({id:'text-smoke',type:'text',name:'Free text',text:'Copied note',visible:true,x:50,y:10,w:50,h:10,rotation:0,fontSizePt:8});
          source.frame = false;
          source.frameInsetMm = 0.8;
          source.threshold = 102;
          localStorage.setItem('b2m-b21-entry-settings-v3', JSON.stringify(all));
          const styles = JSON.parse(localStorage.getItem('b2m-b21-text-style-v22') || '{}');
          styles[key] = {label: {fontFamily:'mono',bold:false}};
          localStorage.setItem('b2m-b21-text-style-v22', JSON.stringify(styles));
        }""", source_key)
        page.locator("#b21-entry-select").dispatch_event("change")
        page.locator("#b21-v4-copy-design").click()
        page.locator("#label-queue .entry-edit").nth(1).click()
        target_before = page.evaluate("""key => {
          const all = JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3') || '{}');
          const row = all[key];
          return {codeValue:row.codeValue,profileId:row.profileId,copies:row.copies};
        }""", target_key)
        page.locator("#b21-v4-paste-design").click()
        target_after = page.evaluate("""key => {
          const all = JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3') || '{}');
          const row = all[key];
          const styles = JSON.parse(localStorage.getItem('b2m-b21-text-style-v22') || '{}');
          return {
            codeValue:row.codeValue,profileId:row.profileId,copies:row.copies,frame:row.frame,
            labelX:row.elements.find(element => element.id === 'label').x,
            note:row.elements.find(element => element.id === 'text-smoke')?.text,
            labelText:document.querySelector('#b21-label-stage [data-element-id="label"]')?.textContent,
            textStyle:styles[key]?.label
          };
        }""", target_key)
        assert target_after["codeValue"] == target_before["codeValue"] == "87654321", target_after
        assert target_after["profileId"] == target_before["profileId"], target_after
        assert target_after["copies"] == target_before["copies"], target_after
        assert target_after["frame"] is False and target_after["labelX"] == 36, target_after
        assert target_after["note"] == "Copied note", target_after
        assert target_after["labelText"] == "CI Label Two", target_after
        assert target_after["textStyle"] == {"fontFamily": "mono", "bold": False}, target_after

        # Apply the current design to every queued code, preserving each entry's
        # encoded value, profile and copy count.
        page.evaluate("""key => {
          const all = JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3') || '{}');
          all[key].elements.find(row => row.id === 'label').x = 79;
          all[key].frame = true;
          localStorage.setItem('b2m-b21-entry-settings-v3', JSON.stringify(all));
        }""", target_key)
        page.locator("#label-queue .entry-edit").nth(0).click()
        page.locator("#b21-v4-apply-all-design").click()
        all_after = page.evaluate("""keys => {
          const all = JSON.parse(localStorage.getItem('b2m-b21-entry-settings-v3') || '{}');
          return keys.map(key => ({
            codeValue:all[key].codeValue,
            profileId:all[key].profileId,
            copies:all[key].copies,
            frame:all[key].frame,
            labelX:all[key].elements.find(row => row.id === 'label').x,
            note:all[key].elements.find(row => row.id === 'text-smoke')?.text
          }));
        }""", [source_key, target_key])
        assert [row["labelX"] for row in all_after] == [36, 36], all_after
        assert [row["frame"] for row in all_after] == [False, False], all_after
        assert [row["note"] for row in all_after] == ["Copied note", "Copied note"], all_after
        assert all_after[1]["codeValue"] == target_before["codeValue"], all_after
        assert all_after[1]["profileId"] == target_before["profileId"], all_after
        assert all_after[1]["copies"] == target_before["copies"], all_after
        assert page.locator("#b21-v4-design-status").inner_text() == "Current design applied to 2 codes."

        # A row Print button submits only that queued label to the canonical job endpoint.
        label_hits = {"batch": 0, "jobs_post": 0, "pages": 0}
        label_quantities = []

        def handle_batch(route):
            label_hits["batch"] += 1
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "quantity": 2}))

        def handle_job_create(route):
            label_hits["jobs_post"] += 1
            payload = route.request.post_data_json
            label_hits["pages"] = len(payload.get("pages", []))
            label_quantities.extend(page.get("quantity") for page in payload.get("pages", []))
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
        expected_single_quantity = page.evaluate("""() => {
          const queue=JSON.parse(localStorage.getItem('b2m-label-generator-v2')||'{}').queue||[];
          return Number(queue[1]?.qty||1);
        }""")
        try:
            with page.expect_request(lambda request: request.url.endswith("/labels/b21/jobs") and request.method == "POST", timeout=7_000):
                page.locator("#label-queue .entry-print").nth(1).click()
        except PlaywrightTimeoutError as exc:
            raise AssertionError(f"Single-label print did not reach canonical job endpoint; hits={label_hits!r}") from exc
        wait_until(
            lambda: label_hits["jobs_post"] == 1,
            f"Current-label job route callback did not complete; hits={label_hits!r}",
            timeout_ms=2_000,
            step_ms=25,
        )
        assert label_hits["batch"] == 0, label_hits
        assert label_hits["pages"] == 1, label_hits
        assert label_quantities == [expected_single_quantity], (label_quantities, expected_single_quantity)

        # Restore Basic mode so later settings checks start from their default.
        if not global_advanced.is_visible():
            tools.click()
            global_advanced.wait_for(state="visible", timeout=5_000)
        if global_advanced.is_checked():
            with page.expect_response(
                lambda response: response.url.endswith("/api/appearance-v24")
                and response.request.method == "POST",
                timeout=5_000,
            ):
                global_advanced.uncheck(force=True)
        wait_until(
            lambda: not page.locator("html").evaluate("el => el.classList.contains('b2m-advanced-enabled')"),
            "Global Advanced mode did not switch off after the printer test.",
        )

        reset_advanced = page.evaluate("""async () => {
            const response = await fetch('/api/appearance-v24', {
                method: 'POST',
                headers: {'Content-Type': 'application/json', Accept: 'application/json'},
                body: JSON.stringify({advanced_settings: false})
            });
            const data = await response.json();
            return {ok: response.ok, advanced: data.advanced_settings};
        }""")
        assert reset_advanced == {"ok": True, "advanced": False}, reset_advanced

        page.goto(f"{BASE_URL}/settings?tab=lookup", wait_until="domcontentloaded", timeout=20_000)
        lookup_strategy = page.locator("#setting_lookup_strategy")
        assert lookup_strategy.is_visible()
        assert lookup_strategy.input_value() in {"failover", "complement"}, lookup_strategy.input_value()
        assert lookup_strategy.locator("option").count() == 2
        assert page.locator('[data-api-url="off_url_base"]').is_visible()
        assert page.locator('[data-api-url="upcdb_url_base"]').is_visible()
        off_url = page.locator('[data-api-url="off_url_base"]').inner_text()
        upcdb_url = page.locator('[data-api-url="upcdb_url_base"]').inner_text()
        assert off_url.startswith(("http://", "https://")), off_url
        assert upcdb_url.startswith(("http://", "https://")), upcdb_url

        page.evaluate("localStorage.removeItem('b2m-settings-advanced-v1')")
        page.goto(f"{BASE_URL}/settings?tab=matching", wait_until="domcontentloaded", timeout=20_000)
        advanced_toggle = page.locator("#settings-show-advanced")
        assert advanced_toggle.count() == 1
        assert not advanced_toggle.evaluate("(element) => element.checked")
        for field_name in (
            "fuzzy_match_threshold",
            "fuzzy_ambiguity_gap",
            "item_sync_interval_hours",
            "lookup_ttl_days",
            "max_retry_attempts",
        ):
            assert page.locator("#setting_" + field_name).is_visible(), field_name

        page.evaluate("localStorage.removeItem('b2m-settings-advanced-v1')")
        page.goto(f"{BASE_URL}/settings?tab=system", wait_until="domcontentloaded", timeout=20_000)
        advanced_toggle = page.locator("#settings-show-advanced")
        assert advanced_toggle.count() == 1
        assert not advanced_toggle.evaluate("(element) => element.checked")
        for field_name in (
            "timezone",
            "dashboard_poll_interval_seconds",
            "health_poll_interval_seconds",
            "shopping_print_poll_interval_seconds",
            "log_level",
        ):
            assert page.locator("#setting_" + field_name).is_visible(), field_name

        page.goto(f"{BASE_URL}/settings?tab=homeassistant", wait_until="domcontentloaded", timeout=20_000)
        scan_automation = page.locator("#ha-scan-automation-yaml").input_value()
        assert "persistent_notification.create" in scan_automation
        assert "barcode_state" in scan_automation
        assert "barcode_known" in scan_automation
        assert "barcode_linked" in scan_automation
        assert "barcode_pending" in scan_automation
        assert "processing" in scan_automation
        assert "Full payload" not in scan_automation
        assert "trigger.json.get(" not in scan_automation
        for field_name in ("barcode", "result_type", "item_source", "brand", "quantity", "via"):
            assert "scan.get('" + field_name + "'" in scan_automation

        page.goto(f"{BASE_URL}/actions/new", wait_until="domcontentloaded", timeout=20_000)
        page.get_by_role("heading", name="New action").wait_for(timeout=5_000)
        page.locator('input[name="name"]').fill("CI action")
        page.locator("#action-v22-builder").wait_for(state="visible", timeout=5_000)
        assert page.locator("#action-v22-builder").is_visible()

        page.locator('input[name="webhook_url"]').evaluate("""el => {
            el.value = 'http://homeassistant.local:8123/api/webhook/ci_action';
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
        }""")
        page.locator('[data-preset="notification"]').click()
        quick_settings = page.locator("#action-v22-preset-settings")
        assert quick_settings.is_visible()
        assert quick_settings.locator("#action-preset-title").is_visible()
        assert quick_settings.locator("#action-preset-message").is_visible()
        quick_settings.locator("#action-preset-title").fill("Kitchen scan")
        quick_settings.locator("#action-preset-message").fill("Scanned {{ scan.barcode }}")
        assert "Kitchen scan" in page.locator("#action-payload-json").input_value()
        notification_yaml = page.locator("#action-ha-yaml").input_value()
        assert "trigger | default({})" in notification_yaml
        assert "trigger.json.get(" not in notification_yaml
        assert "action: persistent_notification.create" in notification_yaml, notification_yaml
        assert "event: b2m_action" not in notification_yaml, notification_yaml
        assert not page.locator("#action-payload-json").is_visible()

        page.evaluate("""() => {
            Object.defineProperty(navigator, 'clipboard', {
                configurable: true,
                value: {writeText: () => Promise.reject(new Error('clipboard unavailable'))}
            });
            document.execCommand = command => {
                window.__b2mCopiedText = document.getElementById('action-ha-yaml').value;
                return command === 'copy';
            };
        }""")
        page.locator("#action-ha-copy").click()
        assert page.evaluate("window.__b2mCopiedText") == notification_yaml
        assert "copied" in page.locator("#action-ha-status").inner_text().lower()

        page.locator('[data-preset="tts"]').click()
        assert quick_settings.locator("#action-preset-tts_entity").is_visible()
        assert quick_settings.locator("#action-preset-media_player").is_visible()
        assert quick_settings.locator("#action-preset-message").is_visible()
        quick_settings.locator("#action-preset-message").fill("Kitchen scan {{ scan.barcode }}")
        tts_yaml = page.locator("#action-ha-yaml").input_value()
        assert "action: tts.speak" in tts_yaml
        assert "media_player_entity_id" in tts_yaml
        assert "trigger | default({})" in tts_yaml
        assert "trigger.json.get(" not in tts_yaml

        page.locator('[data-preset="timer"]').click()
        quick_settings.locator("#action-preset-timer").fill("timer.kitchen")
        quick_settings.locator("#action-preset-duration").fill("00:05:00")
        timer_yaml = page.locator("#action-ha-yaml").input_value()
        assert "entity_id: 'timer.kitchen'" in timer_yaml
        assert "duration: '00:05:00'" in timer_yaml
        assert "trigger.json.timer" not in timer_yaml
        assert "trigger.json.duration" not in timer_yaml

        page.locator('[data-preset="light"]').click()
        quick_settings.locator("#action-preset-entity_id").fill("light.living_room")
        light_yaml = page.locator("#action-ha-yaml").input_value()
        assert "entity_id: 'light.living_room'" in light_yaml
        assert "trigger.json.entity_id" not in light_yaml

        local_advanced = page.locator("#action-advanced-toggle")
        local_advanced.wait_for(state="attached", timeout=5_000)
        assert not local_advanced.is_visible()

        tools = page.locator('.d-none.d-md-flex a[data-bs-toggle="dropdown"]').first
        tools.wait_for(state="visible", timeout=5_000)
        tools.click()
        global_advanced = page.locator("#b2m-global-advanced-toggle")
        global_advanced.wait_for(state="visible", timeout=5_000)
        assert global_advanced.is_visible()
        global_advanced.click()
        assert page.locator("#action-v22-preset-settings").is_visible()
        assert page.locator("#action-preset-entity_id").is_visible()

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

        # Large saved quantities must not create thousands of interactive preview cells.
        page.goto(f"{BASE_URL}/labels", wait_until="domcontentloaded", timeout=20_000)
        large_queue_payload = {
            "queue": [
                {
                    "_id": index + 100,
                    "code": "CI" + str(index).zfill(6),
                    "label": "CI Preview " + str(index),
                    "kind": "code128",
                    "qty": 99,
                }
                for index in range(35)
            ]
        }
        page.evaluate(
            "payload => localStorage.setItem('b2m-label-generator-v2', JSON.stringify(payload))",
            large_queue_payload,
        )
        page.reload(wait_until="domcontentloaded")
        page.wait_for_function(
            "() => document.querySelector('#label-count')?.textContent === '(3465)'",
            timeout=5_000,
        )
        assert page.locator("#label-queue .label-card").count() == 35
        assert page.locator("#preview-grid .label-preview-cell").count() == 24
        assert page.locator("#preview-grid img[loading='lazy']").count() == 24
        assert page.locator("#label-queue img.label-code-preview[loading='lazy']").count() == 35
        preview_summary = page.locator("#preview-summary").inner_text()
        assert "showing 24 of 35 code previews" in preview_summary, preview_summary
        assert "printing includes all labels" in preview_summary, preview_summary

        # A second tab must see new codes, and later writes must preserve both tabs' entries.
        second_tab = context.new_page()
        second_tab_errors: list[str] = []
        second_tab.on("pageerror", lambda error: second_tab_errors.append(str(error)))
        second_tab.goto(f"{BASE_URL}/labels", wait_until="domcontentloaded", timeout=20_000)
        second_tab.wait_for_function(
            "() => document.querySelector('#label-count')?.textContent === '(3465)'",
            timeout=5_000,
        )
        second_tab.locator("#generic-text").fill("Generated from second tab")
        second_tab.locator("#generic-add").click()
        page.wait_for_function(
            "() => document.querySelector('#label-count')?.textContent === '(3466)'",
            timeout=5_000,
        )
        assert page.locator("#label-queue .label-card").count() == 36

        page.locator("#generic-text").fill("Generated from first tab")
        page.locator("#generic-add").click()
        second_tab.wait_for_function(
            "() => document.querySelector('#label-count')?.textContent === '(3467)'",
            timeout=5_000,
        )
        assert page.locator("#label-queue .label-card").count() == 37
        assert second_tab.locator("#label-queue .label-card").count() == 37
        assert page.locator("#preview-grid .label-preview-cell").count() == 24
        assert second_tab.locator("#preview-grid .label-preview-cell").count() == 24
        labels = page.locator("#label-queue .entry-label").evaluate_all(
            "(inputs) => inputs.map(input => input.value)"
        )
        assert "Generated from second tab" in labels
        assert "Generated from first tab" in labels
        assert second_tab_errors == [], second_tab_errors

        if page_errors:
            raise AssertionError("Browser JavaScript errors: " + " | ".join(page_errors))

        browser.close()
    print("browser smoke ok")


if __name__ == "__main__":
    main()

