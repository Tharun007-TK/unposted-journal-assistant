# Unposted: Private Audio Journaling Assistant

Unposted is a Streamlit application for recording short voice journal entries privately on your machine. It transcribes audio (Deepgram) and optionally enriches entries with emotion analysis, summaries, and reflections using Groq LLM. When API keys are absent, the app falls back to lightweight on-device heuristics so you can still journal.

## Features
- Record ~60–90s audio entries directly in the browser (Streamlit)
- Transcription via Deepgram API (optional)
- Emotion detection, summary, and reflection generation via Groq API (optional)
- Graceful fallback heuristics when LLM/transcription keys are missing
- Local SQLite storage of entries and daily streak tracking
- Basic privacy: data lives locally; optional Fernet encryption key hook

## Quick Start
1. Clone and enter the project directory:
```powershell
git clone <your-repo-url>
cd unposted-working-streamlit
```
2. Create and populate your `.env` (never commit it):
```bash
cp .env.example .env
```
Fill in: `DEEPGRAM_API_KEY`, `GROQ_API_KEY`, optionally `FERNET_KEY` and adjust `LOCAL_DB_PATH`.
Generate a Fernet key:
```powershell
python key.py
```
3. Install dependencies (using a venv recommended):
```powershell
python -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
4. Run the app:
```powershell
streamlit run app.py
```

## Environment Variables
| Variable | Required | Purpose |
|----------|----------|---------|
| DEEPGRAM_API_KEY | Optional (needed for transcription) | Deepgram audio transcription API key |
| GROQ_API_KEY | Optional | Groq LLM for summarization/emotion/reflections |
| FERNET_KEY | Optional | Encryption key if you later encrypt specific fields |
| LOCAL_DB_PATH | Optional | Custom path to SQLite DB file (defaults `journal_data.db`) |
| HUGGINGFACE_API_KEY | Optional (future use) | Hugging Face models integration |

Missing keys simply disable related features; journaling still works.

## Testing
A minimal test ensures the module imports:
```powershell
pytest -q
```

## Security & Privacy
- Data stored locally in SQLite; not uploaded.
- Do **not** commit your real `.env`.
- Consider enabling disk encryption and keeping backups.
- Fernet support is scaffolded; currently plaintext storage. Extend by encrypting `transcription` before insert.

## Roadmap / Future Improvements
- Encrypt transcription and reflections when `FERNET_KEY` provided
- Add CI workflow (GitHub Actions) for lint + tests
- Pre-commit hooks (black, isort, ruff)
- More nuanced emotion model (local transformer)
- Option to export to markdown or JSON bundle

## License
MIT License (see `LICENSE`).

## Acknowledgements
- Deepgram for speech-to-text
- Groq for LLM text generation
- Streamlit framework

Enjoy private, reflective journaling! ✨
