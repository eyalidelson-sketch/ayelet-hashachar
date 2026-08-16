"""
Adapter לסריקת Airbnb דרך Apify.

ברירת המחדל היא האקטור tri_angle/airbnb-scraper (נכון לבדיקה מ-2026-08):
- Input: locationQueries (array), checkIn, checkOut (YYYY-MM-DD), adults, currency, maxResults...
- Output לדוגמה: title, url, thumbnail, roomType, subDescription.items,
  rating: {guestSatisfaction (0-5), reviewsCount},
  price: {amount ("$107"), breakDown: {totalBeforeTaxes: {price: "$302"}}},
  amenities: [{title, values: [{title, available}]}], highlights: [{title}]

ניתן לעקוף את האקטור ע"י שינוי APIFY_AIRBNB_ACTOR_ID ב-.env - יש לוודא שהשדות
ב-_parse_item תואמים לפלט של האקטור שנבחר.
"""
import logging
import re
from typing import List, Optional

from apify_client import ApifyClient

import config
from models import Listing, SearchRequest
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

DEFAULT_ACTOR_ID = "tri_angle/airbnb-scraper"
_PRICE_RE = re.compile(r"[\d.]+")


def _parse_price(value) -> Optional[float]:
    """מחלץ מספר מתוך מחרוזת מחיר כמו '$302' או '1,234.5'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace(",", "")
    match = _PRICE_RE.search(cleaned)
    return float(match.group()) if match else None


class AirbnbApifyScraper(BaseScraper):
    source_name = "airbnb"

    def __init__(self, api_token: Optional[str] = None, actor_id: Optional[str] = None, max_results: int = 30):
        self.api_token = api_token or config.APIFY_API_TOKEN
        self.actor_id = actor_id or config.APIFY_AIRBNB_ACTOR_ID or DEFAULT_ACTOR_ID
        self.max_results = max_results
        if not self.api_token:
            raise ValueError("חסר APIFY_API_TOKEN בקובץ .env")
        self.client = ApifyClient(self.api_token)

    def _build_run_input(self, request: SearchRequest) -> dict:
        run_input = {
            "locationQueries": [request.destination],
            "checkIn": request.check_in.isoformat(),
            "checkOut": request.check_out.isoformat(),
            "adults": request.guests,
            "currency": "USD",
            "maxResults": self.max_results,
        }
        # לאיירבנב אין מושג ישיר של "כמות חדרים שהוזמנו" (זה נכס שלם, לא חדרים
        # בודדים) - הפרוקסי הסביר ביותר ל"אני צריך N חדרים" הוא לדרוש נכס עם
        # לפחות N חדרי שינה (minBedrooms).
        if request.rooms and request.rooms > 1:
            run_input["minBedrooms"] = request.rooms
        return run_input

    def search(self, request: SearchRequest) -> List[Listing]:
        run_input = self._build_run_input(request)
        try:
            run = self.client.actor(self.actor_id).call(run_input=run_input)
        except Exception as exc:
            logger.error("Airbnb Apify run failed: %s", exc)
            raise

        dataset_id = run["defaultDatasetId"] if isinstance(run, dict) else run.get("defaultDatasetId", getattr(run, "default_dataset_id", None)) if hasattr(run, "get") else getattr(run, "default_dataset_id", None) if run else None
        if not dataset_id:
            return []

        nights = max(request.nights, 1)
        listings: List[Listing] = []
        for item in self.client.dataset(dataset_id).iterate_items():
            listing = self._parse_item(item, nights)
            if listing:
                listings.append(listing)
        return listings

    def _parse_item(self, item: dict, nights: int) -> Optional[Listing]:
        try:
            title = item.get("title")
            url = item.get("url")
            if not title or not url:
                return None

            price_info = item.get("price") or {}
            breakdown = price_info.get("breakDown") or {}
            total = None
            if breakdown.get("totalBeforeTaxes"):
                total = _parse_price(breakdown["totalBeforeTaxes"].get("price"))
            if total is None:
                per_night = _parse_price(price_info.get("amount"))
                total = per_night * nights if per_night is not None else None
            if total is None:
                return None

            rating_info = item.get("rating") or {}
            rating_5 = rating_info.get("guestSatisfaction")
            rating_10 = round(float(rating_5) * 2, 1) if rating_5 is not None else 0.0
            review_count = int(rating_info.get("reviewsCount") or 0)

            image = item.get("thumbnail") or ""

            amenities = set()
            for group in item.get("amenities") or []:
                for value in group.get("values") or []:
                    if value.get("available"):
                        val_title = (value.get("title") or "").strip().lower()
                        if val_title:
                            amenities.add(val_title)
            for highlight in item.get("highlights") or []:
                h_title = (highlight.get("title") or "").strip().lower()
                if h_title:
                    amenities.add(h_title)
            room_type = item.get("roomType")
            if room_type:
                amenities.add(str(room_type).strip().lower())
            for sub_item in (item.get("subDescription") or {}).get("items") or []:
                if sub_item:
                    amenities.add(str(sub_item).strip().lower())

            return Listing(
                source=self.source_name,
                title=title,
                image_url=image,
                price_total=total,
                currency=price_info.get("currency") or "USD",
                rating=rating_10,
                review_count=review_count,
                booking_url=url,
                amenities=sorted(amenities),
                extra={"room_type": room_type},
            )
        except Exception as exc:
            logger.warning("Skipping malformed Airbnb item: %s", exc)
            return None
