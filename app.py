"""
איילת השחר 🌅 - אסיסטנט חיפוש דירות ומלונות (ממשק Streamlit).

טופס קלט עם השלמה אוטומטית עולמית של יעדים -> הרצת שרשרת החיפוש
(סריקה משלושה מקורות -> סינון -> דירוג לפי מצב מחיר/איכות נבחר) ->
תצוגת 3 האופציות המובילות עם תפריט שיתוף, והיסטוריית חיפושים בסרגל הצד.
"""
import base64
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

from geocoding import search_destinations
from models import SearchFilters, SearchRequest
from pipeline import run_pipeline
from ranking import MODE_LABELS
from sharing import SOURCE_LABELS, build_share_message, email_share_url, whatsapp_share_url
from storage import list_search_history, load_search_history_entry, save_search_history

st.set_page_config(page_title="איילת השחר", page_icon="🌅", layout="centered")

LOGO_PATH = Path(__file__).resolve().parent / "assets" / "logo.png"
_MODE_KEY_BY_LABEL = {label: key for key, label in MODE_LABELS.items()}

# ---------------------------------------------------------------------------
# עיצוב: Sunrise & Luxury - רקע שמנת חם, כרטיסים לבנים עם גבול זהב והצללה
# יוקרתית, כפתורים בגרדיאנט זהב-כתום (הכפתור הראשי - "חפש" - גדול ובולט
# במיוחד), פונטים Rubik/Assistant. כל כלל מוגן ב-!important כדי שהעיצוב
# הדיפולטיבי של Streamlit לא ידרוס אותו.
# ---------------------------------------------------------------------------
PAGE_BG = "#FAF8F5"
GOLD_BORDER = "#D4AF37"

st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Assistant:wght@400;500;600;700&family=Rubik:wght@400;500;600;700&display=swap');

    html, body, .stApp, [class*="css"] {{
        font-family: 'Rubik', 'Assistant', -apple-system, sans-serif !important;
    }}

    /* --- רקע כללי: שמנת חם בכל שכבות הדף --- */
    html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"],
    [data-testid="stMain"], .main {{
        background-color: {PAGE_BG} !important;
    }}
    [data-testid="stHeader"] {{ background: transparent !important; }}
    .stApp {{ direction: rtl !important; text-align: right !important; }}

    div[data-testid="stForm"] label, .stRadio label, .stCheckbox label,
    .stTextInput label, .stNumberInput label, .stDateInput label {{ text-align: right !important; }}
    section[data-testid="stSidebar"] {{
        direction: rtl !important; text-align: right !important;
        background-color: #FBF6EE !important; border-left: 1px solid #EAD8C0 !important;
    }}

    /* --- לוגו: mix-blend-mode מעלים את ההילה הלבנה/שמנתית סביב האייל בלי
       תלות בהתאמת צבע מדויקת - עובד גם עם גרדיאנט/רקע לא אחיד --- */
    .ayelet-logo-wrap {{
        display: flex !important; justify-content: center !important; align-items: center !important;
        padding: 10px 0 2px !important;
    }}
    .ayelet-logo {{
        max-width: 300px !important; width: 100% !important; height: auto !important;
        object-fit: contain !important; display: block !important;
        mix-blend-mode: multiply !important;
    }}

    /* --- היררכיית כותרות: גדולות, ברורות, ריווח נעים --- */
    h1 {{ font-size: 30px !important; font-weight: 700 !important; color: #2B1D0E !important; }}
    h2, .stApp h2 {{ font-size: 22px !important; font-weight: 700 !important; color: #2B1D0E !important; }}
    h3, .stApp h3 {{ font-size: 18px !important; font-weight: 600 !important; color: #3A2817 !important; }}
    div[data-testid="stMarkdownContainer"] p {{ line-height: 1.6 !important; }}

    /* --- כרטיסים (טופס, תוצאות): לבן נקי, גבול זהב, הצללה יוקרתית --- */
    div[data-testid="stForm"] {{
        border-radius: 12px !important; border: 1px solid {GOLD_BORDER} !important;
        background: #FFFFFF !important; padding: 30px !important;
        box-shadow: 0 10px 30px rgba(184, 134, 11, 0.10) !important;
    }}
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        border-radius: 12px !important; border: 1px solid {GOLD_BORDER} !important;
        background: #FFFFFF !important; padding: 4px !important;
        box-shadow: 0 10px 30px rgba(184, 134, 11, 0.10) !important;
    }}

    /* --- שדות קלט: רקע לבן נקי, גבול זהב עדין, פינות מעוגלות --- */
    .stTextInput input, .stNumberInput input, .stDateInput input,
    div[data-baseweb="input"], div[data-baseweb="select"] > div {{
        border-radius: 12px !important; border: 1px solid {GOLD_BORDER} !important;
        background-color: #FFFFFF !important; color: #2B1D0E !important;
        font-family: 'Rubik', 'Assistant', sans-serif !important;
    }}
    .stTextInput input:focus, .stNumberInput input:focus, .stDateInput input:focus {{
        border: 1px solid #C9791E !important;
        box-shadow: 0 0 0 3px rgba(201, 121, 30, 0.18) !important;
    }}

    /* --- כפתורים כלליים: גרדיאנט זריחה זהב-כתום, Hover בולט --- */
    .stButton>button, .stFormSubmitButton>button, .stLinkButton>a {{
        border-radius: 10px !important; border: none !important;
        background: linear-gradient(135deg, #C9791E 0%, #D4AF37 55%, #F2C066 100%) !important;
        color: #ffffff !important; font-weight: 700 !important; letter-spacing: 0.2px !important;
        box-shadow: 0 4px 14px rgba(201, 121, 30, 0.35) !important;
        transition: transform 0.15s ease, box-shadow 0.15s ease !important;
    }}
    .stButton>button:hover, .stFormSubmitButton>button:hover, .stLinkButton>a:hover {{
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 20px rgba(201, 121, 30, 0.5) !important;
    }}

    /* --- כפתור "חפש": כרטיס ענק, מוזהב ומזמין --- */
    .stFormSubmitButton>button {{
        font-size: 22px !important; font-weight: 800 !important;
        padding: 22px 0 !important; border-radius: 14px !important;
        box-shadow: 0 8px 24px rgba(201, 121, 30, 0.45) !important;
        border: 1px solid #B8860B !important;
    }}
    .stFormSubmitButton>button:hover {{
        box-shadow: 0 12px 30px rgba(201, 121, 30, 0.6) !important;
    }}

    section[data-testid="stSidebar"] .stButton>button {{
        background: #FFFFFF !important; color: #4A2C10 !important;
        border: 1px solid {GOLD_BORDER} !important; box-shadow: none !important;
        text-align: right !important; font-weight: 500 !important;
    }}
    section[data-testid="stSidebar"] .stButton>button:hover {{
        background: #F5E6C8 !important; transform: none !important;
    }}

    /* --- Progress bar בגווני זריחה --- */
    .stProgress > div > div {{ background: linear-gradient(90deg, #C9791E, #F2C066) !important; }}
    </style>
    """,
    unsafe_allow_html=True,
)


def _render_logo() -> None:
    if not LOGO_PATH.exists():
        st.markdown("<h1 style='text-align:center;'>איילת השחר</h1>", unsafe_allow_html=True)
        return
    logo_b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode("utf-8")
    st.markdown(
        f'<div class="ayelet-logo-wrap">'
        f'<img class="ayelet-logo" src="data:image/png;base64,{logo_b64}" alt="איילת השחר">'
        f"</div>",
        unsafe_allow_html=True,
    )


_render_logo()
st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)


def _format_date_display(iso_date: str) -> str:
    try:
        year, month, day = iso_date.split("-")
        return f"{day}/{month}/{year}"
    except Exception:
        return iso_date


def _render_result_card(rank: int, ranked_item) -> None:
    listing = ranked_item.listing
    source_label = SOURCE_LABELS.get(listing.source, listing.source)
    with st.container(border=True):
        cols = st.columns([1, 2])
        with cols[0]:
            if listing.image_url:
                st.image(listing.image_url, use_container_width=True)
        with cols[1]:
            st.markdown(f"**#{rank} · {listing.title}**")
            st.caption(source_label)
            st.markdown(f"💰 מחיר כולל: **{listing.price_total:,.0f} {listing.currency}**")
            st.markdown(f"⭐ ציון: **{listing.rating}/10** ({listing.review_count} ביקורות)")
            st.markdown(f"🏆 ציון תמורה למחיר: **{ranked_item.score}**")
            st.link_button("להזמנה →", listing.booking_url, use_container_width=True)


def _render_sharing_section(destination, check_in_disp, check_out_disp, nights, guests, ranked) -> None:
    if not ranked:
        return
    st.markdown("### 📤 שיתוף התוצאות")
    message = build_share_message(destination, check_in_disp, check_out_disp, nights, guests, ranked)

    share_cols = st.columns(2)
    with share_cols[0]:
        st.link_button("🟢 שיתוף ב-WhatsApp", whatsapp_share_url(message), use_container_width=True)
    with share_cols[1]:
        st.link_button(
            "✉️ שליחה במייל",
            email_share_url(f"3 האופציות המובילות ל{destination}", message),
            use_container_width=True,
        )

    st.caption("📋 להעתקה ידנית - לחצו על סמל ההעתקה בפינת התיבה למטה:")
    st.code(message, language=None)


# --- סרגל צד: היסטוריית חיפושים ---
with st.sidebar:
    st.markdown("### 🕰️ היסטוריית חיפושים")

    history_files = list_search_history()
    if not history_files:
        st.caption("עוד לא ביצעת חיפושים באיילת השחר.")
    else:
        for path in history_files:
            entry = load_search_history_entry(path)
            if not entry:
                continue
            req_data = entry["request"]
            label = (
                f"🏙️ {req_data['destination']}\n"
                f"{_format_date_display(req_data['check_in'])} – {_format_date_display(req_data['check_out'])}"
            )
            if st.button(label, key=f"hist_{path.name}", use_container_width=True):
                st.session_state["viewing_history"] = str(path)
                st.rerun()

    if st.session_state.get("viewing_history"):
        st.divider()
        if st.button("➕ חיפוש חדש", use_container_width=True):
            st.session_state.pop("viewing_history", None)
            st.rerun()


# --- תצוגת היסטוריה שמורה (אם נבחרה בסרגל הצד) ---
viewing_path = st.session_state.get("viewing_history")
if viewing_path:
    entry = load_search_history_entry(Path(viewing_path))
    if not entry:
        st.error("לא ניתן לטעון את החיפוש שנבחר.")
    else:
        req_data = entry["request"]
        mode_used = entry.get("mode", "balanced")
        check_in_disp = _format_date_display(req_data["check_in"])
        check_out_disp = _format_date_display(req_data["check_out"])

        st.subheader(f"🔎 תוצאות שמורות: {req_data['destination']}")
        st.caption(
            f"{check_in_disp} – {check_out_disp} · {req_data['nights']} לילות · "
            f"{req_data['guests']} אורחים · מצב: {MODE_LABELS.get(mode_used, mode_used)}"
        )

        ranked_objects = entry.get("ranked_objects", [])
        if ranked_objects:
            for i, ranked_item in enumerate(ranked_objects, start=1):
                _render_result_card(i, ranked_item)
            _render_sharing_section(
                req_data["destination"], check_in_disp, check_out_disp,
                req_data["nights"], req_data["guests"], ranked_objects,
            )
        else:
            st.info("לחיפוש הזה לא נמצאו תוצאות שמורות.")

        if entry.get("errors"):
            with st.expander("פרטי שגיאות/אזהרות מהחיפוש המקורי"):
                for err in entry["errors"]:
                    st.warning(err)

    st.stop()


# --- טופס חיפוש חדש ---
st.markdown("#### 🌍 יעד החיפוש")
destination_query = st.text_input(
    "הקלידו שם עיר (עברית או אנגלית)",
    key="destination_query",
    placeholder="לדוגמה: שטוקהולם, Rio de Janeiro, פוקט, יאמאגאטה...",
    label_visibility="collapsed",
)

if "ayelet_destination" not in st.session_state:
    st.session_state["ayelet_destination"] = ""

if destination_query and len(destination_query.strip()) >= 2:
    with st.spinner("מחפש ערים תואמות..."):
        suggestions = search_destinations(destination_query.strip())
    if suggestions:
        manual_option = f'✏️ המשך עם "{destination_query.strip()}" כפי שהוקלד'
        options = suggestions + [manual_option]
        choice = st.radio(
            "בחרו מתוך ההצעות:", options, key="destination_radio", label_visibility="collapsed"
        )
        st.session_state["ayelet_destination"] = (
            destination_query.strip() if choice == manual_option else choice
        )
    else:
        # אין הצעות אוטומטיות מהמאגרים - ממשיכים בשקט עם הטקסט שהוקלד, בלי הודעת
        # שגיאה מפריעה (יעדים תקינים רבים פשוט לא מופיעים במאגרי הגאוקודינג).
        st.session_state["ayelet_destination"] = destination_query.strip()
elif destination_query:
    st.session_state["ayelet_destination"] = destination_query.strip()
else:
    st.session_state["ayelet_destination"] = ""

if st.session_state["ayelet_destination"]:
    st.success(f"✅ יעד נבחר: **{st.session_state['ayelet_destination']}**")

with st.form("search_form"):
    st.subheader("פרטי החיפוש")

    col1, col2 = st.columns(2)
    with col1:
        check_in = st.date_input(
            "תאריך צ'ק-אין",
            value=date.today() + timedelta(days=7),
            min_value=date.today(),
        )
    with col2:
        check_out = st.date_input(
            "תאריך צ'ק-אאוט",
            value=date.today() + timedelta(days=10),
            min_value=date.today(),
        )

    guests = st.number_input("כמות אורחים", min_value=1, max_value=16, value=2, step=1)

    st.subheader("סינונים")
    fcol1, fcol2 = st.columns(2)
    with fcol1:
        air_conditioning = st.checkbox("מיזוג אוויר")
        private_bathroom = st.checkbox("שירותים פרטיים")
        breakfast_included = st.checkbox("ארוחת בוקר")
    with fcol2:
        separate_beds = st.checkbox("מיטות נפרדות")
        free_cancellation = st.checkbox("ביטול בחינם")

    submitted = st.form_submit_button("🔍 חפש", use_container_width=True)

    st.caption("התאמת תוצאות:")
    mode_label = st.radio(
        "התאמת תוצאות",
        list(MODE_LABELS.values()),
        index=0,
        horizontal=True,
        key="mode_radio",
        label_visibility="collapsed",
    )


if submitted:
    selected_mode = _MODE_KEY_BY_LABEL.get(mode_label, "balanced")

    request = SearchRequest(
        destination=st.session_state.get("ayelet_destination", ""),
        check_in=check_in,
        check_out=check_out,
        guests=int(guests),
        filters=SearchFilters(
            air_conditioning=air_conditioning,
            private_bathroom=private_bathroom,
            breakfast_included=breakfast_included,
            separate_beds=separate_beds,
            free_cancellation=free_cancellation,
        ),
    )

    errors = request.validate()

    if errors:
        st.error("יש לתקן את הבעיות הבאות:")
        for err in errors:
            st.markdown(f"- {err}")
    else:
        progress_bar = st.progress(0.0)
        status_text = st.empty()

        def update_progress(message: str, fraction: float) -> None:
            status_text.info(message)
            progress_bar.progress(min(max(fraction, 0.0), 1.0))

        with st.spinner("מריץ את שרשרת החיפוש (סריקה, סינון ודירוג)..."):
            result = run_pipeline(request, mode=selected_mode, on_progress=update_progress)

        progress_bar.empty()
        status_text.empty()

        save_search_history(
            request, result.ranked, errors=result.errors,
            total_scraped=result.total_scraped, mode=selected_mode,
        )

        if result.ranked:
            st.success(
                f"נמצאו {len(result.ranked)} אופציות מובילות מתוך {result.total_scraped} תוצאות שנסרקו "
                f"(מצב: {MODE_LABELS.get(selected_mode, selected_mode)}). ✅"
            )
            st.subheader("3 האופציות המובילות")
            for i, ranked_item in enumerate(result.ranked, start=1):
                _render_result_card(i, ranked_item)

            _render_sharing_section(
                request.destination,
                request.check_in.strftime("%d/%m/%Y"),
                request.check_out.strftime("%d/%m/%Y"),
                request.nights,
                request.guests,
                result.ranked,
            )
        else:
            st.error("לא נמצאו תוצאות מתאימות לבקשת החיפוש.")

        if result.errors:
            with st.expander("פרטי שגיאות / אזהרות"):
                for err in result.errors:
                    st.warning(err)
