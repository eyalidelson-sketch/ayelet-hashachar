"""
קונפיגורציה וסודות.

תומך בשני מקורות, בסדר עדיפות הזה:
1. st.secrets - לפריסה ב-Streamlit Community Cloud (Settings -> Secrets).
2. משתני סביבה / קובץ .env מקומי (python-dotenv) - לפיתוח מקומי.

כדי להריץ מקומית: העתיקו את .env.example ל-.env ומלאו ערכים אמיתיים.
כדי לפרוס ל-Streamlit Community Cloud: הדביקו את אותם מפתחות בפורמט TOML
תחת Settings -> Secrets באתר (ראו .env.example להשראה לשמות המשתנים).
"""
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def _get_secret(key: str, default: str = "") -> str:
    """מנסה קודם st.secrets (לפריסה בענן), ואז נופל למשתני סביבה/.env.

    strip() מוחל בכוונה על כל ערך - תקלה נפוצה מאוד היא הדבקת מפתח API עם רווח
    או שורה חדשה מיותרת בסוף לתוך תיבת ה-Secrets ב-Streamlit Cloud, מה שגורם
    לשגיאת אימות (401) שנראית כמו "אין תוצאות" בלי שום סיבה נראית לעין.
    """
    try:
        if key in st.secrets:
            return str(st.secrets[key]).strip()
    except Exception:
        # אין קובץ secrets.toml (למשל בהרצה מקומית רגילה) - זה תקין, ממשיכים ל-.env
        pass
    return os.getenv(key, default).strip()


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SEARCHES_DIR = DATA_DIR / "searches"
HISTORY_DIR = DATA_DIR / "history"

# --- Apify (סריקת Booking / Airbnb / Expedia) ---
APIFY_API_TOKEN = _get_secret("APIFY_API_TOKEN", "")
# ניתן להשאיר ריק - יש ברירת מחדל בכל scraper
APIFY_BOOKING_ACTOR_ID = _get_secret("APIFY_BOOKING_ACTOR_ID", "")
APIFY_AIRBNB_ACTOR_ID = _get_secret("APIFY_AIRBNB_ACTOR_ID", "")
APIFY_EXPEDIA_ACTOR_ID = _get_secret("APIFY_EXPEDIA_ACTOR_ID", "")

# --- RapidAPI (אופציונלי, גיבוי) ---
RAPIDAPI_KEY = _get_secret("RAPIDAPI_KEY", "")

# --- השלמה אוטומטית של יעדים ---
# GeoNames: הרשמה חינמית וקצרה ב-https://www.geonames.org/login (יש להפעיל
# "free web services" בעמוד ה-Account לאחר ההרשמה). אם ריק, נעשה שימוש
# אוטומטי ב-Nominatim בלבד (מאגר קטן/פחות מדויק לישובים קטנים).
GEONAMES_USERNAME = _get_secret("GEONAMES_USERNAME", "")

# --- אלגוריתם דירוג ---
WEIGHT_PRICE = float(_get_secret("WEIGHT_PRICE", "0.45"))
WEIGHT_RATING = float(_get_secret("WEIGHT_RATING", "0.40"))
WEIGHT_REVIEW_COUNT = float(_get_secret("WEIGHT_REVIEW_COUNT", "0.15"))

# תיקון סטטיסטי (Bayesian shrinkage) לציון ביקורות, כדי שמקום עם ציון 10
# מביקורת בודדת לא "ינצח" מקום עם ציון גבוה ומאות ביקורות. RATING_PRIOR הוא
# ציון "ממוצע צפוי" (בסקאלת 0-10) שאליו מכווצים ציונים עם מעט ביקורות;
# RATING_CONFIDENCE הוא כמות הביקורות הדרושה כדי לבטוח כמעט לגמרי בציון הגולמי.
RATING_PRIOR = float(_get_secret("RATING_PRIOR", "8.0"))
RATING_CONFIDENCE = float(_get_secret("RATING_CONFIDENCE", "20"))

# כמות תוצאות מקסימלית לבקש מכל מקור סריקה (עלות/ביצועים)
MAX_RESULTS_PER_SOURCE = int(_get_secret("MAX_RESULTS_PER_SOURCE", "30"))

# כמות פריטי היסטוריה מקסימלית להצגה בסרגל הצד
HISTORY_DISPLAY_LIMIT = int(_get_secret("HISTORY_DISPLAY_LIMIT", "15"))

SEARCHES_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_DIR.mkdir(parents=True, exist_ok=True)
