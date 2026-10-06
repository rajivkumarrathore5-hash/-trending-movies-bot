import sqlite3
import os
from datetime import datetime
from config import DATABASE_PATH

def get_db_connection():
    """Create a database connection with dict-like row access."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the SQLite database and create tables if they do not exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tmdb_id INTEGER,
            media_type TEXT DEFAULT 'movie',
            title TEXT NOT NULL,
            poster_url TEXT,
            backdrop_url TEXT,
            release_date TEXT,
            imdb_rating REAL,
            overview TEXT,
            genres TEXT,
            language TEXT,
            trailer_youtube_key TEXT,
            watch_provider TEXT,
            category TEXT NOT NULL,
            rank_order INTEGER,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(tmdb_id, media_type, category)
        )
    """)
    
    # Lightweight migration for databases created before rank_order existed
    cursor.execute("PRAGMA table_info(movies)")
    existing_cols = {row["name"] for row in cursor.fetchall()}
    if "rank_order" not in existing_cols:
        cursor.execute("ALTER TABLE movies ADD COLUMN rank_order INTEGER")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS free_movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            youtube_video_id TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            thumbnail_url TEXT,
            channel_name TEXT,
            channel_id TEXT,
            language TEXT NOT NULL,
            published_at TEXT,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_category ON movies(category);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_imdb_rating ON movies(imdb_rating);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_free_lang ON free_movies(language);")
    
    conn.commit()
    conn.close()

# Single shared UPSERT statement. UNIQUE(tmdb_id, media_type, category) guarantees no duplicates.
_UPSERT_SQL = """
    INSERT INTO movies (
        tmdb_id, media_type, title, poster_url, backdrop_url, release_date,
        imdb_rating, overview, genres, language, trailer_youtube_key,
        watch_provider, category, rank_order, last_updated
    ) VALUES (
        :tmdb_id, :media_type, :title, :poster_url, :backdrop_url, :release_date,
        :imdb_rating, :overview, :genres, :language, :trailer_youtube_key,
        :watch_provider, :category, :rank_order, :last_updated
    )
    ON CONFLICT(tmdb_id, media_type, category) DO UPDATE SET
        title = excluded.title,
        poster_url = excluded.poster_url,
        backdrop_url = excluded.backdrop_url,
        release_date = excluded.release_date,
        imdb_rating = excluded.imdb_rating,
        overview = excluded.overview,
        genres = excluded.genres,
        language = excluded.language,
        trailer_youtube_key = excluded.trailer_youtube_key,
        watch_provider = excluded.watch_provider,
        rank_order = excluded.rank_order,
        last_updated = excluded.last_updated
"""

def _movie_params(movie_data, now):
    return {
        'tmdb_id': movie_data.get('tmdb_id'),
        'media_type': movie_data.get('media_type', 'movie'),
        'title': movie_data.get('title'),
        'poster_url': movie_data.get('poster_url', ''),
        'backdrop_url': movie_data.get('backdrop_url', ''),
        'release_date': movie_data.get('release_date', ''),
        'imdb_rating': movie_data.get('imdb_rating'),
        'overview': movie_data.get('overview', ''),
        'genres': movie_data.get('genres', ''),
        'language': movie_data.get('language', ''),
        'trailer_youtube_key': movie_data.get('trailer_youtube_key', ''),
        'watch_provider': movie_data.get('watch_provider', ''),
        'category': movie_data.get('category'),
        'rank_order': movie_data.get('rank_order'),
        'last_updated': now
    }

def upsert_movie(movie_data):
    """
    Insert or update a movie item in the database.
    movie_data is expected to be a dict containing keys matching table columns.
    """
    conn = get_db_connection()
    now = datetime.utcnow().isoformat()
    conn.execute(_UPSERT_SQL, _movie_params(movie_data, now))
    conn.commit()
    conn.close()

def upsert_movies_batch(movies_list):
    """Batch upsert multiple movies."""
    if not movies_list:
        return
    conn = get_db_connection()
    now = datetime.utcnow().isoformat()
    for movie in movies_list:
        conn.execute(_UPSERT_SQL, _movie_params(movie, now))
    conn.commit()
    conn.close()

def get_all_movies():
    """Retrieve all movies as a list of dicts."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM movies ORDER BY imdb_rating DESC NULLS LAST, release_date DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_movies_by_category(category):
    """
    Retrieve all movies for a given category.
    Ordered by the TMDb-derived rank (popularity position) when available,
    falling back to rating. 'coming_soon' is ordered by nearest release first.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    if category == "coming_soon":
        order = "release_date ASC, imdb_rating DESC NULLS LAST"
    else:
        order = ("CASE WHEN rank_order IS NULL THEN 1 ELSE 0 END, rank_order ASC, "
                 "imdb_rating DESC NULLS LAST, release_date DESC")
    cursor.execute(f"SELECT * FROM movies WHERE category = ? ORDER BY {order}", (category,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_top_rated(min_rating=8.0, limit=60):
    """Retrieve distinct titles with an IMDb rating of min_rating or higher."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM movies 
        WHERE imdb_rating >= ? AND poster_url IS NOT NULL AND poster_url != ''
        GROUP BY tmdb_id, media_type
        ORDER BY imdb_rating DESC, release_date DESC
        LIMIT ?
        """,
        (min_rating, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_latest_update_timestamp():
    """Retrieve the most recent last_updated timestamp in the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(last_updated) as max_updated FROM movies")
    row = cursor.fetchone()
    conn.close()
    return row['max_updated'] if row and row['max_updated'] else None

def purge_stale_category_rows(category, before_ts):
    """
    Remove rows of a category that were not refreshed in the current sync run
    (last_updated older than before_ts). Keeps daily-refreshed rows (Top 10, trending...) current.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM movies WHERE category = ? AND last_updated < ?",
        (category, before_ts)
    )
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted

def cleanup_stale_category_movies(today_str=None):
    """
    Remove stale entries from 'coming_soon' (where release_date is today or in the past)
    and from 'today_release' (where release_date is not today).
    """
    if not today_str:
        today_str = datetime.now().strftime("%Y-%m-%d")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Remove items from coming_soon that are released today or earlier, or have no valid future date
    cursor.execute("""
        DELETE FROM movies 
        WHERE category = 'coming_soon' 
          AND (release_date <= ? OR release_date IS NULL OR release_date = '')
    """, (today_str,))
    deleted_coming_soon = cursor.rowcount
    
    # 2. Remove items from today_release that do not match today's date
    cursor.execute("""
        DELETE FROM movies 
        WHERE category = 'today_release' 
          AND (release_date != ? OR release_date IS NULL OR release_date = '')
    """, (today_str,))
    deleted_today_release = cursor.rowcount
    
    conn.commit()
    conn.close()
    return {"coming_soon": deleted_coming_soon, "today_release": deleted_today_release}


def upsert_free_movie(movie_data):
    """Insert or update a free full YouTube movie."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    
    cursor.execute("""
        INSERT INTO free_movies (
            youtube_video_id, title, thumbnail_url, channel_name,
            channel_id, language, published_at, last_updated
        ) VALUES (
            :youtube_video_id, :title, :thumbnail_url, :channel_name,
            :channel_id, :language, :published_at, :last_updated
        )
        ON CONFLICT(youtube_video_id) DO UPDATE SET
            title = excluded.title,
            thumbnail_url = excluded.thumbnail_url,
            channel_name = excluded.channel_name,
            channel_id = excluded.channel_id,
            language = excluded.language,
            published_at = excluded.published_at,
            last_updated = excluded.last_updated
    """, {
        'youtube_video_id': movie_data.get('youtube_video_id'),
        'title': movie_data.get('title'),
        'thumbnail_url': movie_data.get('thumbnail_url', ''),
        'channel_name': movie_data.get('channel_name', ''),
        'channel_id': movie_data.get('channel_id', ''),
        'language': movie_data.get('language', 'Hindi'),
        'published_at': movie_data.get('published_at', ''),
        'last_updated': now
    })
    conn.commit()
    conn.close()

def get_all_free_movies():
    """Retrieve all free movies sorted by publish date / id."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM free_movies ORDER BY published_at DESC, id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_free_movies(language=None):
    """Retrieve free movies filtered by language, or all if language is None."""
    conn = get_db_connection()
    cursor = conn.cursor()
    if language:
        cursor.execute("SELECT * FROM free_movies WHERE language = ? ORDER BY published_at DESC, id DESC", (language,))
    else:
        cursor.execute("SELECT * FROM free_movies ORDER BY published_at DESC, id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_free_movies_languages():
    """Retrieve distinct languages available in free_movies."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT language FROM free_movies ORDER BY language ASC")
    rows = cursor.fetchall()
    conn.close()
    return [row['language'] for row in rows if row['language']]

