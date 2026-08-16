"""
ממשק אחיד לכל מקור סריקה (Adapter Pattern).
כל מקור חדש (Apify, RapidAPI, וכו') צריך רק לממש את search().
"""
from abc import ABC, abstractmethod
from typing import List

from models import Listing, SearchRequest


class BaseScraper(ABC):
    source_name: str = "unknown"

    @abstractmethod
    def search(self, request: SearchRequest) -> List[Listing]:
        """מריץ חיפוש עבור request ומחזיר רשימת Listing מנורמלת."""
        raise NotImplementedError
