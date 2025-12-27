#!/usr/bin/env python3
"""
Dashboard Screenshot Capture
Automatically captures dashboard screenshots for daily records
"""

import os
import time
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright


def capture_dashboard_screenshot(url="http://localhost:8501", output_dir="dashboard_screenshots",
                                  copy_to_assets=True):
    """
    Capture screenshot of the Streamlit dashboard

    Args:
        url: Dashboard URL
        output_dir: Directory to save timestamped screenshots (local backup)
        copy_to_assets: If True, also copy to assets/dashboard.png for README
    """
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_file = output_path / f"dashboard_{timestamp}.png"

    print(f"📸 Capturing dashboard screenshot...")
    print(f"   URL: {url}")

    try:
        with sync_playwright() as p:
            # Launch browser in headless mode
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1920, "height": 1080})

            # Navigate to dashboard
            page.goto(url, wait_until="networkidle", timeout=30000)

            # Wait for content to load
            time.sleep(5)  # Give Streamlit time to render

            # Capture full page screenshot
            page.screenshot(path=str(screenshot_file), full_page=True)

            browser.close()

            print(f"   ✅ Screenshot saved: {screenshot_file}")
            print(f"   📁 File size: {screenshot_file.stat().st_size / 1024:.1f} KB")

            # Copy to assets folder for README (overwrites previous)
            if copy_to_assets:
                assets_dir = Path("assets")
                assets_dir.mkdir(exist_ok=True)
                assets_file = assets_dir / "dashboard.png"

                import shutil
                shutil.copy2(screenshot_file, assets_file)
                print(f"   📋 Copied to README assets: {assets_file}")

            return screenshot_file

    except Exception as e:
        print(f"   ❌ Screenshot failed: {e}")
        return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Capture dashboard screenshot")
    parser.add_argument("--url", default="http://localhost:8501", help="Dashboard URL")
    parser.add_argument("--output-dir", default="dashboard_screenshots", help="Output directory")
    parser.add_argument("--no-assets", action="store_true",
                       help="Don't copy to assets/ folder (disable README update)")

    args = parser.parse_args()

    result = capture_dashboard_screenshot(args.url, args.output_dir,
                                         copy_to_assets=not args.no_assets)

    if result:
        print(f"\n✅ Screenshot capture complete!")
    else:
        print(f"\n❌ Screenshot capture failed")
        exit(1)
