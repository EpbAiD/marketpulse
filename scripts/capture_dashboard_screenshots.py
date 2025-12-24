#!/usr/bin/env python3
"""
Capture screenshots of the Streamlit dashboard for README
Requires: playwright
Install: pip install playwright && playwright install chromium
"""

import asyncio
import sys
from pathlib import Path
from playwright.async_api import async_playwright

async def capture_dashboard_screenshots():
    """Capture screenshots of the dashboard"""

    # Create screenshots directory
    screenshots_dir = Path(__file__).parent.parent / "screenshots"
    screenshots_dir.mkdir(exist_ok=True)

    print("Starting browser...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})

        # Navigate to dashboard
        print("Loading dashboard at http://localhost:8503...")
        await page.goto("http://localhost:8503", wait_until="networkidle", timeout=30000)

        # Wait for content to load
        await page.wait_for_timeout(5000)

        # Capture full page screenshot
        screenshot_path = screenshots_dir / "dashboard_full.png"
        await page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"✅ Saved: {screenshot_path}")

        # Capture viewport screenshot (above the fold)
        screenshot_path = screenshots_dir / "dashboard_hero.png"
        await page.screenshot(path=str(screenshot_path))
        print(f"✅ Saved: {screenshot_path}")

        await browser.close()

    print("\n✅ Screenshots captured successfully!")
    print(f"   Location: {screenshots_dir}")
    print("\nNext steps:")
    print("1. Review screenshots in the screenshots/ folder")
    print("2. Add them to README.md")
    print("3. Commit and push to GitHub")

if __name__ == "__main__":
    asyncio.run(capture_dashboard_screenshots())
