import re
import os
from curl_cffi import requests
from bs4 import BeautifulSoup

ROOT = "https://rabobank.jobs/nl/"
LISTING = "https://rabobank.jobs/nl/vacatures/?page={n}"
VACANCY_RE = re.compile(r"/nl/vacature/[^/\"]+/JR_\d+/")

# Comma-separated keywords from .env; a job's title must contain one to qualify.
KEYWORDS = [k.strip().lower() for k in os.environ.get(
    "JOB_KEYWORDS",
    "risk,data,engineer,salesforce,analyst,platform,resilience,integration,crisis"
).split(",") if k.strip()]



import curl_cffi.requests as _rq

def _country_ok(url, want="nl"):
    """Read addressCountry from the vacancy JSON-LD; keep only NL roles."""
    try:
        html = _rq.get(url, impersonate="chrome", timeout=30).text
        m = re.search(r'"addressCountry"\s*:\s*"([a-zA-Z]{2})"', html)
        return bool(m) and m.group(1).lower() == want
    except Exception:
        return False


class RoleClosed(Exception):
    pass

ROLE_CLOSED = True


def fetch_description(url):
    r = requests.get(url, impersonate="chrome", timeout=30)
    if r.status_code == 404:
        raise RoleClosed(url)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = main.get_text("\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text)[:6000]


def _title_from_slug(url):
    m = re.search(r"/vacature/([^/]+)/", url)
    return m.group(1).replace("-", " ").title() if m else "Role"


def _matches(title):
    if not KEYWORDS:
        return True
    t = title.lower()
    return any(k in t for k in KEYWORDS)


def scrape_new_jobs(max_pages=10):
    """Walk listing pages, collect vacancy URLs, keep keyword matches."""
    seen_urls = set()
    jobs = []
    for n in range(1, max_pages + 1):
        try:
            r = requests.get(LISTING.format(n=n), impersonate="chrome", timeout=30)
            r.raise_for_status()
        except Exception:
            break
        found = set(VACANCY_RE.findall(r.text))
        new = found - seen_urls
        if not new:
            break  # ran out of pages (repeat or empty)
        seen_urls |= found
        for path in sorted(new):
            url = "https://rabobank.jobs" + path
            title = _title_from_slug(url)
            if _matches(title) and _country_ok(url):
                jobs.append({"url": url, "title": title, "company": "Rabobank",
                             "description": ""})  # description fetched lazily below
    # fetch descriptions only for the ones we kept (saves requests)
    out = []
    for j in jobs:
        try:
            j["description"] = fetch_description(j["url"])
            out.append(j)
        except Exception:
            continue
    return out


def scrape_single(url, company="Rabobank"):
    return {"url": url, "title": _title_from_slug(url), "company": company,
            "description": fetch_description(url)}


if __name__ == "__main__":
    js = scrape_new_jobs()
    print(f"{len(js)} matching jobs:")
    for j in js:
        print(" -", j["title"], "|", len(j["description"]), "chars")
