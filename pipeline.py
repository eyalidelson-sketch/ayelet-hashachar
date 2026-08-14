"""
אורקסטרציה: מריץ את שרשרת החיפוש (סריקה -> סינון -> דירוג) עבור בקשת חיפוש
בודדת, עם callback אופציונלי לעדכוני התקדמות (לשימוש ב-Streamlit) ותמיכה
במצב "מחיר/איכות" שנבחר ע"י המשתמש (balanced/cheaper/better).
"""
import logging
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import config
from models import Listing, RankedListing, SearchRequest
from ranking import filter_listings, get_weights_for_mode, rank_listings
from scrapers.airbnb_apify import AirbnbApifyScraper
from scrapers.booking_apify import BookingApifyScraper
from scrapers.expedia_apify import ExpediaApifyScraper

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable[[str, float], None]]

# (source_name, factory שמייצר scraper מוכן, notify label, progress fraction)
# כל scraper מקבל שם פרמטר שונה למגבלת התוצאות (max_items / max_results) -
# הפונקציות הקטנות למטה מאחדות את זה מאחורי ממשק זהה: factory() -> BaseScraper.
_SOURCES = [
    ("Booking.com", lambda: BookingApifyScraper(max_items=config.MAX_RESULTS_PER_SOURCE),
     "סורק את Booking.com...", 0.12),
    ("Airbnb", lambda: AirbnbApifyScraper(max_results=config.MAX_RESULTS_PER_SOURCE),
     "סורק את Airbnb...", 0.32),
    ("Expedia", lambda: ExpediaApifyScraper(max_items=config.MAX_RESULTS_PER_SOURCE),
     "סורק את Expedia...", 0.52),
]


@dataclass
class PipelineResult:
    ranked: List[RankedListing] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    total_scraped: int = 0
    mode: str = "balanced"


def run_pipeline(
    request: SearchRequest, mode: str = "balanced", on_progress: ProgressCallback = None
) -> PipelineResult:
    def notify(message: str, fraction: float) -> None:
        if on_progress:
            on_progress(message, fraction)

    errors: List[str] = []
    all_listings: List[Listing] = []

    for label, make_scraper, message, fraction in _SOURCES:
        notify(message, fraction)
        try:
            scraper = make_scraper()
            all_listings.extend(scraper.search(request))
        except Exception as exc:
            logger.exception("%s scraping failed", label)
            errors.append(f"סריקת {label} נכשלה: {exc}")

    if not all_listings:
        errors.append("לא נמצאו תוצאות מאף מקור. בדקו את פרטי החיבור ל-Apify או נסו יעד/תאריכים אחרים.")
        return PipelineResult(ranked=[], errors=errors, total_scraped=0, mode=mode)

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
    return PipelineResult(ranked=ranked, errors=errors, total_scraped=len(all_listings), mode=mode)
