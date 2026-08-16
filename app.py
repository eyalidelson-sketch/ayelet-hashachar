"""
איילת השחר 🌅 - אסיסטנט חיפוש דירות ומלונות.
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

PAGE_BG = "#FAF8F5"
GOLD_BORDER = "#D4AF37"

st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Assistant:wght@400;500;600;700&family=Rubik:wght@400;500;600;700&display=swap');

    html, body, .stApp, [class*="css"] {{
        font-family: 'Rubik', 'Assistant', -apple-system, sans-serif !important;
    }}

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

    .ayelet-logo-wrap {{
        display: flex !important; justify-content: center !important; align-items: center !important;
        padding: 10px 0 2px !important;
    }}
    .ayelet-logo {{
        max-width: 300px !important; width: 100% !important; height: auto !important;
        object-fit: contain !important; display: block !important;
        mix-blend-mode: multiply !important;
    }}

    /* אנימציית טעינה יוקרתית */
    .ayelet-loader {{
        display: flex; flex-direction: column; align-items: center; justify-content: center;
        padding: 30px; margin: 20px 0; background: #FFFFFF;
        border: 1px solid {GOLD_BORDER}; border-radius: 12px;
        box-shadow: 0 10px 30px rgba(184, 134, 11, 0.10);
    }}
    .ayelet-spinner {{
        width: 50px; height: 50px; border: 5px solid #F3E5AB;
        border-top: 5px solid #C9791E; border-radius: 50%;
        animation: spin 1s linear infinite; margin-bottom: 15px;
    }}
    @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}

    h1 {{ font-size: 30px !important; font-weight: 700 !important; color: #2B1D0E !important; }}
    h2, .stApp h2 {{ font-size: 22px !important; font-weight: 700 !important; color: #2B1D0E !important; }}
    h3, .stApp h3 {{ font-size: 18px !important; font-weight: 600 !important; color: #3A2817 !important; }}

    div[data-testid="stForm"] {{
        border-radius: 12px !important; border: 1px solid {GOLD_BORDER} !important;
        background: #FFFFFF !important; padding: 30px !important;
        box-shadow: 0 10px 30px rgba(184, 134, 11, 0.10) !important;
    }}

    .stTextInput input, .stNumberInput input, .stDateInput input, .stTextArea textarea,
    div[data-baseweb="input"], div[data-baseweb="select"] > div {{
        border-radius: 12px !important; border: 1px solid {GOLD_BORDER} !important;
        background-color: #FFFFFF !important; color: #2B1D0E !important;
        font-family: 'Rubik', 'Assistant', sans-serif !important;
    }}

    .stButton>button, .stFormSubmitButton>button, .stLinkButton>a {{
        border-radius: 10px !important; border: none !important;
        background: linear-gradient(135deg, #C9791E 0%, #D4AF37 55%, #F2C066 100%) !important;
        color: #ffffff !important; font-weight: 700 !important;
        box-shadow: 0 4px 14px rgba(201, 121, 30, 0.35) !important;
    }}
    .stFormSubmitButton>button {{
        font-size: 22px !important; font-weight: 800 !important;
        padding: 22px 0 !important; border-radius: 14px !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

def parse_free_text_requests(text: str) -> dict:
    if not text:
        return {}
    t = text.lower()
    return {
        "air_conditioning": any(w in t for w in ["מזגן", "מיזוג", "ac", "air con"]),
        "private_bathroom": any(w in t for w in ["שירותים פרטיים", "אמבטיה פרטית", "private bathroom"]),
        "breakfast_included": any(w in t for w in ["ארוחת בוקר", "ארוחה", "breakfast"]),
        "separate_beds": any(w in t for w in ["מיטות נפרדות", "twin", "separate beds"]),
        "free_cancellation": any(w in t for w in ["ביטול בחינם", "ביטול ללא עלות", "free cancellation"]),
    }

def _render_logo() -> None:
    if not LOGO_PATH.exists():
        st.markdown("<h1 style='text-align:center;'>איילת השחר</h1>", unsafe_allow_html=True)
        return
    logo_b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode("utf-8")
    st.markdown(
        f'<div class="ayelet-logo-wrap"><img class="ayelet-logo" src="data:image/png;base64,{logo_b64}" alt="איילת השחר"></div>',
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
            st.markdown(f"⭐ ציון משוקלל: **{listing.rating}/10** ({listing.review_count} ביקורות)")
            st.markdown(f"🏆 ציון תמורה למחיר: **{ranked_item.score}**")
            st.link_button("להזמנה ←", listing.booking_url, use_container_width=True)

def _render_sharing_section(destination, check_in_disp, check_out_disp, nights, guests, ranked) -> None:
    if not ranked:
        return
    st.markdown("### 📢 שיתוף התוצאות")
    message = build_share_message(destination, check_in_disp, check_out_disp, nights, guests, ranked)

    share_cols = st.columns(2)
    with share_cols[0]:
        st.link_button("🟢 שיתוף ב-WhatsApp", whatsapp_share_url(message), use_container_width=True)
    with share_cols[1]:
        st.link_button(
            "✉️ שליחה במייל",
            email_share_url(f"3 האפשרויות המובילות ל{destination}", message),
            use_container_width=True,
        )

    st.caption("📋 להעתקה ידנית:")
    st.code(message, language=None)

# --- סרגל צד: היסטוריית חיפושים ---
with st.sidebar:
    st.markdown("### 🕒 היסטוריית חיפושים")

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
                f"🏝️ {req_data['destination']}\n"
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

# --- תצוגת היסטוריה ---
viewing_path = st.session_state.get("viewing_history")
if viewing_path:
    entry = load_search_history_entry(Path(viewing_path))
    if entry:
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
    st.stop()

# --- טופס חיפוש ---
st.markdown("#### 🌍 יעד החיפוש")
destination_query = st.text_input(
    "הקלד שם עיר",
    key="destination_query",
    placeholder="לדוגמה: שטוקהולם, Rio de Janeiro, פוקט...",
    label_visibility="collapsed",
)

if "ayelet_destination" not in st.session_state:
    st.session_state["ayelet_destination"] = ""

if destination_query and len(destination_query.strip()) >= 2:
    suggestions = search_destinations(destination_query.strip())
    if suggestions:
        manual_option = f'✍️ המשך עם "{destination_query.strip()}" כפי שהוקלד'
        options = suggestions + [manual_option]
        choice = st.radio("בחר מההצעות:", options, key="destination_radio", label_visibility="collapsed")
        st.session_state["ayelet_destination"] = destination_query.strip() if choice == manual_option else choice
    else:
        st.session_state["ayelet_destination"] = destination_query.strip()

with st.form("search_form"):
    st.subheader("פרטי החיפוש")
    col1, col2 = st.columns(2)
    with col1:
        check_in = st.date_input("תאריך צ'ק-אין", value=date.today() + timedelta(days=7), min_value=date.today())
    with col2:
        check_out = st.date_input("תאריך צ'ק-אאוט", value=date.today() + timedelta(days=10), min_value=date.today())

    guests = st.number_input("כמות אורחים", min_value=1, max_value=16, value=2, step=1)

    st.subheader("סינונים ודרישות מיוחדות")
    fcol1, fcol2 = st.columns(2)
    with fcol1:
        air_conditioning = st.checkbox("מיזוג אוויר")
        private_bathroom = st.checkbox("שירותים פרטיים")
        breakfast_included = st.checkbox("ארוחת בוקר")
    with fcol2:
        separate_beds = st.checkbox("מיטות נפרדות")
        free_cancellation = st.checkbox("ביטול בחינם")

    special_requests_text = st.text_area(
        "בקשות מיוחדות בשפה חופשית",
        placeholder="למשל: 'חייב מזגן, ארוחת בוקר וביטול בחינם'",
    )

    submitted = st.form_submit_button("🔍 חפש", use_container_width=True)
    mode_label = st.radio("התאמת תוצאות", list(MODE_LABELS.values()), index=0, horizontal=True, key="mode_radio", label_visibility="collapsed")

if submitted:
    selected_mode = _MODE_KEY_BY_LABEL.get(mode_label, "balanced")
    parsed_filters = parse_free_text_requests(special_requests_text)
    
    request = SearchRequest(
        destination=st.session_state.get("ayelet_destination", ""),
        check_in=check_in,
        check_out=check_out,
        guests=int(guests),
        filters=SearchFilters(
            air_conditioning=air_conditioning or parsed_filters.get("air_conditioning", False),
            private_bathroom=private_bathroom or parsed_filters.get("private_bathroom", False),
            breakfast_included=breakfast_included or parsed_filters.get("breakfast_included", False),
            separate_beds=separate_beds or parsed_filters.get("separate_beds", False),
            free_cancellation=free_cancellation or parsed_filters.get("free_cancellation", False),
        ),
    )

    errors = request.validate()
    if errors:
        st.error("יש לתקן את הבעיות הבאות:")
        for err in errors:
            st.markdown(f"- {err}")
    else:
        loader_placeholder = st.empty()
        loader_placeholder.markdown(
            """
            <div class="ayelet-loader">
                <div class="ayelet-spinner"></div>
                <h3 style="margin:0;">איילת השחר סורקת ומדרגת עבורך את האפשרויות הטובות ביותר...</h3>
            </div>
            """,
            unsafe_allow_html=True
        )

        result = run_pipeline(request, mode=selected_mode)
        loader_placeholder.empty()

        save_search_history(
            request, result.ranked, errors=result.errors,
            total_scraped=result.total_scraped, mode=selected_mode,
        )

        if result.ranked:
            st.success(f"נמצאו {len(result.ranked)} אפשרויות מובילות מתוך {result.total_scraped} תוצאות. ✅")
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
