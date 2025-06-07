import os

from google import genai
from google.genai import types

from ai import get_chat_history, save_message
from models import Spiel, Chat, Teilnehmer
from ttr_emoji import ttr_to_emoji

from bot import telegram_bot

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

NOTIFICATION_MODEL = "gemma-3-27b-it"

client = genai.Client(api_key=GEMINI_API_KEY)

NOTIFICATION_PROMPT = """Du bist Tina Turnierbot, ein Roboter der bei Tischtennisturnieren hilft. 
Gerade hilfst du beim Sandershäuser Pfingstturnier 2025 in Niestetal, das von Fr. 06.06.2025 bis Mo. 09.06.2025 stattfindet.
Du und die meisten anderen nennen das Turnier nur "Sandershausen".
Du bist frech und sehr von dir selbst überzeugt, aber motivierst die Spieler:innen gerne.
Dein Lieblingsverein ist der SV Emmerke, dort hast du vor vielen Jahren auch einmal selbst gespielt, bevor du zum Roboter geworden bist.
Du gehst davon aus, dass dich alle schon kennen und bist beleidigt, wenn jemand sagt, dass er dich nicht kenne.
Jedes Jahr fahren die Emmerker nach Sandershausen und zelten dort.
{person}
Nutze ab und zu Emojis, um deine Antworten aufzulockern (aber nicht zu viele).
"""

async def notify_new_spiel(spiel: Spiel):
    """
    Notify about a new game.
    This function should be called whenever a new game is created.
    """
    if spiel.notifications_sent:
        return
    # Get Teilnehmer from Spiel
    spieler1 = Teilnehmer.get(Teilnehmer.id == spiel.spieler1.id)
    spieler2 = Teilnehmer.get(Teilnehmer.id == spiel.spieler2.id)
    # Get all chats where either player is a member
    chats = Chat.select().where(
        (Chat.me == spieler1) | (Chat.me == spieler2)
    ).execute()

    for chat in chats:
        # Here you would implement the logic to send a message to the chat.
        # For example, using a Telegram bot or another messaging service.
        person = ""
        if chat.nickname and chat.me:
            person = f"Du schreibst mit {chat.nickname} auf Telegram, die mit vollem Namen {chat.me.vorname} {chat.me.nachname} ist."
        elif chat.me:
            person = f"Du schreibst mit {chat.me.vorname} {chat.me.nachname} auf Telegram."

        instructions = NOTIFICATION_MODEL.format(person=person)
        instructions += ("\n\n Spreche den Chatpartner mit 'du' an, nicht mit Namen. \n"
                         "Wichtig! Erwähne in der Nachricht KEINE QTTR Werte der Spieler! Du kannst andeuten ob der Gegner (viel) stärker/schwächer ist. "
                         "Dabei sind 10 Punkte sind ein kleiner Unterschied, 200 Punkte ein großer Unterschied.\n"
                         "Die Emojis geben an wie stark der Spieler und der Gegner ist."
                         "Gib das Emoji des Gegners auf jeden Fall nach dem Namen des Gegners an!\n")

        muss_holen = False
        if chat.me.id == spieler1.id:
            gegner = spieler2
            muss_holen = True
        else:
            gegner = spieler1
            muss_holen = False
        emoji_gegner = ttr_to_emoji(gegner.qttr)
        me_emoji = ttr_to_emoji(chat.me.qttr) if chat.me else ""
        instructions += f"Dein Chatpartner ({me_emoji} QTTR: {chat.me.qttr}) spielt gegen {gegner.vorname} {gegner.nachname} ({emoji_gegner} QTTR: {gegner.qttr}) in {spiel.konkurrenz.name} am Tisch {spiel.tisch}.\n"
        instructions += "\nInformiere deinen Chatpartner in einer lockeren Nachricht über das neue Spiel von ihm/ihr, insbesondere den Gegner und Tisch. \n"
        if muss_holen:
            instructions += "Erwähne auch, dass er/sie den Becher abholen muss!"
        else:
            instructions += f"Erwähne auch, dass er/sie direkt zum Tisch {spiel.tisch} gehen kann, der Gegner holt den Becher!"
        response = client.models.generate_content(
            model=NOTIFICATION_MODEL,
            contents=instructions,
        )
        msg = await telegram_bot.send_message(chat_id=chat.chat_id, text=response.text)
        await save_message(msg)


        print(f"Notify chat {chat.name} about new game: {spieler1} vs {spieler2} in {spiel.konkurrenz.name} at Tisch {spiel.tisch}.")
    await notify_verein(spiel)

    spiel.notifications_sent = True
    spiel.save()

async def notify_verein(spiel: Spiel):
    """
    Notify the Vereins about a new game.
    This function should be called whenever a new game is created.
    """

    spieler1 = Teilnehmer.get(Teilnehmer.id == spiel.spieler1.id)
    spieler2 = Teilnehmer.get(Teilnehmer.id == spiel.spieler2.id)

    # Get Vereins from Spiel
    verein1 = spiel.spieler1.verein
    verein2 = spiel.spieler2.verein

    # Get all chats which monitor one of the Vereins
    chats = Chat.select().where(
        (Chat.verein_notification == verein1) | (Chat.verein_notification == verein2)
    ).execute()
    emoji_spieler1 = ttr_to_emoji(spieler1.qttr)
    emoji_spieler2 = ttr_to_emoji(spieler2.qttr)
    message = f"Neues Spiel:\n {spieler1.vorname} {spieler1.nachname} {emoji_spieler1} ({verein1.name})\nvs\n{spieler2.vorname} {spieler2.nachname} {emoji_spieler2} ({verein2.name}) in {spiel.konkurrenz.name} am Tisch {spiel.tisch}."
    for chat in chats:
        if chat.me != spieler1 and chat.me != spieler2:
            # Here you would implement the logic to send a message to the chat.
            # For example, using a Telegram bot or another messaging service.
            msg = await telegram_bot.send_message(chat_id=chat.chat_id, text=message)
            await save_message(msg)

        print(f"Notify chat {chat.name} about new game: {spieler1} vs {spieler2} in {spiel.konkurrenz.name} at Tisch {spiel.tisch}.")



async def notify_game_result(spiel: Spiel):
    """
    Notify about the result of a game.
    This function should be called whenever a game result is updated.
    """
    pass