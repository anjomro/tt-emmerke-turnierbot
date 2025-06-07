from datetime import datetime

from peewee import *
import os

DB_PATH = os.getenv("DB_PATH", "./db/turnier.db")
db = SqliteDatabase(DB_PATH)

class BaseModel(Model):
    class Meta:
        database = db


class Verein(BaseModel):
    name = CharField()

    def __str__(self):
        return self.name


class Konkurrenz(BaseModel):
    name = CharField()
    link = CharField()
    start = DateTimeField(null=True)

    def __str__(self):
        return self.name


# Starter: Has an number (id) as pk, firstname lastname, qttr and a foreign key to a club
# Teilnehmer: id als pk, vorname, nachname, qttr, verein (foreign key to Verein)
class Teilnehmer(BaseModel):
    id = IntegerField(primary_key=True)
    vorname = CharField()
    nachname = CharField()
    qttr = IntegerField()
    verein = ForeignKeyField(Verein, backref='mitglieder')
    konkurrenz = ManyToManyField(Konkurrenz, backref='teilnehmer')

    def __str__(self):
        return f"{self.id}: {self.vorname} {self.nachname} ({self.qttr})"

    async def lade_teilnehmer(self, id):
        try:
            teilnehmer = await Teilnehmer.get(Teilnehmer.id == id)
            return teilnehmer
        except DoesNotExist:
            return None


class Spiel(BaseModel):
    tisch = IntegerField()
    spieler1 = ForeignKeyField(Teilnehmer, backref='spieler1')
    spieler2 = ForeignKeyField(Teilnehmer, backref='spieler2')
    konkurrenz = ForeignKeyField(Konkurrenz, backref='spiele', null=True)
    typ = CharField()  # e.g., "Finale", "Halbfinale", etc.
    start = DateTimeField(default=datetime.now())
    end = DateTimeField(null=True)
    ergebnis_punkte = CharField(null=True)  # e.g., "11:6, 11:8, 11:5"
    ergebnis_satz = CharField(null=True)  # e.g., "3:0"
    notifications_sent = BooleanField(default=False)


class Chat(BaseModel):
    chat_id = IntegerField(primary_key=True)
    name = CharField()
    nickname = CharField(null=True)
    me = ForeignKeyField(Teilnehmer, backref='chats', null=True)
    is_participant = BooleanField(null=True)  # True if the user plays in the tournament
    verein_notification = ForeignKeyField(Verein, backref='trainer', null=True)

    def __str__(self):
        return f"{self.name} ({self.chat_id})"

class ChatMessage(BaseModel):
    chat = ForeignKeyField(Chat, backref='messages')
    from_user = BooleanField(default=True)
    message_id = IntegerField()
    text = TextField()
    date = DateTimeField(default=datetime.now())

    def __str__(self):
        return f"Message {self.message_id} in {self.chat.name}: {self.text[:30]}..."

class DoppelPaarung(BaseModel):
    teilnehmer1 = ForeignKeyField(Teilnehmer, backref='doppel_teilnehmer1')
    teilnehmer2 = ForeignKeyField(Teilnehmer, backref='doppel_teilnehmer2')

class DoppelSpiel(BaseModel):
    tisch = IntegerField()
    spieler1 = ForeignKeyField(DoppelPaarung, backref='doppel_spieler1')
    spieler2 = ForeignKeyField(DoppelPaarung, backref='doppel_spieler2')
    konkurrenz = ForeignKeyField(Konkurrenz, backref='doppel_spiele', null=True)
    typ = CharField()  # e.g., "Finale", "Halbfinale", etc.
    start = DateTimeField(default=datetime.now())
    end = DateTimeField(null=True)
    ergebnis_punkte = CharField(null=True)  # e.g., "11:6, 11:8, 11:5"
    ergebnis_satz = CharField(null=True)  # e.g., "3:0"
    notifications_sent = BooleanField(default=False)

def init_db():
    db.connect()
    db.create_tables([Verein, Konkurrenz, Teilnehmer, Spiel, Teilnehmer.konkurrenz.get_through_model(), Chat, ChatMessage, DoppelSpiel, DoppelPaarung])
    print("Database initialized and tables created.")