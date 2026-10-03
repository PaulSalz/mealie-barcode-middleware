#!/usr/bin/env python3
from __future__ import annotations

import os

from playwright.sync_api import sync_playwright


BASE_URL = os.environ.get("B2M_BROWSER_URL", "http://127.0.0.1:8001")
USERNAME = "ci-admin"
PASSWORD = "ci-browser-smoke-password"


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded", timeout=20_000)
        page.locator('input[name="username"]').fill(USERNAME)
        page.locator('input[name="password"]').fill(PASSWORD)
        page.get_by_role("button", name="Sign in").click()
        page.wait_for_load_state("domcontentloaded")

        # The old admin/global Appearance entrypoint must no longer exist as a
        # distinct settings surface.
        page.goto(f"{BASE_URL}/settings?tab=appearance", wait_until="domcontentloaded", timeout=20_000)
        assert page.url.endswith("/profile/appearance"), page.url

        # Navbar switch: compare actual rendered surfaces, not only data-bs-theme.
        page.goto(f"{BASE_URL}/", wait_until="domcontentloaded", timeout=20_000)

        def surfaces() -> dict[str, str]:
            return page.evaluate(
                """() => {
                    const css = (s, p) => {
                        const el = document.querySelector(s);
                        return el ? getComputedStyle(el)[p] : '';
                    };
                    return {
                        body: css('body', 'backgroundColor'),
                        navbar: css('.navbar', 'backgroundColor'),
                        card: css('.card', 'backgroundColor'),
                        text: css('body', 'color')
                    };
                }"""
            )

        def theme_debug() -> dict:
            return page.evaluate(
                """() => {
                    const root = document.documentElement;
                    const css = getComputedStyle(root);
                    const attr = name => root.getAttribute(name) || '';
                    const variable = name => css.getPropertyValue(name).trim();
                    return {
                        attrs: {
                            mode: attr('data-bs-theme'),
                            base: attr('data-b2m-base'),
                            button: attr('data-b2m-button-color'),
                            logo: attr('data-b2m-logo-color'),
                            radius: attr('data-b2m-radius'),
                            font: attr('data-b2m-font'),
                            epaper: attr('data-b2m-epaper'),
                            contrast: attr('data-b2m-contrast')
                        },
                        vars: {
                            page: variable('--b2m-page-bg'),
                            surface: variable('--b2m-surface-bg'),
                            text: variable('--b2m-text'),
                            muted: variable('--b2m-muted'),
                            border: variable('--b2m-border'),
                            tblrBody: variable('--tblr-body-bg'),
                            tblrSurface: variable('--tblr-bg-surface'),
                            savedMode: variable('--b2m-saved-mode'),
                            savedBase: variable('--b2m-saved-base'),
                            authorityPage: variable('--b2m-v35-page-bg'),
                            authoritySurface: variable('--b2m-v35-surface-bg'),
                            bodyPage: getComputedStyle(document.body).getPropertyValue('--b2m-v35-page-bg').trim(),
                            navbarSurface: getComputedStyle(document.querySelector('.navbar')).getPropertyValue('--b2m-v35-surface-bg').trim()
                        },
                        sheets: Array.from(document.styleSheets).map(sheet => sheet.href || 'inline')
                    };
                }"""
            )

        # Existing smoke leaves persisted mode on light. Make this explicit.
        if page.locator("html").get_attribute("data-bs-theme") != "light":
            with page.expect_response(lambda r: r.url.endswith("/api/appearance-v24/mode") and r.request.method == "POST"):
                page.locator("#theme-toggle-light").click(force=True)
        light = surfaces()
        light_debug = theme_debug()

        with page.expect_response(lambda r: r.url.endswith("/api/appearance-v24/mode") and r.request.method == "POST"):
            page.locator("#theme-toggle-dark").click(force=True)
        dark = surfaces()
        dark_debug = theme_debug()
        assert page.locator("html").get_attribute("data-bs-theme") == "dark"
        for key in ("body", "navbar", "card", "text"):
            assert dark[key] and dark[key] != light[key], (key, light, dark, light_debug, dark_debug)

        # Persisted navbar mode must survive a navigation/reload with the same
        # complete dark surfaces, not only the root attribute.
        page.reload(wait_until="domcontentloaded")
        assert page.locator("html").get_attribute("data-bs-theme") == "dark"
        dark_reload = surfaces()
        assert dark_reload == dark, (dark, dark_reload, theme_debug())

        page.goto(f"{BASE_URL}/profile/appearance", wait_until="domcontentloaded", timeout=20_000)
        form = page.locator("#appearance-v35-form")
        form.wait_for(state="visible", timeout=5_000)
        assert page.locator('input[name="theme_color"]').count() == 0
        assert page.locator('input[name="theme_logo_color"][value="rainbow"]').count() == 1
        assert page.locator('input[name="theme_button_color"][value="rainbow"]').count() == 0

        html = page.locator("html")

        def assert_saved_background_after_load() -> None:
            state = page.evaluate("""() => {
                const root = document.documentElement;
                const input = document.querySelector('input[name="theme_base"]:checked');
                const swatch = input && input.nextElementSibling;
                const expectedHex = root.getAttribute('data-bs-theme') === 'dark'
                    ? swatch.dataset.b2mSwatchDark
                    : swatch.dataset.b2mSwatchLight;
                const n = parseInt(expectedHex.slice(1), 16);
                const expected = 'rgb(' + ((n >> 16) & 255) + ', ' + ((n >> 8) & 255) + ', ' + (n & 255) + ')';
                return {
                    base: input.value,
                    rootBase: root.getAttribute('data-b2m-base'),
                    expected,
                    swatch: getComputedStyle(swatch).backgroundColor,
                    page: getComputedStyle(document.body).backgroundColor
                };
            }""")
            assert state["rootBase"] == state["base"], state
            assert state["swatch"] == state["expected"], state
            assert state["page"] == state["expected"], state

        # Saved colors must be restored at first paint and remain after F5.
        assert_saved_background_after_load()
        page.reload(wait_until="domcontentloaded")
        page.locator("#appearance-v35-form").wait_for(state="visible", timeout=5_000)
        assert_saved_background_after_load()

        # Background: must take over synchronously on the same change event.
        before_bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
        page.locator('input[name="theme_base"][value="stone"]').check(force=True)
        assert html.get_attribute("data-b2m-base") == "stone"
        after_bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
        assert before_bg != after_bg, (before_bg, after_bg, theme_debug())
        swatch_state = page.evaluate("""() => ({
            mode: document.documentElement.getAttribute('data-bs-theme'),
            color: getComputedStyle(document.querySelector('input[name="theme_base"][value="stone"] + .b2m-base-swatch')).backgroundColor
        })""")
        expected_swatch = "rgb(28, 16, 7)" if swatch_state["mode"] == "dark" else "rgb(243, 233, 220)"
        assert swatch_state["color"] == expected_swatch, (swatch_state, theme_debug())

        # Radius: direct CSS state, no delayed preview or reload.
        page.locator('input[name="theme_radius"][value="2"]').check(force=True)
        radius = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--tblr-border-radius').trim()")
        assert radius == "1.1rem", (radius, theme_debug())

        # Button color is separate from the logo and never rainbow.
        page.locator('input[name="theme_button_color"][value="green"]').check(force=True)
        primary = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--tblr-primary').trim()")
        assert primary.lower() == "#2fb344", (primary, theme_debug())
        page.locator('input[name="theme_logo_color"][value="rainbow"]').check(force=True)
        assert html.get_attribute("data-b2m-logo-color") == "rainbow"
        # In normal mode the wordmark itself must animate, not only its parent.
        epaper_toggle = page.locator('input[name="theme_epaper"]')
        if epaper_toggle.is_checked():
            epaper_toggle.uncheck()
        normal_logo = page.locator('.navbar-brand a .b2m-brand-text')
        normal_animation = normal_logo.evaluate("""el => {
            const style = getComputedStyle(el);
            return {name: style.animationName, duration: style.animationDuration, timing: style.animationTimingFunction, state: style.animationPlayState, position: style.backgroundPosition};
        }""")
        assert normal_animation["name"] == "b2m-logo-rainbow-live", (normal_animation, theme_debug())
        assert normal_animation["duration"] == "6s" and normal_animation["timing"] == "linear" and normal_animation["state"] == "running", (normal_animation, theme_debug())
        normal_position_before = normal_animation["position"]
        page.wait_for_timeout(250)
        normal_position_after = normal_logo.evaluate("el => getComputedStyle(el).backgroundPosition")
        assert normal_position_before != normal_position_after, (normal_position_before, normal_position_after, theme_debug())
        logo_background = page.evaluate("getComputedStyle(document.querySelector('.navbar-brand a .b2m-brand-text')).backgroundImage")
        assert "gradient" in logo_background.lower(), (logo_background, theme_debug())

        # E-paper + contrast: the page must remain monochrome while contrast is
        # changed; only monochrome border/surface variables are allowed to move.
        light_mode = page.locator('input[name="theme_mode"][value="light"]')
        light_mode.check(force=True)
        light_mode.dispatch_event("change")
        assert html.get_attribute("data-bs-theme") == "light"
        assert page.locator('input[name="theme_base"][value="stone"] + .b2m-base-swatch').evaluate("el => getComputedStyle(el).backgroundColor") == "rgb(243, 233, 220)"
        epaper = page.locator('input[name="theme_epaper"]')
        epaper.check()
        assert html.get_attribute("data-b2m-epaper") == "true"
        filter_before = page.evaluate("getComputedStyle(document.documentElement).filter")
        body_epaper = page.evaluate("getComputedStyle(document.body).backgroundColor")
        border_before = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--b2m-epaper-border').trim()")
        assert "grayscale" in filter_before, (filter_before, theme_debug())
        assert body_epaper == "rgb(255, 255, 255)", (body_epaper, theme_debug())

        contrast = page.locator('input[name="theme_contrast"]')
        contrast.fill("0")
        contrast.dispatch_event("input")
        border_after = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--b2m-epaper-border').trim()")
        assert epaper.is_checked()
        assert html.get_attribute("data-b2m-epaper") == "true"
        assert "grayscale" in page.evaluate("getComputedStyle(document.documentElement).filter")
        assert border_after != border_before, (border_before, border_after, theme_debug())
        assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(255, 255, 255)"

        # The dark e-paper palette reverses action fills to white with black text.
        dark_mode = page.locator('input[name="theme_mode"][value="dark"]')
        dark_mode.check(force=True)
        dark_mode.dispatch_event("change")
        assert html.get_attribute("data-bs-theme") == "dark"
        assert page.locator('input[name="theme_base"][value="stone"] + .b2m-base-swatch').evaluate("el => getComputedStyle(el).backgroundColor") == "rgb(28, 16, 7)"
        dark_page = page.evaluate("getComputedStyle(document.body).backgroundColor")
        assert dark_page == "rgb(0, 0, 0)", (dark_page, theme_debug())
        assert page.evaluate("getComputedStyle(document.body).color") == "rgb(255, 255, 255)"
        action_colors = page.evaluate("""() => {
            const style = getComputedStyle(document.getElementById('appearance-save-button'));
            return [style.backgroundColor, style.color];
        }""")
        assert action_colors == ["rgb(255, 255, 255)", "rgb(0, 0, 0)"], (action_colors, theme_debug())

        # Save must persist exactly the already-visible state; it must not be the
        # event that finally makes the design correct.
        with page.expect_response(lambda r: r.url.endswith("/api/appearance-v24") and r.request.method == "POST") as saved:
            page.locator("#appearance-save-button").click()
        assert saved.value.ok
        page.get_by_text("Saved", exact=True).wait_for(timeout=5_000)

        # Restoring the saved appearance page from browser history must not revive
        # its pre-save theme snapshot.
        page.goto(f"{BASE_URL}/", wait_until="domcontentloaded", timeout=20_000)
        page.go_back(wait_until="commit", timeout=20_000)
        page.locator("#appearance-v35-form").wait_for(state="visible", timeout=5_000)
        page.wait_for_function("""() => {
            const root = document.documentElement;
            return root.getAttribute('data-bs-theme') === 'dark' &&
                root.dataset.b2mBase === 'stone' &&
                root.dataset.b2mEpaper === 'true';
        }""", timeout=5_000)

        # The page behind Appearance can also be a stale BFCache snapshot.
        page.go_back(wait_until="commit", timeout=20_000)
        page.wait_for_function("""() => {
            const root = document.documentElement;
            return location.pathname === '/' &&
                root.getAttribute('data-bs-theme') === 'dark' &&
                root.dataset.b2mBase === 'stone' &&
                root.dataset.b2mEpaper === 'true';
        }""", timeout=8_000)
        page.go_forward(wait_until="commit", timeout=20_000)
        page.locator("#appearance-v35-form").wait_for(state="visible", timeout=5_000)

        page.reload(wait_until="domcontentloaded")
        html = page.locator("html")
        assert page.locator('input[name="theme_base"][value="stone"]').is_checked()
        assert page.locator('input[name="theme_radius"][value="2"]').is_checked()
        assert page.locator('input[name="theme_button_color"][value="green"]').is_checked()
        assert page.locator('input[name="theme_logo_color"][value="rainbow"]').is_checked()
        assert page.locator('input[name="theme_epaper"]').is_checked()
        assert page.locator('input[name="theme_contrast"]').input_value() == "0"
        assert "grayscale" in page.evaluate("getComputedStyle(document.documentElement).filter")
        assert page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--tblr-border-radius').trim()") == "1.1rem"
        primary_reload = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--tblr-primary').trim()")
        assert page.locator("html").get_attribute("data-bs-theme") == "dark"
        assert primary_reload.lower() in ("#fff", "#ffffff"), (primary_reload, theme_debug())

        # Dashboard icons and status text stay legible in dark e-paper at the
        # lowest contrast setting; legacy semantic colors must be neutralized.
        page.goto(f"{BASE_URL}/", wait_until="domcontentloaded", timeout=20_000)
        dashboard_colors = page.evaluate("""() => {
            const card = document.querySelector('.b2m-stat-card');
            const avatar = document.querySelector('.b2m-stat-card .avatar');
            const icon = avatar && avatar.querySelector('i');
            const status = document.getElementById('health-status');
            return {
                page: getComputedStyle(document.body).backgroundColor,
                text: getComputedStyle(document.body).color,
                card: card ? getComputedStyle(card).backgroundColor : '',
                avatar: avatar ? getComputedStyle(avatar).backgroundColor : '',
                icon: icon ? getComputedStyle(icon).color : '',
                status: status ? getComputedStyle(status).color : '',
                statValue: document.getElementById('stat-total') ? getComputedStyle(document.getElementById('stat-total')).color : '',
                statusCircle: document.querySelector('#health-indicator .status-indicator-circle') ? getComputedStyle(document.querySelector('#health-indicator .status-indicator-circle')).backgroundColor : ''
            };
        }""")
        logo_animation = page.evaluate("""() => {
            const style = getComputedStyle(document.querySelector('.navbar-brand a .b2m-brand-text'));
            return {
                name: style.animationName,
                duration: style.animationDuration,
                timing: style.animationTimingFunction,
                iterations: style.animationIterationCount,
                state: style.animationPlayState,
                gradient: style.backgroundImage.includes('linear-gradient')
            };
        }""")
        assert logo_animation == {
            "name": "b2m-logo-rainbow-live",
            "duration": "6s",
            "timing": "linear",
            "iterations": "infinite",
            "state": "running",
            "gradient": True,
        }, (logo_animation, theme_debug())

        assert dashboard_colors == {
            "page": "rgb(0, 0, 0)",
            "text": "rgb(255, 255, 255)",
            "card": "rgb(184, 184, 184)",
            "avatar": "rgb(192, 192, 192)",
            "icon": "rgb(0, 0, 0)",
            "status": "rgb(0, 0, 0)",
            "statValue": "rgb(0, 0, 0)",
            "statusCircle": "rgb(0, 0, 0)"
        }, (dashboard_colors, theme_debug())

        # Items uses compact, labeled cards instead of a wide table on phones.
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{BASE_URL}/items", wait_until="domcontentloaded", timeout=20_000)
        page.locator("#items-card").wait_for(state="visible", timeout=5_000)
        mobile_items = page.evaluate("""() => {
            const selects = Array.from(document.querySelectorAll('#items-filter-form select'));
            const tops = selects.map(el => Math.round(el.getBoundingClientRect().top));
            const table = document.getElementById('items-table');
            const title = document.querySelector('.items-page-header .page-title');
            return {
                header: getComputedStyle(table.tHead).display,
                body: getComputedStyle(table.tBodies[0]).display,
                titleSize: parseFloat(getComputedStyle(title).fontSize),
                selectSize: parseFloat(getComputedStyle(selects[0]).fontSize),
                firstPairSameRow: tops.length >= 2 && tops[0] === tops[1],
                secondPairSameRow: tops.length >= 4 && tops[2] === tops[3],
                secondRowBelow: tops.length >= 3 && tops[2] > tops[1],
                searchIconSize: parseFloat(getComputedStyle(document.querySelector('#items-card .input-group-text .ti-search')).fontSize),
                filterRadius: getComputedStyle(document.querySelector('#items-card > .card-header')).borderBottomLeftRadius
            };
        }""")
        assert mobile_items["header"] == "none", mobile_items
        assert mobile_items["body"] == "grid", mobile_items
        assert mobile_items["titleSize"] <= 18 and mobile_items["selectSize"] <= 12, mobile_items
        assert mobile_items["searchIconSize"] <= 14 and mobile_items["filterRadius"] != "0px", mobile_items
        assert mobile_items["firstPairSameRow"] and mobile_items["secondPairSameRow"] and mobile_items["secondRowBelow"], mobile_items
        # Bulk-selection checkboxes are injected after load; keep each one at the item-title row's top-right.
        bulk_checkbox = page.locator("#items-table .b2m-bulk-row").first
        if bulk_checkbox.count():
            bulk_checkbox.wait_for(state="visible", timeout=5_000)
            bulk_layout = bulk_checkbox.evaluate("""el => {
                const row = el.closest('tr');
                const box = el.getBoundingClientRect();
                const title = row.querySelector('td.sort-name').getBoundingClientRect();
                const rowBox = row.getBoundingClientRect();
                return {
                    topDelta: Math.abs(box.top - title.top),
                    rightInset: rowBox.right - box.right,
                    size: box.width
                };
            }""")
            assert bulk_layout["topDelta"] <= 4, bulk_layout
            assert 4 <= bulk_layout["rightInset"] <= 24, bulk_layout
            assert bulk_layout["size"] <= 18, bulk_layout
        # Actions and Barcodes use compact card rows on the same phone width.
        page.goto(f"{BASE_URL}/actions", wait_until="domcontentloaded", timeout=20_000)
        page.locator(".actions-table").wait_for(state="visible", timeout=5_000)
        mobile_actions = page.evaluate("""() => {
            const table = document.querySelector('.actions-table');
            const row = table.querySelector('tbody tr:not(:has(td[colspan]))');
            return {
                header: getComputedStyle(table.tHead).display,
                body: getComputedStyle(table.tBodies[0]).display,
                row: row ? getComputedStyle(row).display : 'none',
                scrollWidth: document.documentElement.scrollWidth,
                viewport: document.documentElement.clientWidth
            };
        }""")
        assert mobile_actions["header"] == "none" and mobile_actions["body"] == "grid", mobile_actions
        assert mobile_actions["row"] in ("grid", "none"), mobile_actions
        assert mobile_actions["scrollWidth"] <= mobile_actions["viewport"] + 1, mobile_actions

        page.goto(f"{BASE_URL}/barcodes", wait_until="domcontentloaded", timeout=20_000)
        page.locator("#barcodes-table").wait_for(state="visible", timeout=5_000)
        mobile_barcodes = page.evaluate("""() => {
            const table = document.getElementById('barcodes-table');
            const rows = table.querySelector('tbody');
            const row = table.querySelector('tbody tr:not(.barcodes-empty-row)');
            return {
                header: getComputedStyle(table.tHead).display,
                body: getComputedStyle(rows).display,
                rowRadius: row ? getComputedStyle(row).borderRadius : '',
                bulkLayout: row && row.querySelector('.b2m-bulk-row') ? (() => {
                    const box = row.querySelector('.b2m-bulk-row').getBoundingClientRect();
                    const barcode = row.querySelector('[data-field="barcode"]').getBoundingClientRect();
                    const rowBox = row.getBoundingClientRect();
                    return {topDelta: Math.abs(box.top - barcode.top), rightInset: rowBox.right - box.right, size: box.width};
                })() : null,
                compactGap: parseFloat(getComputedStyle(rows).rowGap),
                scrollWidth: document.documentElement.scrollWidth,
                viewport: document.documentElement.clientWidth
            };
        }""")
        assert mobile_barcodes["header"] == "none" and mobile_barcodes["body"] == "grid", mobile_barcodes
        assert mobile_barcodes["rowRadius"] != "0px", mobile_barcodes
        assert mobile_barcodes["compactGap"] <= 4, mobile_barcodes
        if mobile_barcodes["bulkLayout"]:
            assert mobile_barcodes["bulkLayout"]["topDelta"] <= 5, mobile_barcodes
            assert 4 <= mobile_barcodes["bulkLayout"]["rightInset"] <= 24, mobile_barcodes
            assert mobile_barcodes["bulkLayout"]["size"] <= 16, mobile_barcodes
        assert mobile_barcodes["scrollWidth"] <= mobile_barcodes["viewport"] + 1, mobile_barcodes

        page.set_viewport_size({"width": 1280, "height": 900})

        # Filled action buttons remain white-on-black in light e-paper.
        for route, selector in (
            ("/", "#shopping-lists-card .btn-primary"),
            ("/profile/appearance", "#appearance-save-button"),
            ("/items", "a.btn-primary"),
        ):
            page.goto(f"{BASE_URL}{route}", wait_until="domcontentloaded", timeout=20_000)
            page.evaluate("""() => {
                document.documentElement.setAttribute('data-bs-theme', 'light');
            }""")
            button = page.locator(selector).first
            assert button.count() == 1, (route, selector)
            colors = button.evaluate("""el => ({
                text: getComputedStyle(el).color,
                icon: el.querySelector('i,svg') ? getComputedStyle(el.querySelector('i,svg')).color : getComputedStyle(el).color,
                background: getComputedStyle(el).backgroundColor
            })""")
            assert colors["text"] == "rgb(255, 255, 255)", (route, colors)
            assert colors["icon"] == "rgb(255, 255, 255)", (route, colors)
            assert colors["background"] == "rgb(0, 0, 0)", (route, colors)

        if errors:
            raise AssertionError("Appearance browser JavaScript errors: " + " | ".join(errors))
        browser.close()
    print("appearance v35 smoke ok")


if __name__ == "__main__":
    main()
