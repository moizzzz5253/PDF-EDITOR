"""Browser walkthrough: python tests/ui_test.py  (server must be running). Saves screenshots."""
import sys, glob
from playwright.sync_api import sync_playwright
OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/shots"
exe = glob.glob("/opt/pw-browsers/chromium*/chrome-linux*/chrome")[0]
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=exe, args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 1600, "height": 950})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.goto("http://127.0.0.1:8000/")
    pg.wait_for_selector("#toolList .tool")
    pg.set_input_files("#upInput", "tests/assets/sample.pdf")
    pg.wait_for_selector(".pg img")
    pg.wait_for_timeout(800)
    pg.screenshot(path=f"{OUT}/1_loaded.png")
    # select pages 2 and 4, remove
    pg.click('.pg[data-i="1"]'); pg.click('.pg[data-i="3"]')
    print("pages field:", pg.input_value('[data-p=pages]'))
    pg.click("#go")
    pg.wait_for_timeout(500); pg.screenshot(path=f"{OUT}/2_removing.png")
    pg.wait_for_timeout(3500); pg.screenshot(path=f"{OUT}/3_removed.png")
    # crop
    pg.click('.tool:has-text("Crop pages")'); pg.wait_for_selector("#cropw")
    pg.fill('[data-p=top]', '15'); pg.fill('[data-p=left]', '10')
    pg.click("#go"); pg.wait_for_timeout(700); pg.screenshot(path=f"{OUT}/4_crop.png"); pg.wait_for_timeout(3000)
    # error
    pg.click('.tool:has-text("Remove pages")'); pg.fill('[data-p=pages]', '99'); pg.click("#go"); pg.wait_for_selector("#fault:not([hidden])"); pg.wait_for_timeout(1500)
    pg.screenshot(path=f"{OUT}/5_fault.png")
    # compare
    pg.click('#tabs button[data-tab=compare]'); pg.wait_for_selector(".rowc"); pg.wait_for_timeout(1500); pg.screenshot(path=f"{OUT}/6_compare.png")
    # share
    pg.click('#tabs button[data-tab=share]'); pg.click('text=Create link'); pg.wait_for_selector('.urlbox input[readonly]'); pg.click('text=Google Drive'); pg.wait_for_timeout(800); pg.screenshot(path=f"{OUT}/7_share.png")
    print("JS errors:", errs)
    b.close()
