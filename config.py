import os

# ==============================================================================
# API CONFIGURATION
# ==============================================================================
# 1. Get your free TMDb API Key: https://www.themoviedb.org/settings/api
# 2. Get your free OMDb API Key: http://www.omdbapi.com/apikey.aspx
#
# Replace the placeholder strings below with your real API keys,
# or set them as environment variables (TMDB_API_KEY and OMDB_API_KEY).
# ==============================================================================

# >>> INSERT YOUR TMDB API KEY HERE <<<
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "01252dd9dd6c80ec7621b17c4feae71e")

# >>> INSERT YOUR OMDB API KEY HERE <<<
OMDB_API_KEY = os.getenv("OMDB_API_KEY", "8b173f0f")


# Secret key for the secure manual trigger endpoint (/trigger-update?key=...)
TRIGGER_SECRET_KEY = os.getenv("TRIGGER_SECRET_KEY", "cinepulse-splasdf54248ase247ase2y2h5lkj6712")


# ==============================================================================
# APPLICATION & DATABASE CONFIGURATION
# ==============================================================================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "database.db")

# Scheduler interval (in hours) to fetch new trending movie data
UPDATE_INTERVAL_HOURS = 24

# TMDb Base URL
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
TMDB_BACKDROP_BASE_URL = "https://image.tmdb.org/t/p/original"

# OMDb Base URL
OMDB_BASE_URL = "http://www.omdbapi.com/"

# Default Placeholder Poster URL for items with missing or broken posters
PLACEHOLDER_POSTER_URL = "/static/placeholder_poster.svg"

# OTT Provider Search URL Templates
OTT_SEARCH_URLS = {
    "Netflix": "https://www.netflix.com/search?q={query}",
    "Amazon Prime Video": "https://www.primevideo.com/search/?phrase={query}",
    "Prime Video": "https://www.primevideo.com/search/?phrase={query}",
    "Amazon Video": "https://www.primevideo.com/search/?phrase={query}",
    "Amazon MX Player": "https://www.mxplayer.in/?search=true&q={query}",
    "MX Player": "https://www.mxplayer.in/?search=true&q={query}",
    "JioCinema": "https://www.jiocinema.com/search/{query}",
    "JioHotstar": "https://www.hotstar.com/in/search?q={query}",
    "Disney+ Hotstar": "https://www.hotstar.com/in/search?q={query}",
    "Disney Plus Hotstar": "https://www.hotstar.com/in/search?q={query}",
    "Hotstar": "https://www.hotstar.com/in/search?q={query}",
    "SonyLIV": "https://www.sonyliv.com/search/{query}",
    "Sony LIV": "https://www.sonyliv.com/search/{query}",
    "Sony Liv": "https://www.sonyliv.com/search/{query}",
    "ZEE5": "https://www.zee5.com/search/{query}",
    "Zee5": "https://www.zee5.com/search/{query}",
    "TVFPlay": "https://tvfplay.com/search?q={query}",
    "TVF Play": "https://tvfplay.com/search?q={query}",
    "Aha": "https://www.aha.video/search?q={query}",
    "Apple TV": "https://tv.apple.com/search?term={query}",
    "Apple TV Plus": "https://tv.apple.com/search?term={query}",
    "YouTube": "https://www.youtube.com/results?search_query={query}",
    "Google Play Movies": "https://play.google.com/store/search?q={query}&c=movies",
    "BookMyShow": "https://in.bookmyshow.com/explore/movies?search={query}",
    "In Theatres": "https://in.bookmyshow.com/explore/movies?search={query}"
}

# ==============================================================================
# YOUTUBE DATA API CONFIGURATION (FOR FREE FULL MOVIES)
# ==============================================================================
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "AIzaSyDBUTXnhYVGIO72cehKU330JAOhCW18REY")
YOUTUBE_BASE_URL = "https://www.googleapis.com/youtube/v3"

# Official verified YouTube channel queries for legal full-length movies
YOUTUBE_OFFICIAL_CHANNELS = {
    "Hindi": [
        {"query": "Shemaroo Movies Hindi full movie", "channel_name": "Shemaroo Movies"},
        {"query": "Goldmines Hindi full movie", "channel_name": "Goldmines"},
        {"query": "Zee Classics Hindi full movie", "channel_name": "Zee Classics"},
        {"query": "Tips Official Hindi full movie", "channel_name": "Tips Official"},
        {"query": "Pen Movies Hindi full movie", "channel_name": "Pen Movies"},
        {"query": "Rajshri Hindi full movie", "channel_name": "Rajshri"},
        {"query": "Ultra Movie Parlour Hindi full movie", "channel_name": "Ultra Movie Parlour"},
    ],
    "English": [
        {"query": "FilmRise Movies full movie", "channel_name": "FilmRise Movies"},
        {"query": "PizzaFlix classic full movie", "channel_name": "PizzaFlix"},
        {"query": "Popcornflix full movie", "channel_name": "Popcornflix"},
        {"query": "YouTube Movies Free full length", "channel_name": "YouTube Movies"},
    ],
    "Korean": [
        {"query": "Korean Classic Film KOFA full movie", "channel_name": "Korean Classic Film"},
        {"query": "Korean Film Archive full length movie", "channel_name": "KOFA Archive"},
    ]
}

# ==============================================================================
# HOME PAGE ROWS (Netflix-style horizontal sliders)
# ------------------------------------------------------------------------------
# key    : movies.category value in SQLite (or special: top_rated / free_movies)
# type   : "top10" (big numbers) | "row" | "free" (YouTube free movies)
# series : True => also shown on the Web Series page (TV items only)
# ==============================================================================
HOME_ROWS = [
    {"key": "top10_india",        "title": "Top 10 in India Today",                "type": "top10", "series": True},
    {"key": "trending_india",     "title": "Trending in India",                    "type": "row",   "series": True},
    {"key": "trending_world",     "title": "Trending Worldwide",                   "type": "row",   "series": True},
    {"key": "today_release",      "title": "Releasing Today",                      "type": "row",   "series": False},
    {"key": "mx_player_movies",   "title": "Free Movies on Amazon MX Player",      "type": "row",   "series": False},
    {"key": "mx_player_series",   "title": "Free Web Series on Amazon MX Player",  "type": "row",   "series": True},
    {"key": "free_to_watch",      "title": "Free to Watch",                        "type": "row",   "series": True},
    {"key": "hindi",              "title": "Hindi",                                "type": "row",   "series": True},
    {"key": "south_indian",       "title": "South Indian",                         "type": "row",   "series": True},
    {"key": "korean",             "title": "Korean",                               "type": "row",   "series": True},
    {"key": "hollywood",          "title": "Hollywood",                            "type": "row",   "series": False},
    {"key": "web_series",         "title": "Web Series",                           "type": "row",   "series": True},
    {"key": "anime",              "title": "Anime",                                "type": "row",   "series": True},
    {"key": "genre_action",       "title": "Action",                               "type": "row",   "series": False},
    {"key": "genre_thriller",     "title": "Thriller",                             "type": "row",   "series": False},
    {"key": "genre_comedy",       "title": "Comedy",                               "type": "row",   "series": False},
    {"key": "genre_romance",      "title": "Romance",                              "type": "row",   "series": False},
    {"key": "genre_horror",       "title": "Horror",                               "type": "row",   "series": False},
    {"key": "ott_netflix",        "title": "Popular on Netflix",                   "type": "row",   "series": True},
    {"key": "ott_prime",          "title": "Popular on Prime Video",               "type": "row",   "series": True},
    {"key": "ott_hotstar",        "title": "Popular on Hotstar",                   "type": "row",   "series": True},
    {"key": "ott_zee5",           "title": "Popular on Zee5",                      "type": "row",   "series": True},
    {"key": "new_on_ott",         "title": "New on OTT",                           "type": "row",   "series": True},
    {"key": "top_rated",          "title": "Top Rated 8+",                         "type": "row",   "series": True},
    {"key": "coming_soon",        "title": "Coming Soon",                          "type": "row",   "series": False},
    {"key": "free_movies",        "title": "Free Movies",                          "type": "free",  "series": False},
]

# TMDb watch-provider IDs (region IN) used for OTT rows
OTT_PROVIDER_IDS = {
    "netflix": 8,
    "prime": 119,
    "hotstar": "122|2336",
    "zee5": 232,
    "sonyliv": 237,
    "mx_player": "1898|515",
}
