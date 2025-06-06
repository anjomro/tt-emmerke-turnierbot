def ttr_to_emoji(ttr: int):
    emoji = [
        "🥚",  # 0
        "🐣",
        "🐥",
        "🐔",
        "🐿️",
        "🦥",  # 5
        "🐢",
        "🦝",
        "🦨",
        "🦊",
        "🐺",  # 10
        "🦘",
        "🐗",
        "🐅",
        "🦁",
        "🐻",  # 15
        "🐻‍❄️",
        "🐊",
        "🦖",
        "🦛",
        "🐉",  # 20
    ]
    if ttr == -1 or ttr == 0:
        # TTR -1 means no TTR is available
        # Use question mark to indicate this
        return "❓"

    # This selects the emoji based on the TTR
    # Have fun figuring out how this works :P
    index_ttr = max(ttr - 1000, 0)
    return emoji[min(index_ttr // 50, len(emoji) - 1)]

def ttr_emoji_explanation() -> str:
    ''' Emoji List with TTR
    Format:
    0:     ❓
    <1000: 🥚
    <1050: 🐣
    ...
    '''
    # Automatically generate list of emojis using function
    emoji_list = "0:     \n"
    for i in range(999, 2000, 50):
        emoji_list += f"\<\= {i}: {ttr_to_emoji(i)}\n"
    emoji_list += f"\>\= 2000: {ttr_to_emoji(2000)}\n"
    return emoji_list.strip()