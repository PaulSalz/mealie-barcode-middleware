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

        # Existing smoke leaves persisted mode on light. Make this explicit.
        if page.locator("html").get_attribute("data-bs-theme") != "light":
            with page.expect_response(lambda r: r.url.endswith("/api/appearance-v24/mode") and r.request.method == "POST"):
                page.locator("#theme-toggle-light").click(force=True)
        light = surfaces()

        with page.expect_response(lambda r: r.url.endswith("/api/appearance-v24/mode") and r.request.method == "POST"):
            page.locator("#theme-toggle-dark").click(force=True)
        dark = surfaces()
        assert page.locator("html").get_attribute("data-bs-theme") == "dark"
        for key in ("body", "navbar", "card", "text"):
            assert dark[key] and dark[key] != light[key], (key, light, dark)

        # Persisted navbar mode must survive a navigation/reload with the same
        # complete dark surfaces, not only the root attribute.
        page.reload(wait_until="domcontentloaded")
        assert page.locator("html").get_attribute("data-bs-theme") == "dark"
        dark_reload = surfaces()
        assert dark_reload == dark, (dark, dark_reload)

        page.goto(f"{BASE_URL}/profile/appearance", wait_until="domcontentloaded", timeout=20_000)
        form = page.locator("#appearance-v35-form")
        form.wait_for(state="visible", timeout=5_000)
        assert page.locator('input[name="theme_color"]').count() == 0
        assert page.locator('input[name="theme_logo_color"][value="rainbow"]').count() == 1
        assert page.locator('input[name="theme_button_color"][value="rainbow"]').count() == 0

        html = page.locator("html")

        # Background: must take over synchronously on the same change event.
        before_bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
        page.locator('select[name="theme_base"]').select_option("stone")
        assert html.get_attribute("data-b2m-base") == "stone"
        after_bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
        assert before_bg != after_bg, (before_bg, after_bg)

        # Radius: direct CSS state, no delayed preview or reload.
        page.locator('input[name="theme_radius"][value="2"]').check(force=True)
        radius = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--tblr-border-radius').trim()")
        assert radius == "1.1rem", radius

        # Button color is separate from the logo and never rainbow.
        page.locator('input[name="theme_button_color"][value="green"]').check(force=True)
        primary = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--tblr-primary').trim()")
        assert primary.lower() == "#2fb344", primary
        page.locator('input[name="theme_logo_color"][value="rainbow"]').check(force=True)
        assert html.get_attribute("data-b2m-logo-color") == "rainbow"
        logo_background = page.evaluate("getComputedStyle(document.querySelector('.navbar-brand a')).backgroundImage")
        assert "gradient" in logo_background.lower(), logo_background

        # E-paper + contrast: the page must remain monochrome while contrast is
        # changed; only monochrome border/surface variables are allowed to move.
        epaper = page.locator('input[name="theme_epaper"]')
        epaper.check()
        assert html.get_attribute("data-b2m-epaper") == "true"
        filter_before = page.evaluate("getComputedStyle(document.documentElement).filter")
        body_epaper = page.evaluate("getComputedStyle(document.body).backgroundColor")
        border_before = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--b2m-epaper-border').trim()")
        assert "grayscale" in filter_before, filter_before
        assert body_epaper == "rgb(255, 255, 255)", body_epaper

        contrast = page.locator('input[name="theme_contrast"]')
        contrast.fill("95")
        contrast.dispatch_event("input")
        border_after = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--b2m-epaper-border').trim()")
        assert epaper.is_checked()
        assert html.get_attribute("data-b2m-epaper") == "true"
        assert "grayscale" in page.evaluate("getComputedStyle(document.documentElement).filter")
        assert border_after != border_before, (border_before, border_after)
        assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(255, 255, 255)"

        # Save must persist exactly the already-visible state; it must not be the
        # event that finally makes the design correct.
        with page.expect_response(lambda r: r.url.endswith("/api/appearance-v24") and r.request.method == "POST") as saved:
            page.locator("#appearance-save-button").click()
        assert saved.value.ok
        page.get_by_text("Saved", exact=True).wait_for(timeout=5_000)

        page.reload(wait_until="domcontentloaded")
        html = page.locator("html")
        assert page.locator('select[name="theme_base"]').input_value() == "stone"
        assert page.locator('input[name="theme_radius"][value="2"]').is_checked()
        assert page.locator('input[name="theme_button_color"][value="green"]').is_checked()
        assert page.locator('input[name="theme_logo_color"][value="rainbow"]').is_checked()
        assert page.locator('input[name="theme_epaper"]').is_checked()
        assert page.locator('input[name="theme_contrast"]').input_value() == "95"
        assert "grayscale" in page.evaluate("getComputedStyle(document.documentElement).filter")
        assert page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--tblr-border-radius').trim()") == "1.1rem"
        assert page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--tblr-primary').trim()").lower() == "#000000"

        if errors:
            raise AssertionError("Appearance browser JavaScript errors: " + " | ".join(errors))
        browser.close()
    print("appearance v35 smoke ok")


if __name__ == "__main__":
    main()
