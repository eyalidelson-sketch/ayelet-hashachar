"""
תפריט שיתוף: בניית הודעה אחת מעוצבת עם 3 האופציות המובילות, וקישורי שיתוף
ל-WhatsApp ו-Email. העתקה ללוח מתבצעת דרך st.code() ב-app.py (יש לו כפתור
העתקה מובנה של Streamlit - פתרון אמין יותר מ-JS מותאם אישית בתוך iframe).
"""
from typing import List
from urllib.parse import quote

from models import RankedListing

SOURCE_LABELS = {"booking": "Booking.com", "airbnb": "Airbnb", "expedia": "Expedia"}


def build_share_message(
    destination: str,
    check_in_display: str,
    check_out_display: str,
    nights: int,
    guests: int,
    ranked: List[RankedListing],
) -> str:
    """בונה הודעת טקסט אחת, ברורה ומעוצבת, עם כל 3 האופציות המובילות."""
    lines = [
        f"🌅 איילת השחר - 3 האופציות המובילות ל{destination}",
        f"📅 {check_in_display} - {check_out_display} ({nights} לילות, {guests} אורחים)",
        "",
    ]
    for i, item in enumerate(ranked, start=1):
        listing = item.listing
        source_label = SOURCE_LABELS.get(listing.source, listing.source)
        lines.append(f"{i}. {listing.title} ({source_label})")
        lines.append(f"   💰 {listing.price_total:,.0f} {listing.currency} לכל השהות")
        lines.append(f"   ⭐ {listing.rating}/10 ({listing.review_count} ביקורות)")
        lines.append(f"   🔗 {listing.booking_url}")
        lines.append("")
    lines.append("נשלח באמצעות איילת השחר 🌅")
    return "\n".join(lines).strip()


def whatsapp_share_url(message: str) -> str:
    return f"https://wa.me/?text={quote(message)}"


def email_share_url(subject: str, message: str) -> str:
    return f"mailto:?subject={quote(subject)}&body={quote(message)}"
