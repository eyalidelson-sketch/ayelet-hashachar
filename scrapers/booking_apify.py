"""
Adapter לסריקת Booking.com דרך Apify.

ברירת המחדל היא האקטור voyager/booking-scraper (נכון לבדיקה מ-2026-08):
- Input: search, checkIn, checkOut (YYYY-MM-DD), adults, rooms, currency, maxItems, sortBy...
- Output לדוגמה: name, url, price, currency, rating (0-10), reviews, image, stars, type,
  rooms: [{price, currency, features: [...], bedType, roomType, available}], breakfast

ניתן לעקוף את האקטור ע"י שינוי APIFY_BOOKING_ACTOR_ID ב-.env אם בוחרים אקטור אחר -
פשוט יש לוודא שהשדות ב-_parse_item תואמים לפלט של האקטור שנבחר.
"""
import logging
from typing import List, Optional

from apify_client import ApifyClient

import config
from models import Listing, SearchRequest
from scrapers.base import BaseScraper, get_run_field

logger = logging.getLogger(__name__)

DEFAULT_ACTOR_ID = "voyager/booking-scraper"


class BookingApifyScraper(BaseScraper):
    source_name = "booking"

    def __init__(self, api_token: Optional[str] = None, actor_id: Optional[str] = None, max_items: int = 30):
        self.api_token = api_token or config.APIFY_API_TOKEN
        self.actor_id = actor_id or config.APIFY_BOOKING_ACTOR_ID or DEFAULT_ACTOR_ID
        self.max_items = max_items
        if not self.api_token:
            raise ValueError("חסר APIFY_API_TOKEN בקובץ .env")
        self.client = ApifyClient(self.api_token)

    def _build_run_input(self, request: SearchRequest) -> dict:
        return {
            "search": request.destination,
            "checkIn": request.check_in.isoformat(),
            "checkOut": request.check_out.isoformat(),
            "adults": request.guests,
            "rooms": request.rooms,
            "currency": "USD",
            "maxItems": self.max_items,
            "sortBy": "review_score_and_price",
        }

    def search(self, request: SearchRequest) -> List[Listing]:
        run_input = self._build_run_input(request)
        try:
            run = self.client.actor(self.actor_id).call(run_input=run_input)
        except Exception as exc:
            logger.error("Booking Apify run failed: %s", exc)
            raise

        # run יכול להיות אובייקט Run (עם run.default_dataset_id) או dict גולמי
        # (עם run["defaultDatasetId"]) - תלוי בגרסת apify-client. get_run_field
        # תומך בשני המצבים בלי לקרוס עם AttributeError/KeyError.
        dataset_id = get_run_field(run, "default_dataset_id", "defaultDatasetId")
        if not dataset_id:
            logger.warning("Booking Apify run returned no defaultDatasetId: %r", run)
            return []

        listings: List[Listing] = []
        for item in self.client.dataset(dataset_id).iterate_items():
            listing = self._parse_item(item)
            if listing:
                listings.append(listing)
        return listings

    def _parse_item(self, item: dict) -> Optional[Listing]:
        try:
            name = item.get("name") or item.get("title")
            url = item.get("url")
            if not name or not url:
                return None

            price = item.get("price")
            currency = item.get("currency") or "USD"
            rooms = item.get("rooms") or []
            if price is None:
                prices = [r.get("price") for r in rooms if r.get("price") is not None]
                price = min(prices) if prices else None
            if price is None:
                return None

            image = item.get("image")
            if not image:
                images = item.get("images") or []
                image = images[0] if images else ""

            rating_raw = item.get("rating")
            rating = float(rating_raw) if rating_raw is not None else 0.0
            review_count = int(item.get("reviews") or 0)

            amenities = set()
            for room in rooms:
                for feat in room.get("features") or []:
                    if feat:
                        amenities.add(str(feat).strip().lower())
                bed_type = room.get("bedType")
                if bed_type:
                    amenities.add(str(bed_type).strip().lower())
                room_type = room.get("roomType")
                if room_type:
                    amenities.add(str(room_type).strip().lower())
            if item.get("breakfast"):
                amenities.add("breakfast included")

            return Listing(
                source=self.source_name,
                title=name,
                image_url=image or "",
                price_total=float(price),
                currency=currency,
                rating=rating,
                review_count=review_count,
                booking_url=url,
                amenities=sorted(amenities),
                extra={"stars": item.get("stars"), "type": item.get("type")},
            )
        except Exception as exc:
            logger.warning("Skipping malformed Booking item: %s", exc)
            return None
