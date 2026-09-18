from flask import Flask, request, jsonify
from flask_cors import CORS
from rapidfuzz import fuzz, process
import requests
import json
import os
import re

app = Flask(__name__)
CORS(app)

# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data", "AnimeInfo.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

# Cache mémoire du catalogue
ANIME_DATABASE = None


# ============================================================
# CHARGEMENT DU CATALOGUE
# ============================================================

def load_database():
    global ANIME_DATABASE

    if ANIME_DATABASE is not None:
        return ANIME_DATABASE

    if not os.path.exists(DATA_FILE):
        ANIME_DATABASE = []
        return ANIME_DATABASE

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, list):
            ANIME_DATABASE = data
        else:
            ANIME_DATABASE = []

    except Exception:
        ANIME_DATABASE = []

    return ANIME_DATABASE


# ============================================================
# NORMALISATION
# ============================================================

def normalize(text):
    if not text:
        return ""

    text = str(text).lower().strip()

    replacements = {
        "é": "e",
        "è": "e",
        "ê": "e",
        "ë": "e",
        "à": "a",
        "â": "a",
        "ä": "a",
        "î": "i",
        "ï": "i",
        "ô": "o",
        "ö": "o",
        "ù": "u",
        "û": "u",
        "ü": "u",
        "ç": "c",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# RECHERCHE
# ============================================================

def search_anime(query, limit=5):

    database = load_database()

    if not database:
        return []

    query_normalized = normalize(query)

    if not query_normalized:
        return []

    choices = {}

    for anime in database:

        title = anime.get("title", "")
        alt_title = anime.get("AlterTitle", "")

        if title:
            choices[title] = anime

        if alt_title:
            choices[alt_title] = anime

    # Recherche rapide RapidFuzz
    matches = process.extract(
        query_normalized,
        {
            normalize(title): anime
            for title, anime in choices.items()
        },
        scorer=fuzz.token_set_ratio,
        limit=limit
    )

    results = []

    already_added = set()

    for _, score, anime in matches:

        if score < 60:
            continue

        title = anime.get("title", "")

        key = normalize(title)

        if key in already_added:
            continue

        already_added.add(key)

        results.append({
            "title": title,
            "AlterTitle": anime.get("AlterTitle", ""),
            "lien": anime.get("link", ""),
            "score": score
        })

    return results


# ============================================================
# RECHERCHE EXACTE / MEILLEUR RESULTAT
# ============================================================

def find_best_anime(query):

    results = search_anime(query, 10)

    if not results:
        return None

    # Priorité au titre exact
    normalized_query = normalize(query)

    for result in results:

        if normalize(result["title"]) == normalized_query:
            return result

    # Sinon meilleur score
    return results[0]


# ============================================================
# REQUETE HTTP
# ============================================================

def fetch(url, timeout=15):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=timeout
    )

    response.raise_for_status()

    return response.text


# ============================================================
# GET /
# ============================================================

@app.route("/", methods=["GET"])
def home():

    database = load_database()

    return jsonify({
        "status": "online",
        "service": "AnimeSama API Vercel",
        "catalogue_loaded": len(database),
        "endpoints": [
            "/api/getSerchAnime?q=My%20Hero%20Academia",
            "/api/getInfoAnime?q=My%20Hero%20Academia",
            "/api/getSpecificAnime?q=My%20Hero%20Academia&s=saison1&v=vostfr",
            "/api/getAnimeLink?n=My%20Hero%20Academia&s=saison1&v=vostfr"
        ]
    })


# ============================================================
# GET SEARCH ANIME
# ============================================================

@app.route("/api/getSerchAnime", methods=["GET"])
def get_search_anime():

    query = request.args.get("q", "").strip()

    try:
        limit = int(
            request.args.get("l", "5")
        )
    except ValueError:
        limit = 5

    limit = max(1, min(limit, 20))

    if not query:

        return jsonify({
            "error": "Paramètre q manquant"
        }), 400

    results = search_anime(
        query,
        limit
    )

    return jsonify(results)


# ============================================================
# GET ALL ANIME
# ============================================================

@app.route("/api/getAllAnime", methods=["GET"])
def get_all_anime():

    database = load_database()

    return jsonify(database)


# ============================================================
# LOAD BASE
# ============================================================

@app.route("/api/loadBaseAnimeData", methods=["GET"])
def load_base():

    return jsonify(
        load_database()
    )


# ============================================================
# GET INFO ANIME
# ============================================================

@app.route("/api/getInfoAnime", methods=["GET"])
def get_info_anime():

    query = request.args.get(
        "q",
        ""
    ).strip()

    if not query:

        return jsonify({
            "error": "Paramètre q manquant"
        }), 400

    anime = find_best_anime(query)

    if not anime:

        return jsonify({
            "error": "Anime introuvable",
            "query": query
        }), 404

    base_url = anime["lien"].rstrip("/") + "/"

    # --------------------------------------------------------
    # On essaie de détecter les saisons disponibles
    # depuis la page Anime-Sama.
    #
    # Si le site ne répond pas, on utilise les saisons
    # connues dans AnimeInfo.json.
    # --------------------------------------------------------

    seasons = []

    try:

        html = fetch(
            base_url,
            timeout=10
        )

        found = re.findall(
            r"saison(\d+)",
            html,
            flags=re.I
        )

        for number in found:

            season = int(number)

            if season not in seasons:
                seasons.append(season)

    except Exception:
        pass

    # Fallback catalogue
    if not seasons:

        catalog_seasons = anime.get(
            "seasons",
            []
        )

        if isinstance(
            catalog_seasons,
            list
        ):
            seasons = catalog_seasons

    seasons = sorted(
        set(seasons)
    )

    result = []

    for season in seasons:

        result.append({
            "base_url": base_url,
            "title": anime["title"],
            "Saison": f"Saison {season}",
            "url": (
                f"{base_url}"
                f"saison{season}/"
            )
        })

    return jsonify(result)


# ============================================================
# GET SPECIFIC ANIME
# ============================================================

@app.route("/api/getSpecificAnime", methods=["GET"])
def get_specific_anime():

    query = request.args.get(
        "q",
        ""
    ).strip()

    season = request.args.get(
        "s",
        "saison1"
    ).strip().lower()

    version = request.args.get(
        "v",
        "vostfr"
    ).strip().lower()

    if not query:

        return jsonify({
            "error": "Paramètre q manquant"
        }), 400

    anime = find_best_anime(query)

    if not anime:

        return jsonify({
            "error": "Anime introuvable",
            "query": query
        }), 404

    if not season.startswith("saison"):
        season = "saison" + season

    base_url = anime["lien"].rstrip("/") + "/"

    url = (
        f"{base_url}"
        f"{season}/"
        f"{version}"
    )

    return jsonify({
        "base_url": base_url,
        "title": anime["title"],
        "Saison": season.replace(
            "saison",
            "Saison "
        ),
        "version": version,
        "url": url
    })


# ============================================================
# EXTRACTION EPISODES
# ============================================================

def extract_episode_links(html):

    episodes = {}

    # --------------------------------------------------------
    # URLs contenant episode / ep
    # --------------------------------------------------------

    patterns = [
        r'["\'](https?://[^"\']+)["\']',
        r'(https?://[^\s<>"\']+)'
    ]

    urls = []

    for pattern in patterns:

        urls.extend(
            re.findall(
                pattern,
                html,
                flags=re.I
            )
        )

    # --------------------------------------------------------
    # Cherche le numéro d'épisode autour des URLs
    # --------------------------------------------------------

    for url in urls:

        clean_url = url.rstrip(
            ".,);]}"
        )

        position = html.find(url)

        if position == -1:
            continue

        start = max(
            0,
            position - 250
        )

        end = min(
            len(html),
            position + len(url) + 250
        )

        context = html[
            start:end
        ]

        patterns_episode = [
            r'episode[\s_-]*(\d+)',
            r'ep[\s_-]*(\d+)',
            r'episode(\d+)',
            r'ep(\d+)'
        ]

        episode_number = None

        for pattern in patterns_episode:

            match = re.search(
                pattern,
                context,
                flags=re.I
            )

            if match:

                episode_number = int(
                    match.group(1)
                )

                break

        if episode_number is None:
            continue

        if episode_number not in episodes:

            episodes[episode_number] = {
                "episode": episode_number,
                "url": clean_url
            }

    return sorted(
        episodes.values(),
        key=lambda x: x["episode"]
    )


# ============================================================
# GET ANIME LINK
# ============================================================

@app.route("/api/getAnimeLink", methods=["GET"])
def get_anime_link():

    query = request.args.get(
        "n",
        ""
    ).strip()

    season = request.args.get(
        "s",
        "saison1"
    ).strip().lower()

    version = request.args.get(
        "v",
        "vostfr"
    ).strip().lower()

    if not query:

        return jsonify({
            "error": "Paramètre n manquant"
        }), 400

    anime = find_best_anime(query)

    if not anime:

        return jsonify({
            "error": "Anime introuvable",
            "query": query
        }), 404

    if not season.startswith("saison"):
        season = "saison" + season

    base_url = anime["lien"].rstrip("/") + "/"

    url = (
        f"{base_url}"
        f"{season}/"
        f"{version}"
    )

    try:

        html = fetch(
            url,
            timeout=20
        )

    except Exception as e:

        return jsonify({
            "error": "Impossible de récupérer la saison",
            "title": anime["title"],
            "url": url,
            "message": str(e)
        }), 502

    episodes = extract_episode_links(
        html
    )

    return jsonify({
        "title": anime["title"],
        "season": season,
        "version": version,
        "url": url,
        "episodes": episodes
    })


# ============================================================
# LANCEMENT LOCAL
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
