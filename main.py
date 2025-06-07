import os
import asyncio
import platform
import signal
from typing import Sequence, Coroutine

from telegram._utils.defaultvalue import DEFAULT_NONE, DefaultValue
from telegram._utils.types import ODVInput
from telegram.ext import ApplicationBuilder, MessageHandler, filters
from models import init_db
from parser import *
from parser import fetch_active_tables
from ai import answer

TELEGRAM_API_KEY = os.environ["TELEGRAM_API_KEY"]

async def init():
    init_db()
    await fetch_konkurrenzen()
    await fetch_teilnehmer()

# Basic async
def main():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init())


    app = ApplicationBuilder().token(TELEGRAM_API_KEY).build()

    app.add_handler(MessageHandler(filters.ALL, answer))

    job_queue = app.job_queue

    # Schedule the task to run every 60 seconds (set interval as needed)
    job_queue.run_repeating(fetch_active_tables, interval=5, first=1)
    app.run_polling()


if __name__ == "__main__":
    main()