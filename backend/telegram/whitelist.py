from typing import List
from backend.config import ALLOWED_USER_IDS

def is_whitelisted(user_id: int) -> bool:
    return str(user_id) in ALLOWED_USER_IDS or user_id in ALLOWED_USER_IDS
