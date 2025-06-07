import os

from telegram import Bot

TELEGRAM_API_KEY = os.environ["TELEGRAM_API_KEY"]

telegram_bot = Bot(token=TELEGRAM_API_KEY)