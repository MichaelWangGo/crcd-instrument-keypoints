"""Browser QA for local or published GitHub Pages static site."""
import argparse
import json
from pathlib import Path
import urllib.request

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765/")
    parser.add_argument("--output", default="qa-results")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.load(urllib.request.urlopen(args.url + "data/clips.json"))
    clips = {clip["id"]: clip for clip in manifest["clips"]}
    errors, checks = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        response = page.goto(args.url, wait_until="networkidle", timeout=60000)
        assert response.status == 200
        page.evaluate("document.fonts.ready")
        page.wait_for_function("document.querySelector('#sequence-video').readyState >= 2")
        assert page.locator("#results-body tr").count() == 6
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert page.evaluate("document.fonts.check('600 20px SiteSans')")
        checks.extend(["desktop HTTP 200", "six measured-result rows", "no desktop horizontal overflow", "local Chinese font loaded"])
        page.screenshot(path=str(output / "desktop-fold.png"))
        page.screenshot(path=str(output / "desktop-full.png"), full_page=True)
        page.locator("#viewer").scroll_into_view_if_needed()
        page.locator(".explorer").screenshot(path=str(output / "viewer.png"))
        page.locator("#play-button").click()
        page.wait_for_function("document.querySelector('#sequence-video').currentTime > 0.8")
        page.locator("#play-button").click()
        assert page.locator("#sequence-video").evaluate("v => v.paused")
        checks.append("real MP4 playback and pause")
        page.locator("#frame-slider").evaluate("e => {e.value=60;e.dispatchEvent(new Event('input',{bubbles:true}));}")
        page.wait_for_function("document.querySelector('#frame-counter').textContent.startsWith('061')")
        page.wait_for_function("!document.querySelector('#sequence-video').seeking")
        assert int(page.locator("#source-frame").inner_text()) == clips["steady"]["first_source_frame"] + 60
        page.locator("#next-frame").click()
        page.wait_for_function("!document.querySelector('#sequence-video').seeking")
        assert page.locator("#frame-counter").inner_text().startswith("062")
        page.locator("#prev-frame").click()
        page.wait_for_function("!document.querySelector('#sequence-video').seeking")
        assert page.locator("#frame-counter").inner_text().startswith("061")
        checks.append("scrubbing and frame stepping preserve source-frame mapping")
        page.locator("#show-prediction").uncheck()
        page.locator("#show-gt").uncheck()
        assert page.locator("#pose-canvas").evaluate("c => {const d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;for(let i=3;i<d.length;i+=4)if(d[i])return false;return true;}")
        page.locator("#show-prediction").check()
        page.locator("#show-gt").check()
        page.locator("#show-labels").check()
        page.locator("#show-boxes").check()
        page.locator('[data-tool="PCH"]').click()
        assert page.locator('[data-tool="PCH"]').get_attribute("aria-pressed") == "true"
        checks.append("GT/prediction/label/box/tool overlays respond")
        page.locator("#playback-rate").select_option("2")
        for name in ("typical", "challenging", "steady"):
            page.locator(f'[data-clip="{name}"]').click()
            page.wait_for_function("expected => Number(document.querySelector('#source-frame').textContent) === expected", arg=clips[name]["first_source_frame"])
            page.wait_for_function("document.querySelector('#sequence-video').readyState >= 2")
            assert name + "-overlay.mp4" in page.locator("#download-clip").get_attribute("href")
        assert page.locator("#sequence-video").evaluate("v => v.playbackRate") == 2
        checks.append("all three clips, download links and persistent playback speed")
        for name in ("per_joint_errors", "test_error_cdf", "learning_curves"):
            page.locator(f'[data-chart="{name}"]').click()
            page.wait_for_function("document.querySelector('#results-chart').complete && document.querySelector('#results-chart').naturalWidth > 0")
            assert name in page.locator("#results-chart").get_attribute("src")
        checks.append("all measured chart tabs")
        page.locator('[data-chart="learning_curves"]').focus()
        page.keyboard.press("ArrowRight")
        assert page.locator('[data-chart="per_joint_errors"]').get_attribute("aria-selected") == "true"
        checks.append("keyboard chart tabs")
        page.set_viewport_size({"width": 390, "height": 844})
        page.evaluate("scrollTo(0,0)")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(output / "mobile-fold.png"))
        page.locator("#viewer").scroll_into_view_if_needed()
        page.locator(".explorer").screenshot(path=str(output / "mobile-viewer.png"))
        page.locator("#show-trails").uncheck()
        page.locator("#show-trails").check()
        checks.append("390px mobile layout and controls")
        response = page.goto(args.url + "credits.html", wait_until="networkidle")
        assert response.status == 200 and page.locator("h1").inner_text() == "来源与许可"
        checks.append("attribution page")
        browser.close()
    assert not errors, errors
    result = {"url": args.url, "checks": checks, "browser_errors": errors, "passed": True}
    (output / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
