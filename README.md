# 🎬 Trending Movies Bot (CinePulse)

A full-stack Flask + SQLite web application that automatically tracks trending movies & TV shows across India and Worldwide, today's releases, upcoming releases, and top-rated titles with live IMDb ratings, OTT watch providers, and official YouTube trailers.

---

## 🌟 Features

- **🔥 Trending India & 🌍 Trending Worldwide**: Real-time trending movies & TV shows.
- **🆕 Today's Releases & 📅 Coming Soon**: Theatrical and digital release tracker.
- **⭐ Top Rated (8+ IMDb)**: Curated high-rated cinema section.
- **🍿 OTT Watch Providers**: Automatically detects streaming availability (Netflix, Prime Video, Disney+ Hotstar, JioCinema, Zee5, etc.).
- **🎥 Embedded YouTube Trailers**: Watch trailers directly in an interactive modal.
- **🔍 Instant Client-Side Search & Multi-Filters**: Real-time title search with Genre and Language filter dropdowns.
- **⏰ Automated Background Scheduler (APScheduler)**: Automatically syncs fresh data every 8 hours.
- **⚡ Instant Out-of-the-Box Demo Mode**: Pre-seeded with realistic trending data so you can test immediately before adding API keys.

---

## 📁 Project Structure

```
trending-movies-bot/
├── app.py              # Flask server & APScheduler background job runner
├── update_data.py      # TMDb & OMDb API fetcher, parser & SQLite updater
├── database.py         # SQLite database schema and query helpers
├── config.py           # API keys and app configuration
├── requirements.txt    # Python dependencies (Flask, requests, apscheduler)
├── templates/
│   └── index.html      # Netflix-style dark UI template
├── static/
│   ├── style.css       # Obsidian & neon dark theme styles
│   └── script.js       # Client-side filtering, modal, and animations
└── README.md
```

---

## 🚀 Getting Started

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure API Keys (Optional but Recommended)
Open [`config.py`](file:///config.py) and insert your free API keys:
- **TMDb API Key**: [Get free key here](https://www.themoviedb.org/settings/api)
- **OMDb API Key**: [Get free key here](http://www.omdbapi.com/apikey.aspx)

```python
# In config.py:
TMDB_API_KEY = "your_actual_tmdb_api_key"
OMDB_API_KEY = "your_actual_omdb_api_key"
```

> *Note: If keys are left as default placeholders, the app automatically runs in Demo Mode with pre-seeded trending titles.*

### 3. Run the Application
```bash
python app.py
```
Open your browser and navigate to:
**`http://127.0.0.1:5000`**

---

## ⚙️ How It Works

1. When `app.py` starts, it initializes `database.db` and launches an `APScheduler` background job that runs `update_data.py` every **8 hours**.
2. `update_data.py` queries TMDb endpoints for India & Global trending, now playing, and upcoming titles.
3. For each title, it resolves external IDs to query OMDb for accurate IMDb ratings, queries watch providers in India, and retrieves YouTube trailers.
4. Data is stored into SQLite using conflict-safe upserts.
5. `app.py` passes the data as JSON to `templates/index.html`, enabling instant zero-latency client-side search and filtering.
