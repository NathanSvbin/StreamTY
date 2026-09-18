from flask import Flask, request, jsonify
from flask_cors import CORS

from rapidfuzz import process, fuzz
from bs4 import BeautifulSoup

import requests
import json
import os
import re
import unicodedata


app = Flask(__name__)
CORS(app)

# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_FILE = os.path.join(
    BASE_DIR,
    "data",
    "AnimeInfo.json"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": (
        "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7"
    ),
}

# Le catalogue est chargé une seule fois
ANIME_DATABASE = None


# ============================================================
# CHARGEMENT DU CATALOGUE
# ============================================================

def load_database():

    global ANIME_DATABASE

    if ANIME_DATABASE is not None:
        return ANIME_DATABASE

    if not os.path.exists(DATA_FILE):
        raise FileNotFoundError(
            f"Fichier introuvable : {DATA_FILE}"
        )

    with open(
        DATA_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(
            "AnimeInfo.json doit contenir une liste"
        )

    ANIME_DATABASE = data

    return ANIME_DATABASE


# ============================================================
# NORMALISATION
# ============================================================

def normalize_title(title):

    if not title:
        return ""

    title = unicodedata.normalize(
        "NFKD",
        str(title)
    )

    title = "".join(
        c for c in title
        if not unicodedata.combining(c)
    )

    title = title.lower()

    title = re.sub(
        r"[^a-zA-Z0-9\s]",
        " ",
        title
    )

    title = re.sub(
        r"\s+",
        " ",
        title
    )

    return title.strip()


# ============================================================
# RECHERCHE ANIME
# ============================================================

def search_anime(query, limit=5):

    database = load_database()

    query_clean = normalize_title(query)

    if not query_clean:
        return []

    # --------------------------------------------------------
    # Recherche exacte en premier
    # --------------------------------------------------------

    for anime in database:

        title = anime.get(
            "title",
            ""
        )

        if normalize_title(title) == query_clean:

            return [{
                "title": title,
                "lien": anime.get(
                    "link",
                    ""
                ),
                "cover": anime.get(
                    "cover",
                    ""
                ),
                "score": 100
            }]

    # --------------------------------------------------------
    # Recherche floue
    # --------------------------------------------------------

    titles = {}

    for anime in database:

        title = anime.get(
            "title",
            ""
        )

        if not title:
            continue

        normalized = normalize_title(
            title
        )

        if normalized:
            titles[normalized] = anime

    matches = process.extract(
        query_clean,
        list(titles.keys()),
        scorer=fuzz.token_set_ratio,
        limit=15
    )

    results = []

    for normalized_title, score, _ in matches:

        if score < 75:
            continue

        anime = titles[
            normalized_title
        ]

        title = anime.get(
            "title",
            ""
        )

        # Bonus si les longueurs sont proches
        query_length = len(query_clean)
        title_length = len(normalized_title)

        if query_length > 0:

            ratio = (
                title_length /
                query_length
            )

        else:
            ratio = 0

        bonus = 0

        if 0.9 <= ratio <= 1.1:
            bonus = 10

        elif ratio < 0.5:
            bonus = -15

        final_score = score + bonus

        results.append({
            "title": title,
            "lien": anime.get(
                "link",
                ""
            ),
            "cover": anime.get(
                "cover",
                ""
            ),
            "score": final_score
        })

    # Meilleur score en premier
    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    # Suppression des doublons
    final_results = []
    seen = set()

    for result in results:

        link = result["lien"]

        if link in seen:
            continue

        seen.add(link)
        final_results.append(result)

        if len(final_results) >= limit:
            break

    return final_results


def find_anime(query):

    results = search_anime(
        query,
        limit=5
    )

    if not results:
        return None

    return results[0]


# ============================================================
# HTTP
# ============================================================

def request_page(url, timeout=15):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=timeout
    )

    response.raise_for_status()

    return response.text


# ============================================================
# EXTRACTION DES SAISONS
#
# Anime-Sama utilise des appels JavaScript du genre :
#
# panneauAnime("Saison 1", "saison1")
#
# Le projet AnimeSamaApi officiel utilise cette méthode.
# ============================================================

def extract_seasons(
    html,
    base_url,
    title,
    cover
):

    results = []

    # Retire les commentaires JS
    html_clean = re.sub(
        r"/\*.*?\*/",
        "",
        html,
        flags=re.DOTALL
    )

    # --------------------------------------------------------
    # panneauAnime
    # panneauFilm
    # panneauScan
    # panneauVisual
    # --------------------------------------------------------

    pattern = re.compile(
        r"""
        panneau
        (?:Anime|Film|Scan|Visual)
        \s*\(
        \s*(['"])(.*?)\1
        \s*,\s*
        (['"])(.*?)\3
        \s*\)
        """,
        re.IGNORECASE |
        re.VERBOSE
    )

    for match in pattern.finditer(
        html_clean
    ):

        name = match.group(2).strip()
        relative_url = match.group(4).strip()

        if not name:
            continue

        if name.lower() == "nom":
            continue

        if relative_url.lower() == "url":
            continue

        full_url = (
            base_url.rstrip("/")
            + "/"
            + relative_url.lstrip("/")
        )

        results.append({
            "base_url": base_url,
            "title": title,
            "cover": cover,
            "Saison": name,
            "url": full_url
        })

    # --------------------------------------------------------
    # Fallback si le JS utilise une autre forme
    # --------------------------------------------------------

    if not results:

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        for script in soup.find_all(
            "script"
        ):

            script_text = (
                script.string
                or script.get_text()
                or ""
            )

            if not script_text:
                continue

            matches = re.findall(
                r"""
                panneau
                (?:Anime|Film|Scan|Visual)
                \s*\(
                \s*['"]([^'"]+)['"]
                \s*,\s*
                ['"]([^'"]+)['"]
                \s*\)
                """,
                script_text,
                flags=re.I |
                re.X
            )

            for name, relative_url in matches:

                if name.lower() == "nom":
                    continue

                if relative_url.lower() == "url":
                    continue

                full_url = (
                    base_url.rstrip("/")
                    + "/"
                    + relative_url.lstrip("/")
                )

                results.append({
                    "base_url": base_url,
                    "title": title,
                    "cover": cover,
                    "Saison": name.strip(),
                    "url": full_url
                })

    # Suppression des doublons
    unique = []
    seen = set()

    for item in results:

        key = item["url"]

        if key in seen:
            continue

        seen.add(key)
        unique.append(item)

    return unique


# ============================================================
# GET /
# ============================================================

@app.route("/")
def home():

    try:
        database = load_database()

        return jsonify({
            "status": "online",
            "service": "StreamTY Anime API",
            "catalogue": len(database),
            "endpoints": {
                "search": "/api/getSerchAnime",
                "info": "/api/getInfoAnime",
                "specific": "/api/getSpecificAnime",
                "episodes": "/api/getAnimeLink"
            }
        })

    except Exception as e:

        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# ============================================================
# GET ALL ANIME
# ============================================================

@app.route(
    "/api/getAllAnime",
    methods=["GET"]
)
def get_all_anime():

    try:

        return jsonify(
            load_database()
        )

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500


# ============================================================
# LOAD BASE
# ============================================================

@app.route(
    "/api/loadBaseAnimeData",
    methods=["GET"]
)
def load_base_anime_data():

    try:

        return jsonify(
            load_database()
        )

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500


# ============================================================
# SEARCH
# ============================================================

@app.route(
    "/api/getSerchAnime",
    methods=["GET"]
)
def get_search_anime():

    query = request.args.get(
        "q",
        ""
    ).strip()

    if not query:

        return jsonify({
            "error": "Paramètre 'q' manquant"
        }), 400

    try:

        limit = int(
            request.args.get(
                "l",
                "5"
            )
        )

    except ValueError:

        limit = 5

    limit = max(
        1,
        min(limit, 20)
    )

    try:

        return jsonify(
            search_anime(
                query,
                limit
            )
        )

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500


# ============================================================
# GET INFO ANIME
# ============================================================

@app.route(
    "/api/getInfoAnime",
    methods=["GET"]
)
def get_info_anime():

    query = request.args.get(
        "q",
        ""
    ).strip()

    if not query:

        return jsonify({
            "error": "Paramètre 'q' manquant"
        }), 400

    try:

        anime = find_anime(
            query
        )

        if not anime:

            return jsonify({
                "error": "Anime introuvable",
                "query": query
            }), 404

        base_url = anime[
            "lien"
        ]

        title = anime[
            "title"
        ]

        cover = anime.get(
            "cover",
            ""
        )

        # ----------------------------------------------------
        # On ne cherche sur Anime-Sama
        # que maintenant que l'anime est trouvé
        # dans le JSON local.
        # ----------------------------------------------------

        html = request_page(
            base_url,
            timeout=15
        )

        seasons = extract_seasons(
            html,
            base_url,
            title,
            cover
        )

        return jsonify(
            seasons
        )

    except requests.RequestException as e:

        return jsonify({
            "error": "Impossible de contacter Anime-Sama",
            "message": str(e)
        }), 502

    except Exception as e:

        return jsonify({
            "error": "Erreur",
            "message": str(e)
        }), 500


# ============================================================
# GET SPECIFIC ANIME
# ============================================================

@app.route(
    "/api/getSpecificAnime",
    methods=["GET"]
)
def get_specific_anime():

    query = request.args.get(
        "q",
        ""
    ).strip()

    season = request.args.get(
        "s",
        "saison1"
    ).strip()

    version = request.args.get(
        "v",
        "vostfr"
    ).strip()

    if not query:

        return jsonify({
            "error": "Paramètre 'q' manquant"
        }), 400

    try:

        info = get_info_anime_internal(
            query
        )

        if not info:

            return jsonify({
                "error": "Anime introuvable",
                "query": query
            }), 404

        # ----------------------------------------------------
        # Normalisation
        # ----------------------------------------------------

        wanted = season.lower().replace(
            " ",
            ""
        )

        # ----------------------------------------------------
        # Cherche la saison demandée
        # ----------------------------------------------------

        selected = None

        for item in info:

            current = (
                item.get(
                    "Saison",
                    ""
                )
                .lower()
                .replace(" ", "")
            )

            if current == wanted:

                selected = item
                break

            # OAV
            if (
                wanted in ["oav", "oavs"]
                and "oav" in current
            ):

                selected = item
                break

            # Film
            if (
                wanted == "film"
                and "film" in current
            ):

                selected = item
                break

        # Si non trouvé : première saison
        if selected is None and info:
            selected = info[0]

        if selected is None:

            return jsonify({
                "error": "Saison introuvable",
                "anime": query,
                "saison": season
            }), 404

        url = selected[
            "url"
        ]

        # ----------------------------------------------------
        # Ajout de la version
        # ----------------------------------------------------

        url = url.rstrip("/")

        if not re.search(
            r"/(?:vostfr|vf)$",
            url,
            flags=re.I
        ):

            url = (
                url
                + "/"
                + version
            )

        else:

            url = re.sub(
                r"/(?:vostfr|vf)$",
                "/" + version,
                url,
                flags=re.I
            )

        result = dict(
            selected
        )

        result["version"] = version
        result["url"] = url

        return jsonify(
            result
        )

    except requests.RequestException as e:

        return jsonify({
            "error": "Impossible de contacter Anime-Sama",
            "message": str(e)
        }), 502

    except Exception as e:

        return jsonify({
            "error": "Erreur",
            "message": str(e)
        }), 500


def get_info_anime_internal(query):

    anime = find_anime(
        query
    )

    if not anime:
        return []

    base_url = anime[
        "lien"
    ]

    title = anime[
        "title"
    ]

    cover = anime.get(
        "cover",
        ""
    )

    html = request_page(
        base_url,
        timeout=15
    )

    return extract_seasons(
        html,
        base_url,
        title,
        cover
    )


# ============================================================
# EPISODES
#
# Anime-Sama utilise episodes.js.
# On récupère le script puis les variables eps1,
# eps2, epsAS, etc.
# ============================================================

@app.route(
    "/api/getAnimeLink",
    methods=["GET"]
)
def get_anime_link():

    name = request.args.get(
        "n",
        ""
    ).strip()

    season = request.args.get(
        "s",
        "saison1"
    ).strip()

    version = request.args.get(
        "v",
        "vostfr"
    ).strip()

    if not name:

        return jsonify({
            "error": "Paramètre 'n' manquant"
        }), 400

    try:

        specific = get_specific_anime_internal(
            name,
            season,
            version
        )

        if not specific:

            return jsonify({
                "error": "Saison introuvable",
                "anime": name,
                "saison": season
            }), 404

        url = specific[
            "url"
        ]

        # ----------------------------------------------------
        # Récupération de la page de la saison
        # ----------------------------------------------------

        html = request_page(
            url,
            timeout=20
        )

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        # ----------------------------------------------------
        # Recherche episodes.js
        # ----------------------------------------------------

        script_tag = soup.find(
            "script",
            src=lambda src: (
                src
                and "episodes.js" in src
            )
        )

        if not script_tag:

            return jsonify({
                "error": "episodes.js introuvable",
                "title": name,
                "season": season,
                "version": version,
                "url": url,
                "episodes": []
            }), 502

        script_src = script_tag.get(
            "src",
            ""
        )

        js_url = (
            url.rstrip("/")
            + "/"
            + script_src.lstrip("/")
        )

        js_response = requests.get(
            js_url,
            headers=HEADERS,
            timeout=20
        )

        js_response.raise_for_status()

        js_text = js_response.text

        # ----------------------------------------------------
        # Recherche :
        #
        # var eps1 = ['...', '...'];
        # var eps2 = ['...', '...'];
        # var epsAS = ['...', '...'];
        # ----------------------------------------------------

        matches = re.findall(
            r"""
            var\s+
            (eps\w+)
            \s*=\s*
            \[
            (.*?)
            \]
            ;
            """,
            js_text,
            flags=re.DOTALL |
            re.IGNORECASE |
            re.VERBOSE
        )

        all_players = {}

        for player_name, content in matches:

            urls = re.findall(
                r"""
                ['"]
                (https?://[^'"]+)
                ['"]
                """,
                content,
                flags=re.I |
                re.X
            )

            if urls:

                all_players[
                    player_name
                ] = urls

        # ----------------------------------------------------
        # Aucun épisode
        # ----------------------------------------------------

        if not all_players:

            return jsonify({
                "title": name,
                "season": season,
                "version": version,
                "url": url,
                "episodes": []
            })

        # ----------------------------------------------------
        # Choisir le meilleur lecteur
        #
        # On ne résout pas les lecteurs ici.
        # On retourne les URLs trouvées par Anime-Sama.
        # ----------------------------------------------------

        player_order = []

        def player_number(player):

            number = re.sub(
                r"[^0-9]",
                "",
                player
            )

            if number:
                return int(number)

            return 999

        player_order = sorted(
            all_players.keys(),
            key=player_number
        )

        max_episodes = max(
            len(urls)
            for urls in all_players.values()
        )

        episodes = []

        for episode_index in range(
            max_episodes
        ):

            selected_url = None
            selected_player = None

            # ------------------------------------------------
            # Priorité aux lecteurs dans l'ordre
            # ------------------------------------------------

            for player in player_order:

                urls = all_players[
                    player
                ]

                if (
                    episode_index
                    >= len(urls)
                ):
                    continue

                candidate = urls[
                    episode_index
                ].strip()

                if not candidate:
                    continue

                selected_url = candidate
                selected_player = player

                break

            if selected_url:

                episodes.append({
                    "episode": episode_index,
                    "url": selected_url,
                    "player": selected_player
                })

        return jsonify({
            "title": name,
            "season": season,
            "version": version,
            "url": url,
            "episodes": episodes
        })

    except requests.RequestException as e:

        return jsonify({
            "error": "Erreur de connexion à Anime-Sama",
            "message": str(e)
        }), 502

    except Exception as e:

        return jsonify({
            "error": "Erreur",
            "message": str(e)
        }), 500


def get_specific_anime_internal(
    name,
    season,
    version
):

    info = get_info_anime_internal(
        name
    )

    if not info:
        return None

    wanted = (
        season
        .lower()
        .replace(" ", "")
    )

    selected = None

    for item in info:

        current = (
            item.get(
                "Saison",
                ""
            )
            .lower()
            .replace(" ", "")
        )

        if current == wanted:

            selected = item
            break

        if (
            wanted in ["oav", "oavs"]
            and "oav" in current
        ):

            selected = item
            break

        if (
            wanted == "film"
            and "film" in current
        ):

            selected = item
            break

    if selected is None:

        selected = info[0]

    result = dict(
        selected
    )

    url = selected[
        "url"
    ].rstrip("/")

    # Anime-Sama :
    # saison1/vostfr
    # saison1/vf

    if not re.search(
        r"/(?:vostfr|vf)$",
        url,
        flags=re.I
    ):

        url += "/" + version

    else:

        url = re.sub(
            r"/(?:vostfr|vf)$",
            "/" + version,
            url,
            flags=re.I
        )

    result["version"] = version
    result["url"] = url

    return result


# ============================================================
# GET ANIME SAMA URL
# ============================================================

@app.route(
    "/api/getAnimeSamaURL",
    methods=["GET"]
)
def get_anime_sama_url():

    return jsonify({
        "url": "https://anime-sama.to"
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
