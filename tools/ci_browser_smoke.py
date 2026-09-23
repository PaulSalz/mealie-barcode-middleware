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

        # Exercise the two historically most patch-heavy pages. External Mealie
        # or printer services may be unavailable in CI; the pages themselves must
        # still render and their controllers must initialize without JS crashes.
        page.goto(f"{BASE_URL}/labels", wait_until="domcontentloaded", timeout=20_000)
        page.get_by_role("heading", name="Code Generator").wait_for(timeout=5_000)
        assert page.locator("#label-queue").is_visible()

        page.goto(f"{BASE_URL}/actions/new", wait_until="domcontentloaded", timeout=20_000)
        page.get_by_role("heading", name="New action").wait_for(timeout=5_000)
        page.locator('input[name="name"]').fill("CI action")
        page.wait_for_timeout(300)
        assert page.locator("#action-v22-builder").is_visible()
        assert page.locator("#action-advanced-toggle").is_visible()

        if page_errors:
            raise AssertionError("Browser JavaScript errors: " + " | ".join(page_errors))

        browser.close()
    print("browser smoke ok")


if __name__ == "__main__":
    main()
