import os
import asyncio

from telegram.ext import ApplicationBuilder, MessageHandler, filters

from models import init_db
from parser import *
from ai import answer

TELEGRAM_API_KEY = os.environ["TELEGRAM_API_KEY"]





# Basic async
async def main():
    init_db()
    await fetch_konkurrenzen()
    await fetch_teilnehmer()

    app = ApplicationBuilder().token(TELEGRAM_API_KEY).build()

    app.add_handler(MessageHandler(filters.ALL, answer))

    app.run_polling()


if __name__ == "__main__":
    asyncio.run(main())