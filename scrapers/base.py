"""
ממשק אחיד לכל מקור סריקה (Adapter Pattern).
כל מקור חדש (Apify, RapidAPI, וכו') צריך רק לממש את search().
"""
from abc import ABC, abstractmethod
from typing import Any, List, Optional

from models import Listing, SearchRequest


class BaseScraper(ABC):
    source_name: str = "unknown"

    @abstractmethod
    def search(self, request: SearchRequest) -> List[Listing]:
        """מריץ חיפוש עבור request ומחזיר רשימת Listing מנורמלת."""
        raise NotImplementedError


def get_run_field(run: Any, snake_case_name: str, camel_case_name: str) -> Optional[Any]:
    """שולף שדה מתוך אובייקט ה-Run שמוחזר מ-`client.actor(...).call(...)` בצורה
    בטוחה לשני הצורות האפשריות שבהן apify-client עלול להחזיר את התשובה
    (תלוי בגרסה המדויקת המותקנת בסביבת ההרצה, מקומית מול Streamlit Cloud):

    1. אובייקט טיפוסי (למשל Run) עם שדות snake_case כתכונות (attributes) -
       למשל run.default_dataset_id. לאובייקט כזה אין מתודת .get(), ולכן
       ניסיון לקרוא לו run.get(...) גורם ל-AttributeError (זה בדיוק מה
       שקרה בפרודקשן ב-Streamlit Cloud).
    2. מילון גולמי (dict) עם מפתחות camelCase - למשל run["defaultDatasetId"].

    לכן: קודם מנסים getattr בטוח (עובד גם אם run הוא dict בלי שדה הזה - יחזיר
    None), ורק אם זה לא נתן תוצאה בודקים אם run הוא בכלל dict ומנסים .get()
    עם שם המפתח camelCase.
    """
    if run is None:
        return None
    value = getattr(run, snake_case_name, None)
    if value is not None:
        return value
    if isinstance(run, dict):
        return run.get(camel_case_name)
    return None
