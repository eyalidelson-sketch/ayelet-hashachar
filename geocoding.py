"""
השלמה אוטומטית עולמית של יעדים (ערים ואזורי תיירות), עברית ואנגלית.

מקור ראשי: GeoNames Search API - מאגר הישובים הגדול והמקיף ביותר שיש בחינם
(https://www.geonames.org/export/geonames-search.html), כולל ישובים קטנים
בכל העולם ואזורי טבע/תיירות (גיא, נהר, הר וכו') ושמות מתורגמים כשקיימים.
דורש רישום חינמי וקצר ל-username באתר geonames.org (יש להפעיל "free web
services" בעמוד ה-Account לאחר ההרשמה) ולהגדיר אותו כ-GEONAMES_USERNAME
(ב-.env או ב-st.secrets - ראו config.py).

מקור גיבוי: Nominatim (OpenStreetMap) - משמש אוטומטית אם GEONAMES_USERNAME
לא הוגדר, אם הבקשה ל-GeoNames נכשלה, או אם היא החזירה מעט מדי תוצאות.

חוסן חיפוש (multi-tier fallback): שמות יעד רבים מגיעים עם "רעש" סביב השם
עצמו - פסיקים, שם מדינה נלווה וכו' (למשל "oirase, japan") - שעלולים לשבש
חיפוש AND-מבוסס-מילים כמו זה של GeoNames/Nominatim. לכן כל חיפוש מנוסה
במספר "וריאציות" של הטקסט (עם/בלי הפסיק, רק החלק הראשון) ובכמה רמות
סינון (featureClass מצומצם -> רחב, isNameRequired -> בלי), עד שנמצאות
תוצאות. אם אחרי כל הניסיונות עדיין אין תוצאות - לא מוצגת שגיאה: המשתמש
פשוט ממשיך עם הטקסט שהקליד (זה קורה גם ליעדים תקינים לגמרי שלא מאונדקסים
בשום מאגר גאוקודינג חינמי).
"""
import logging
from typing import List, Optional

import requests
import streamlit as st

import config

logger = logging.getLogger(__name__)

GEONAMES_URL = "http://api.geonames.org/searchJSON"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "AyeletHaShachar-TravelAssistant/1.0 (Streamlit demo app)"

_NOMINATIM_RELEVANT_CLASSES = {"place", "boundary", "natural", "leisure", "tourism"}
_MIN_RESULTS_BEFORE_FALLBACK = 3
# ישובים (P), אזורים מנהליים (A), תבליט/הרים (T), הידרוגרפיה - נהרות/גאיות/אגמים (H),
# פארקים/שטחים (L) - כיסוי רחב שמתאים ליעדי תיירות ולא רק לערים רשמיות.
_GEONAMES_FEATURE_CLASSES = ["P", "A", "T", "H", "L"]


def _query_variants(query: str) -> List[str]:
    """מייצר כמה ניסוחים לאותה שאילתה, כדי להתגבר על פיסוק/מילות-עזר שמבלבלות
    חיפוש AND-מבוסס-מילים (כמו הפסיק ב-'oirase, japan')."""
    query = query.strip()
    variants = [query]

    no_comma = query.replace(",", " ").strip()
    no_comma = " ".join(no_comma.split())  # מכווץ רווחים כפולים
    if no_comma and no_comma not in variants:
        variants.append(no_comma)

    if "," in query:
        base = query.split(",")[0].strip()
        if base and base not in variants:
            variants.append(base)

    return variants


def _geonames_request(query: str, limit: int, feature_classes: Optional[List[str]],
                       fuzzy: float, name_required: bool) -> List[dict]:
    params = {
        "q": query,
        "maxRows": limit,
        "username": config.GEONAMES_USERNAME,
        "lang": "he",
        "fuzzy": fuzzy,
        "orderby": "relevance",
        "style": "FULL",
    }
    if feature_classes:
        params["featureClass"] = feature_classes
    if name_required:
        params["isNameRequired"] = "true"

    response = requests.get(params=params, url=GEONAMES_URL, headers={"User-Agent": USER_AGENT}, timeout=6)
    response.raise_for_status()
    data = response.json()

    if data.get("status"):
        logger.warning("GeoNames API error for %r: %s", query, data["status"])
        return []
    return data.get("geonames", [])


def _format_geonames_item(item: dict) -> Optional[str]:
    hebrew_name = (item.get("name") or "").strip()
    default_name = (item.get("toponymName") or hebrew_name).strip()
    country = (item.get("countryName") or "").strip()

    if not default_name:
        return None

    if hebrew_name and hebrew_name != default_name:
        label = f"{hebrew_name} ({default_name})"
    else:
        label = default_name
    if country:
        label = f"{label}, {country}"
    return label


def _search_geonames(query: str, limit: int) -> List[str]:
    if not config.GEONAMES_USERNAME:
        return []

    variants = _query_variants(query)
    # רמת חיפוש 1: מצומצם (featureClass רלוונטי + isNameRequired) על כל הוריאציות
    # רמת חיפוש 2 (רק אם עדיין ריק): הכי רחב שאפשר - בלי הגבלות, fuzzy נמוך יותר
    attempts = [
        {"feature_classes": _GEONAMES_FEATURE_CLASSES, "fuzzy": 0.7, "name_required": True},
        {"feature_classes": None, "fuzzy": 0.5, "name_required": False},
    ]

    suggestions: List[str] = []
    seen = set()
    for attempt in attempts:
        for variant in variants:
            try:
                raw_items = _geonames_request(variant, limit, **attempt)
            except requests.RequestException as exc:
                logger.warning("GeoNames request failed for %r: %s", variant, exc)
                continue
            except ValueError as exc:
                logger.warning("GeoNames returned invalid JSON for %r: %s", variant, exc)
                continue

            for item in raw_items:
                label = _format_geonames_item(item)
                if label and label not in seen:
                    seen.add(label)
                    suggestions.append(label)

            if len(suggestions) >= limit:
                return suggestions[:limit]
        if len(suggestions) >= _MIN_RESULTS_BEFORE_FALLBACK:
            break

    return suggestions[:limit]


def _search_nominatim(query: str, limit: int) -> List[str]:
    suggestions: List[str] = []
    seen = set()

    for variant in _query_variants(query):
        try:
            response = requests.get(
                NOMINATIM_URL,
                params={
                    "q": variant,
                    "format": "jsonv2",
                    "addressdetails": 1,
                    "accept-language": "he,en",
                    "limit": limit,
                },
                headers={"User-Agent": USER_AGENT},
                timeout=6,
            )
            response.raise_for_status()
            results = response.json()
        except requests.RequestException as exc:
            logger.warning("Nominatim request failed for %r: %s", variant, exc)
            continue
        except ValueError as exc:
            logger.warning("Nominatim returned invalid JSON for %r: %s", variant, exc)
            continue

        for item in results:
            display_name = item.get("display_name")
            place_class = item.get("class")
            if not display_name or display_name in seen:
                continue
            if place_class not in _NOMINATIM_RELEVANT_CLASSES:
                continue
            seen.add(display_name)
            suggestions.append(display_name)

        if len(suggestions) >= _MIN_RESULTS_BEFORE_FALLBACK:
            break

    return suggestions[:limit]


@st.cache_data(ttl=3600, show_spinner=False)
def search_destinations(query: str, limit: int = 8) -> List[str]:
    """מחזיר רשימת הצעות יעד לפי טקסט חופשי, בעברית או באנגלית.

    מנסה קודם GeoNames (מאגר עולמי מקיף, כולל אזורי טבע/תיירות); אם לא
    מוגדר / נכשל / מחזיר מעט מדי תוצאות - משלים עם Nominatim. כל שכבה
    מנסה כמה ניסוחים של הטקסט כדי להתגבר על פיסוק שמבלבל חיפוש AND-מבוסס
    מילים. אף שכבה לא זורקת שגיאה כלפי חוץ - כשל מלא פשוט מחזיר רשימה ריקה.
    """
    query = (query or "").strip()
    if len(query) < 2:
        return []

    try:
        suggestions = _search_geonames(query, limit)
    except Exception:
        logger.exception("Unexpected error in GeoNames search for %r", query)
        suggestions = []

    if len(suggestions) < _MIN_RESULTS_BEFORE_FALLBACK:
        try:
            fallback = _search_nominatim(query, limit)
        except Exception:
            logger.exception("Unexpected error in Nominatim search for %r", query)
            fallback = []
        for item in fallback:
            if item not in suggestions:
                suggestions.append(item)

    return suggestions[:limit]
