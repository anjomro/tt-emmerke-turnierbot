from datetime import datetime
from typing import Dict
import os
import httpx
from bs4 import BeautifulSoup
from telegram.ext import ContextTypes
from thefuzz import process

from models import Konkurrenz, Teilnehmer, Verein, Spiel
from notify import notify_new_spiel, notify_game_result


base_url = os.getenv("BASE_URL", "https://www.httv.de/mktt_getPage.php?url=012/48._internationales_sandershaeuser_tischtennis-pfingstturnier_2025-06-06/")
#base_url = "https://www.httv.de/mktt_getPage.php?url=012/47._internationales_sandershaeuser_tischtennis-pfingstturnier_2024-05-17/"
#base_url = "https://www.httv.de/mktt_getPage.php?url=012/48._internationales_sandershaeuser_tischtennis-pfingstturnier_2025-06-06/"

active_tables_url = f"{base_url}active_tables.html"
konkurrenzen_url = f"{base_url}index.html"
teilnehmer_url = f"{base_url}starters.html"


async def fetch_url(url) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        if response.status_code == 200:
            return response.text
        else:
            raise Exception(f"Failed to fetch URL: {url} with status code {response.status_code}")

def html_to_unicode(text: str) -> str:
    """
    Convert HTML entities such as &uuml; to their unicode equivalents.
    """
    return text.replace('&uuml;', 'ü').replace('&ouml;', 'ö').replace('&auml;', 'ä').replace('&szlig;', 'ß')


async def get_konkurrenz_by_name(name: str) -> Konkurrenz:
    """
    Fetch a Konkurrenz database object by its name.
    If no exact match found, find Konkurrenz where given name starts with the name in the database.
    E.g. Database has "Herren S (offen)" and we search for "Herren S (offen) Einzel 2024"
    """
    try:
        konkurrenz = Konkurrenz.get(Konkurrenz.name == name)
        return konkurrenz
    except Konkurrenz.DoesNotExist:
        all_konkurrenzen_names = [k.name for k in Konkurrenz.select()]
        matching_konkurrenzen = [k for k in all_konkurrenzen_names if name.startswith(k)]
        if matching_konkurrenzen:
            # Return the first match
            return Konkurrenz.get(Konkurrenz.name == matching_konkurrenzen[0])
        else:
            raise ValueError(f"No competition found with name: {name}")

async def get_teilnehmer_by_name(name: str) -> Teilnehmer:
    """
    Find a teilnehmer by "Nachname, Vorname" format.
    """
    try:
        # Split the name into last and first name
        if name.count(', ') != 1:
            raise ValueError(f"Invalid name format: {name}. Expected format is 'Nachname, Vorname'.")
        last_name, first_name = name.split(', ')
        last_name = last_name.strip()
        first_name = first_name.strip()
        teilnehmer = Teilnehmer.get(
            (Teilnehmer.nachname == last_name) & (Teilnehmer.vorname == first_name)
        )
        return teilnehmer
    except Teilnehmer.DoesNotExist:
        raise ValueError(f"No participant found with name: {name}")
    except ValueError:
        raise ValueError(f"Invalid name format: {name}. Expected format is 'Nachname, Vorname'.")


async def fetch_active_tables(context: ContextTypes.DEFAULT_TYPE):
    '''
    Parse active table
    <TABLE class='mktt_active_tables'>
        <TR><TH class='mktt_at_tisch'>Tisch</TH><TH class='mktt_at_spieler'>Spieler 1</TH><TH class='mktt_at_spieler'>Spieler 2</TH><TH class='mktt_at_klasse'>Klasse</TH><TH class='mktt_at_matchtyp'>Typ</TH></TR>
        <TR><TD>15</TD><TD>Peter Müller</TD><TD>Test, Thomas</TD><TD><A href='./type_1.html'>Herren S (offen) Einzel</A></TD><TD>Finale</TD></TR>
    </TABLE>
        <BR /><BR /><BR /><A name='anfang' class='mktt_gruppen_ueberschrift'>Beendete Spiele der letzten 30 min</A><BR /><BR />
    <TABLE class='mktt_group_single_results'>
        <TR><TH class='mktt_gsr_uhrzeit'>Uhrzeit</TH><TH class='mktt_gsr_spieler'>Spieler 1</TH><TH class='mktt_gsr_spieler'>Spieler 2</TH><TH class='mktt_gsr_einzelsaetze'>Klasse</TH><TH class='mktt_gsr_saetze'>Ergebnis</TH></TR>
        <TR><TD>23:37</TD><TD>Zeimys, Kestutis</TD><TD>Reindl, Niclas</TD><TD><A href='./type_1.html'>Herren S (offen) Einzel</A></TD><TD><SPAN class='mktt_ko_ergebnisse' title='11 : 6
        11 : 6
        11 : 8'>3 : 0</SPAN></TD></TR>
    </TABLE>
    '''
    html_content = await fetch_url(active_tables_url)
    soup = BeautifulSoup(html_content, 'html.parser')

    active_tables = []

    # Parse active tables
    active_table = soup.find('table', class_='mktt_active_tables')
    #headers = ["Tisch", "Spieler 1", "Spieler 2", "Klasse", "Typ"]
    if active_table:
        rows = active_table.find_all('tr')[1:]  # Skip header row
        for row in rows:
            cols = row.find_all('td')
            if len(cols) == 5:  # Ensure we have the right number of columns
                try:
                    tisch = int(cols[0].text.strip())
                except ValueError:
                    print(f"Invalid table number: {row.text}")
                    continue
                spieler1 = html_to_unicode(cols[1].text.strip())
                spieler2 = html_to_unicode(cols[2].text.strip())
                klasse_link = cols[3].find('a').get('href') if cols[3].find('a') else None
                klasse = html_to_unicode(cols[3].text.strip())
                typ = html_to_unicode(cols[4].text.strip())
                # Find konkurrenz by link
                konkurrenz = None
                if klasse_link:
                    try:
                        konkurrenz = Konkurrenz.get(Konkurrenz.link == klasse_link)
                    except Konkurrenz.DoesNotExist:
                        print(f"Konkurrenz not found for link: {klasse_link}")
                if not konkurrenz:
                    try:
                        konkurrenz = get_konkurrenz_by_name(klasse)
                    except ValueError as e:
                        print(f"Error finding competition for klasse {klasse}: {e}")
                try:
                    spieler1_obj = await get_teilnehmer_by_name(spieler1)
                    spieler2_obj = await get_teilnehmer_by_name(spieler2)
                except ValueError as e:
                    print(f"Error finding participants: {e}")
                    continue

                # Find or create Spiel object
                try:
                    spiel = Spiel.get(
                        (Spiel.tisch == tisch) &
                        (Spiel.spieler1 == spieler1_obj) &
                        (Spiel.spieler2 == spieler2_obj) &
                        (Spiel.konkurrenz == konkurrenz)
                    )
                    # print(f"Found existing game: {spiel}")
                except Spiel.DoesNotExist:
                    spiel = Spiel.create(
                        tisch=tisch,
                        spieler1=spieler1_obj,
                        spieler2=spieler2_obj,
                        konkurrenz=konkurrenz,
                        typ=typ
                    )
                    print(f"Created new game: {spiel}")
                # Notify about the new game
                try:
                    await notify_new_spiel(spiel)
                except Exception as e:
                    print(f"---- Error notifying about new game {spiel}: {e}")
                    continue

                table_data = {
                    "Tisch": cols[0].text.strip(),
                    "Spieler 1": cols[1].text.strip(),
                    "Spieler 2": cols[2].text.strip(),
                    "Klasse": cols[3].text.strip(),
                    "Typ": cols[4].text.strip()
                }
                active_tables.append(table_data)
    else:
        print("No active tables found.")
    ended_games = []

    # Parse ended games
    ended_games_section = soup.find('table', class_='mktt_group_single_results')
    if ended_games_section:
        rows = ended_games_section.find_all('tr')[1:]  # Skip header row
        for row in rows:
            cols = row.find_all('td')
            if len(cols) == 5:  # Ensure we have the right number of columns
                spieler1 = html_to_unicode(cols[1].text.strip())
                spieler2 = html_to_unicode(cols[2].text.strip())
                klasse = html_to_unicode(cols[3].text.strip())
                klasse_link = cols[3].find('a').get('href') if cols[3].find('a') else None
                typ = html_to_unicode(cols[4].text.strip())
                end_game_time = datetime.strptime(cols[0].text.strip(), '%H:%M').time()
                result_sets = html_to_unicode(cols[4].text.strip())
                # Parse result points from title attribute
                # Example: <SPAN class='mktt_ko_ergebnisse' title='11 : 6
                #         11 : 6
                #         11 : 8'>3 : 0</SPAN>
                result_points = html_to_unicode(cols[4].find('span', class_='mktt_ko_ergebnisse').get('title', '')).strip()
                # Find konkurrenz by link
                konkurrenz = None
                if klasse_link:
                    try:
                        konkurrenz = Konkurrenz.get(Konkurrenz.link == klasse_link)
                    except Konkurrenz.DoesNotExist:
                        print(f"Konkurrenz not found for link: {klasse_link}")
                if not konkurrenz:
                    try:
                        konkurrenz = get_konkurrenz_by_name(klasse)
                    except ValueError as e:
                        print(f"Error finding competition for klasse {klasse}: {e}")
                        continue
                try:
                    spieler1_obj = await get_teilnehmer_by_name(spieler1)
                    spieler2_obj = await get_teilnehmer_by_name(spieler2)
                except ValueError as e:
                    print(f"Error finding participants: {e}")
                    continue
                try:
                    konkurrenz = get_konkurrenz_by_name(klasse)
                except ValueError as e:
                    print(f"Error finding competition for klasse {klasse}: {e}")

                try:
                    spiele = Spiel.select(
                        (Spiel.spieler1 == spieler1_obj) &
                        (Spiel.spieler2 == spieler2_obj) &
                        (Spiel.konkurrenz == konkurrenz)
                    )
                    if spiele.exists():
                        spiel = spiele[0]
                    else:
                        raise Spiel.DoesNotExist
                    # print(f"Found existing game: {spiel}")
                except Spiel.DoesNotExist:
                    spiel = Spiel.create(
                        tisch=0,
                        spieler1=spieler1_obj,
                        spieler2=spieler2_obj,
                        konkurrenz=konkurrenz,
                        typ=typ
                    )
                    print(f"Found new ended game: {spiel}")
                if not spiel.end:
                    # Set end datetime
                    spiel.end = datetime.combine(datetime.today(), end_game_time)
                    spiel.ergebnis_satz = result_sets
                    spiel.ergebnis_punkte = result_points
                    spiel.save()
                    print(f"Saved ended game: {spiel.spieler1.nachname} - {spiel.spieler2.nachname} in {spiel.konkurrenz.name} with result {spiel.ergebnis_satz}")

    else:
        print("No ended games found.")


    return active_table, ended_games



async def fetch_konkurrenzen():
    try:
        html_content = await fetch_url(konkurrenzen_url)
    except Exception as e:
        print(f"Error fetching competitions: {e}")
        return
    soup = BeautifulSoup(html_content, 'html.parser')
    x=5
    # Get class class='mktt_nav_link'
    konkurrenzen = soup.find_all('a', class_='mktt_nav_link')
    for konkurrenz in konkurrenzen:
        name = html_to_unicode(konkurrenz.text.strip())
        href = konkurrenz.get('href')
        # Check if same competition already exists, if so, update the link if different
        if Konkurrenz.select().where(Konkurrenz.name == name).exists():
            existing_konkurrenz = Konkurrenz.get(Konkurrenz.name == name)
            if existing_konkurrenz.link != href:
                existing_konkurrenz.link = href
                existing_konkurrenz.save()
        else:
            # Create new competition
            Konkurrenz.create(name=name, link=href)
            print(f"Added competition: {name} with link {href}")


async def fetch_teilnehmer():
    try:
        html_content = await fetch_url(teilnehmer_url)
    except Exception as e:
        print(f"Error fetching participants: {e}")
        return
    soup = BeautifulSoup(html_content, 'html.parser')
    # Find all konkurrenzen class='mktt_grouptype'
    konkurrenzen = soup.find_all('span', class_='mktt_grouptype')
    for konkurrenz in konkurrenzen:
        name = html_to_unicode(konkurrenz.text.strip())
        name = name.split(":")[0].strip()  # Remove any additional text after the colon
        # Remove "Einzel" or "Doppel" from the name if present
        name = name.replace(" Einzel", "").replace("Doppelkonkurrenz", "konkurrenz").strip()
        # Get the corresponding Konkurrenz object
        try:
            konkurrenz_obj = await get_konkurrenz_by_name(name)
        except ValueError as e:
            print(e)
            continue

        teilnehmer_table = konkurrenz.find_next('table')
        teilnehmer_rows = teilnehmer_table.find_all("tr")[1:]

        for row in teilnehmer_rows:
            # infos: id, nachname, vorname, verein, qttr
            infos = row.find_all("td")
            if len(infos) != 5:
                print(f"Unexpected number of columns in row: {row} {row.text}")
                continue
            id_exists = infos[0].text.strip().isdigit()
            if id_exists:
                id = int(infos[0].text.strip())
            nachname = html_to_unicode(infos[1].text.strip())
            vorname = html_to_unicode(infos[2].text.strip())
            verein_name = html_to_unicode(infos[3].text.strip())
            qttr = int(infos[4].text.strip())
            if not id_exists:
                # Try to find existing participant by name, verein and qttr
                try:
                    teilnehmer = Teilnehmer.get(
                        (Teilnehmer.vorname == vorname) &
                        (Teilnehmer.nachname == nachname) &
                        (Teilnehmer.qttr == qttr)
                    )
                    id = teilnehmer.id  # Use existing ID
                except Teilnehmer.DoesNotExist:
                    # If no existing participant found, set id to not used value starting from 1000000
                    id = 1000
                    found_id = True
                    while found_id:
                        try:
                            Teilnehmer.get(Teilnehmer.id == id)
                            id += 1  # Increment ID until a free one is found
                        except Teilnehmer.DoesNotExist:
                            found_id = False
            # Check if teilnehmer already exists
            try:
                teilnehmer = Teilnehmer.get(Teilnehmer.id == id)
                print(f"Matched participant: {teilnehmer}")
            except Teilnehmer.DoesNotExist:
                # Create new participant
                verein, created = Verein.get_or_create(name=verein_name)
                teilnehmer = Teilnehmer.create(
                    id=id,
                    vorname=vorname,
                    nachname=nachname,
                    qttr=qttr,
                    verein=verein
                )
                print(f"Added participant: {teilnehmer}")
            # Check if the participant is already linked to the competition
            connection_exists = len(Teilnehmer.konkurrenz.get_through_model().select().where(
                Teilnehmer.konkurrenz.get_through_model().teilnehmer == teilnehmer,
                Teilnehmer.konkurrenz.get_through_model().konkurrenz == konkurrenz_obj
            )) > 0
            if not connection_exists:
                teilnehmer.konkurrenz.add(konkurrenz_obj)
                print(f"Linked participant {teilnehmer} to competition {konkurrenz_obj}")
            else:
                print(f"Participant {teilnehmer} already linked to competition {konkurrenz_obj}")
        print(f"Finished fetching participants for {name}")
    print("Finished fetching all participants.")