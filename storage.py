"""
שמירת בקשות חיפוש והיסטוריית תוצאות כ-JSON.

save_search_request  - שמירת גולמית של בקשה בלבד (נקודת מסירה לפייפליין, שלב 1 המקורי).
save_search_history   - שמירת בקשה + התוצאות המדורגות + מצב מחיר/איכות שנבחר, לשימוש
                        בסרגל הצד "היסטוריית חיפושים" באפליקציה.
"""
import json
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from config import HISTORY_DIR, SEARCHES_DIR
from models import Listing, RankedListing, SearchRequest


def save_search_request(request: SearchRequest) -> Path:
    """שומר בקשת חיפוש גולמית לקובץ JSON ומחזיר את הנתיב שנוצר."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{uuid.uuid4().hex[:8]}.json"
    filepath = SEARCHES_DIR / filename

    payload = request.to_dict()
    payload["created_at"] = datetime.now().isoformat()
    payload["status"] = "pending"

    filepath.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return filepath


def load_search_request(filepath: Path) -> Optional[dict]:
    if not filepath.exists():
        return None
    return json.loads(filepath.read_text(encoding="utf-8"))


def list_saved_searches() -> list:
    return sorted(SEARCHES_DIR.glob("*.json"), reverse=True)


def save_search_history(
    request: SearchRequest,
    ranked: List[RankedListing],
    errors: Optional[List[str]] = None,
    total_scraped: int = 0,
    mode: str = "balanced",
) -> Path:
    """שומר בקשה + תוצאות מדורגות + מצב מחיר/איכות, לשימוש בסרגל ה'היסטוריה'."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{uuid.uuid4().hex[:8]}.json"
    filepath = HISTORY_DIR / filename

    payload = {
        "created_at": datetime.now().isoformat(),
        "request": request.to_dict(),
        "total_scraped": total_scraped,
        "mode": mode,
        "errors": errors or [],
        "ranked": [
            {"score": item.score, "listing": asdict(item.listing)}
            for item in ranked
        ],
    }
    filepath.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return filepath


def list_search_history(limit: Optional[int] = None) -> List[Path]:
    """מחזיר את קבצי ההיסטוריה, מהחדש לישן."""
    files = sorted(HISTORY_DIR.glob("*.json"), reverse=True)
    return files[:limit] if limit else files


def load_search_history_entry(filepath: Path) -> Optional[dict]:
    """טוען פריט היסטוריה שמור, כולל שחזור אובייקטי RankedListing/Listing."""
    if not filepath.exists():
        return None
    raw = json.loads(filepath.read_text(encoding="utf-8"))

    ranked_objects = []
    for entry in raw.get("ranked", []):
        try:
            listing = Listing(**entry["listing"])
            ranked_objects.append(RankedListing(listing=listing, score=entry["score"]))
        except Exception:
            continue

    raw["ranked_objects"] = ranked_objects
    return raw
