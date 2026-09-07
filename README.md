# job-agent

A self-hosted bot that watches a company's careers site, writes a tailored
motivation letter for roles that fit, and files the application after I approve
it from my phone. It runs on a Raspberry Pi.

It is not a mass-apply tool. It targets one employer I actually want, drafts in
my own voice, and never submits anything without me tapping approve and then
replying GO. Quality over spam, and I own the whole stack.

## What it does

1. Crawls the careers listing on a schedule and keeps roles that match my
   keywords and sit in the Netherlands.
2. Sends the job description plus my CV facts to an LLM, which writes a letter
   in my voice. It can only use facts I give it. It is told not to invent
   employers, dates, or skills.
3. Renders the letter into a PDF.
4. Sends the PDF to my phone on Telegram with three buttons.
5. On approve, it opens the real application form in a browser, fills it,
   uploads my CV and the letter, ticks the required box, screenshots the filled
   form, and waits.
6. I check the screenshot and reply GO to send, or NO to cancel. Nothing is
   submitted without GO.

Every cycle also sends a short status message to my phone, whether it found
anything or not. If there are new roles it says how many it is drafting. If
there are none it says so, with a count of how many it scanned. That way I know
the bot ran and the scraper is still reaching the site, even on a quiet day.

## Buttons

- Approve: fill the form, screenshot it, wait for GO.
- Reject letter: keep the role but drop this draft. Bring it back later with
  /redraft.
- Reject role: drop the role for good.

## Commands

Send these to the bot in Telegram.

- `/start` prints your Telegram chat id.
- `/redraft JR_00XXXXXX` drafts or re-drafts a letter for one role.
- `/apply <title>` followed by a pasted job description drafts from text, no
  scraping.
- `/test <url>` drafts from a single vacancy URL.
- Reply `GO` or `NO` to send or cancel a form that is waiting after approve.

## How it is built

Five parts, chained together. The core is generic. Only the scraper and the
submit step know about the specific careers site.

| File | What it does |
|------|--------------|
| `main.py` | The bot. Scheduler, Telegram handlers, the approve to fill to GO flow. |
| `scraper.py` | Crawls listings, filters by location, pulls the job description. |
| `letter_gen.py` | Calls the LLM and holds the prompt that keeps the voice and the guardrails. |
| `pdf_render.py` | Turns the letter into a PDF. |
| `submit.py` | Fills and submits the application form with a real browser. |
| `store.py` | SQLite. Tracks each job's status so nothing is applied to twice. |
| `config.py` | Reads all settings and secrets from `.env`. |

## Setup

Tested on a Raspberry Pi running Raspberry Pi OS, Python 3.11 or newer.

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
sudo apt install -y xvfb
```

Copy `.env.example` to `.env` and fill in your values. You need an LLM API key,
a Telegram bot token from @BotFather, and your own details for the form. Put
your CV in the folder as `cv.pdf` and your CV as plain text in `facts.txt`.

## Running it

The form needs a real browser, and the Pi has no screen, so the browser runs
under a virtual display (Xvfb). Always start it inside the venv and under Xvfb:

```
source .venv/bin/activate
xvfb-run -a -s "-screen 0 1400x2400x24" python main.py
```

To run it as a background service that survives reboots, install the systemd
unit in `deploy/job-agent.service` (edit the paths and username first):

```
sudo cp deploy/job-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now job-agent
journalctl -u job-agent -f
```

## Notes from building this

A few things that were not obvious and cost real time. Writing them down so the
next person does not repeat them.

- The careers site blocks bots at the TLS layer. Plain HTTP libraries and a
  headless browser both get a 403. Reading pages works with curl_cffi, which
  copies a real browser's TLS fingerprint. The application form works with a
  headed browser under a virtual display. Headless still gets blocked.
- The LLM key format changed. Newer keys go in a header, not the URL. The old
  way returns 401 even with a valid key.
- Do not run the scrape in a background thread inside the bot's event loop. The
  HTTP client used for scraping swallows the job with no error when called that
  way. Run it inline.
- The Pi could reach the outside world over IPv6 for small requests, but larger
  uploads over IPv6 hung and timed out. Preferring IPv4 fixed it.
- The phone field on the form defaults to the wrong country. It has to pick
  Netherlands explicitly, and avoid the Caribbean Netherlands entry that sorts
  first.
- The job title can match roles in the wrong country. Filter on the structured
  location field in the page, not the word appearing in the description text.
- Only run one copy of the bot at a time. Two copies fight over the same
  messages and commands get lost.

## Roadmap

- Support more than one employer through a small adapter per site, so the shared
  core stays the same and only the site-specific parts change.
- Tailor the CV summary per role type, not just the letter.
- Handle roles that close between drafting and approval.

## What is not included in this repo

Secrets and personal data are kept out on purpose. `.env`, `facts.txt`,
`cv.pdf`, the database, and generated letters are all gitignored. Copy
`.env.example` and add your own.
