
# VIPMUSIC/utils/database/__init__.py
# Centralized database import layer — supports both old and new modules

# --- Import core DB helpers (legacy) ---
# These are usually defined in other files like sudo.py, cmode.py, etc.
# The try/except ensures the bot won't crash if one file is missing.
try:
    from VIPMUSIC.utils.database.sudo import get_sudoers
except ImportError:
    get_sudoers = None

try:
    from VIPMUSIC.utils.database.cmode import get_cmode
except ImportError:
    get_cmode = None

try:
    from VIPMUSIC.utils.database.mongo import mongodb
except ImportError:
    mongodb = None


# --- Import new reaction database ---
try:
    from VIPMUSIC.utils.database.reactiondb import get_reaction_status, set_reaction_status
except ImportError:
    def get_reaction_status(chat_id: int) -> bool:
        return True

    def set_reaction_status(chat_id: int, status: bool):
        pass


# --- Export everything cleanly ---
__all__ = [
    "get_sudoers",
    "get_cmode",
    "mongodb",
    "get_reaction_status",
    "set_reaction_status",
]
