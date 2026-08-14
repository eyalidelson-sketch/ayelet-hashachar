"""
מנוע סינון ודירוג.

1. filter_listings: מסנן לפי ה-checkboxes שנבחרו (hard filter, סינון קשיח).
2. rank_listings: מחשב ציון Value for Money משוקלל ומחזיר את ה-top_n הטובות ביותר.
3. get_weights_for_mode: 3 פרופילי משקלים לפי בחירת המשתמש (מיטבי/זול/איכותי).

הציון בנוי מנרמול min-max (0-1) של שלושה מדדים בתוך קבוצת התוצאות:
- מחיר (הפוך - נמוך יותר = ציון גבוה יותר)
- ציון ביקורות "מתוקן" (Bayesian shrinkage, ראו _bayesian_rating למטה)
- log(1+כמות ביקורות) - איתות פופולריות נוסף, בנפרד מהתיקון הסטטיסטי לציון עצמו

הערה חשובה על "מקום עם ציון 10 מביקורת בודדת": שקלול נאיבי (רק נרמול min-max
על הציון הגולמי + משקל נפרד לכמות ביקורות) לא באמת פותר את זה, כי אחרי
נרמול min-max שני ערכים תמיד ממופים ל-0 ו-1 בלי קשר לפער האמיתי ביניהם -
כך שציון 10 מביקורת אחת עדיין "מנצח" ציון 9.2 ממאות ביקורות בממד הציון,
ורק משקל קטן לכמות ביקורות לא בהכרח מספיק כדי להפוך את הסדר.
הפתרון הנכון (סטנדרטי בתעשייה, בדומה לציון המשוקלל של IMDb): "מכווצים"
(shrink) את הציון הגולמי של כל מקום לכיוון ציון "ממוצע צפוי" (RATING_PRIOR),
ביחס הפוך לכמות הביקורות שלו - מקום עם מעט ביקורות מקבל תיקון חזק לכיוון
הממוצע, ומקום עם הרבה ביקורות כמעט ולא מתוקן. כך "ציון 10 מביקורת אחת"
נחשב בעצם כ"אמין באופן חלקי" ולא כ"מושלם".
"""
import math
from typing import Dict, List

import config
from models import Listing, RankedListing, SearchFilters

# מיפוי בין שם הסינון לבין מילות מפתח לחיפוש בתוך amenities של כל Listing.
# ה-matching הוא היוריסטי (substring, lowercase) - מבוסס על הטקסטים החופשיים
# שמוחזרים בפועל מהאקטורים של Apify. יתכן שיידרש כיוונון לאחר בדיקה מול נתונים אמיתיים.
FILTER_KEYWORDS: Dict[str, List[str]] = {
    "air_conditioning": ["air conditioning", "aircon", "air-conditioning", "a/c"],
    "private_bathroom": ["private bathroom", "en suite", "ensuite", "private en suite"],
    "breakfast_included": ["breakfast"],
    "separate_beds": ["twin beds", "separate beds", "two single beds", "2 single beds", "twin bed"],
    "free_cancellation": ["free cancellation"],
}

# 3 פרופילי משקלים לבחירת "התאמת מחיר/איכות" של המשתמש.
# "balanced" מכבד את משקלי ברירת המחדל שהוגדרו ב-.env (config.WEIGHT_*),
# ואילו "cheaper" ו-"better" הם פרסטים קבועים שמטים את השיקלול בכוונה.
WEIGHT_PRESETS: Dict[str, Dict[str, float]] = {
    "balanced": {
        "w_price": config.WEIGHT_PRICE,
        "w_rating": config.WEIGHT_RATING,
        "w_review_count": config.WEIGHT_REVIEW_COUNT,
    },
    "cheaper": {"w_price": 0.70, "w_rating": 0.20, "w_review_count": 0.10},
    "better": {"w_price": 0.15, "w_rating": 0.65, "w_review_count": 0.20},
}

MODE_LABELS = {
    "balanced": "🔄 מיטבי (מחיר/איכות)",
    "cheaper": "💰 זול יותר",
    "better": "⭐ טוב יותר",
}


def get_weights_for_mode(mode: str) -> Dict[str, float]:
    return WEIGHT_PRESETS.get(mode, WEIGHT_PRESETS["balanced"])


def _matches_filter(listing: Listing, keywords: List[str]) -> bool:
    haystack = " | ".join(listing.amenities)
    return any(keyword in haystack for keyword in keywords)


def filter_listings(listings: List[Listing], filters: SearchFilters) -> List[Listing]:
    """מחזיר רק תוצאות שעומדות בכל הסינונים הפעילים."""
    active_filters = filters.as_dict()
    result = []
    for listing in listings:
        keep = True
        for filter_key, is_active in active_filters.items():
            if is_active and not _matches_filter(listing, FILTER_KEYWORDS[filter_key]):
                keep = False
                break
        if keep:
            result.append(listing)
    return result


def _normalize(values: List[float], invert: bool = False) -> List[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [1.0 for _ in values]
    normalized = [(v - lo) / (hi - lo) for v in values]
    return [1 - n for n in normalized] if invert else normalized


def _bayesian_rating(rating: float, review_count: int, prior: float, confidence: float) -> float:
    """מכווץ (shrink) ציון גולמי לכיוון prior, ביחס הפוך לכמות הביקורות.

    review_count=0 -> הציון כולו מוחלף ב-prior (אין שום מידע אמין).
    review_count >> confidence -> הציון כמעט ולא משתנה (יש מספיק ביקורות לבטוח בו).
    """
    weight = review_count / (review_count + confidence)
    return weight * rating + (1 - weight) * prior


def rank_listings(
    listings: List[Listing],
    top_n: int = 3,
    w_price: float = 0.45,
    w_rating: float = 0.40,
    w_review_count: float = 0.15,
    rating_prior: float = None,
    rating_confidence: float = None,
) -> List[RankedListing]:
    """מדרג לפי ציון Value for Money משוקלל ומחזיר את top_n הטובות ביותר."""
    if not listings:
        return []

    if rating_prior is None:
        rating_prior = config.RATING_PRIOR
    if rating_confidence is None:
        rating_confidence = config.RATING_CONFIDENCE

    prices = [l.price_total for l in listings]
    adjusted_ratings = [
        _bayesian_rating(l.rating, l.review_count, rating_prior, rating_confidence) for l in listings
    ]
    log_review_counts = [math.log1p(l.review_count) for l in listings]

    price_scores = _normalize(prices, invert=True)
    rating_scores = _normalize(adjusted_ratings)
    review_scores = _normalize(log_review_counts)

    ranked: List[RankedListing] = []
    for listing, price_score, rating_score, review_score in zip(
        listings, price_scores, rating_scores, review_scores
    ):
        score = (
            w_price * price_score
            + w_rating * rating_score
            + w_review_count * review_score
        )
        ranked.append(RankedListing(listing=listing, score=round(score, 4)))

    ranked.sort(key=lambda r: r.score, reverse=True)
    return ranked[:top_n]
