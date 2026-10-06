import json
import logging
import threading
from flask import Flask, render_template, jsonify, request
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

from config import UPDATE_INTERVAL_HOURS, TMDB_API_KEY, OMDB_API_KEY, OTT_SEARCH_URLS, TRIGGER_SECRET_KEY, HOME_ROWS
from database import (
    init_db,
    get_all_movies,
    get_movies_by_category,
    get_top_rated,
    get_latest_update_timestamp,
    get_all_free_movies,
    get_free_movies_languages
)
from update_data import fetch_and_update_all, is_key_configured

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

def setup_scheduler():
    """Configure and start APScheduler background job running every 24 hours."""
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        func=fetch_and_update_all,
        trigger="interval",
        hours=UPDATE_INTERVAL_HOURS,
        id="trending_movies_update_job",
        name="Fetch & Update Trending Movies Every 24 Hours",
        replace_existing=True
    )
    scheduler.start()
    logger.info(f"APScheduler background job started. Runs every {UPDATE_INTERVAL_HOURS} hours.")
    atexit.register(lambda: scheduler.shutdown(wait=False))
    return scheduler

# Initialize SQLite database and run initial sync if needed
init_db()
if not get_all_movies() or not get_all_free_movies():
    logger.info("Database is empty or missing free movies on start. Running initial fetch...")
    fetch_and_update_all()
elif not get_movies_by_category("top10_india"):
    # Existing DB from the older version: fetch the new rows without blocking server start
    logger.info("New category rows missing. Running background sync...")
    threading.Thread(target=fetch_and_update_all, name="InitialCategorySync", daemon=True).start()

# Start the background scheduler
scheduler = setup_scheduler()

# Navbar pages: slug -> (label, url path)
PAGES = {
    "home": ("Home", "/"),
    "movies": ("Movies", "/movies"),
    "tv": ("TV Shows", "/tv-shows"),
    "web-series": ("Web Series", "/web-series"),
}

def get_grouped_movie_data():
    """Compile structured dictionary of movies organized by home-page rows and metadata."""
    all_movies = get_all_movies()
    
    data = {}
    for row in HOME_ROWS:
        key = row["key"]
        if row["type"] == "free":
            continue
        data[key] = get_top_rated(min_rating=8.0) if key == "top_rated" else get_movies_by_category(key)
    
    # Free full movies from verified YouTube channels
    free_movies = get_all_free_movies()
    free_movies_languages = get_free_movies_languages()
    
    # Group free movies by language
    free_movies_by_language = {}
    for fm in free_movies:
        free_movies_by_language.setdefault(fm.get("language", "Other"), []).append(fm)
    
    # Extract distinct genres and languages for filter dropdowns
    genres_set = set()
    languages_set = set()
    for m in all_movies:
        if m.get("genres"):
            for g in m["genres"].split(","):
                cleaned = g.strip()
                if cleaned:
                    genres_set.add(cleaned)
        if m.get("language"):
            languages_set.add(m["language"].strip().upper())
    
    data.update({
        "rows": HOME_ROWS,
        "free_movies": free_movies,
        "free_movies_by_language": free_movies_by_language,
        "free_movies_languages": free_movies_languages,
        "genres": sorted(genres_set),
        "languages": sorted(languages_set),
        "last_updated": get_latest_update_timestamp(),
        "is_demo_mode": not is_key_configured(TMDB_API_KEY),
        "ott_search_urls": OTT_SEARCH_URLS
    })
    return data

def render_page(page):
    """Render the single-page Netflix-style UI for a navbar page (home/movies/tv/web-series)."""
    data = get_grouped_movie_data()
    return render_template(
        "index.html",
        initial_data_json=json.dumps(data).replace("</", "<\\/"),
        last_updated=data["last_updated"],
        is_demo_mode=data["is_demo_mode"],
        active_page=page,
        pages=PAGES
    )

@app.route("/")
def index():
    """Home - all category rows."""
    return render_page("home")

@app.route("/movies")
def movies_page():
    """Movies only."""
    return render_page("movies")

@app.route("/tv-shows")
def tv_shows_page():
    """TV shows only."""
    return render_page("tv")

@app.route("/web-series")
def web_series_page():
    """Web series (TV titles from OTT / regional rows)."""
    return render_page("web-series")

@app.route("/api/movies", methods=["GET"])
def api_movies():
    """API endpoint to get all structured movie data as JSON."""
    return jsonify(get_grouped_movie_data())

@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    """API endpoint to manually trigger an immediate data update from TMDb & OMDb."""
    try:
        fetch_and_update_all()
        return jsonify({
            "status": "success",
            "message": "Movie data refreshed successfully!",
            "data": get_grouped_movie_data()
        })
    except Exception as e:
        logger.error(f"Manual refresh failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/trigger-update", methods=["GET"])
def trigger_update():
    """Secure endpoint to trigger data update in background via secret key query parameter."""
    provided_key = request.args.get("key")
    if not provided_key or provided_key != TRIGGER_SECRET_KEY:
        return jsonify({
            "status": "error",
            "message": "Forbidden: Invalid or missing secret key"
        }), 403

    # Run update in a background thread so the HTTP request does not time out
    thread = threading.Thread(
        target=fetch_and_update_all,
        name="ManualTriggerUpdateThread",
        daemon=True
    )
    thread.start()
    return jsonify({
        "status": "success",
        "message": "Update triggered"
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
