# VIPMUSIC/utils/database/reactiondb.py
import os
import json

# Persistent JSON file path (relative to project root)
REACTION_DB_PATH = os.path.join("VIPMUSIC", "utils", "database", "reaction_status.json")

# In-memory cache (string keys)
reaction_status = {}

def load_reaction_data():
    global reaction_status
    try:
        if os.path.exists(REACTION_DB_PATH):
            with open(REACTION_DB_PATH, "r", encoding="utf-8") as f:
                reaction_status = json.load(f)
            print(f"[ReactionDB] Loaded {len(reaction_status)} chat statuses from JSON.")
        else:
            reaction_status = {}
            print("[ReactionDB] No saved reaction DB found — starting fresh.")
    except Exception as e:
        print(f"[ReactionDB] Error loading DB: {e}")
        reaction_status = {}

def save_reaction_data():
    try:
        os.makedirs(os.path.dirname(REACTION_DB_PATH), exist_ok=True)
        with open(REACTION_DB_PATH, "w", encoding="utf-8") as f:
            json.dump(reaction_status, f)
    except Exception as e:
        print(f"[ReactionDB] Failed to save DB: {e}")

# Async helpers for plugin usage
async def get_reaction_status(chat_id: int) -> bool:
    return reaction_status.get(str(chat_id), False)

async def set_reaction_status(chat_id: int, status: bool):
    reaction_status[str(chat_id)] = bool(status)
    save_reaction_data()
    print(f"[ReactionDB] Chat {chat_id} set to {'ON' if status else 'OFF'}")

# load on import
load_reaction_data()
