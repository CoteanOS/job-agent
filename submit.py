"""
Real form submission for rabobank.jobs, driven by a headed Chromium under Xvfb
(headless gets 403'd by Akamai; headed-under-virtual-display gets through).

Safety model: fills everything, ticks the REQUIRED privacy box, leaves the
optional data-retention box unticked, screenshots the completed form, and then
STOPS. It does NOT click "Send application". The caller sends the screenshot to
Telegram and only calls confirm_send() after the user replies GO.

Field map (from the live form):
  input[name=firstName]        input[name=lastName]
  input[name=email]            input[name="form1.phone"]
  input[name="form1.cvUploadFile"]        <- cv.pdf
  input[name="form1.documentUploadFile"]  <- the letter pdf
  input[name="form1.termsAndConditions"]  <- REQUIRED, tick
  button (text "Send application")        <- submit
"""
from pathlib import Path
import config


class SubmitNotConfigured(RuntimeError):
    pass


def _apply_url(vacancy_url: str) -> str:
    u = vacancy_url.replace("/nl/vacature/", "/en/job/")
    if not u.endswith("#apply"):
        u = u.rstrip("/") + "/#apply"
    return u


async def prepare_application(*, url: str, letter_pdf: str, cv_pdf: str = None,
                              shot_path: str = "form_filled.png"):
    """
    Open the form, fill it, tick required box, screenshot. Returns
    (playwright, browser, page, shot_path) with the browser LEFT OPEN so
    confirm_send can click Send. Raises SubmitNotConfigured on missing files.
    """
    from playwright.async_api import async_playwright

    cv = cv_pdf or str(config.BASE_DIR / "cv.pdf")
    if not Path(cv).exists():
        raise SubmitNotConfigured(f"CV not found at {cv}")
    if not Path(letter_pdf).exists():
        raise SubmitNotConfigured(f"letter PDF not found at {letter_pdf}")

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=False)  # headed; run under xvfb-run
    page = await browser.new_page(viewport={'width':1400,'height':2200})
    await page.goto(_apply_url(url), wait_until="networkidle", timeout=60000)
    await page.wait_for_timeout(3000)

    for label in ["ACCEPT", "Accepteren", "Accept"]:
        try:
            b = page.get_by_text(label, exact=True).first
            if await b.is_visible():
                await b.click()
                await page.wait_for_timeout(1000)
                break
        except Exception:
            pass

    await page.fill('input[name="firstName"]', config.APPLICANT_FIRST_NAME)
    await page.fill('input[name="lastName"]', config.APPLICANT_LAST_NAME)
    await page.fill('input[name="email"]', config.APPLICANT_EMAIL)
    # set phone country code to Netherlands (+31). The list also contains
    # "Caribbean Netherlands (+599)" which must NOT be matched.
    try:
        await page.click('button[aria-label="Phone number country code"]')
        await page.wait_for_timeout(1000)
        # exact button whose text starts with "Netherlands (Nederland)"
        opt = page.locator("button", has_text="Netherlands (Nederland)").first
        await opt.click()
        await page.wait_for_timeout(500)
    except Exception:
        pass
    await page.fill('input[name="form1.phone"]', config.APPLICANT_PHONE)

    await page.set_input_files('input[name="form1.cvUploadFile"]', cv)
    await page.set_input_files('input[name="form1.documentUploadFile"]', letter_pdf)

    try:
        await page.check('input[name="form1.termsAndConditions"]')
    except Exception:
        pass

    await page.wait_for_timeout(1500)
    try:
        form = page.locator('form').first
        await form.screenshot(path=shot_path)
    except Exception:
        await page.screenshot(path=shot_path, full_page=False)
    return pw, browser, page, shot_path


async def confirm_send(page):
    """Click the actual Send button. Only call after the user says GO."""
    btn = page.get_by_role("button", name="Send application")
    await btn.click()
    await page.wait_for_timeout(4000)
    return "clicked Send application"


async def submit_application(*, url, pdf_path, facts=None):
    raise SubmitNotConfigured(
        "Two-step submit: use prepare_application() then confirm_send() after GO.")
