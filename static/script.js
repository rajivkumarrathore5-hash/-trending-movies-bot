/**
 * CINEPULSE - Netflix-style client
 * Rows are rendered from appData.rows (defined in config.HOME_ROWS).
 * Handles: navbar pages, search + genre/language filters, hero auto-slider (top 3),
 * Top 10 big-number row, horizontal sliders with arrows, trailer/info modal, free movies, sync.
 */
document.addEventListener("DOMContentLoaded", () => {
    const PLACEHOLDER_POSTER_URL = "/static/placeholder_poster.svg";
    const PAGE = document.body.dataset.page || "home";

    const OTT_SEARCH_URLS_FALLBACK = {
        "Netflix": "https://www.netflix.com/search?q={query}",
        "Amazon Prime Video": "https://www.primevideo.com/search/?phrase={query}",
        "Prime Video": "https://www.primevideo.com/search/?phrase={query}",
        "Amazon Video": "https://www.primevideo.com/search/?phrase={query}",
        "Amazon MX Player": "https://www.mxplayer.in/?search=true&q={query}",
        "MX Player": "https://www.mxplayer.in/?search=true&q={query}",
        "JioCinema": "https://www.jiocinema.com/search/{query}",
        "JioHotstar": "https://www.hotstar.com/in/search?q={query}",
        "Disney+ Hotstar": "https://www.hotstar.com/in/search?q={query}",
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
        "YouTube": "https://www.youtube.com/results?search_query={query}",
        "BookMyShow": "https://in.bookmyshow.com/explore/movies?search={query}",
        "In Theatres": "https://in.bookmyshow.com/explore/movies?search={query}"
    };

    // --- State ---
    let appData = { rows: [], free_movies: [], free_movies_languages: [], genres: [], languages: [], last_updated: null, ott_search_urls: {} };
    let activeFilters = { search: "", genre: "", language: "" };
    let activeFreeLanguage = "all";

    // --- DOM ---
    const $ = (id) => document.getElementById(id);
    const rowsContainer = $("rows-container");
    const searchInput = $("search-input");
    const clearSearchBtn = $("clear-search-btn");
    const genreFilter = $("genre-filter");
    const languageFilter = $("language-filter");
    const filterStatusBar = $("filter-status-bar");
    const filterStatusText = $("filter-status-text");
    const noResultsBox = $("no-results-box");
    const btnRefresh = $("btn-refresh");
    const navbar = $("navbar");

    const movieModal = $("movie-modal");
    const modalVideoContainer = $("modal-video-container");
    const modalYoutubeIframe = $("modal-youtube-iframe");
    const modalPlayTrailerBtn = $("modal-play-trailer-btn");

    // --- Helpers ---
    function escapeHtml(str) {
        if (!str) return "";
        return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
    }

    function getOttSearchUrl(providerName, title) {
        if (!providerName) return "#";
        const p = providerName.trim();
        const q = encodeURIComponent((title || "").trim());
        const mapping = Object.keys(appData.ott_search_urls || {}).length ? appData.ott_search_urls : OTT_SEARCH_URLS_FALLBACK;
        if (mapping[p]) return mapping[p].replace("{query}", q);
        const lp = p.toLowerCase();
        for (const [key, tpl] of Object.entries(mapping)) {
            if (lp.includes(key.toLowerCase()) || key.toLowerCase().includes(lp)) return tpl.replace("{query}", q);
        }
        return `https://www.google.com/search?q=${q}+${encodeURIComponent(p)}`;
    }

    function formatTimeAgo(iso) {
        if (!iso) return "Updated recently";
        const s = Math.floor((Date.now() - new Date(iso + (iso.endsWith("Z") ? "" : "Z")).getTime()) / 1000);
        if (isNaN(s) || s < 60) return "Updated just now";
        const m = Math.floor(s / 60);
        if (m < 60) return `Updated ${m}m ago`;
        const h = Math.floor(m / 60);
        if (h < 24) return `Updated ${h}h ago`;
        const d = Math.floor(h / 24);
        return d === 1 ? "Updated yesterday" : `Updated ${d} days ago`;
    }

    function updateTimestamps() {
        const text = formatTimeAgo(appData.last_updated);
        const f = $("footer-update-text");
        if (f) f.textContent = `${text} • Auto-syncs daily`;
        if (btnRefresh) btnRefresh.title = `${text} — click to sync`;
    }

    function getLanguageDisplayName(code) {
        const map = { EN: "English", HI: "Hindi", TE: "Telugu", TA: "Tamil", ML: "Malayalam", KN: "Kannada",
                      JA: "Japanese", KO: "Korean", ES: "Spanish", FR: "French" };
        return map[code] ? `${map[code]} (${code})` : code;
    }

    // --- Page-level filtering (Home / Movies / TV Shows / Web Series) ---
    function pageRows() {
        const rows = appData.rows || [];
        if (PAGE === "web-series") return rows.filter(r => r.series);
        if (PAGE === "tv") return rows.filter(r => r.type !== "free");
        return rows;
    }

    function pageItems(list) {
        if (PAGE === "movies") return list.filter(m => m.media_type !== "tv");
        if (PAGE === "tv" || PAGE === "web-series") return list.filter(m => m.media_type === "tv");
        return list;
    }

    function matchesFilters(m) {
        if (activeFilters.search) {
            const t = activeFilters.search.toLowerCase();
            if (!((m.title || "").toLowerCase().includes(t) || (m.overview || "").toLowerCase().includes(t))) return false;
        }
        if (activeFilters.genre && !(m.genres || "").toLowerCase().includes(activeFilters.genre.toLowerCase())) return false;
        if (activeFilters.language && (m.language || "").toUpperCase() !== activeFilters.language.toUpperCase()) return false;
        return true;
    }

    // --- Cards ---
    function createMovieCard(movie) {
        const card = document.createElement("article");
        card.className = "movie-card";
        card.tabIndex = 0;

        const rating = movie.imdb_rating ? Number(movie.imdb_rating).toFixed(1) : null;
        const year = movie.release_date ? movie.release_date.split("-")[0] : "";
        const genres = movie.genres ? movie.genres.split(",").slice(0, 2).map(g => g.trim()).join(" • ") : "";
        const poster = (movie.poster_url && movie.poster_url.trim()) ? movie.poster_url : PLACEHOLDER_POSTER_URL;

        let providerHtml = "";
        if (movie.watch_provider && movie.watch_provider.trim()) {
            const first = movie.watch_provider.split(",")[0].trim();
            providerHtml = `<a href="${escapeHtml(getOttSearchUrl(first, movie.title))}" target="_blank" rel="noopener noreferrer"
                class="badge-provider-card" title="Watch ${escapeHtml(movie.title)} on ${escapeHtml(first)}">
                <i class="fa-solid fa-circle-play"></i><span>${escapeHtml(first)}</span></a>`;
        }

        card.innerHTML = `
            <div class="card-poster-wrap">
                <img class="card-poster" src="${escapeHtml(poster)}" alt="${escapeHtml(movie.title)} poster" width="200" height="300"
                     loading="lazy" decoding="async">
                ${rating ? `<span class="badge-imdb card-rating"><i class="fa-solid fa-star"></i> ${rating}</span>` : ""}
                ${providerHtml}
                <div class="card-overlay">
                    <p class="card-overlay-meta">${year}${year && genres ? " • " : ""}${escapeHtml(genres)}</p>
                    <div class="card-actions">
                        <button class="card-btn card-btn-play" title="Watch trailer" aria-label="Watch trailer of ${escapeHtml(movie.title)}"><i class="fa-solid fa-play"></i></button>
                        <button class="card-btn card-btn-info" title="More info" aria-label="More info about ${escapeHtml(movie.title)}"><i class="fa-solid fa-chevron-down"></i></button>
                    </div>
                </div>
            </div>
            <h3 class="card-title" title="${escapeHtml(movie.title)}">${escapeHtml(movie.title)}</h3>`;

        const img = card.querySelector("img");
        img.addEventListener("error", () => { img.onerror = null; img.src = PLACEHOLDER_POSTER_URL; img.classList.add("placeholder-poster"); }, { once: true });
        const stop = (e) => e.stopPropagation();
        const prov = card.querySelector(".badge-provider-card");
        if (prov) prov.addEventListener("click", stop);
        card.querySelector(".card-btn-play").addEventListener("click", (e) => { stop(e); openModal(movie, true); });
        card.querySelector(".card-btn-info").addEventListener("click", (e) => { stop(e); openModal(movie, false); });
        card.addEventListener("click", () => openModal(movie, false));
        card.addEventListener("keydown", (e) => { if (e.key === "Enter") openModal(movie, false); });
        return card;
    }

    function createTop10Card(movie, index) {
        const wrap = document.createElement("div");
        wrap.className = `top10-item ${index + 1 >= 10 ? "two-digit" : ""}`;
        const num = document.createElement("span");
        num.className = "top10-number";
        num.setAttribute("aria-hidden", "true");
        num.textContent = index + 1;
        wrap.appendChild(num);
        wrap.appendChild(createMovieCard(movie));
        return wrap;
    }

    function createFreeMovieCard(movie) {
        const card = document.createElement("article");
        card.className = "free-movie-card";
        card.tabIndex = 0;
        const thumb = (movie.thumbnail_url && movie.thumbnail_url.trim()) ? movie.thumbnail_url : PLACEHOLDER_POSTER_URL;
        card.innerHTML = `
            <div class="free-card-poster-wrap">
                <img src="${escapeHtml(thumb)}" alt="${escapeHtml(movie.title)}" width="320" height="180" loading="lazy" decoding="async">
                <span class="badge-free-tag"><i class="fa-solid fa-play"></i> Free</span>
                <div class="card-overlay center"><div class="card-btn card-btn-play big"><i class="fa-solid fa-play"></i></div></div>
            </div>
            <h3 class="card-title" title="${escapeHtml(movie.title)}">${escapeHtml(movie.title)}</h3>
            <p class="free-card-meta">${escapeHtml(movie.language || "")} • ${escapeHtml(movie.channel_name || "YouTube")}</p>`;
        const img = card.querySelector("img");
        img.addEventListener("error", () => { img.onerror = null; img.src = PLACEHOLDER_POSTER_URL; }, { once: true });
        card.addEventListener("click", () => openFreeMovieModal(movie));
        card.addEventListener("keydown", (e) => { if (e.key === "Enter") openFreeMovieModal(movie); });
        return card;
    }

    // --- Section / slider builder ---
    function buildSection(row, items, isFree) {
        const section = document.createElement("section");
        section.className = `movie-section ${row.type === "top10" ? "top10-section" : ""}`;
        section.id = `section-${row.key.replace(/_/g, "-")}`;

        const header = document.createElement("div");
        header.className = "section-header";
        header.innerHTML = `<h2 class="section-title">${escapeHtml(row.title)}</h2>`;

        if (isFree) {
            const langs = ["all", ...(appData.free_movies_languages || [])];
            const tabs = document.createElement("div");
            tabs.className = "free-movies-tabs";
            tabs.id = "free-movies-tabs";
            langs.forEach(l => {
                const b = document.createElement("button");
                b.className = `tab-pill ${l === activeFreeLanguage ? "active" : ""}`;
                b.textContent = l === "all" ? "All" : l;
                b.addEventListener("click", () => { activeFreeLanguage = l; renderAll(); });
                tabs.appendChild(b);
            });
            header.appendChild(tabs);
        }
        section.appendChild(header);

        const wrapper = document.createElement("div");
        wrapper.className = "row-wrapper";
        const scroller = document.createElement("div");
        scroller.className = `card-row ${isFree ? "free-row" : ""} ${row.type === "top10" ? "top10-row" : ""}`;
        scroller.id = `row-${row.key.replace(/_/g, "-")}`;

        items.forEach((m, i) => {
            if (isFree) scroller.appendChild(createFreeMovieCard(m));
            else if (row.type === "top10") scroller.appendChild(createTop10Card(m, i));
            else scroller.appendChild(createMovieCard(m));
        });

        const mkBtn = (dir) => {
            const b = document.createElement("button");
            b.className = `row-arrow row-arrow-${dir}`;
            b.setAttribute("aria-label", dir === "left" ? "Scroll left" : "Scroll right");
            b.innerHTML = `<i class="fa-solid fa-chevron-${dir}"></i>`;
            b.addEventListener("click", () => scroller.scrollBy({ left: (dir === "left" ? -1 : 1) * scroller.clientWidth * 0.85, behavior: "smooth" }));
            return b;
        };
        const left = mkBtn("left"), right = mkBtn("right");
        const updateArrows = () => {
            left.classList.toggle("hidden", scroller.scrollLeft < 8);
            right.classList.toggle("hidden", scroller.scrollLeft + scroller.clientWidth >= scroller.scrollWidth - 8);
        };
        scroller.addEventListener("scroll", updateArrows, { passive: true });
        wrapper.append(left, scroller, right);
        section.appendChild(wrapper);
        requestAnimationFrame(updateArrows);
        return section;
    }

    function renderAll() {
        rowsContainer.innerHTML = "";
        let total = 0;

        pageRows().forEach(row => {
            if (row.type === "free") {
                let list = appData.free_movies || [];
                if (activeFreeLanguage !== "all") list = list.filter(m => (m.language || "").toLowerCase() === activeFreeLanguage.toLowerCase());
                if (activeFilters.search) {
                    const t = activeFilters.search.toLowerCase();
                    list = list.filter(m => (m.title || "").toLowerCase().includes(t) || (m.channel_name || "").toLowerCase().includes(t));
                }
                if (activeFilters.genre || activeFilters.language) list = [];
                // Hide row if fewer than 5 titles exist
                if (list.length >= 5) { rowsContainer.appendChild(buildSection(row, list, true)); total += list.length; }
                return;
            }
            let list = pageItems(appData[row.key] || []).filter(matchesFilters);
            if (row.type === "top10") list = list.slice(0, 10);
            // Hide row if fewer than 5 titles exist (top10 requires at least 1)
            const minRequired = row.type === "top10" ? 1 : 5;
            if (list.length >= minRequired) { rowsContainer.appendChild(buildSection(row, list, false)); total += list.length; }
        });

        const hasFilters = Boolean(activeFilters.search || activeFilters.genre || activeFilters.language);
        filterStatusBar.style.display = hasFilters ? "flex" : "none";
        if (hasFilters) {
            const d = [];
            if (activeFilters.search) d.push(`"${activeFilters.search}"`);
            if (activeFilters.genre) d.push(activeFilters.genre);
            if (activeFilters.language) d.push(getLanguageDisplayName(activeFilters.language));
            filterStatusText.textContent = `${d.join(" • ")} — ${total} results`;
        }
        noResultsBox.style.display = total === 0 ? "block" : "none";
    }

    function renderSkeletons() {
        rowsContainer.innerHTML = "";
        for (let r = 0; r < 3; r++) {
            const sec = document.createElement("section");
            sec.className = "movie-section";
            sec.innerHTML = `<div class="section-header"><div class="skeleton-line title"></div></div>
                <div class="card-row">${'<div class="skeleton-card"><div class="skeleton-poster"></div><div class="skeleton-line"></div></div>'.repeat(8)}</div>`;
            rowsContainer.appendChild(sec);
        }
    }

    function populateDropdowns() {
        genreFilter.innerHTML = '<option value="">All Genres</option>';
        (appData.genres || []).forEach(g => genreFilter.add(new Option(g, g)));
        languageFilter.innerHTML = '<option value="">All Languages</option>';
        (appData.languages || []).forEach(l => languageFilter.add(new Option(getLanguageDisplayName(l), l)));
    }

    // --- Hero (top 3 trending, auto-slider) ---
    let heroItems = [], heroIndex = 0, heroTimer = null, heroLayer = 1;
    const hero = {
        section: $("hero-spotlight"), b1: $("hero-backdrop-1"), b2: $("hero-backdrop-2"), content: $("hero-content"),
        badge: $("hero-badge"), title: $("hero-title"), imdb: $("hero-imdb"), year: $("hero-year"),
        genre: $("hero-genre"), provider: $("hero-provider"), overview: $("hero-overview"), dots: $("hero-indicators")
    };

    function initHero() {
        const pool = [...(appData.trending_world || []), ...(appData.trending_india || []), ...(appData.top10_india || [])];
        const seen = new Set();
        heroItems = [];
        for (const m of pageItems(pool)) {
            const key = `${m.media_type}-${m.tmdb_id}`;
            if (seen.has(key) || !m.backdrop_url) continue;
            seen.add(key);
            heroItems.push(m);
            if (heroItems.length >= 3) break;
        }
        hero.section.style.display = heroItems.length ? "" : "none";
        if (!heroItems.length) return;

        hero.dots.innerHTML = "";
        heroItems.forEach((_, i) => {
            const d = document.createElement("button");
            d.className = `hero-dot ${i === 0 ? "active" : ""}`;
            d.setAttribute("aria-label", `Show featured title ${i + 1}`);
            d.addEventListener("click", () => { showHero(i); startHeroTimer(); });
            hero.dots.appendChild(d);
        });
        heroIndex = 0;
        showHero(0, false);
        startHeroTimer();
    }

    function showHero(idx, animate = true) {
        heroIndex = (idx + heroItems.length) % heroItems.length;
        const m = heroItems[heroIndex];
        const [show, hide] = heroLayer === 1 ? [hero.b2, hero.b1] : [hero.b1, hero.b2];
        show.style.backgroundImage = `url('${m.backdrop_url}')`;
        show.classList.add("active");
        hide.classList.remove("active");
        heroLayer = heroLayer === 1 ? 2 : 1;

        const apply = () => {
            hero.badge.textContent = `#${heroIndex + 1} Trending`;
            hero.title.textContent = m.title;
            hero.imdb.innerHTML = `<i class="fa-solid fa-star"></i> ${m.imdb_rating ? Number(m.imdb_rating).toFixed(1) : "N/A"}`;
            hero.year.textContent = m.release_date ? m.release_date.split("-")[0] : "";
            hero.genre.textContent = m.genres ? m.genres.split(",").slice(0, 3).map(g => g.trim()).join(" • ") : "";
            hero.overview.textContent = m.overview || "";
            if (m.watch_provider && m.watch_provider.trim()) {
                const first = m.watch_provider.split(",")[0].trim();
                hero.provider.href = getOttSearchUrl(first, m.title);
                hero.provider.innerHTML = `<i class="fa-solid fa-tv"></i> ${escapeHtml(first)}`;
                hero.provider.style.display = "inline-flex";
            } else {
                hero.provider.style.display = "none";
            }
        };
        if (animate) {
            hero.content.classList.add("fading");
            setTimeout(() => { apply(); hero.content.classList.remove("fading"); }, 250);
        } else apply();
        hero.dots.querySelectorAll(".hero-dot").forEach((d, i) => d.classList.toggle("active", i === heroIndex));
    }

    function startHeroTimer() {
        clearInterval(heroTimer);
        if (heroItems.length > 1) heroTimer = setInterval(() => showHero(heroIndex + 1), 7000);
    }
    hero.section.addEventListener("mouseenter", () => clearInterval(heroTimer));
    hero.section.addEventListener("mouseleave", startHeroTimer);
    $("hero-trailer-btn").addEventListener("click", () => heroItems[heroIndex] && openModal(heroItems[heroIndex], true));
    $("hero-details-btn").addEventListener("click", () => heroItems[heroIndex] && openModal(heroItems[heroIndex], false));

    // --- Modal ---
    function showModalShell() {
        movieModal.classList.add("active");
        movieModal.setAttribute("aria-hidden", "false");
        document.body.style.overflow = "hidden";
    }

    function playTrailer(key) {
        if (!key) return;
        modalYoutubeIframe.src = `https://www.youtube-nocookie.com/embed/${key}?autoplay=1&rel=0&modestbranding=1`;
        modalVideoContainer.style.display = "block";
    }

    function stopTrailer() {
        modalYoutubeIframe.src = "";
        modalVideoContainer.style.display = "none";
    }

    function openModal(movie, autoplay) {
        $("modal-movie-title").textContent = movie.title;
        const imdb = $("modal-imdb");
        imdb.className = "badge-imdb";
        imdb.innerHTML = `<i class="fa-solid fa-star"></i> ${movie.imdb_rating ? Number(movie.imdb_rating).toFixed(1) : "N/A"}`;
        $("modal-release-date").textContent = movie.release_date || "Coming Soon";
        $("modal-language").textContent = (movie.language || "EN").toUpperCase();
        $("modal-media-type").textContent = movie.media_type === "tv" ? "TV SERIES" : "MOVIE";

        const genres = $("modal-genres");
        genres.innerHTML = "";
        (movie.genres || "").split(",").map(g => g.trim()).filter(Boolean).forEach(g => {
            const s = document.createElement("span");
            s.className = "genre-pill";
            s.textContent = g;
            genres.appendChild(s);
        });
        $("modal-overview").textContent = movie.overview || "No overview available.";

        const wrap = $("modal-provider-wrap"), badges = $("modal-watch-provider");
        badges.innerHTML = "";
        const providers = (movie.watch_provider || "").split(",").map(p => p.trim()).filter(Boolean);
        providers.forEach(p => {
            const a = document.createElement("a");
            a.href = getOttSearchUrl(p, movie.title);
            a.target = "_blank";
            a.rel = "noopener noreferrer";
            a.className = "badge-provider-large";
            a.innerHTML = `<i class="fa-solid fa-play"></i> <span>${escapeHtml(p)}</span>`;
            badges.appendChild(a);
        });
        wrap.style.display = providers.length ? "block" : "none";

        $("modal-backdrop-img").style.backgroundImage = `url('${movie.backdrop_url || movie.poster_url || PLACEHOLDER_POSTER_URL}')`;

        if (autoplay && movie.trailer_youtube_key) playTrailer(movie.trailer_youtube_key); else stopTrailer();
        if (movie.trailer_youtube_key) {
            modalPlayTrailerBtn.style.display = "inline-flex";
            modalPlayTrailerBtn.innerHTML = '<i class="fa-solid fa-play"></i> Watch Trailer';
            modalPlayTrailerBtn.onclick = () => playTrailer(movie.trailer_youtube_key);
        } else {
            modalPlayTrailerBtn.style.display = "none";
        }
        showModalShell();
    }

    function openFreeMovieModal(movie) {
        $("modal-movie-title").textContent = movie.title;
        const imdb = $("modal-imdb");
        imdb.className = "badge-imdb badge-free-movie";
        imdb.innerHTML = '<i class="fa-solid fa-circle-check"></i> FREE';
        $("modal-release-date").textContent = movie.published_at ? movie.published_at.split("T")[0] : "Official Upload";
        $("modal-language").textContent = (movie.language || "Hindi").toUpperCase();
        $("modal-media-type").textContent = "FULL MOVIE";
        $("modal-genres").innerHTML = `<span class="genre-pill">Free Full Movie</span><span class="genre-pill">${escapeHtml(movie.language || "Cinema")}</span>`;
        $("modal-overview").textContent = `Full-length movie streaming officially and legally courtesy of ${movie.channel_name || "the official channel"} on YouTube.`;
        $("modal-watch-provider").innerHTML = `<a href="https://www.youtube.com/watch?v=${encodeURIComponent(movie.youtube_video_id)}" target="_blank" rel="noopener noreferrer" class="badge-provider-large"><i class="fa-brands fa-youtube" style="color:#ff0000"></i> <span>${escapeHtml(movie.channel_name || "YouTube")}</span></a>`;
        $("modal-provider-wrap").style.display = "block";
        $("modal-backdrop-img").style.backgroundImage = `url('${movie.thumbnail_url || PLACEHOLDER_POSTER_URL}')`;
        playTrailer(movie.youtube_video_id);
        modalPlayTrailerBtn.style.display = "inline-flex";
        modalPlayTrailerBtn.innerHTML = '<i class="fa-brands fa-youtube"></i> Watch on YouTube';
        modalPlayTrailerBtn.onclick = () => window.open(`https://www.youtube.com/watch?v=${encodeURIComponent(movie.youtube_video_id)}`, "_blank");
        showModalShell();
    }

    function closeModal() {
        movieModal.classList.remove("active");
        movieModal.setAttribute("aria-hidden", "true");
        document.body.style.overflow = "";
        stopTrailer();
    }
    $("modal-close-btn").addEventListener("click", closeModal);
    movieModal.addEventListener("click", (e) => { if (e.target === movieModal) closeModal(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && movieModal.classList.contains("active")) closeModal(); });

    // --- Search & filters ---
    let searchTimer = null;
    searchInput.addEventListener("input", (e) => {
        clearSearchBtn.style.display = e.target.value ? "block" : "none";
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => { activeFilters.search = e.target.value.trim(); renderAll(); }, 150);
    });
    clearSearchBtn.addEventListener("click", () => {
        searchInput.value = "";
        clearSearchBtn.style.display = "none";
        activeFilters.search = "";
        renderAll();
    });
    genreFilter.addEventListener("change", (e) => { activeFilters.genre = e.target.value; renderAll(); });
    languageFilter.addEventListener("change", (e) => { activeFilters.language = e.target.value; renderAll(); });

    function resetFilters() {
        activeFilters = { search: "", genre: "", language: "" };
        searchInput.value = "";
        clearSearchBtn.style.display = "none";
        genreFilter.value = "";
        languageFilter.value = "";
        renderAll();
    }
    $("btn-reset-filters").addEventListener("click", resetFilters);
    $("clear-all-filters-link").addEventListener("click", resetFilters);
    $("btn-clear-empty-filter").addEventListener("click", resetFilters);

    // --- Navbar: scroll state, mobile menu, mobile search ---
    window.addEventListener("scroll", () => navbar.classList.toggle("scrolled", window.scrollY > 20), { passive: true });
    $("nav-toggle").addEventListener("click", () => {
        const open = navbar.classList.toggle("menu-open");
        $("nav-toggle").setAttribute("aria-expanded", String(open));
    });
    if ($("search-toggle")) {
        $("search-toggle").addEventListener("click", () => {
            navbar.classList.toggle("search-open");
            if (navbar.classList.contains("search-open")) searchInput.focus();
        });
    }

    // --- Manual sync ---
    btnRefresh.addEventListener("click", async () => {
        btnRefresh.classList.add("spinning");
        btnRefresh.disabled = true;
        renderSkeletons();
        try {
            const res = await fetch("/api/refresh", { method: "POST", headers: { "Content-Type": "application/json" } });
            if (res.ok) {
                const result = await res.json();
                if (result.data) appData = { ...appData, ...result.data };
                populateDropdowns();
                initHero();
                updateTimestamps();
            }
        } catch (err) {
            console.error("Error refreshing data:", err);
        } finally {
            renderAll();
            btnRefresh.classList.remove("spinning");
            btnRefresh.disabled = false;
        }
    });

    // --- Creator Modal ---
    const creatorModal = $("creator-modal");
    function openCreatorModal() {
        if (!creatorModal) return;
        creatorModal.classList.add("active");
        creatorModal.setAttribute("aria-hidden", "false");
        document.body.style.overflow = "hidden";
    }
    function closeCreatorModal() {
        if (!creatorModal) return;
        creatorModal.classList.remove("active");
        creatorModal.setAttribute("aria-hidden", "true");
        document.body.style.overflow = "";
    }
    if ($("btn-creator")) $("btn-creator").addEventListener("click", openCreatorModal);
    if ($("creator-modal-close-btn")) $("creator-modal-close-btn").addEventListener("click", closeCreatorModal);
    if (creatorModal) {
        creatorModal.addEventListener("click", (e) => { if (e.target === creatorModal) closeCreatorModal(); });
    }
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && creatorModal && creatorModal.classList.contains("active")) closeCreatorModal();
    });

    // --- Init ---
    try {
        appData = { ...appData, ...JSON.parse($("initial-data").textContent) };
    } catch (err) {
        console.error("Error parsing initial data:", err);
    }
    populateDropdowns();
    initHero();
    renderAll();
    updateTimestamps();
});
