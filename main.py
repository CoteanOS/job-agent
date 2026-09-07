"""
The agent, as one always-on asyncio process.

Two jobs share a single event loop via python-telegram-bot:
  1. A scheduled cycle (JobQueue): scrape -> letter -> PDF -> queue -> ping you.
  2. A callback handler: your Approve / Reject taps on the phone.

Nothing is submitted without your tap. Run it:  python main.py
"""
import asyncio
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    MessageHandler, filters,
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
)

from datetime import datetime

import config
import store
import scraper
import letter_gen
import pdf_render
import submit

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)

# job_id -> (playwright, browser, page) for a form filled and awaiting GO
PENDING_SEND = {}

log = logging.getLogger("job-agent")


def _facts() -> str:
    return config.FACTS_FILE.read_text(encoding="utf-8")


def _keyboard(job_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve:{job_id}"),
    ], [
        InlineKeyboardButton("✏️ Reject letter", callback_data=f"rejletter:{job_id}"),
        InlineKeyboardButton("🚫 Reject role", callback_data=f"rejrole:{job_id}"),
    ]])


async def process_job(app: Application, job: dict, force: bool = False):
    """One job: make letter, render PDF, send to phone for approval."""
    job_id = store.add_job(job["url"], job["title"], job["company"], job["description"])
    row = store.get(job_id)
    if not force and row["status"] in (
        "pending", "approved", "submitted", "role_rejected", "letter_rejected"):
        return  # already handled in a previous run

    try:
        letter = await asyncio.to_thread(
            letter_gen.generate_letter,
            title=job["title"], company=job["company"],
            description=job["description"], facts=_facts(),
        )
        pdf = await asyncio.to_thread(
            pdf_render.render_letter,
            body_text=letter, job_title=job["title"], company=job["company"],
        )
    except Exception as e:
        log.exception("letter/pdf failed for %s", job["url"])
        store.set_status(job_id, "error", str(e)[:400])
        await app.bot.send_message(config.TELEGRAM_CHAT_ID,
                                   f"Failed on {job['title']}: {e}")
        return

    store.set_letter(job_id, letter, str(pdf))
    caption = (f"New application ready\n\n"
               f"{job['title']} @ {job['company']}\n{job['url']}\n\n"
               f"Review the letter, then approve or reject.")
    with open(pdf, "rb") as fh:
        await app.bot.send_document(
            config.TELEGRAM_CHAT_ID, InputFile(fh, filename=pdf.name),
            caption=caption, reply_markup=_keyboard(job_id))


async def cycle(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled scrape cycle, capped at MAX_PER_RUN new applications."""
    log.info("cycle start")
    try:
        jobs = await asyncio.to_thread(scraper.scrape_new_jobs)
    except Exception:
        log.exception("scrape failed")
        return
    fresh = [j for j in jobs if not store.already_seen(j["url"])][: config.MAX_PER_RUN]
    log.info("cycle: %d scraped, %d new (cap %d)", len(jobs), len(fresh), config.MAX_PER_RUN)
    for j in fresh:
        await process_job(context.application, j)
    stamp = datetime.now().strftime("%H:%M")
    try:
        if fresh:
            await context.bot.send_message(
                config.TELEGRAM_CHAT_ID,
                f"Checked Rabobank: {len(fresh)} new role(s), drafting. "
                f"(scanned {len(jobs)}) {stamp}")
        else:
            await context.bot.send_message(
                config.TELEGRAM_CHAT_ID,
                f"Checked Rabobank: no new roles. "
                f"(scanned {len(jobs)}, all seen before) {stamp}")
    except Exception:
        log.exception("heartbeat message failed")


async def on_tap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    action, sid = q.data.split(":")
    job_id = int(sid)
    row = store.get(job_id)
    if row is None:
        await q.edit_message_caption("Gone (not in store).")
        return

    if action == "rejletter":
        store.set_status(job_id, "letter_rejected")
        await q.edit_message_caption(
            f"Letter rejected (role kept): {row['title']}\n"
            f"Redraft later with:  /redraft {row['url'].split('/')[-2]}")
        return

    if action == "rejrole":
        store.set_status(job_id, "role_rejected")
        await q.edit_message_caption(f"Role rejected for good: {row['title']}")
        return

    # approve -> fill the form under xvfb, screenshot, wait for GO
    store.set_status(job_id, "approved")
    await q.edit_message_caption(f"Approved: {row['title']}. Filling the form, one moment...")
    try:
        import submit
        pw, browser, page, shot = await submit.prepare_application(
            url=row["url"], letter_pdf=row["pdf_path"])
        PENDING_SEND[job_id] = (pw, browser, page)
        with open(shot, "rb") as fh:
            await context.bot.send_photo(
                config.TELEGRAM_CHAT_ID, fh,
                caption=(f"Form ready: {row['title']} @ {row['company']}\n\n"
                         f"Check it. Reply  GO  to send, or  NO  to cancel."))
    except submit.SubmitNotConfigured as e:
        await q.edit_message_caption(f"Approved, PDF saved. Submit not ready: {e}")
    except Exception as e:
        import traceback; traceback.print_exc()
        await q.edit_message_caption(f"Approved but form-fill failed: {e}")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Job agent online. Your chat id is {update.effective_chat.id} "
        f"(put this in TELEGRAM_CHAT_ID). It scrapes every {config.CYCLE_HOURS}h "
        f"and pings you to approve each application.")


async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Running a cycle now...")
    await cycle(context)


async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("usage: /test <vacancy_url>")
        return
    try:
        job = scraper.scrape_single(context.args[0])
    except getattr(scraper, "RoleClosed", Exception) as e:
        await update.message.reply_text(f"That role is closed (404): {e}")
        return
    except Exception as e:
        await update.message.reply_text(f"Couldn't fetch ({e}). If blocked, use /apply.")
        return
    await update.message.reply_text(f"Drafting: {job['title']} ...")
    await process_job(context.application, job, force=True)


async def on_error(update, context):
    import traceback
    err = "".join(traceback.format_exception(type(context.error), context.error, context.error.__traceback__))
    log.error("HANDLER ERROR:\n%s", err)
    try:
        await context.bot.send_message(config.TELEGRAM_CHAT_ID, f"ERROR: {context.error}")
    except Exception:
        pass


async def cmd_redraft(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/redraft <JR_id or full url> -> regenerate a letter for a dormant role."""
    if not context.args:
        await update.message.reply_text("usage: /redraft JR_00144519")
        return
    arg = context.args[0]
    if arg.startswith("http"):
        url = arg
    else:
        # look up the stored url containing this JR id
        import sqlite3
        con = sqlite3.connect(config.DB_FILE); con.row_factory = sqlite3.Row
        r = con.execute("SELECT url FROM jobs WHERE url LIKE ?", (f"%{arg}%",)).fetchone()
        con.close()
        if not r:
            await update.message.reply_text(f"No stored role matches {arg}")
            return
        url = r["url"]
    await update.message.reply_text("Redrafting, fetching role...")
    try:
        job = scraper.scrape_single(url)
    except getattr(scraper, "RoleClosed", Exception) as e:
        await update.message.reply_text(f"That role is closed (404): {e}")
        return
    await process_job(context.application, job, force=True)


async def on_go(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip().upper()
    if text not in ("GO", "NO"):
        return
    if not PENDING_SEND:
        await update.message.reply_text("Nothing is waiting to send.")
        return
    # act on the most recently prepared one
    job_id = list(PENDING_SEND.keys())[-1]
    pw, browser, page = PENDING_SEND.pop(job_id)
    try:
        if text == "NO":
            await update.message.reply_text("Cancelled. Not sent.")
            store.set_status(job_id, "approved", "user cancelled send")
        else:
            import submit
            result = await submit.confirm_send(page)
            store.set_status(job_id, "submitted", result)
            await update.message.reply_text("Sent. Application submitted.")
    except Exception as e:
        import traceback; traceback.print_exc()
        await update.message.reply_text(f"Send failed: {e}")
    finally:
        try:
            await browser.close(); await pw.stop()
        except Exception:
            pass


def main():
    problems = config.check()
    store.init()
    if problems:
        print("Config issues (fix in .env / facts.txt):")
        for p in problems:
            print("  -", p)
        print("Starting anyway so /start can print your chat id.\n")

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).connect_timeout(30).read_timeout(30).write_timeout(60).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("run", cmd_run))
    app.add_handler(CommandHandler("test", cmd_test))
    app.add_handler(CommandHandler("redraft", cmd_redraft))
    app.add_handler(CallbackQueryHandler(on_tap))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_go))
    app.add_error_handler(on_error)

    # schedule the cycle: once ~10s after boot, then every CYCLE_HOURS
    jq = app.job_queue
    jq.run_once(cycle, when=10)
    jq.run_repeating(cycle, interval=config.CYCLE_HOURS * 3600)

    log.info("agent starting (model=%s, cap=%d/run, every %sh)",
             config.GEMINI_MODEL, config.MAX_PER_RUN, config.CYCLE_HOURS)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
