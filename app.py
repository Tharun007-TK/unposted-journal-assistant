import os
import streamlit as st
import requests
from datetime import datetime
import sqlite3
from dotenv import load_dotenv
from cryptography.fernet import Fernet
import logging
from groq import Groq
import re

# ==============================
# Setup
# ==============================
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

"""Environment variable contract:
Required for full functionality (transcription + Groq integration):
    DEEPGRAM_API_KEY  -> Deepgram audio transcription
    GROQ_API_KEY      -> Groq text generation (optional; fallbacks used if missing)
    FERNET_KEY        -> Optional encryption key for local sensitive fields
    LOCAL_DB_PATH     -> Path to SQLite DB file (default: journal_data.db)

This app will degrade gracefully if keys are missing: transcription and/or
LLM enhancements become unavailable, but journaling still works locally.
"""

# API / App Keys
DEEPGRAM_KEY = os.getenv("DEEPGRAM_API_KEY")
FERNET_KEY = os.getenv("FERNET_KEY")
GROQ_KEY = os.getenv("GROQ_API_KEY")
DB_PATH = os.getenv("LOCAL_DB_PATH", "journal_data.db")

# Create Groq client only if key is provided
groq_client = Groq(api_key=GROQ_KEY) if GROQ_KEY else None

# DB Setup (ensure directory exists if a path component is present)
db_dir = os.path.dirname(DB_PATH)
if db_dir and not os.path.exists(db_dir):
    try:
        os.makedirs(db_dir, exist_ok=True)
    except OSError as e:
        logger.warning(f"Could not create DB directory '{db_dir}': {e}")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS streaks (date TEXT PRIMARY KEY, count INTEGER)''')
c.execute('''CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY,
    date TEXT,
    transcription TEXT,
    emotion TEXT,
    summary TEXT,
    reflection TEXT
)''')
conn.commit()

# Encryption setup (optional)
fernet = Fernet(FERNET_KEY.encode()) if FERNET_KEY else None

# Streamlit setup
st.set_page_config(page_title="Unposted: Private Audio Journaling", layout="centered")

st.title("🎙️ Unposted - Private Audio Journaling Assistant")
st.write("Private by default. Speak your thoughts. Get reflections, emotions, and next prompts.")

# ==============================
# Navigation
# ==============================
page = st.sidebar.radio("Navigation", ["Journal", "Past Entries", "Streak Tracker"])

# ==============================
# Helper Functions
# ==============================

def groq_generate(prompt: str, model="llama3-8b-8192"):
    """Generic Groq text generation function"""
    try:
        if groq_client is None:
            return "Unavailable"
        response = groq_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=400
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Groq generation failed: {e}")
        return "Unavailable"

# ---- Fallbacks when Groq isn't available ----
EMO_LABELS = ["Happy", "Sad", "Angry", "Calm", "Stressed"]

EMO_KEYWORDS = {
    "Happy": ["happy", "joy", "joyful", "excited", "good", "great", "love", "grateful", "proud"],
    "Sad": ["sad", "down", "depressed", "blue", "tired", "lonely", "upset", "cry", "unhappy"],
    "Angry": ["angry", "mad", "furious", "frustrated", "annoyed", "irritated", "rage"],
    "Stressed": ["stressed", "anxious", "overwhelmed", "worried", "nervous", "tense", "pressure"],
    "Calm": ["calm", "peaceful", "relaxed", "okay", "fine"]
}


def is_unavailable(s: str) -> bool:
    return (s is None) or (str(s).strip().lower() in {"", "unavailable", "error", "n/a"})


def simple_emotion_fallback(text: str) -> str:
    t = text.lower()
    scores = {k: 0 for k in EMO_LABELS}
    for label, kws in EMO_KEYWORDS.items():
        for kw in kws:
            scores[label] += t.count(kw)
    # tie-break: prefer Calm if no signal, else max
    if all(v == 0 for v in scores.values()):
        return "Calm"
    return max(scores, key=scores.get)


def sanitize_emotion_label(raw: str) -> str:
    if is_unavailable(raw):
        return "Calm"
    rl = str(raw).strip().lower()
    for lab in EMO_LABELS:
        if lab.lower() in rl:
            return lab
    # fallback to first token
    tok = rl.split()[0] if rl.split() else "calm"
    tok = re.sub(r"[^a-z]", "", tok)
    if tok in [l.lower() for l in EMO_LABELS]:
        return tok.capitalize()
    return "Calm"


def summary_fallback(text: str) -> str:
    sents = re.split(r"(?<=[.!?])\s+", text.strip())
    sents = [s.strip() for s in sents if s.strip()]
    if not sents:
        return text[:200]
    if len(sents) == 1:
        return sents[0][:300]
    return (sents[0] + " " + sents[1])[:400]


def reflections_fallback(text: str) -> str:
    # simple template-based reflections
    emo = simple_emotion_fallback(text)
    first_line = text.strip().splitlines()[0] if text.strip() else ""
    pts = [
        f"It sounds like you felt {emo.lower()} while describing this.",
        (f"A key point you mentioned: {first_line[:120]}" if first_line else "Recall one concrete moment from today that stands out."),
        "What is one small step you can take tomorrow to support yourself?"
    ]
    return "\n".join(f"- {p}" for p in pts)


# ==============================
# JOURNAL PAGE
# ==============================
if page == "Journal":
    starter = st.selectbox("Pick a conversation starter:", ["Person", "Event", "Incident", "Life Situation", "Other"])
    audio_data = st.audio_input("Tap to record your journal (~60–90s):")

    if audio_data is not None:
        try:
            if not DEEPGRAM_KEY:
                st.error("Transcription unavailable: DEEPGRAM_API_KEY not set. Add it to your .env (not committed).")
                transcription = ""
            else:
                with st.spinner("Transcribing audio with Deepgram..."):
                    headers = {"Authorization": f"Token {DEEPGRAM_KEY}"}
                    params = {"model": "nova-2-general", "smart_format": "true"}

                    response = requests.post(
                        "https://api.deepgram.com/v1/listen",
                        headers=headers,
                        params=params,
                        data=audio_data.read(),
                        timeout=60
                    )
                    response.raise_for_status()
                    dg_data = response.json()
                    transcription = dg_data["results"]["channels"][0]["alternatives"][0]["transcript"].strip()

            if not transcription:
                st.warning("No speech detected. Please try recording again.")
            else:
                if not GROQ_KEY:
                    st.info("GROQ_API_KEY not set. Using on-device fallbacks for emotion, summary, and reflections.")

                st.subheader("📝 Transcript")
                st.write(transcription)

                # =========================
                # Emotion Analysis (Groq + fallback)
                # =========================
                emo_prompt = (
                    "Analyze the emotion expressed in the following journal entry and return only the primary emotion "
                    "(e.g., Happy, Sad, Angry, Calm, Stressed):\n\n" + transcription
                )
                emo_raw = groq_generate(emo_prompt) if GROQ_KEY else "Unavailable"
                emo_label = sanitize_emotion_label(emo_raw) if not is_unavailable(emo_raw) else simple_emotion_fallback(transcription)

                # =========================
                # Summary Generation (Groq + fallback)
                # =========================
                summary_prompt = "Summarize this journal entry in 2 concise sentences:\n\n" + transcription
                summary_text = groq_generate(summary_prompt) if GROQ_KEY else "Unavailable"
                if is_unavailable(summary_text):
                    summary_text = summary_fallback(transcription)

                # =========================
                # Reflection Generation (Groq + fallback)
                # =========================
                reflection_prompt = (
                    "Write three insightful reflections based on this journal entry. "
                    "Return 3 bullet points only.\n\n" + transcription + "\n\nReflections:"
                )
                reflection_output = groq_generate(reflection_prompt) if GROQ_KEY else "Unavailable"
                if is_unavailable(reflection_output):
                    reflection_output = reflections_fallback(transcription)

                # =========================
                # Display Outputs
                # =========================
                st.subheader("💭 Reflections")
                st.write(reflection_output)

                st.subheader("🧭 Emotion Analysis")
                st.metric("Detected Emotion", emo_label)

                st.subheader("✨ Follow-up Prompt for Tomorrow")
                follow_prompt = f"What made you feel {emo_label.lower()} today? Reflect more on it tomorrow."
                st.write(follow_prompt)

                # =========================
                # Store Entry & Streaks
                # =========================
                today = datetime.now().strftime("%Y-%m-%d")
                c.execute("SELECT count FROM streaks WHERE date=?", (today,))
                result = c.fetchone()
                new_count = (result[0] + 1) if result else 1
                c.execute("INSERT OR REPLACE INTO streaks VALUES (?, ?)", (today, new_count))

                c.execute(
                    "INSERT INTO entries (date, transcription, emotion, summary, reflection) VALUES (?, ?, ?, ?, ?)",
                    (today, transcription, emo_label, summary_text, reflection_output)
                )
                conn.commit()

                st.success("Journal saved locally and privately.")
                st.download_button("Export Reflections", reflection_output, file_name="reflections.txt")

        except requests.exceptions.RequestException as e:
            st.error(f"API Error: {e}. Please check your API key or internet connection.")
            logger.error(f"Request failed: {e}")
        except Exception as e:
            st.error(f"Unexpected error: {e}")
            logger.error(f"Unexpected error: {e}")

# ==============================
# PAST ENTRIES PAGE
# ==============================
elif page == "Past Entries":
    st.subheader("📚 Your Journal Entries")
    c.execute("SELECT date, emotion, summary FROM entries ORDER BY date DESC LIMIT 10")
    entries = c.fetchall()

    if entries:
        for date, emotion, summary in entries:
            with st.expander(f"{date} - {emotion}"):
                st.write(summary)
    else:
        st.info("No entries yet. Start journaling!")

# ==============================
# STREAK TRACKER PAGE
# ==============================
elif page == "Streak Tracker":
    st.subheader("🔥 Your Streak")
    c.execute("SELECT COUNT(*) FROM streaks")
    total_days = c.fetchone()[0]
    st.metric("Total Journal Days", total_days)

    c.execute("SELECT date, count FROM streaks ORDER BY date DESC LIMIT 30")
    recent_streaks = c.fetchall()

    if recent_streaks:
        st.write("Recent Activity:")
        for date, count in recent_streaks:
            st.write(f"{date}: {count} entry")
    else:
        st.info("No streak data yet.")

conn.close()