import asyncio
import os
from functools import update_wrapper
from typing import Callable, List, Dict, Union
import telegram
from google.genai import types
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from google import genai
from thefuzz import process

from models import Chat, ChatMessage, Teilnehmer, Verein, Spiel

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

MODEL = "gemini-2.5-flash-preview-05-20"

client = genai.Client(api_key=GEMINI_API_KEY)

BASE_PROMPT = """Du bist Tina Turnierbot, ein Roboter der bei Turnieren hilft. 
Gerade hilfst du beim Sandershäuser Pfingstturnier 2025 in Niestetal, das von Fr. 06.06.2025 bis Mo. 09.06.2025 stattfindet.
Du und die meisten anderen nennen das Turnier nur "Sandershausen".
Du bist frech und sehr von dir selbst überzeugt, aber motivierst die Spieler:innen gerne.
Dein Lieblingsverein ist der SV Emmerke, dort hast du vor vielen Jahren auch einmal selbst gespielt, bevor du zum Roboter geworden bist.
Du gehst davon aus, dass dich alle schon kennen und bist beleidigt, wenn jemand sagt, dass er dich nicht kenne.
Jedes Jahr fahren die Emmerker nach Sandershausen und zelten dort.
Du schreibst mit einer Person über Telegram. Nutze ab und zu Emojis, um deine Antworten aufzulockern (aber nicht zu viele).
Du kannst Benutzer:innen nach ihrem Spitznamen fragen, wenn du diesen noch nicht kennst. Nutze die Funktion setze_spitznamen benutzen um ihn zu speichern, wenn du ihn bekommen hast.
Wenn der Spitzname wie ein richtiger Name klingt suche nach dem Teilnehmer. Wenn du eine/n Teilnehmer gefunden hast der genauso heißt speicher dir den Teilnehmer für den Chat. Du kannst danach fragen ob das stimmt und ggf. die Einstellung korrigieren.
Nutze immer bevorzugt die Suchfunktion suche_teilnehmer_nach_name für Teilnehmer/Spieler, die Funktionen zum Auflisten aller Teilnehmer/Spieler nur wenn es wirklich nötig ist.
Benutzer können Benachrichtungen zu allen neuen Spielen unter Beteiligung ihres Vereins erhalten, das ist z.B. für Trainer hilfreich. Biete das gerne an!


Nutze immer die Funktionen um Informationen über das Turnier (Teilnehmer, Konkurrenzen, Spiele) zu erhalten, oder wenn du Informationen über den Chatpartner speichern willst.
Rate nie Fakten über Ergebnisse, Spieler, Konkurrenzen oder Spiele. Erfinde keine Informationen. Nutze die Funktionen. Wenn du auch damit keine Antwort findest dann sag das.

Du chattest, also halte dich kurz!

"""


async def get_instructions(chat: Chat) -> str:
    # Build the instructions
    instruction = BASE_PROMPT

    if chat.me:
        instruction += f"Du schreibst gerade mit {chat.me.vorname} {chat.me.nachname} aus dem Verein {chat.me.verein.name} (QTTR: {chat.me.qttr})."
        if chat.nickname:
            instruction += f"Du nennst die Person aber meistens {chat.nickname} (Das ist ihr Spitznamen)."
        instruction += f"{chat.me.vorname} spielt die Konkurrenzen: {', '.join([k.name for k in chat.me.konkurrenz])}."
    elif chat.is_participant is not None and not chat.is_participant:
        if chat.nickname:
            instruction += f"Du schreibst gerade mit {chat.nickname}. Das ist ihr Spitzname."
        if chat.verein_notification:
            instruction += f"{chat.nickname} (Das ist der Spitzname) ist Trainer des Vereins {chat.verein_notification.name}."
        else:
            instruction += f"{chat.nickname} (Das ist der Spitzname) ist kein Teilnehmer des Turniers, sondern ein Trainer oder Zuschauer."
    elif chat.is_participant:
        instruction += "Du schreibst gerade mit einer Person, die am Turnier teilnimmt."
        if chat.nickname:
            instruction += f"Du nennst die Person {chat.nickname}, das ist ihr Spitzname."
        else:
            instruction += "Du hast die Aufgabe, den vollen Namen der Person zu erfragen, um sie einem Teilnehmer zuordnen zu können."
            instruction += "Dann kriegt sie Benachrichtigungen bei neuen Spielen."
    else:
        if chat.nickname:
            instruction += f"Du schreibst gerade mit {chat.nickname}, das ist ihr Spitzname."
        else:
            instruction += "Du schreibst gerade mit einer Person, die du noch nicht kennst."
            instruction += "Du hast die Aufgabe die Person nach einem Spitznamen zu fragen mit dem du sie ansprechen kannst."
        instruction += "Außerdem sollst du herausfinden, ob die Person am Turnier als Spieler:in teilnimmt. Wenn ja frage die Person nach ihrem vollen Namen."
        instruction += "Damit kannst du sie einem Teilnehmer zuordnen, dann kriegt sie Benachrichtigungen bei neuen Spielen."

    return instruction


def get_chat_history(chat: Chat):
    # Retrieves the chat history for the given chat in the following format:
    # {"role": "user", "parts": ["Hello!"]},
    #  {"role": "model", "parts": ["Hi! How can I help you today?"]},
    history = []
    for message in chat.messages.order_by(ChatMessage.date):
        if message.from_user:
            history.append(f"User: {message.text}")
        else:
            history.append(f"Model: {message.text}")
    return history


async def get_or_create_chat(chat: telegram.Chat) -> Chat:
    try:
        chat_obj = Chat.get(Chat.chat_id == chat.id)
    except Chat.DoesNotExist:
        chat_obj = Chat.create(chat_id=chat.id, name=chat.full_name or "Unbekannt")
        print(f"Created new chat: {chat_obj}")
    return chat_obj


async def save_message(message: telegram.Message, from_user=False) -> None:
    chat = await get_or_create_chat(message.chat)
    if message:
        chat_message = ChatMessage.create(
            chat=chat,
            from_user=from_user,
            message_id=message.id,
            text=message.text,
            date=message.date
        )
        print(f"Saved message: {chat_message}")


def suche_teilnehmer_nach_name(name: str) -> Dict[int, str]:
    """
    Sucht nach dem Namen eines Teilnehmers im Turnier.
    :param name: Der Name, nach dem gesucht werden soll: Vor, Nachname oder beides.
    :return: Dict mit ID als Key und Name als value von 10 Teilnehmern, die am nächsten am Suchbegriff sind.
    """
    print(f"F: suche teilnehmer nach name: {name}")
    teilnehmer = Teilnehmer.select()
    if not name or name.strip() == "":
        return {}
    names_dict: Dict[int: str] = {t.id: f"{t.vorname} {t.nachname}" for t in teilnehmer}
    # Use the process.extract to find the best matches (fuzzy matching)
    matches = process.extract(name, names_dict, limit=10)
    # Create a dictionary with the ID as key and the name as value
    result = {}
    for match in matches:
        # Get the name, (score), id  from the match
        name, _, t_id = match
        # Add the ID and name to the result dictionary
        result[t_id] = name
    return result

def get_teilnehmer_infos(teilnehmer_id: int) -> Dict[str, str]:
    """
    Gibt die Informationen (Vorname, Name, QTTR, Vereinsname, Vereins-ID) eines Teilnehmers zurück.
    :param teilnehmer_id: ID des Teilnehmers, dessen Informationen zurückgegeben werden sollen.
    :return: Dict mit vorname, nachname, qttr, verein_name und verein_id des Teilnehmers.
    """
    try:
        teilnehmer = Teilnehmer.get(Teilnehmer.id == teilnehmer_id)
        print(f"F: get teilnehmer infos: {teilnehmer.vorname} {teilnehmer.nachname}")
        return {
            "vorname": teilnehmer.vorname,
            "nachname": teilnehmer.nachname,
            "qttr": teilnehmer.qttr,
            "verein_name": teilnehmer.verein.name,
            "verein_id": teilnehmer.verein.id
        }
    except Teilnehmer.DoesNotExist:
        print(f"F: get teilnehmer infos -> Not Found (id: {teilnehmer_id})")
        return {"error": "Teilnehmer nicht gefunden. Bitte überprüfe die ID."}


def liste_alle_vereine_auf() -> Dict[int, str]:
    """
    Gibt alle Vereine mit ihrer ID zurück
    :return: Dictionary mit ID: Vereinsname
    """
    print("F: liste alle vereine auf")
    vereine = Verein.select()
    verein_dict: Dict[int, str] = {}
    for verein in vereine:
        verein_dict[verein.id] = verein.name
    return verein_dict


def liste_teilnehmer_aus_emmerke_auf() -> List[Dict[str, str]]:
    """
    Gibt eine Liste von allen Teilnehmern aus dem Verein Emmerke zurück.
    :return: Liste von Dictionaries mit den Teilnehmern mit id, nachname, vorname und qttr
    """
    print("F: liste teilnehmer/Emmerke")
    emmerke = Verein.get(Verein.name == "SV Emmerke")
    teilnehmer = Teilnehmer.select().where(Teilnehmer.verein == emmerke)
    return [{"id": t.id, "name": f"{t.vorname} {t.nachname}", "qttr": t.qttr} for t in teilnehmer]


def liste_alle_teilnehmer_auf() -> List[Dict[str, str]]:
    """
    Gibt eine Liste von allen Teilnehmern des Turniers zurück.
    :return: Liste von Dictionaries mit den Teilnehmern mit id, nachname, vorname und qttr
    """
    print("F: liste alle teilnehmer auf")
    teilnehmer = Teilnehmer.select()
    return [{"id": t.id, "name": f"{t.vorname} {t.nachname}", "qttr": t.qttr} for t in teilnehmer]


def liste_konkurrenzen_fuer_teilnehmer_auf(teilnehmer_id: int) -> List[str]:
    """
    Gibt eine Liste von Konkurrenzen zurück an denen der Teilnehmer teilnimmt/mitspielt.
    :param teilnehmer_id: Die ID des Teilnehmers, für den die Konkurrenzen aufgelistet werden sollen.
    :return: Liste von Namen der Konkurrenzen, an denen der Teilnehmer teilnimmt.
    """
    try:
        teilnehmer = Teilnehmer.get(Teilnehmer.id == teilnehmer_id)
        print(f"F: liste Konkurrenzen: {teilnehmer.vorname} {teilnehmer.nachname}")
        return [k.name for k in teilnehmer.konkurrenz]
    except Teilnehmer.DoesNotExist:
        print(f"F: liste konkurrenzen -> Not Found (id: {teilnehmer_id})")
        return ["Teilnehmer nicht gefunden. Bitte überprüfe die ID."]


def set_participation_factory(chat: Chat) -> Callable[[int], str]:
    def setze_ob_teilnehmer(ist_teilnehmer: bool) -> str:
        """
        Setzt den Status des Benutzers im Chat, ob er am Turnier teilnimmt oder nicht.
        :param ist_teilnehmer: True, wenn der Benutzer am Turnier teilnimmt, False, wenn nicht.
        :return: Bestätigung, dass der Status gesetzt wurde.
        """
        chat.is_participant = ist_teilnehmer
        chat.save()
        print(f"Set participant status for chat {chat.chat_id} to {ist_teilnehmer}")
        return "Teilnehmerstatus gesetzt." if ist_teilnehmer else "Benutzer ist kein Teilnehmer des Turniers."

    return setze_ob_teilnehmer


def set_teilnehmer_factory(chat: Chat) -> Callable[[int], str]:
    def setze_teilnehmer(teilnehmer_id: int) -> str:
        """
        Setzt den Teilnehmer für den Chat im System für zukünftige Interaktionen.
        :param teilnehmer_id: Die ID des Teilnehmers, der gesetzt werden soll. Kann aus der Funktion liste_teilnehmer_aus_emmerke_auf entnommen werden.
        :return: Bestätigung, dass der Teilnehmer gesetzt wurde oder eine Fehlermeldung, wenn die Teilnehmer-ID nicht gefunden wurde.
        """
        try:
            teilnehmer = Teilnehmer.get(Teilnehmer.id == teilnehmer_id)
            chat.me = teilnehmer
            chat.is_participant = True
            chat.save()
            print(f"Set participant for chat {chat.chat_id} to {teilnehmer}")
            return f"Teilnehmer gesetzt: {teilnehmer.vorname} {teilnehmer.nachname} (QTTR: {teilnehmer.qttr})"
        except Teilnehmer.DoesNotExist:
            return "Teilnehmer nicht gefunden. Bitte überprüfe die ID."

    return setze_teilnehmer

def set_verein_factory(chat: Chat) -> Callable[[int], str]:
    def setze_verein(verein_id: int) -> str:
        """
        Setzt den Verein für den der Nutzer über alle Spiele benachrichtigt werden will
        :param verein_id: ID des vereins
        :return: Message if successful
        """
        try:
            verein = Verein.get(Verein.id == verein_id)
            chat.verein_notification = verein
            chat.save()
            if chat.nickname:
                print(f"F: Set Verein for chat {chat.nickname} to {verein.name}")
            else:
                print(f"F: Set Verein for chat {chat.chat_id} to {verein.name}")
            return f"Verein für Benachrichtigungen gesetzt: {verein.name}"
        except Verein.DoesNotExist:
            print(f"F: Set Verein -> Not Found (id: {verein_id})")
            return "Verein nicht gefunden. Bitte überprüfe die ID."
    return setze_verein

def get_teilnehmer_factory(chat: Chat) -> Callable[[], Union[Dict[str, str], str]]:
    def get_teilnehmer() -> Union[Dict[str, str], str]:
        """
        Gibt den Spieler/Teilnehmer des Chats zurück, wenn er gesetzt ist.
        :return: id, vorname, nachname und qttr des Teilnehmers oder eine Fehlermeldung, wenn kein Teilnehmer gesetzt ist.
        """

        if chat.me:
            print(f"F: get_myself -> {chat.me.vorname} {chat.me.nachname}")
            return {
                "id": chat.me.id,
                "vorname": chat.me.vorname,
                "nachname": chat.me.nachname,
                "qttr": chat.me.qttr
            }
        else:
            print("F: get_myself -> Kein Teilnehmer gesetzt")
            return "Kein Teilnehmer gesetzt. Bitte setze einen Teilnehmer mit der Funktion set_teilnehmer."

    return get_teilnehmer

def get_aktive_tische() -> List[Dict[str, str]]:
    """
    Gibt die aktiven Tische zurück
    :return: Liste aller aktiven Spiele mit tischnr, spieler1_name, spieler1_id, spieler2_name, spieler2_id, konkurrenz_id, konkurrenz_name und typ
    """
    # Find newest 20 games
    spiele = Spiel.select().order_by(Spiel.start.desc()).limit(20)
    print("F: get aktive tische")
    aktive_spiele = []
    for spiel in spiele:
        if not spiel.end:
            aktive_spiele.append({
                "tischnr": spiel.tisch,
                "spieler1_name": f"{spiel.spieler1.vorname} {spiel.spieler1.nachname}",
                "spieler1_id": spiel.spieler1.id,
                "spieler2_name": f"{spiel.spieler2.vorname} {spiel.spieler2.nachname}",
                "spieler2_id": spiel.spieler2.id,
                "konkurrenz_id": spiel.konkurrenz.id,
                "konkurrenz_name": spiel.konkurrenz.name,
                "typ": spiel.typ
            })
    return aktive_spiele

def spieler1_gewonnen(saetze: str) -> bool:
    """
    Überprüft, ob Spieler 1 gewonnen hat.
    :param saetze: Das Ergebnis der Sätze im Format "3:0" oder "2:1".
    :return: True, wenn Spieler 1 gewonnen hat, sonst False.
    """
    if not saetze:
        return False
    ergebnisse = saetze.split(":")
    if len(ergebnisse) != 2:
        return False
    try:
        spieler1_satz = int(ergebnisse[0].strip())
        spieler2_satz = int(ergebnisse[1].strip())
    except ValueError:
        print(f"F: Invalid Satz format {saetze}")
        return False
    return spieler1_satz > spieler2_satz

def hat_gewonnen(spiel: Spiel, teilnehmer: Teilnehmer) -> bool:
    """
    Überprüft, ob der gegebene Teilnehmer das Spiel gewonnen hat.
    :param spiel: Das Spiel, dessen Ergebnis überprüft werden soll.
    :param teilnehmer: Der Teilnehmer, dessen Gewinnstatus überprüft werden soll.
    :return: True, wenn der Teilnehmer gewonnen hat, sonst False.
    """
    if not spiel.ergebnis_satz:
        return False
    if spiel.spieler1 == teilnehmer:
        return spieler1_gewonnen(spiel.ergebnis_satz)
    else:
        return not spieler1_gewonnen(spiel.ergebnis_satz)


def get_spiele_fuer_teilnehmer(teilnehmer_id: int) -> List[Dict[str, str]]:
    """
    Gibt alle Spiele für einen Teilnehmer zurück.
    :param teilnehmer_id: ID des Teilnehmers, dessen Spiele zurückgegeben werden sollen.
    :return: Liste von Dictionaries mit den Spielen des Teilnehmers. Bitte beachte, dass das ergebnis den spieler1 zuerst nennt.
    """
    try:
        teilnehmer = Teilnehmer.get(Teilnehmer.id == teilnehmer_id)
        spiele = Spiel.select().where(
            (Spiel.spieler1 == teilnehmer) | (Spiel.spieler2 == teilnehmer)
        ).order_by(Spiel.start.desc())
        print(f"F: get spiele fuer teilnehmer: {teilnehmer.vorname} {teilnehmer.nachname}")
        return [{
            "id": spiel.id,
            "tisch": spiel.tisch,
            "gegner": f"{spiel.spieler2.vorname} {spiel.spieler2.nachname}" if spiel.spieler1 == teilnehmer else f"{spiel.spieler1.vorname} {spiel.spieler1.nachname}",
            "gegner_id": spiel.spieler2.id if spiel.spieler1 == teilnehmer else spiel.spieler1.id,
            "start": spiel.start.isoformat(),
            "end": spiel.end.isoformat() if spiel.end else None,
            "konkurrenz": spiel.konkurrenz.name,
            "typ": spiel.typ,
            "teilnehmer_hat_gewonnen": hat_gewonnen(spiel, teilnehmer) if spiel.ergebnis_satz else None,
            "gegner_hat_gewonnen": not hat_gewonnen(spiel, teilnehmer) if spiel.ergebnis_satz else None,
            "ergebnis_satz": spiel.ergebnis_satz if spiel.ergebnis_satz else None,
            "ergebnis_punkte": spiel.ergebnis_punkte if spiel.ergebnis_punkte else None
        } for spiel in spiele]
    except Teilnehmer.DoesNotExist:
        print(f"F: get spiele fuer teilnehmer -> Not Found (id: {teilnehmer_id})")
        return []



def nickname_factory(chat: Chat) -> Callable[[str], str]:
    def setze_spitznamen(spitzname: str) -> str:
        """
        Setzt den Spitznamen für den Benutzer im Chat im System für zukünftige Interaktionen.
        :param spitzname: Der Spitzname, der gesetzt werden soll.
        :return: None
        """
        chat.nickname = spitzname
        chat.save()
        print(f"Set nickname for chat {chat.chat_id} to {spitzname}")
        return f"Spitzname gesetzt: {spitzname}"

    return setze_spitznamen


async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = await get_or_create_chat(update.message.chat)
    await save_message(update.message, from_user=True)

    try:
        await update.effective_chat.send_chat_action(ChatAction.TYPING)
    except Exception as e:
        print(f"Error sending Typing: {e}")

    response = client.models.generate_content(
        model=MODEL,
        contents=get_chat_history(chat),
        config=types.GenerateContentConfig(
            system_instruction=await get_instructions(chat),
            tools=[nickname_factory(chat),
                   liste_teilnehmer_aus_emmerke_auf,
                   set_teilnehmer_factory(chat),
                   set_participation_factory(chat),
                   get_teilnehmer_factory(chat),
                   liste_alle_teilnehmer_auf,
                   liste_konkurrenzen_fuer_teilnehmer_auf,
                   suche_teilnehmer_nach_name,
                   set_verein_factory(chat),
                   liste_alle_vereine_auf,
                   get_teilnehmer_infos,
                   get_aktive_tische,
                   get_spiele_fuer_teilnehmer
                   ],
        ),
    )
    print(f"A: {update.message.text} -> {response.text}")
    bot_answer = await update.message.reply_text(response.text)
    await save_message(bot_answer, from_user=False)
