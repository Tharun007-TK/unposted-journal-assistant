import os
import streamlit as st
from datetime import datetime
import sqlite3
from dotenv import load_dotenv
from groq import Groq
import requests, logging
from cryptography.fernet import Fernet

# ==============================
# Setup
# ==============================
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEEPGRAM_KEY = os.getenv("DEEPGRAM_API_KEY")
FERNET_KEY = os.getenv("FERNET_KEY")
GROQ_KEY = os.getenv("GROQ_API_KEY")
DB_PATH = os.getenv("LOCAL_DB_PATH", "journal_data.db")

groq_client = Groq(api_key=GROQ_KEY) if GROQ_KEY else None
fernet = Fernet(FERNET_KEY.encode()) if FERNET_KEY else None

# Ensure database folder
db_dir = os.path.dirname(DB_PATH)
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir, exist_ok=True)

# DB setup (UTF-8 enforced)
conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
conn.text_factory = lambda b: b.decode(errors='ignore')
c = conn.cursor()
c.execute("""CREATE TABLE IF NOT EXISTS streaks (date TEXT PRIMARY KEY, count INTEGER)""")
c.execute("""CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY,
    date TEXT,
    transcription TEXT,
    emotion TEXT,
    summary TEXT,
    reflection TEXT
)""")
conn.commit()

# ==============================
# Config + Style
# ==============================
st.set_page_config(page_title="Unposted Journal", page_icon="📝", layout="wide")
st.markdown("""
<style>
header, #MainMenu, footer {visibility:hidden;}
.block-container {max-width: 980px; padding-top:1.5rem;}
body {background:#ffffff; color:#111827; font-family: 'Inter','Segoe UI',sans-serif;}
h1,h2,h3 {color:#111827 !important; font-weight:600; letter-spacing:.5px;}
.uj-card {background:#ffffff; border:1px solid #e5e7eb; border-radius:14px; padding:1.1rem 1.25rem; margin:1rem 0; box-shadow:0 1px 2px rgba(0,0,0,0.04);} 
div.stButton > button {border-radius:8px; background:#111827; color:#ffffff; font-weight:500; border:1px solid #111827;}
div.stButton > button:hover {background:#374151;}
section[data-testid="stSidebar"] {background:#f9fafb; border-right:1px solid #e5e7eb;}
</style>
""", unsafe_allow_html=True)

# ==============================
# Navigation
# ==============================
try:
    from streamlit_option_menu import option_menu
except Exception:
    option_menu = None

NAV_OPTIONS = ["Journal", "Past Entries", "Streak Tracker"]
with st.sidebar:
    page = option_menu(
        menu_title="",
        options=NAV_OPTIONS,
        icons=["mic-fill", "book", "fire"],
        default_index=0,
        orientation="vertical",
        styles={
            "icon": {"color": "#6b7280", "font-size": "18px"},
            "nav-link": {"font-size": "14px", "color": "#111827", "--hover-color": "#f3f4f6"},
            "nav-link-selected": {"background-color": "#e5e7eb", "font-weight": "600"},
        },
    )

# ==============================
# Helpers
# ==============================
def is_unavailable(s):
    return (not s) or str(s).strip().lower() in {"", "unavailable", "error"}

def simple_emotion_fallback(text):
    EMO_KEYWORDS = {
        "Happy": ["happy", "joy", "excited", "good", "great", "love"],
        "Sad": ["sad", "down", "lonely", "upset"],
        "Angry": ["angry", "mad", "furious"],
        "Stressed": ["stressed", "anxious", "tense"],
        "Calm": ["calm", "peaceful", "relaxed"],
    }
    t = text.lower()
    scores = {k: sum(t.count(w) for w in v) for k, v in EMO_KEYWORDS.items()}
    if not any(scores.values()):
        return "Calm"
    # item-based max to satisfy static analyzers
    return max(scores.items(), key=lambda kv: kv[1])[0]

def groq_generate(prompt, model="llama3-8b-8192"):
    if not groq_client:
        return "Unavailable"
    try:
        res = groq_client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": prompt}],
            temperature=0.7, max_tokens=600
        )
        return res.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Groq error: {e}")
        return "Unavailable"

def summary_fallback(text: str) -> str:
    """Very small offline summarizer: first 1-2 sentences or first 300 chars."""
    import re as _re
    sents = [_s.strip() for _s in _re.split(r"(?<=[.!?])\s+", text.strip()) if _s.strip()]
    if not sents:
        return text[:300]
    if len(sents) == 1:
        return sents[0][:300]
    return (sents[0] + " " + sents[1])[:400]

def reflections_fallback(text: str, emotion: str) -> str:
    """Template reflections when Groq is unavailable."""
    first_line = text.strip().splitlines()[0] if text.strip() else ""
    lines = [
        f"- You felt {emotion.lower()} while describing this.",
        (f"- You mentioned: {first_line[:120]}" if first_line else "- Recall one concrete moment from today that stands out."),
        "- What is one small step you can take tomorrow to support yourself?",
    ]
    return "\n".join(lines)

def process_text(transcription):
    """Handles emotion detection, summarization, and reflection (English only)."""
    # Emotion detection
    emo_prompt = f"Identify the main emotion (Happy, Sad, Angry, Calm, Stressed) from this journal entry:\n\n{transcription}"
    emotion = groq_generate(emo_prompt)
    if is_unavailable(emotion):
        emotion = simple_emotion_fallback(transcription)

    # Summary
    summary_prompt = f"Summarize this in 2 concise sentences:\n\n{transcription}"
    summary = groq_generate(summary_prompt)
    if is_unavailable(summary):
        summary = summary_fallback(transcription)

    # Reflections
    reflections_prompt = f"Write 3 insightful bullet reflections based on this entry:\n\n{transcription}"
    reflection = groq_generate(reflections_prompt)
    if is_unavailable(reflection):
        reflection = reflections_fallback(transcription, emotion)

    return {
        "emotion": emotion.strip(),
        "summary": summary.strip(),
        "reflection": reflection.strip()
    }

# ==============================
# JOURNAL PAGE
# ==============================
if page == "Journal":
    st.markdown("<h1>Private Audio Journaling</h1>", unsafe_allow_html=True)
    st.caption("English-only transcription mode. Deepgram handles speech, Groq handles reflection and summary.")

    starter = st.selectbox("Pick a conversation starter:", ["Person", "Event", "Incident", "Life Situation", "Other"])

    if hasattr(st, "audio_input"):
        audio_data = st.audio_input("🎙️ Record your journal (~60–90s):")
    else:
        st.warning("⚠️ Your Streamlit version doesn’t support st.audio_input. Upgrade to >=1.30.")
        audio_data = None

    if audio_data:
        with st.spinner("Processing your audio..."):
            try:
                # ---- Transcription (English only) ----
                if not DEEPGRAM_KEY:
                    st.error("Missing DEEPGRAM_API_KEY.")
                    transcription = ""
                else:
                    headers = {"Authorization": f"Token {DEEPGRAM_KEY}", "Content-Type": audio_data.type}
                    params = {
                        "model": "nova-2-general",
                        "smart_format": "true",
                        "language": "en"  # Force English
                    }
                    res = requests.post(
                        "https://api.deepgram.com/v1/listen",
                        headers=headers,
                        params=params,
                        data=audio_data.getvalue()
                    )
                    transcription = res.json().get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("transcript", "")

                if not transcription:
                    st.warning("No speech detected.")
                else:
                    # Show transcript first
                    st.markdown("<div class='uj-card'><h2>Transcript</h2><pre style='white-space:pre-wrap; font-size:.9rem; line-height:1.3;'>{}</pre></div>".format(transcription.replace('<','&lt;').replace('>','&gt;')), unsafe_allow_html=True)

                    outputs = process_text(transcription)

                    st.markdown(f"<div class='uj-card'><h2>Emotion</h2><p><strong>{outputs['emotion']}</strong></p></div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='uj-card'><h2>Summary</h2><p>{outputs['summary']}</p></div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='uj-card'><h2>Reflections</h2><pre style='white-space:pre-wrap; font-size:.9rem; line-height:1.35;'>{outputs['reflection']}</pre></div>", unsafe_allow_html=True)

                    st.download_button("⬇️ Export Reflections", outputs['reflection'], file_name="reflection_english.txt")

                    today = datetime.now().strftime("%Y-%m-%d")
                    c.execute("INSERT INTO entries (date, transcription, emotion, summary, reflection) VALUES (?, ?, ?, ?, ?)",
                              (today, transcription, outputs['emotion'], outputs['summary'], outputs['reflection']))
                    c.execute("INSERT OR REPLACE INTO streaks VALUES (?, COALESCE((SELECT count+1 FROM streaks WHERE date=?), 1))",
                              (today, today))
                    conn.commit()
                    st.success("✅ Saved privately.")
            except Exception as e:
                st.error(f"Error: {e}")

# ==============================
# PAST ENTRIES PAGE
# ==============================
elif page == "Past Entries":
    st.markdown("<h1>Past Journal Entries</h1>", unsafe_allow_html=True)
    c.execute("SELECT date, emotion, summary FROM entries ORDER BY date DESC LIMIT 10")
    entries = c.fetchall()
    if not entries:
        st.info("No entries yet.")
    for date, emotion, summary in entries:
        st.markdown(f"<div class='uj-card'><h2>{date} – {emotion}</h2><p>{summary}</p></div>", unsafe_allow_html=True)

# ==============================
# STREAK TRACKER PAGE
# ==============================
elif page == "Streak Tracker":
    st.markdown("<h1>Streak Tracker</h1>", unsafe_allow_html=True)
    c.execute("SELECT COUNT(*) FROM streaks")
    total = c.fetchone()[0]
    st.metric("Total Journal Days", total)
    c.execute("SELECT date, count FROM streaks ORDER BY date DESC LIMIT 30")
    for d, c_ in c.fetchall():
        st.markdown(f"<div class='uj-card'><p><strong>{d}</strong> — {c_} entry</p></div>", unsafe_allow_html=True)

conn.close()
