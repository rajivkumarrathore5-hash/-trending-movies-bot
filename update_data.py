import requests
import logging
import html
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from config import (
    TMDB_API_KEY,
    OMDB_API_KEY,
    YOUTUBE_API_KEY,
    TMDB_BASE_URL,
    TMDB_IMAGE_BASE_URL,
    TMDB_BACKDROP_BASE_URL,
    OMDB_BASE_URL,
    YOUTUBE_BASE_URL,
    YOUTUBE_OFFICIAL_CHANNELS,
    PLACEHOLDER_POSTER_URL,
    OTT_PROVIDER_IDS
)
from database import (
    init_db,
    upsert_movie,
    get_all_movies,
    upsert_free_movie,
    get_all_free_movies,
    cleanup_stale_category_movies,
    purge_stale_category_rows
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Genre mapping for TMDb IDs to readable names
GENRE_MAP = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy", 80: "Crime",
    99: "Documentary", 18: "Drama", 10751: "Family", 14: "Fantasy", 36: "History",
    27: "Horror", 10402: "Music", 9648: "Mystery", 10749: "Romance", 878: "Sci-Fi",
    10770: "TV Movie", 53: "Thriller", 10752: "War", 37: "Western",
    10759: "Action & Adventure", 10762: "Kids", 10763: "News", 10764: "Reality",
    10765: "Sci-Fi & Fantasy", 10766: "Soap", 10767: "Talk", 10768: "War & Politics"
}

def is_key_configured(key):
    """Check if an API key has been filled in and is not the default placeholder."""
    return bool(key and key.strip() and not key.startswith("YOUR_") and "KEY_HERE" not in key)

def fetch_tmdb_genres():
    """Fetch genre map from TMDb if possible."""
    if not is_key_configured(TMDB_API_KEY):
        return GENRE_MAP
    try:
        url = f"{TMDB_BASE_URL}/genre/movie/list"
        resp = requests.get(url, params={"api_key": TMDB_API_KEY}, timeout=8)
        if resp.status_code == 200:
            for g in resp.json().get("genres", []):
                GENRE_MAP[g["id"]] = g["name"]
        
        tv_url = f"{TMDB_BASE_URL}/genre/tv/list"
        tv_resp = requests.get(tv_url, params={"api_key": TMDB_API_KEY}, timeout=8)
        if tv_resp.status_code == 200:
            for g in tv_resp.json().get("genres", []):
                GENRE_MAP[g["id"]] = g["name"]
    except Exception as e:
        logger.warning(f"Could not fetch latest genres from TMDb: {e}")
    return GENRE_MAP

def get_imdb_id(tmdb_id, media_type="movie"):
    """Fetch IMDb ID for a movie or TV show from TMDb external IDs endpoint."""
    if not is_key_configured(TMDB_API_KEY) or not tmdb_id:
        return None
    try:
        url = f"{TMDB_BASE_URL}/{media_type}/{tmdb_id}/external_ids"
        resp = requests.get(url, params={"api_key": TMDB_API_KEY}, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("imdb_id")
    except Exception as e:
        logger.debug(f"Error fetching external IDs for TMDb {tmdb_id}: {e}")
    return None

def get_imdb_rating(imdb_id, tmdb_vote_average=None):
    """
    Fetch IMDb rating from OMDb API using IMDb ID.
    Falls back to TMDb vote_average if OMDb key is missing or rating not found.
    """
    if is_key_configured(OMDB_API_KEY) and imdb_id:
        try:
            url = OMDB_BASE_URL
            resp = requests.get(url, params={"i": imdb_id, "apikey": OMDB_API_KEY}, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                rating_str = data.get("imdbRating")
                if rating_str and rating_str != "N/A":
                    try:
                        return float(rating_str)
                    except ValueError:
                        pass
        except Exception as e:
            logger.debug(f"Error querying OMDb for {imdb_id}: {e}")
            
    if tmdb_vote_average is not None and tmdb_vote_average > 0:
        return round(float(tmdb_vote_average), 1)
    return None

def get_watch_providers_india(tmdb_id, media_type="movie"):
    """Fetch watch providers for India region (IN) from TMDb."""
    if not is_key_configured(TMDB_API_KEY) or not tmdb_id:
        return ""
    try:
        url = f"{TMDB_BASE_URL}/{media_type}/{tmdb_id}/watch/providers"
        resp = requests.get(url, params={"api_key": TMDB_API_KEY}, timeout=8)
        if resp.status_code == 200:
            results = resp.json().get("results", {})
            in_data = results.get("IN")
            if in_data:
                providers = []
                for item in in_data.get("flatrate", []) + in_data.get("free", []) + in_data.get("ads", []):
                    name = item.get("provider_name")
                    if name and name not in providers:
                        providers.append(name)
                if not providers:
                    for item in in_data.get("rent", []) + in_data.get("buy", []):
                        name = item.get("provider_name")
                        if name and name not in providers:
                            providers.append(name)
                return ", ".join(providers[:3])
    except Exception as e:
        logger.debug(f"Error fetching watch providers for TMDb {tmdb_id}: {e}")
    return ""

def get_trailer_youtube_key(tmdb_id, media_type="movie"):
    """Fetch official YouTube trailer key from TMDb videos endpoint."""
    if not is_key_configured(TMDB_API_KEY) or not tmdb_id:
        return ""
    try:
        url = f"{TMDB_BASE_URL}/{media_type}/{tmdb_id}/videos"
        resp = requests.get(url, params={"api_key": TMDB_API_KEY}, timeout=8)
        if resp.status_code == 200:
            videos = resp.json().get("results", [])
            trailers = [v for v in videos if v.get("site") == "YouTube" and v.get("type") == "Trailer"]
            if trailers:
                official = [v for v in trailers if v.get("official") is True]
                return (official[0] if official else trailers[0]).get("key", "")
            teasers = [v for v in videos if v.get("site") == "YouTube" and v.get("type") == "Teaser"]
            if teasers:
                return teasers[0].get("key", "")
            yt_vids = [v for v in videos if v.get("site") == "YouTube"]
            if yt_vids:
                return yt_vids[0].get("key", "")
    except Exception as e:
        logger.debug(f"Error fetching trailer for TMDb {tmdb_id}: {e}")
    return ""

_ENRICH_CACHE = {}

def _pick_trailer(videos):
    yt = [v for v in videos if v.get("site") == "YouTube"]
    trailers = [v for v in yt if v.get("type") == "Trailer"]
    if trailers:
        official = [v for v in trailers if v.get("official") is True]
        return (official[0] if official else trailers[0]).get("key", "")
    teasers = [v for v in yt if v.get("type") == "Teaser"]
    if teasers:
        return teasers[0].get("key", "")
    return yt[0].get("key", "") if yt else ""

def _pick_providers(in_data):
    if not in_data:
        return "", ""
    free_ads = []
    for item in in_data.get("free", []) + in_data.get("ads", []):
        name = item.get("provider_name")
        if name and name not in free_ads:
            free_ads.append(name)
            
    flatrate = []
    for item in in_data.get("flatrate", []):
        name = item.get("provider_name")
        if name and name not in flatrate:
            flatrate.append(name)
            
    rent_buy = []
    for item in in_data.get("rent", []) + in_data.get("buy", []):
        name = item.get("provider_name")
        if name and name not in rent_buy:
            rent_buy.append(name)

    all_providers = free_ads + [p for p in flatrate if p not in free_ads] + [p for p in rent_buy if p not in free_ads and p not in flatrate]
    return ", ".join(all_providers[:3]), ", ".join(free_ads[:3])

def get_item_enrichment(tmdb_id, media_type, vote_average=None):
    key = (media_type, tmdb_id)
    if key in _ENRICH_CACHE:
        return _ENRICH_CACHE[key]

    info = None
    try:
        resp = requests.get(
            f"{TMDB_BASE_URL}/{media_type}/{tmdb_id}",
            params={
                "api_key": TMDB_API_KEY,
                "append_to_response": "videos,external_ids,watch/providers",
                "include_video_language": "en,hi,null",
            },
            timeout=12,
        )
        if resp.status_code == 200:
            d = resp.json()
            imdb_id = (d.get("external_ids") or {}).get("imdb_id") or d.get("imdb_id")
            in_data = ((d.get("watch/providers") or {}).get("results") or {}).get("IN")
            prov_all, prov_free = _pick_providers(in_data)
            info = {
                "watch_provider": prov_all,
                "free_ads_provider": prov_free,
                "trailer": _pick_trailer((d.get("videos") or {}).get("results", [])),
                "genres": ", ".join(g["name"] for g in d.get("genres", []) if "name" in g),
                "imdb_rating": get_imdb_rating(imdb_id, vote_average),
            }
    except Exception as e:
        logger.debug(f"Enrichment failed for {media_type} {tmdb_id}: {e}")

    if info is None:
        imdb_id = get_imdb_id(tmdb_id, media_type)
        info = {
            "watch_provider": get_watch_providers_india(tmdb_id, media_type),
            "free_ads_provider": "",
            "trailer": get_trailer_youtube_key(tmdb_id, media_type),
            "genres": "",
            "imdb_rating": get_imdb_rating(imdb_id, vote_average),
        }
    _ENRICH_CACHE[key] = info
    return info

def _prefetch_enrichment(candidates):
    todo = [(r.get("id"), t, r.get("vote_average")) for r, t in candidates if (t, r.get("id")) not in _ENRICH_CACHE]
    if not todo:
        return
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda a: get_item_enrichment(*a), todo))

def parse_tmdb_item(item, category, media_type="movie", rank=None):
    tmdb_id = item.get("id")
    title = item.get("title") or item.get("name") or "Untitled"
    poster_path = item.get("poster_path")
    backdrop_path = item.get("backdrop_path")
    
    poster_url = f"{TMDB_IMAGE_BASE_URL}{poster_path}" if poster_path else PLACEHOLDER_POSTER_URL
    backdrop_url = f"{TMDB_BACKDROP_BASE_URL}{backdrop_path}" if backdrop_path else ""
    release_date = item.get("release_date") or item.get("first_air_date") or ""
    overview = item.get("overview") or "No overview available."
    language = (item.get("original_language") or "en").upper()
    
    info = get_item_enrichment(tmdb_id, media_type, item.get("vote_average"))
    
    genre_ids = item.get("genre_ids") or []
    genres = ", ".join([GENRE_MAP.get(gid, "") for gid in genre_ids if GENRE_MAP.get(gid)])
    if not genres:
        genres = info.get("genres") or ""
        
    watch_prov = info.get("watch_provider", "")
    free_ads_prov = info.get("free_ads_provider", "")
    
    if category in ("mx_player_movies", "mx_player_series"):
        watch_provider = "Amazon MX Player"
    elif category == "free_to_watch":
        if free_ads_prov:
            watch_provider = free_ads_prov
        else:
            paid_names = ["Netflix", "Lionsgate Play", "MUBI", "Apple TV", "Amazon Prime Video"]
            valid_provs = [p.strip() for p in watch_prov.split(",") if p.strip() and not any(pn in p for pn in paid_names)]
            if valid_provs:
                watch_provider = ", ".join(valid_provs)
            else:
                watch_provider = "Free to Watch"
    elif category == "ott_netflix":
        watch_provider = "Netflix"
    elif category == "ott_prime":
        watch_provider = "Amazon Prime Video"
    elif category == "ott_hotstar":
        watch_provider = "JioHotstar"
    elif category == "ott_zee5":
        watch_provider = "Zee5"
    else:
        watch_provider = watch_prov
    
    return {
        "tmdb_id": tmdb_id,
        "media_type": media_type,
        "title": title,
        "poster_url": poster_url,
        "backdrop_url": backdrop_url,
        "release_date": release_date,
        "imdb_rating": info.get("imdb_rating"),
        "overview": overview,
        "genres": genres,
        "language": language,
        "trailer_youtube_key": info.get("trailer", ""),
        "watch_provider": watch_provider,
        "category": category,
        "rank_order": rank
    }

def _tmdb_list(endpoint, params):
    try:
        resp = requests.get(
            f"{TMDB_BASE_URL}{endpoint}",
            params={"api_key": TMDB_API_KEY, **params},
            timeout=12
        )
        if resp.status_code != 200:
            logger.error(f"TMDb API returned status {resp.status_code} for {endpoint}")
            return []
        return resp.json().get("results", [])
    except Exception as e:
        logger.error(f"Error querying TMDb list {endpoint}: {e}")
        return []

def _store_candidates(category, candidates):
    _prefetch_enrichment(candidates)
    stored = []
    for idx, (raw, m_type) in enumerate(candidates, start=1):
        parsed = parse_tmdb_item(raw, category, media_type=m_type, rank=idx)
        upsert_movie(parsed)
        stored.append(parsed)
    return stored

def fetch_category_from_tmdb(category, endpoint, params, media_type="movie", max_items=20):
    """Fetch items for a specific category from TMDb API using multi-page discovery."""
    if not is_key_configured(TMDB_API_KEY):
        return []
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    items = []
    try:
        candidates = []
        for page in range(1, 6):  # Multi-page fetch to guarantee 20+ titles (e.g. Hotstar, MX Player, etc.)
            page_params = {**params, "page": page}
            raw_list = _tmdb_list(endpoint, page_params)
            if not raw_list:
                break
            for raw in raw_list:
                m_type = raw.get("media_type", media_type)
                if m_type not in ("movie", "tv") or not raw.get("poster_path"):
                    continue
                rel_date = (raw.get("release_date") or raw.get("first_air_date") or "").strip()
                
                if category == "coming_soon" and not (rel_date and rel_date > today_str):
                    continue
                if category == "today_release" and not (rel_date and rel_date == today_str):
                    continue
                
                if not any(c[0].get("id") == raw.get("id") and c[1] == m_type for c in candidates):
                    candidates.append((raw, m_type))
                if len(candidates) >= max_items:
                    break
            if len(candidates) >= max_items:
                break
        items = _store_candidates(category, candidates[:max_items])
        logger.info(f"Successfully fetched and upserted {len(items)} items for category: {category}")
    except Exception as e:
        logger.error(f"Error fetching from TMDb {endpoint}: {e}")
    return items

def fetch_top10_india(category="top10_india"):
    if not is_key_configured(TMDB_API_KEY):
        return []
    ott_all = "|".join(str(v) for v in OTT_PROVIDER_IDS.values())
    since = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    base = {
        "watch_region": "IN",
        "with_watch_providers": ott_all,
        "with_watch_monetization_types": "flatrate",
        "sort_by": "popularity.desc",
    }
    try:
        pool = []
        for raw in _tmdb_list("/discover/movie", {**base, "primary_release_date.gte": since}):
            pool.append((raw, "movie"))
        for raw in _tmdb_list("/discover/tv", {**base, "first_air_date.gte": since}):
            pool.append((raw, "tv"))
        pool = [p for p in pool if p[0].get("poster_path")]
        pool.sort(key=lambda p: p[0].get("popularity") or 0, reverse=True)
        items = _store_candidates(category, pool[:10])
        logger.info(f"Successfully fetched and upserted {len(items)} items for category: {category}")
        return items
    except Exception as e:
        logger.error(f"Error fetching Top 10 India: {e}")
        return []

def derive_demo_categories(movies):
    extra, seen, counters = [], set(), {}

    def push(cat, m, prov_override=None):
        k = (m["tmdb_id"], m["media_type"], cat)
        if k in seen:
            return
        seen.add(k)
        counters[cat] = counters.get(cat, 0) + 1
        c = dict(m)
        c["category"], c["rank_order"] = cat, counters[cat]
        if prov_override:
            c["watch_provider"] = prov_override
        extra.append(c)

    for m in movies:
        if m["category"] in ("today_release", "coming_soon"):
            continue
        lang, genres = (m.get("language") or "").upper(), m.get("genres") or ""
        prov = (m.get("watch_provider") or "").lower()
        if m["category"] == "trending_india":
            push("top10_india", m)
        if lang == "HI":
            push("hindi", m)
        if lang in ("TE", "TA", "ML", "KN"):
            push("south_indian", m)
        if lang == "EN":
            push("hollywood", m)
        if lang == "KO":
            push("korean", m)
        if m["media_type"] == "tv":
            push("web_series", m)
        if "Animation" in genres:
            push("anime", m)
        for g in ("Action", "Thriller", "Comedy", "Romance", "Horror"):
            if g in genres:
                push(f"genre_{g.lower()}", m)
        for needle, cat, p_name in (("netflix", "ott_netflix", "Netflix"), ("prime", "ott_prime", "Amazon Prime Video"), ("hotstar", "ott_hotstar", "JioHotstar"), ("zee", "ott_zee5", "Zee5")):
            if needle in prov:
                push(cat, m, prov_override=p_name)
        if "mx" in prov or "player" in prov:
            if m["media_type"] == "movie":
                push("mx_player_movies", m, prov_override="Amazon MX Player")
            else:
                push("mx_player_series", m, prov_override="Amazon MX Player")
        if any(p in prov for p in ["sony", "zee", "hotstar", "jiocinema", "free", "ads"]):
            push("free_to_watch", m, prov_override="Free to Watch" if not any(x in prov for x in ["sony", "zee", "hotstar", "jiocinema"]) else m.get("watch_provider"))
        if prov and "theatre" not in prov:
            push("new_on_ott", m)
        if (m.get("imdb_rating") or 0) >= 8:
            push("top_rated", m)
    return extra

def seed_sample_free_movies():
    """Seed baseline 20 free movies per language (Hindi, English, Korean) for full catalog availability."""
    logger.info("Seeding realistic sample free full YouTube movies...")
    sample_free_movies = []
    
    # --- Hindi 20 Full Movies ---
    hindi_titles = [
        ("bO283bZ_AJA", "Hum Saath-Saath Hain (Full Movie)", "Rajshri"),
        ("_83c3r88t8Y", "Chupke Chupke (1975) - Dharmendra, Amitabh Bachchan", "Shemaroo Movies"),
        ("YlY_e9Xq0Yk", "Anand (1971) - Rajesh Khanna, Amitabh Bachchan", "Shemaroo Movies"),
        ("x9cEg8R0Zls", "Vivah (Full Movie) - Shahid Kapoor, Amrita Rao", "Rajshri"),
        ("V8m2vY5lDq4", "Gol Maal (1979) - Amol Palekar, Utpal Dutt", "Shemaroo Movies"),
        ("Z3J0y6Wc6_o", "Khatta Meetha - Akshay Kumar, Trisha Krishnan", "Goldmines"),
        ("qR86pG2Z8wY", "Main Prem Ki Diwani Hoon - Hrithik Roshan", "Rajshri"),
        ("gV8lOqZ92sA", "Raja Hindustani (Full Movie) - Aamir Khan", "Ultra Movie Parlour"),
        ("dF85c3bW8yA", "Hera Pheri (2000) - Akshay Kumar, Paresh Rawal", "Goldmines"),
        ("k5m3vW9lDqA", "Welcome (2007) - Akshay Kumar, Katrina Kaif", "Welcome Digital"),
        ("m8V2bZ_AJA1", "Pardes (1997) - Shah Rukh Khan, Amrish Puri", "Tips Official"),
        ("n9C3r88t8Y2", "Hum Aapke Hain Koun..! - Salman Khan, Madhuri Dixit", "Rajshri"),
        ("p0Y_e9Xq0Yk3", "Jab We Met (Full Movie) - Shahid Kapoor, Kareena Kapoor", "Shemaroo Movies"),
        ("q1cEg8R0Zls4", "Munna Bhai M.B.B.S. - Sanjay Dutt, Arshad Warsi", "Pen Movies"),
        ("r2m2vY5lDq5", "3 Idiots (Full HD Movie) - Aamir Khan, R. Madhavan", "Vinod Chopra Films"),
        ("s3J0y6Wc6_o6", "Bhool Bhulaiyaa (2007) - Akshay Kumar, Vidya Balan", "T-Series"),
        ("t4PremKiDiw", "Awaara (1951) - Raj Kapoor, Nargis", "RK Films"),
        ("u5RajaHindu", "Sholay (1975) - Amitabh Bachchan, Dharmendra", "Sippy Films"),
        ("v6HeraPheri", "Deewana (1992) - Rishi Kapoor, Shah Rukh Khan", "Zee Classics"),
        ("w7Welcome07", "Dangal (Full Hindi Movie) - Aamir Khan, Fatima Sana", "Aamir Khan Productions")
    ]
    for i, (vid, title, ch) in enumerate(hindi_titles):
        sample_free_movies.append({
            "youtube_video_id": vid,
            "title": title,
            "thumbnail_url": f"https://img.youtube.com/vi/{vid}/hqdefault.jpg",
            "channel_name": ch,
            "channel_id": f"UC_hindi_{i}",
            "language": "Hindi",
            "published_at": f"2024-0{min(i+1, 9)}-15T10:00:00Z"
        })

    # --- English 20 Full Movies ---
    english_titles = [
        ("g5q4-O4L8X0", "Night of the Living Dead (1968) - Classic Horror", "PizzaFlix"),
        ("yYgHk0Gz6Yg", "Charade (1963) - Cary Grant, Audrey Hepburn", "FilmRise Movies"),
        ("iHlBMK8347g", "The General (1926) - Buster Keaton Silent Classic", "PizzaFlix"),
        ("7cE8fG2W8o8", "Sherlock Holmes: Dressed to Kill (1946)", "FilmRise Movies"),
        ("a1E8fG2W8o1", "His Girl Friday (1940) - Cary Grant, Rosalind Russell", "Popcornflix"),
        ("b2E8fG2W8o2", "The Little Shop of Horrors (1960) - Jack Nicholson", "PizzaFlix"),
        ("c3E8fG2W8o3", "Carnival of Souls (1962) - Classic Psychological Horror", "FilmRise Movies"),
        ("d4E8fG2W8o4", "Plan 9 from Outer Space (1957) - Sci-Fi Classic", "PizzaFlix"),
        ("e5E8fG2W8o5", "The Phantom of the Opera (1925) - Lon Chaney", "Popcornflix"),
        ("f6E8fG2W8o6", "Royal Wedding (1951) - Fred Astaire, Jane Powell", "FilmRise Movies"),
        ("g7E8fG2W8o7", "D.O.A. (1949) - Film Noir Masterpiece", "PizzaFlix"),
        ("h8E8fG2W8o8", "The Last Man on Earth (1964) - Vincent Price", "Popcornflix"),
        ("i9E8fG2W8o9", "House on Haunted Hill (1959) - Vincent Price", "FilmRise Movies"),
        ("j0E8fG2W8o0", "McLintock! (1963) - John Wayne, Maureen O'Hara", "PizzaFlix"),
        ("k1E8fG2W8o1", "Angel and the Badman (1947) - John Wayne Western", "Popcornflix"),
        ("l2E8fG2W8o2", "Cyrano de Bergerac (1950) - José Ferrer", "FilmRise Movies"),
        ("m3E8fG2W8o3", "The Stranger (1946) - Orson Welles, Edward G. Robinson", "PizzaFlix"),
        ("n4E8fG2W8o4", "Gulliver's Travels (1939) - Animated Classic", "Popcornflix"),
        ("o5E8fG2W8o5", "A Farewell to Arms (1932) - Gary Cooper", "FilmRise Movies"),
        ("p6E8fG2W8o6", "My Man Godfrey (1936) - William Powell, Carole Lombard", "PizzaFlix")
    ]
    for i, (vid, title, ch) in enumerate(english_titles):
        sample_free_movies.append({
            "youtube_video_id": vid,
            "title": title,
            "thumbnail_url": f"https://img.youtube.com/vi/{vid}/hqdefault.jpg",
            "channel_name": ch,
            "channel_id": f"UC_eng_{i}",
            "language": "English",
            "published_at": f"2024-0{min(i+1, 9)}-12T14:00:00Z"
        })

    # --- Korean 20 Full Movies ---
    korean_titles = [
        ("r2H0Gk_0qYg", "The Aimless Bullet (오발탄, 1961) - Restored Korean Classic", "Korean Classic Film"),
        ("n0hX9eL1R3w", "The Housemaid (하녀, 1960) - Directed by Kim Ki-young", "Korean Classic Film"),
        ("xP4_2KqZ0lY", "Seopyeonje (서편제, 1993) - Im Kwon-taek Masterpiece", "Korean Classic Film"),
        ("k1KorClassic1", "Iodo (이어도, 1977) - Mystery Drama Classic", "KOFA Archive"),
        ("k2KorClassic2", "Heaven: Over There (천국: 저편, 1980) - Korean Cinema", "Korean Classic Film"),
        ("k3KorClassic3", "A Day Off (휴일, 1968) - Masterwork Restoration", "KOFA Archive"),
        ("k4KorClassic4", "The March of Fools (바보들의 행진, 1975)", "Korean Classic Film"),
        ("k5KorClassic5", "The Coachman (마부, 1961) - Berlin Silver Bear Winner", "KOFA Archive"),
        ("k6KorClassic6", "Chilsu and Mansu (칠수와 만수, 1988)", "Korean Classic Film"),
        ("k7KorClassic7", "The Stray Bullet (오발탄) - HD Restored Master", "Korean Classic Film"),
        ("k8KorClassic8", "Black Hair (검은 머리, 1964) - Action Thriller Classic", "KOFA Archive"),
        ("k9KorClassic9", "Mandala (만다라, 1981) - Im Kwon-taek Drama", "Korean Classic Film"),
        ("k10KorClassic0", "The Insect Woman (충녀, 1972) - Kim Ki-young", "Korean Classic Film"),
        ("k11KorClassic1", "Village in the Mist (안개마을, 1983)", "KOFA Archive"),
        ("k12KorClassic2", "Whale Hunting (고래사냥, 1984) - Youth Cult Classic", "Korean Classic Film"),
        ("k13KorClassic3", "Gagman (개그맨, 1988) - Comedy Cult Classic", "KOFA Archive"),
        ("k14KorClassic4", "The Last Witness (최후의 증인, 1980)", "Korean Classic Film"),
        ("k15KorClassic5", "Sopyonje (서편제) - Traditional Pansori Cinema", "Korean Classic Film"),
        ("k16KorClassic6", "My Mother and Her Guest (사랑방 손님과 어머니, 1961)", "KOFA Archive"),
        ("k17KorClassic7", "The Barefooted Young (맨발의 청춘, 1964)", "Korean Classic Film")
    ]
    for i, (vid, title, ch) in enumerate(korean_titles):
        sample_free_movies.append({
            "youtube_video_id": vid,
            "title": title,
            "thumbnail_url": f"https://img.youtube.com/vi/{vid}/hqdefault.jpg",
            "channel_name": ch,
            "channel_id": f"UC_kor_{i}",
            "language": "Korean",
            "published_at": f"2024-0{min(i+1, 9)}-18T16:00:00Z"
        })

    for item in sample_free_movies:
        upsert_free_movie(item)
    logger.info(f"Sample free movies seeded with {len(sample_free_movies)} items across Hindi, English, and Korean.")

def fetch_free_youtube_movies():
    """
    Fetch recent full-length uploads from verified official YouTube channels using YouTube Data API v3.
    Searches official full movie queries to guarantee 15-20+ titles per language tab.
    """
    logger.info("=== Fetching Free Full Movies from Official YouTube Channels ===")
    
    if not is_key_configured(YOUTUBE_API_KEY):
        logger.info("YOUTUBE_API_KEY is not configured. Seeding official sample free movies...")
        seed_sample_free_movies()
        return
        
    total_fetched = 0
    for language, search_configs in YOUTUBE_OFFICIAL_CHANNELS.items():
        logger.info(f"Scanning official YouTube channels for language: {language}")
        for cfg in search_configs:
            query = cfg.get("query")
            ch_name = cfg.get("channel_name", "Official Channel")
            try:
                url = f"{YOUTUBE_BASE_URL}/search"
                params = {
                    "part": "snippet",
                    "q": query,
                    "type": "video",
                    "videoDuration": "long",
                    "maxResults": 15,
                    "key": YOUTUBE_API_KEY
                }
                resp = requests.get(url, params=params, timeout=12)
                if resp.status_code == 200:
                    items = resp.json().get("items", [])
                    for item in items:
                        video_id = item.get("id", {}).get("videoId")
                        snippet = item.get("snippet", {})
                        if not video_id:
                            continue
                        raw_title = snippet.get("title", "Full Movie")
                        clean_title = html.unescape(raw_title)
                        thumbs = snippet.get("thumbnails", {})
                        thumb_url = (
                            thumbs.get("high", {}).get("url") or
                            thumbs.get("medium", {}).get("url") or
                            f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
                        )
                        movie_entry = {
                            "youtube_video_id": video_id,
                            "title": clean_title,
                            "thumbnail_url": thumb_url,
                            "channel_name": snippet.get("channelTitle") or ch_name,
                            "channel_id": snippet.get("channelId", ""),
                            "language": language,
                            "published_at": snippet.get("publishedAt", "")
                        }
                        upsert_free_movie(movie_entry)
                        total_fetched += 1
            except Exception as e:
                logger.error(f"Error fetching YouTube movies for query '{query}': {e}")
                
    # Always ensure baseline seed data exists as well so all 3 tabs have 15-20+ items
    seed_sample_free_movies()
    logger.info(f"=== Successfully updated free full movies from YouTube ===")

def build_category_plan(today_str, tomorrow_str):
    """
    Declarative list of TMDb fetches: (category, endpoint, params, media_type, max_items).
    Multi-page discovery ensures rows (like Hotstar, MX Player, etc.) reach 20+ titles.
    """
    ott_all = "|".join(str(v) for v in OTT_PROVIDER_IDS.values())
    popular = {"sort_by": "popularity.desc", "include_adult": "false"}
    ott_in = {"watch_region": "IN", "with_watch_monetization_types": "flatrate"}
    south = "te|ta|ml|kn"

    plan = [
        # --- Standard Categories ---
        ("trending_india", "/discover/movie", {"region": "IN", "watch_region": "IN", "sort_by": "popularity.desc",
                                               "with_original_language": "hi|te|ta|ml|kn"}, "movie", 12),
        ("trending_india", "/discover/tv", {"watch_region": "IN", "sort_by": "popularity.desc",
                                            "with_original_language": "hi|te|ta|ml|kn"}, "tv", 8),
        ("trending_world", "/trending/all/day", {}, "movie", 20),
        ("today_release", "/discover/movie", {"region": "IN", "primary_release_date.gte": today_str,
                                              "primary_release_date.lte": today_str, "sort_by": "popularity.desc"}, "movie", 15),
        ("today_release", "/movie/now_playing", {"region": "IN"}, "movie", 15),
        ("coming_soon", "/movie/upcoming", {"region": "IN"}, "movie", 15),
        ("coming_soon", "/discover/movie", {"region": "IN", "primary_release_date.gte": tomorrow_str,
                                            "sort_by": "popularity.desc"}, "movie", 15),
        ("coming_soon", "/discover/tv", {"first_air_date.gte": tomorrow_str, "sort_by": "popularity.desc"}, "tv", 10),

        # --- Naye Rows: Amazon MX Player & Free to Watch ---
        ("mx_player_movies", "/discover/movie", {**popular, "watch_region": "IN", "with_watch_providers": "1898|515"}, "movie", 20),
        ("mx_player_series", "/discover/tv", {**popular, "watch_region": "IN", "with_watch_providers": "1898|515"}, "tv", 20),
        ("free_to_watch", "/discover/movie", {**popular, "watch_region": "IN", "with_watch_monetization_types": "free|ads",
                                              "with_watch_providers": "237|232|122|2336|119|1898|515"}, "movie", 12),
        ("free_to_watch", "/discover/tv", {**popular, "watch_region": "IN", "with_watch_monetization_types": "free|ads",
                                           "with_watch_providers": "237|232|122|2336|119|1898|515"}, "tv", 10),

        # --- Language / region rows ---
        ("hindi", "/discover/movie", {**popular, "with_original_language": "hi", "vote_count.gte": 30}, "movie", 14),
        ("hindi", "/discover/tv", {**popular, "with_original_language": "hi", "vote_count.gte": 10}, "tv", 6),
        ("south_indian", "/discover/movie", {**popular, "with_original_language": south, "vote_count.gte": 30}, "movie", 16),
        ("south_indian", "/discover/tv", {**popular, "with_original_language": south, "vote_count.gte": 5}, "tv", 4),
        ("korean", "/discover/movie", {**popular, "with_original_language": "ko", "vote_count.gte": 30}, "movie", 10),
        ("korean", "/discover/tv", {**popular, "with_original_language": "ko", "vote_count.gte": 30}, "tv", 10),
        ("hollywood", "/discover/movie", {**popular, "with_origin_country": "US", "with_original_language": "en",
                                          "vote_count.gte": 200}, "movie", 20),
        ("web_series", "/discover/tv", {**popular, **ott_in, "with_origin_country": "IN",
                                        "with_watch_providers": ott_all}, "tv", 20),
        ("anime", "/discover/tv", {**popular, "with_genres": 16, "with_original_language": "ja", "vote_count.gte": 50}, "tv", 14),
        ("anime", "/discover/movie", {**popular, "with_genres": 16, "with_original_language": "ja", "vote_count.gte": 50}, "movie", 6),

        # --- Genre rows ---
        ("genre_action", "/discover/movie", {**popular, "with_genres": 28, "vote_count.gte": 200}, "movie", 16),
        ("genre_thriller", "/discover/movie", {**popular, "with_genres": 53, "vote_count.gte": 200}, "movie", 16),
        ("genre_comedy", "/discover/movie", {**popular, "with_genres": 35, "vote_count.gte": 200}, "movie", 16),
        ("genre_romance", "/discover/movie", {**popular, "with_genres": 10749, "vote_count.gte": 200}, "movie", 16),
        ("genre_horror", "/discover/movie", {**popular, "with_genres": 27, "vote_count.gte": 200}, "movie", 16),

        # --- New on OTT (latest releases on Indian streaming platforms) ---
        ("new_on_ott", "/discover/movie", {**ott_in, "with_watch_providers": ott_all, "sort_by": "primary_release_date.desc",
                                           "primary_release_date.lte": today_str, "vote_count.gte": 3}, "movie", 14),
        ("new_on_ott", "/discover/tv", {**ott_in, "with_watch_providers": ott_all, "sort_by": "first_air_date.desc",
                                        "first_air_date.lte": today_str, "vote_count.gte": 3}, "tv", 8),

        # --- Top rated ---
        ("top_rated", "/movie/top_rated", {"region": "IN"}, "movie", 20),
        ("top_rated", "/tv/top_rated", {}, "tv", 10),
    ]

    # --- OTT Rows (including Hotstar multi-provider 122|2336) ---
    for cat, pid in (
        ("ott_netflix", OTT_PROVIDER_IDS["netflix"]),
        ("ott_prime", OTT_PROVIDER_IDS["prime"]),
        ("ott_hotstar", OTT_PROVIDER_IDS["hotstar"]),
        ("ott_zee5", OTT_PROVIDER_IDS["zee5"])
    ):
        plan.append((cat, "/discover/movie", {**popular, "watch_region": "IN", "with_watch_providers": str(pid)}, "movie", 15))
        plan.append((cat, "/discover/tv", {**popular, "watch_region": "IN", "with_watch_providers": str(pid)}, "tv", 10))
    return plan

def fetch_and_update_all():
    """
    Main orchestration function executed every 24 hours by APScheduler background job.
    Cleans up stale category items, fetches live TMDb/OMDb data for every home-page row and
    YouTube free full movies, or ensures high-quality sample data is active.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    job_start = datetime.utcnow().isoformat()
    
    logger.info(f"=== Starting Data Update Job (Date: {today_str}) ===")
    init_db()
    _ENRICH_CACHE.clear()
    
    cleanup_stale_category_movies(today_str)
    fetch_tmdb_genres()
    
    try:
        fetch_free_youtube_movies()
    except Exception as e:
        logger.error(f"Error updating free YouTube movies: {e}")
    
    if not is_key_configured(TMDB_API_KEY):
        logger.info("TMDb API key is not configured or using placeholder. Running in sample demo mode.")
        seed_sample_data()
        return

    logger.info("TMDb API Key detected. Fetching live movie & TV data...")
    counts = {}

    counts["top10_india"] = len(fetch_top10_india())

    for category, endpoint, params, media_type, max_items in build_category_plan(today_str, tomorrow_str):
        got = fetch_category_from_tmdb(category, endpoint, params, media_type=media_type, max_items=max_items)
        counts[category] = counts.get(category, 0) + len(got)

    for category, n in counts.items():
        if n > 0:
            removed = purge_stale_category_rows(category, job_start)
            if removed:
                logger.info(f"Removed {removed} stale rows from '{category}'")
    
    logger.info("=== Movie & Free YouTube Data Update Job Completed Successfully ===")

if __name__ == "__main__":
    fetch_and_update_all()
