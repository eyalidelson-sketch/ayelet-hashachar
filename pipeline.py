
"""
אורקסטרציה: מריץ את שרשרת החיפוש (סריקה -> סינון -> דירוג) עבור בקשת חיפוש
בודדת, עם callback אופציונלי לעדכוני התקדמות (לשימוש ב-Streamlit) ותמיכה
במצב "מחיר/איכות" שנבחר ע"י המשתמש (balanced/cheaper/better).
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import config
from models import Listing, RankedListing, SearchRequest
from ranking import filter_listings, get_weights_for_mode, rank_listings
from scrapers.airbnb_apify import AirbnbApifyScraper
from scrapers.booking_apify import BookingApifyScraper
from scrapers.expedia_apify import ExpediaApifyScraper

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable[[str, float], None]]

_SOURCES = [
    ("Booking.com", lambda: BookingApifyScraper(max_items=config.MAX_RESULTS_PER_SOURCE)),
    ("Airbnb", lambda: AirbnbApifyScraper(max_results=config.MAX_RESULTS_PER_SOURCE)),
    ("Expedia", lambda: ExpediaApifyScraper(max_items=config.MAX_RESULTS_PER_SOURCE)),
]


@dataclass
class PipelineResult:
    ranked: List[RankedListing] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    # פילוח שקוף לצורכי דיבוג: כמה תוצאות התקבלו מכל מקור בנפרד, כדי שאפשר
    # יהיה להבחין בין "מקור X נכשל עם שגיאה" ל"מקור X רץ בהצלחה אבל החזיר 0
    # תוצאות" (למשל בגלל actor ID שגוי, פרמטר קלט לא תקין, או פשוט אין זמינות) -
    # שני מצבים שקודם לכן נראו זהים למשתמש ("לא נמצאו תוצאות").
    source_counts: Dict[str, int] = field(default_factory=dict)
    total_scraped: int = 0
    mode: str = "balanced"


def _fetch_source(source_tuple, request: SearchRequest):
    label, make_scraper = source_tuple
    scraper = make_scraper()
    results = scraper.search(request)
    return label, results


def run_pipeline(
    request: SearchRequest, mode: str = "balanced", on_progress: ProgressCallback = None
) -> PipelineResult:
    def notify(message: str, fraction: float) -> None:
        if on_progress:
            on_progress(message, fraction)

    errors: List[str] = []
    source_counts: Dict[str, int] = {}
    all_listings: List[Listing] = []

    if not config.APIFY_API_TOKEN:
        errors.append(
            "APIFY_API_TOKEN חסר. יש להגדיר אותו תחת Settings → Secrets באפליקציית "
            "Streamlit Cloud (או בקובץ .env בהרצה מקומית) ולבצע Reboot לאפליקציה."
        )
        return PipelineResult(ranked=[], errors=errors, source_counts=source_counts, total_scraped=0, mode=mode)

    notify("מריץ חיפוש מקבילי ב-Booking, Airbnb ו-Expedia...", 0.15)

    with ThreadPoolExecutor(max_workers=len(_SOURCES)) as executor:
        future_to_label = {
            executor.submit(_fetch_source, src, request): src[0]
            for src in _SOURCES
        }

        completed_count = 0
        for future in as_completed(future_to_label):
            label = future_to_label[future]
            completed_count += 1
            try:
                _, listings = future.result()
                all_listings.extend(listings)
                source_counts[label] = len(listings)
                notify(f"סיום סריקת {label} ({completed_count}/{len(_SOURCES)})", 0.15 + (completed_count * 0.15))
                if not listings:
                    errors.append(
                        f"{label}: הסריקה רצה בהצלחה אך החזירה 0 תוצאות "
                        "(ייתכן actor ID שגוי, פרמטרי חיפוש לא תואמים לסכמת ה-Actor, "
                        "או פשוט אין זמינות ליעד/תאריכים שנבחרו)."
                    )
            except Exception as exc:
                logger.exception("%s scraping failed", label)
                source_counts[label] = 0
                errors.append(f"סריקת {label} נכשלה: {exc}")

    if not all_listings:
        errors.append("לא נמצאו תוצאות מאף מקור. בדקו את פרטי החיבור ל-Apify או נסו יעד/תאריכים אחרים.")
        return PipelineResult(ranked=[], errors=errors, source_counts=source_counts, total_scraped=0, mode=mode)

    notify("מסנן לפי הדרישות שנבחרו...", 0.68)
    filtered = filter_listings(all_listings, request.filters)
    if not filtered and any(request.filters.as_dict().values()):
        errors.append(
            "לא נמצאו תוצאות שעונות על כל הסינונים שנבחרו. מוצגות התוצאות הטובות ביותר ללא הסינונים."
        )
        filtered = all_listings

    notify("מחשב ציון תמורה למחיר...", 0.85)
    weights = get_weights_for_mode(mode)
    ranked = rank_listings(filtered, top_n=3, **weights)
    if not ranked:
        errors.append("לא נותרו תוצאות לדירוג.")

    notify("הושלם!", 1.0)
    return PipelineResult(
        ranked=ranked, errors=errors, source_counts=source_counts,
        total_scraped=len(all_listings), mode=mode,
    )
