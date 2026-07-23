from emoji import CUSTOM_EMOJIS

def emoji(key):
    return CUSTOM_EMOJIS.get(key, "")

def emoji_tag(key, fallback=""):
    eid = CUSTOM_EMOJIS.get(key)
    if eid:
        return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'
    return fallback

def get_emoji(key, fallback=""):
    return CUSTOM_EMOJIS.get(key, fallback)