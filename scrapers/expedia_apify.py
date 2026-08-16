"""
Adapter לסריקת Expedia דרך Apify.

ברירת המחדל היא האקטור parseforge/expedia-scraper (נבדק מול Apify Store,
תיעוד עדכני ל-2026-08). שימו לב: זהו אקטור קהילתי חדש יחסית (~37 משתמשים,
עדיין ללא דירוגים) - מומלץ להריץ בדיקה ידנית קטנה לפני הסתמכות מלאה עליו.
אלטרנטיבות מתועדות בחנות שכדאי להשוות אליהן אם האקטור הזה לא עונה מספיק
טוב: jungle_synthesizer/expedia-scraper, khadinakbar/expedia-hotels-scraper,
haketa/expedia-scraper, crawlerbros/expedia-hotels-scraper - כולן ניתנות
להחלפה פשוטה דרך APIFY_EXPEDIA_ACTOR_ID ב-.env, בכפוף להתאמת _parse_item
לשדות הפלט שלהן.

לגבי Hotels.com: לא אותר אקטור עצמאי מתועד/אמין מספיק בבדיקה שנעשתה
(רוב הכיסוי ל-Hotels.com מגיע מאקטורים משולבים כמו
jungle_synthesizer/hotel-price-comparison-scraper שמכסה כמה אתרים יחד,
אך ה-schema המדויק שלו לא אומת) - לכן לא נוסף אקטור Hotels.com בשלב זה,
כדי לא "לנחש" קוד שעלול להישבר בפועל. אפשר להוסיף בהמשך באותה תבנית Adapter.

- Input: destination, checkIn, checkOut (YYYY-MM-DD), adults, children, rooms, maxItems...
- Output לדוגמה (שדות מתועדים): name, url, imageUrl, images, price, pricePerNight,
  totalPrice, currency, guestRating (0-10), guestReviewCount, starRating,
  amenities, badges, breakfastIncluded, freeCancellation, city, country...
"""
import logging
from typing import List, Optional

from apify_client import ApifyClient

import config
from models import Listing, SearchRequest
from scrapers.base import BaseScraper, get_run_field

logger = logging.getLogger(__name__)

DEFAULT_ACTOR_ID = "parseforge/expedia-scraper"


class ExpediaApifyScraper(BaseScraper):
    source_name = "expedia"

    def __init__(self, api_token: Optional[str] = None, actor_id: Optional[str] = None, max_items: int = 30):
        self.api_token = api_token or config.APIFY_API_TOKEN
        self.actor_id = actor_id or config.APIFY_EXPEDIA_ACTOR_ID or DEFAULT_ACTOR_ID
        self.max_items = max_items
        if not self.api_token:
            raise ValueError("חסר APIFY_API_TOKEN בקובץ .env")
        self.client = ApifyClient(self.api_token)

    def _build_run_input(self, request: SearchRequest) -> dict:
        return {
            "destination": request.destination,
            "checkIn": request.check_in.isoformat(),
            "checkOut": request.check_out.isoformat(),
            "adults": request.guests,
            "rooms": request.rooms,
            "maxItems": self.max_items,
            "sort": "GUEST_RATING",
        }

    def search(self, request: SearchRequest) -> List[Listing]:
        run_input = self._build_run_input(request)
        try:
            run = self.client.actor(self.actor_id).call(run_input=run_input)
        except Exception as exc:
            logger.error("Expedia Apify run failed: %s", exc)
            raise

        # run יכול להיות אובייקט Run (עם run.default_dataset_id) או dict גולמי
        # (עם run["defaultDatasetId"]) - תלוי בגרסת apify-client. get_run_field
        # תומך בשני המצבים בלי לקרוס עם AttributeError/KeyError.
        dataset_id = get_run_field(run, "default_dataset_id", "defaultDatasetId")
        if not dataset_id:
            logger.warning("Expedia Apify run returned no defaultDatasetId: %r", run)
            return []

        listings: List[Listing] = []
        for item in self.client.dataset(dataset_id).iterate_items():
            listing = self._parse_item(item)
            if listing:
                listings.append(listing)
        return listings

    def _parse_item(self, item: dict) -> Optional[Listing]:
        try:
            name = item.get("name")
            url = item.get("url")
            if not name or not url:
                return None

            price = item.get("totalPrice")
            if price is None:
                price = item.get("price")
            if price is None:
                price = item.get("pricePerNight")
            if price is None:
                return None

            image = item.get("imageUrl")
            if not image:
                images = item.get("images") or []
                image = images[0] if images else ""

            rating_raw = item.get("guestRating")
            rating = float(rating_raw) if rating_raw is not None else 0.0
            review_count = int(item.get("guestReviewCount") or 0)

            amenities = set()
            for amenity in item.get("amenities") or []:
                if amenity:
                    amenities.add(str(amenity).strip().lower())
            for badge in item.get("badges") or []:
                if badge:
                    amenities.add(str(badge).strip().lower())
            if item.get("breakfastIncluded"):
                amenities.add("breakfast included")
            if item.get("freeCancellation"):
                amenities.add("free cancellation")

            return Listing(
                source=self.source_name,
                title=name,
                image_url=image or "",
                price_total=float(price),
                currency=item.get("currency") or "USD",
                rating=rating,
                review_count=review_count,
                booking_url=url,
                amenities=sorted(amenities),
                extra={"star_rating": item.get("starRating"), "city": item.get("city")},
            )
        except Exception as exc:
            logger.warning("Skipping malformed Expedia item: %s", exc)
            return None
