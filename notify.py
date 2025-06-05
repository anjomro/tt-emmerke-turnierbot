from models import Spiel





async def notify_new_spiel(spiel: Spiel):
    """
    Notify about a new game.
    This function should be called whenever a new game is created.
    """
    # Here you would implement the logic to notify users, e.g., via Telegram or another service.
    print(f"New game created: {spiel.spieler1} vs {spiel.spieler2} in {spiel.konkurrenz.name} at Tisch {spiel.tisch}.")
    # Example: await send_telegram_message(f"New game: {spiel.spieler1} vs {spiel.spieler2} in {spiel.konkurrenz.name} at Tisch {spiel.tisch}.")


async def notify_game_result(spiel: Spiel):
    """
    Notify about the result of a game.
    This function should be called whenever a game result is updated.
    """
    pass