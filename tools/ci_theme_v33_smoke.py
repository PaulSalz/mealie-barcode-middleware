#!/usr/bin/env python3
from __future__ import annotations

import os

from playwright.sync_api import sync_playwright


BASE_URL = os.environ.get("B2M_BROWSER_URL", "http://127.0.0.1:8001")


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page_errors: list[str] = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))

        def css_var(name: str) -> str:
            return page.locator("html").evaluate(
                "(el, name) => getComputedStyle(el).getPropertyValue(name).trim()",
                name,
            )

        def wait_value(read, expected: str, message: str, timeout_ms: int = 2_000) -> None:
            elapsed = 0
            while elapsed < timeout_ms:
                if read() == expected:
                    return
                page.wait_for_timeout(25)
                elapsed += 25
            raise AssertionError(f"{message}: expected={expected!r} actual={read()!r}")

        # ci_browser_smoke.py runs first and creates this account in the same DB.
        page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded", timeout=20_000)
        page.locator('input[name="username"]').fill("ci-admin")
        page.locator('input[name="password"]').fill("ci-browser-smoke-password")
        page.get_by_role("button", name="Sign in").click()
        page.wait_for_load_state("domcontentloaded")

        # Any dependency on the old server preview endpoint is a regression. Live
        # appearance must be completely synchronous in the browser.
        preview_hits = {"count": 0}

        def reject_preview(route):
            preview_hits["count"] += 1
            route.abort()

        page.route("**/api/appearance-v24/preview", reject_preview)
        page.goto(f"{BASE_URL}/profile/appearance", wait_until="domcontentloaded", timeout=20_000)
        form = page.locator('form[action="/profile/appearance"]')
        form.wait_for(state="visible", timeout=5_000)

        # Background palette must update as one complete state, without Save.
        page.locator('select[name="theme_base"]').select_option("stone")
        wait_value(lambda: css_var("--tblr-body-bg"), "#f0ebe5", "Stone light background did not apply live")
        wait_value(lambda: css_var("--tblr-bg-surface"), "#fbf9f6", "Stone light surface did not apply live")

        # Light/dark must change the actual palette, not just data-bs-theme.
        page.locator('input[name="theme_mode"][value="dark"]').check(force=True)
        wait_value(lambda: page.locator("html").get_attribute("data-bs-theme") or "", "dark", "Dark mode marker did not update")
        wait_value(lambda: css_var("--tblr-body-bg"), "#0e0c0a", "Dark background did not apply live")
        wait_value(lambda: css_var("--tblr-bg-surface"), "#1c1815", "Dark surface did not apply live")

        # E-paper must become fully monochrome immediately, then restore the exact
        # underlying palette when disabled again.
        epaper = page.locator('input[name="theme_epaper"]')
        epaper.check()
        wait_value(lambda: css_var("--tblr-body-bg"), "#fff", "E-paper background did not apply live")
        assert "b2m-epaper" in (page.locator("html").get_attribute("class") or "").split()
        preview = page.locator("#b2m-theme-v32-preview")
        preview.wait_for(state="attached", timeout=2_000)
        assert "grayscale(1)" in (preview.text_content() or "")
        epaper.uncheck()
        wait_value(lambda: css_var("--tblr-body-bg"), "#0e0c0a", "Palette did not restore after E-paper")

        # The remaining visible appearance controls use the same synchronous CSS
        # state, rather than waiting for Save/reload.
        page.locator('input[name="theme_color"][value="red"]').check(force=True)
        wait_value(lambda: css_var("--tblr-primary"), "#d63939", "Accent did not apply live")
        page.locator('select[name="theme_font"]').select_option("serif")
        assert "Georgia" in css_var("--tblr-body-font-family")
        page.locator('input[name="theme_radius"][value="2"]').check(force=True)
        wait_value(lambda: css_var("--tblr-border-radius"), "1.1rem", "Radius did not apply live")
        assert preview_hits["count"] == 0, preview_hits

        # Save a deterministic personal appearance, then remove all local cache
        # hints. The next page must still start in the correct personal palette,
        # proving Default Appearance is no longer painted first.
        page.locator('input[name="theme_mode"][value="light"]').check(force=True)
        if epaper.is_checked():
            epaper.uncheck()
        page.locator('select[name="theme_base"]').select_option("stone")
        with page.expect_navigation(wait_until="domcontentloaded", timeout=10_000):
            page.get_by_role("button", name="Save appearance").click()

        page.evaluate(
            """() => {
                localStorage.removeItem('theme-mode-override');
                localStorage.removeItem('theme-base-override');
                localStorage.removeItem('theme-epaper-override');
            }"""
        )
        page.goto(f"{BASE_URL}/items", wait_until="domcontentloaded", timeout=20_000)
        assert page.locator("html").get_attribute("data-bs-theme") == "light"
        wait_value(lambda: css_var("--tblr-body-bg"), "#f0ebe5", "Personal background was not present on first page state")

        # Navbar switch must change the full live palette and persist personally.
        with page.expect_response(
            lambda response: response.url.endswith("/api/appearance-v24/mode") and response.request.method == "POST",
            timeout=5_000,
        ) as response_info:
            page.locator("#theme-toggle-dark").click(force=True)
        assert response_info.value.ok
        wait_value(lambda: page.locator("html").get_attribute("data-bs-theme") or "", "dark", "Navbar did not switch mode")
        wait_value(lambda: css_var("--tblr-body-bg"), "#0e0c0a", "Navbar did not switch the full palette")

        # Remove the local fast-path and navigate again. The server-rendered
        # personal mode must already be dark before any async correction exists.
        page.evaluate("localStorage.removeItem('theme-mode-override')")
        page.goto(f"{BASE_URL}/barcodes", wait_until="domcontentloaded", timeout=20_000)
        assert page.locator("html").get_attribute("data-bs-theme") == "dark"
        wait_value(lambda: css_var("--tblr-body-bg"), "#0e0c0a", "Persisted dark personal palette was not first-paint state")
        assert preview_hits["count"] == 0, preview_hits

        if page_errors:
            raise AssertionError("Browser JavaScript errors: " + " | ".join(page_errors))

        browser.close()

    print("theme v33 smoke ok")


if __name__ == "__main__":
    main()
