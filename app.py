from flask import Flask, request, jsonify
from flask_cors import CORS
from rapidfuzz import fuzz, process

import requests
import json
import os
import re


# ============================================================
# CONFIGURATION
# ============================================================

app = Flask(__name__)

# Autorise les requêtes provenant de ton site
# et des autres clients web.
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": "*",
            "methods": ["GET", "OPTIONS"],
            "allow_headers": ["Content-Type"]
        }
    }
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data", "AnimeInfo.json")

ANIME_DATABASE = None


# ============================================================
# CHARGEMENT DE LA BASE
# ============================================================

def load_database():
    global ANIME_DATABASE

    if ANIME_DATABASE is not None:
        return ANIME_DATABASE

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            ANIME_DATABASE = data
        else:
            ANIME_DATABASE = []

        return ANIME_DATABASE

    except Exception as e:
        print("Erreur chargement AnimeInfo.json :", e)
        ANIME_DATABASE = []
        return ANIME_DATABASE


# ============================================================
# UTILITAIRES
# ============================================================

def normalize(text):
    if not text:
        return ""

    text = str(text).lower().strip()

    # Suppression des accents
    replacements = {
        "à": "a",
        "â": "a",
        "ä": "a",
        "á": "a",
        "ã": "a",
        "å": "a",
        "ç": "c",
        "é": "e",
        "è": "e",
        "ê": "e",
        "ë": "e",
        "î": "i",
        "ï": "i",
        "ì": "i",
        "í": "i",
        "ô": "o",
        "ö": "o",
        "ò": "o",
        "ó": "o",
        "õ": "o",
        "ù": "u",
        "û": "u",
        "ü": "u",
        "ú": "u",
        "ÿ": "y",
        "ñ": "n"
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def search_anime(query, limit=10):
    database = load_database()

    if not query:
        return []

    query_normalized = normalize(query)

    if not query_normalized:
        return []

    # On crée une liste de titres normalisés.
    # On garde ensuite l'index pour retrouver l'anime.
    choices = []

    for index, anime in enumerate(database):
        if not isinstance(anime, dict):
            continue

        title = anime.get("title", "")

        if title:
            choices.append((normalize(title), index))

        # Compatibilité avec une éventuelle ancienne base
        alter_title = anime.get("AlterTitle", "")

        if alter_title:
            if isinstance(alter_title, list):
                for alt in alter_title:
                    choices.append((normalize(alt), index))
            else:
                choices.append((normalize(alter_title), index))

    if not choices:
        return []

    title_list = [item[0] for item in choices]

    matches = process.extract(
        query_normalized,
        title_list,
        scorer=fuzz.token_set_ratio,
        limit=limit
    )

    results = []
    already_added = set()

    for matched_title, score, choice_index in matches:

        anime_index = choices[choice_index][1]

        if anime_index in already_added:
            continue

        already_added.add(anime_index)

        anime = database[anime_index]

        results.append({
            "title": anime.get("title", ""),
            "link": anime.get("link", ""),
            "cover": anime.get("cover", ""),
            "score": round(score, 2)
        })

    return results


def find_best_anime(query):
    results = search_anime(query, limit=5)

    if not results:
        return None

    return results[0]


# ============================================================
# ANIME-SAMA
# ============================================================

ANIME_SAMA_DOMAIN = "https://anime-sama.to"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"
}


def anime_sama_request(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20
        )

        response.raise_for_status()

        return response.text

    except Exception as e:
        print("Erreur requête AnimeSama :", e)
        return None


# ============================================================
# ROUTE PRINCIPALE
# ============================================================

@app.route("/")
def home():
    database = load_database()

    return jsonify({
        "status": "online",
        "service": "AnimeSama API",
        "catalogue_loaded": len(database),
        "endpoints": [
            "/api/getAllAnime",
            "/api/loadBaseAnimeData",
            "/api/getSerchAnime?q=My%20Hero%20Academia",
            "/api/getInfoAnime?q=Demon%20Slayer",
            "/api/getSpecificAnime?q=One%20Piece&s=saison1&v=vostfr",
            "/api/getAnimeLink?n=Spy%20x%20Family&s=saison1&v=vostfr",
            "/api/getAnimeSamaURL?n=My%20Hero%20Academia"
        ]
    })


# ============================================================
# GET ALL ANIME
# ============================================================

@app.route("/api/getAllAnime", methods=["GET"])
def get_all_anime():

    database = load_database()

    return jsonify(database)


# ============================================================
# LOAD BASE ANIME DATA
# ============================================================

@app.route("/api/loadBaseAnimeData", methods=["GET"])
def load_base_anime_data():

    database = load_database()

    return jsonify({
        "success": True,
        "count": len(database),
        "data": database
    })


# ============================================================
# RECHERCHE ANIME
# ============================================================

@app.route("/api/getSerchAnime", methods=["GET"])
def get_search_anime():

    query = request.args.get("q", "").strip()

    if not query:
        return jsonify({
            "error": "Paramètre q manquant"
        }), 400

    results = search_anime(query)

    return jsonify({
        "query": query,
        "results": results
    })


# ============================================================
# URL ANIME-SAMA
# ============================================================

@app.route("/api/getAnimeSamaURL", methods=["GET"])
def get_anime_sama_url():

    query = request.args.get("n", "").strip()

    if not query:
        query = request.args.get("q", "").strip()

    if not query:
        return jsonify({
            "error": "Paramètre n ou q manquant"
        }), 400

    anime = find_best_anime(query)

    if not anime:
        return jsonify({
            "error": "Anime introuvable",
            "query": query
        }), 404

    return jsonify({
        "title": anime.get("title", ""),
        "url": anime.get("link", ""),
        "cover": anime.get("cover", "")
    })


# ============================================================
# GET INFO ANIME
# ============================================================

@app.route("/api/getInfoAnime", methods=["GET"])
def get_info_anime():

    query = request.args.get("q", "").strip()

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

    anime_url = anime.get("link", "")

    if not anime_url:
        return jsonify({
            "error": "URL AnimeSama introuvable",
            "anime": anime
        }), 404

    html = anime_sama_request(anime_url)

    if html is None:
        return jsonify({
            "error": "Impossible de contacter AnimeSama",
            "title": anime.get("title", ""),
            "url": anime_url
        }), 502

    result = {
        "title": anime.get("title", ""),
        "url": anime_url,
        "cover": anime.get("cover", ""),
        "seasons": []
    }

    # --------------------------------------------------------
    # Recherche des informations panneauAnime(...)
    # --------------------------------------------------------

    panneau_matches = re.findall(
        r'panneauAnime\s*\((.*?)\)',
        html,
        re.DOTALL
    )

    seasons = []

    for match in panneau_matches:

        parts = [
            x.strip().strip("'\"")
            for x in match.split(",")
        ]

        if not parts:
            continue

        for part in parts:

            part_lower = part.lower()

            if "saison" in part_lower:

                if part not in seasons:
                    seasons.append(part)

    # --------------------------------------------------------
    # Recherche directe des dossiers saisonX
    # --------------------------------------------------------

    season_matches = re.findall(
        r'saison\d+',
        html,
        re.IGNORECASE
    )

    for season in season_matches:

        season = season.lower()

        if season not in seasons:
            seasons.append(season)

    # Tri naturel
    def season_number(value):
        match = re.search(r"(\d+)", value)

        if match:
            return int(match.group(1))

        return 9999

    seasons = sorted(
        seasons,
        key=season_number
    )

    result["seasons"] = seasons

    return jsonify(result)


# ============================================================
# GET SPECIFIC ANIME
# ============================================================

@app.route("/api/getSpecificAnime", methods=["GET"])
def get_specific_anime():

    query = request.args.get("q", "").strip()
    season = request.args.get("s", "saison1").strip()
    version = request.args.get("v", "vostfr").strip()

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

    base_url = anime.get("link", "")

    if not base_url:
        return jsonify({
            "error": "URL AnimeSama introuvable"
        }), 404

    base_url = base_url.rstrip("/")

    # Si l'URL catalogue contient déjà quelque chose,
    # on récupère uniquement la partie catalogue.
    match = re.search(
        r"(https://anime-sama\.to/catalogue/[^/]+)",
        base_url
    )

    if match:
        catalogue_url = match.group(1)
    else:
        catalogue_url = base_url

    final_url = (
        f"{catalogue_url}/"
        f"{season}/"
        f"{version}"
    )

    html = anime_sama_request(final_url)

    if html is None:
        return jsonify({
            "error": "Impossible de contacter AnimeSama",
            "url": final_url
        }), 502

    return jsonify({
        "title": anime.get("title", ""),
        "season": season,
        "version": version,
        "url": final_url,
        "cover": anime.get("cover", "")
    })


# ============================================================
# GET EPISODES / LIENS
# ============================================================

@app.route("/api/getAnimeLink", methods=["GET"])
def get_anime_link():

    query = request.args.get("n", "").strip()
    season = request.args.get("s", "saison1").strip()
    version = request.args.get("v", "vostfr").strip()

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

    base_url = anime.get("link", "")

    if not base_url:
        return jsonify({
            "error": "URL AnimeSama introuvable"
        }), 404

    base_url = base_url.rstrip("/")

    match = re.search(
        r"(https://anime-sama\.to/catalogue/[^/]+)",
        base_url
    )

    if match:
        catalogue_url = match.group(1)
    else:
        catalogue_url = base_url

    final_url = (
        f"{catalogue_url}/"
        f"{season}/"
        f"{version}"
    )

    html = anime_sama_request(final_url)

    if html is None:
        return jsonify({
            "error": "Impossible de contacter AnimeSama",
            "url": final_url
        }), 502

    episodes = []

    # --------------------------------------------------------
    # Recherche du fichier episodes.js
    # --------------------------------------------------------

    episode_scripts = re.findall(
        r'<script[^>]+src=["\']([^"\']*episodes\.js[^"\']*)["\']',
        html,
        re.IGNORECASE
    )

    # --------------------------------------------------------
    # Si episodes.js est trouvé
    # --------------------------------------------------------

    for script_url in episode_scripts:

        if script_url.startswith("//"):
            script_url = "https:" + script_url

        elif script_url.startswith("/"):
            script_url = ANIME_SAMA_DOMAIN + script_url

        elif not script_url.startswith("http"):
            script_url = final_url.rstrip("/") + "/" + script_url

        script_content = anime_sama_request(script_url)

        if not script_content:
            continue

        # ----------------------------------------------------
        # Recherche :
        #
        # var eps1 = [...]
        # let eps1 = [...]
        # const eps1 = [...]
        # ----------------------------------------------------

        pattern = re.compile(
            rf"(?:var|let|const)\s+eps(\d+)\s*=\s*(\[[\s\S]*?\])",
            re.IGNORECASE
        )

        matches = pattern.findall(script_content)

        for player_number, array_content in matches:

            # Recherche des URLs dans le tableau
            urls = re.findall(
                r'https?://[^"\']+',
                array_content
            )

            for episode_index, url in enumerate(urls):

                # Évite les doublons
                if any(
                    ep["url"] == url
                    for ep in episodes
                ):
                    continue

                episodes.append({
                    "episode": episode_index,
                    "player": f"eps{player_number}",
                    "url": url
                })

    # --------------------------------------------------------
    # Méthode alternative :
    # recherche directe de eps1, eps2, etc.
    # --------------------------------------------------------

    if not episodes:

        pattern = re.compile(
            r'eps(\d+)\s*=\s*(\[[\s\S]*?\])',
            re.IGNORECASE
        )

        matches = pattern.findall(html)

        for player_number, array_content in matches:

            urls = re.findall(
                r'https?://[^"\']+',
                array_content
            )

            for episode_index, url in enumerate(urls):

                if any(
                    ep["url"] == url
                    for ep in episodes
                ):
                    continue

                episodes.append({
                    "episode": episode_index,
                    "player": f"eps{player_number}",
                    "url": url
                })

    # --------------------------------------------------------
    # Tri des épisodes
    # --------------------------------------------------------

    episodes.sort(
        key=lambda x: (
            x["player"],
            x["episode"]
        )
    )

    return jsonify({
        "title": anime.get("title", ""),
        "season": season,
        "version": version,
        "url": final_url,
        "episodes": episodes
    })


# ============================================================
# LANCEMENT LOCAL
# ============================================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
