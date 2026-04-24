import config


def is_admin(chat_id: int) -> bool:
    return chat_id in config.ADMIN_CHAT_IDS


def is_allowed(chat_id: int) -> bool:
    return chat_id in config.ALLOWED_CHAT_IDS

