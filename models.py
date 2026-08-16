"""
מבני הנתונים המרכזיים של האפליקציה.
כל שלב עתידי (סקרייפינג, דירוג) עובד מול SearchRequest -
כך שאפשר להחליף מקורות נתונים בלי לגעת ב-UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Any, Dict, List


MAX_NIGHTS = 30
MAX_GUESTS = 16


@dataclass
class SearchFilters:
    """5 הסינונים הנדרשים (Checkboxes)."""
    air_conditioning: bool = False
    private_bathroom: bool = False
    breakfast_included: bool = False
    separate_beds: bool = False
    free_cancellation: bool = False

    def as_dict(self) -> dict:
        return asdict(self)

    def active_labels(self) -> List[str]:
        """שמות הסינונים הפעילים, לתצוגה בלבד."""
        labels = {
            "air_conditioning": "מיזוג אוויר",
            "private_bathroom": "שירותים פרטיים",
            "breakfast_included": "ארוחת בוקר כלולה",
            "separate_beds": "מיטות נפרדות",
            "free_cancellation": "ביטול בחינם",
        }
        return [label for key, label in labels.items() if getattr(self, key)]


MAX_ROOMS = 10


@dataclass
class SearchRequest:
    """בקשת חיפוש בודדת, כפי שנתפסת מהטופס (כולל תוצאת פענוח בקשות מיוחדות)."""
    destination: str
    check_in: date
    check_out: date
    guests: int
    filters: SearchFilters = field(default_factory=SearchFilters)
    rooms: int = 1
    special_requests: str = ""

    @property
    def nights(self) -> int:
        return (self.check_out - self.check_in).days

    def validate(self) -> List[str]:
        """מחזיר רשימת שגיאות ולידציה (רשימה ריקה = תקין)."""
        errors: List[str] = []

        if not self.destination or len(self.destination.strip()) < 2:
            errors.append("יש לבחור יעד תקין (לפחות 2 תווים).")

        if self.check_in < date.today():
            errors.append("תאריך הצ'ק-אין לא יכול להיות בעבר.")

        if self.check_out <= self.check_in:
            errors.append("תאריך הצ'ק-אאוט חייב להיות אחרי תאריך הצ'ק-אין.")
        elif self.nights > MAX_NIGHTS:
            errors.append(f"טווח החיפוש ארוך מדי (מקסימום {MAX_NIGHTS} לילות).")

        if not (1 <= self.guests <= MAX_GUESTS):
            errors.append(f"מספר האורחים חייב להיות בין 1 ל-{MAX_GUESTS}.")

        if not (1 <= self.rooms <= MAX_ROOMS):
            errors.append(f"מספר החדרים חייב להיות בין 1 ל-{MAX_ROOMS}.")

        return errors

    def to_dict(self) -> dict:
        return {
            "destination": self.destination.strip(),
            "check_in": self.check_in.isoformat(),
            "check_out": self.check_out.isoformat(),
            "nights": self.nights,
            "guests": self.guests,
            "rooms": self.rooms,
            "special_requests": self.special_requests,
            "filters": self.filters.as_dict(),
        }


@dataclass
class Listing:
    """תוצאת חיפוש בודדת ומנורמלת, ממקור כלשהו (Booking / Airbnb / ...)."""
    source: str  # "booking" | "airbnb"
    title: str
    image_url: str
    price_total: float
    currency: str
    rating: float  # מנורמל לסקאלה של 0-10
    review_count: int
    booking_url: str
    amenities: List[str] = field(default_factory=list)  # מחרוזות lowercase, לשימוש בסינון
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RankedListing:
    """תוצאה אחרי חישוב ציון Value for Money."""
    listing: Listing
    score: float
