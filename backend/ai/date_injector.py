from datetime import datetime, timezone

def get_date_prefix() -> str:
    return datetime.now(timezone.utc).strftime("Today's date: %B %d, %Y")
