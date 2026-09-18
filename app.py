from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
import re
import unicodedata

app = Flask(__name__)
CORS(app)

# ============================================================
# CONFIGURATION
# ============================================================

BASE_URL = "https://anime-sama.fr"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}


# ============================================================
# OUTILS
# ============================================================

def clean_text(text):
    if not text:
        return ""

    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        c for c in text
        if not unicodedata.combining(c)
    )

    return re.sub(r"\s+", " ", text).strip()


def slugify(text):
    text = clean_text(text).lower()

    text = text.replace("&", " and ")

    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)

    return text.strip("-")


def get_page(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20
        )

        response.raise_for_status()

        return response.text

    except requests.RequestException as e:
        raise Exception(
            f"Impossible d'accéder à {url}: {str(e)}"
        )


# ============================================================
# RECHERCHE ANIME
# ============================================================

def find_anime(q):
    """
    Recherche un anime sur Anime-Sama.

    Retourne notamment :
    - titre
    - slug
    - url
    """

    q = clean_text(q)

    if not q:
        return None

    slug = slugify(q)

    # --------------------------------------------------------
    # 1. Essai direct
    # --------------------------------------------------------

    possible_urls = [
        f"{BASE_URL}/catalogue/{slug}/",
        f"{BASE_URL}/catalogue/{slug}"
    ]

    for url in possible_urls:

        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=15,
                allow_redirects=True
            )

            if response.status_code == 200:

                soup = BeautifulSoup(
                    response.text,
                    "html.parser"
                )

                title = None

                if soup.title:
                    title = soup.title.get_text(" ", strip=True)

                if not title:
                    h1 = soup.find("h1")

                    if h1:
                        title = h1.get_text(
                            " ",
                            strip=True
                        )

                if title:
                    title = re.sub(
                        r"\s*\|\s*Anime-Sama.*$",
                        "",
                        title,
                        flags=re.I
                    )

                    return {
                        "title": clean_text(title),
                        "slug": slug,
                        "url": f"{BASE_URL}/catalogue/{slug}/"
                    }

        except Exception:
            pass

    return None


# ============================================================
# SAISONS
# ============================================================

def get_seasons_from_anime(anime_url):
    """
    Cherche les saisons disponibles.
    """

    html = get_page(anime_url)

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    seasons = []

    # Recherche des URLs de type :
    #
    # /saison1/
    # /saison2/
    # /saison3/
    #

    links = soup.find_all("a", href=True)

    for link in links:

        href = link.get("href", "")

        match = re.search(
            r"/saison(\d+)/",
            href,
            flags=re.I
        )

        if not match:
            continue

        number = int(match.group(1))

        if number not in seasons:
            seasons.append(number)

    # Recherche également dans tout le HTML
    matches = re.findall(
        r"/saison(\d+)/",
        html,
        flags=re.I
    )

    for match in matches:

        number = int(match)

        if number not in seasons:
            seasons.append(number)

    seasons.sort()

    return seasons


# ============================================================
# GET INFO ANIME
# ============================================================

@app.route("/api/getInfoAnime", methods=["GET"])
def get_info_anime():

    q = request.args.get("q", "").strip()

    if not q:
        return jsonify({
            "error": "Le paramètre q est obligatoire"
        }), 400

    try:

        anime = find_anime(q)

        if not anime:
            return jsonify({
                "error": "Anime introuvable",
                "query": q
            }), 404

        seasons = get_seasons_from_anime(
            anime["url"]
        )

        return jsonify({
            "title": anime["title"],
            "slug": anime["slug"],
            "url": anime["url"],
            "seasons": seasons
        })

    except Exception as e:

        return jsonify({
            "error": "Erreur lors de la recherche",
            "message": str(e)
        }), 500


# ============================================================
# GET SPECIFIC ANIME
# ============================================================

@app.route("/api/getSpecificAnime", methods=["GET"])
def get_specific_anime():

    q = request.args.get("q", "").strip()
    season = request.args.get("s", "saison1").strip()
    version = request.args.get("v", "vostfr").strip()

    if not q:
        return jsonify({
            "error": "Le paramètre q est obligatoire"
        }), 400

    try:

        anime = find_anime(q)

        if not anime:
            return jsonify({
                "error": "Anime introuvable",
                "query": q
            }), 404

        season = season.lower()

        if not season.startswith("saison"):
            season = f"saison{season}"

        version = version.lower()

        url = (
            f"{anime['url']}"
            f"{season}/"
            f"{version}/"
        )

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20
        )

        if response.status_code != 200:

            return jsonify({
                "error": "Saison introuvable",
                "url": url,
                "status": response.status_code
            }), 404

        return jsonify({
            "title": anime["title"],
            "slug": anime["slug"],
            "season": season,
            "version": version,
            "url": url
        })

    except Exception as e:

        return jsonify({
            "error": "Erreur",
            "message": str(e)
        }), 500


# ============================================================
# EXTRACTION DES EPISODES
# ============================================================

def extract_episode_links(html):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    episodes = []

    # --------------------------------------------------------
    # Recherche des liens
    # --------------------------------------------------------

    for tag in soup.find_all(
        ["a", "button", "div"],
        attrs=True
    ):

        text = tag.get_text(
            " ",
            strip=True
        )

        if not text:
            continue

        match = re.search(
            r"(?:episode|ep)\s*(\d+)",
            text,
            flags=re.I
        )

        if not match:
            continue

        number = int(match.group(1))

        # Cherche les URLs dans les attributs
        possible_urls = []

        for attribute in [
            "href",
            "data-url",
            "data-link",
            "data-src",
            "onclick"
        ]:

            value = tag.get(attribute)

            if value:
                possible_urls.append(value)

        for value in possible_urls:

            if not isinstance(value, str):
                continue

            urls = re.findall(
                r'https?://[^\s\'"<>]+',
                value
            )

            for found_url in urls:

                if number not in [
                    x["episode"]
                    for x in episodes
                ]:

                    episodes.append({
                        "episode": number,
                        "url": found_url
                    })

    # --------------------------------------------------------
    # Recherche brute dans le HTML
    # --------------------------------------------------------

    url_pattern = re.compile(
        r'https?://[^\s\'"<>]+',
        flags=re.I
    )

    for found_url in url_pattern.findall(html):

        # Nettoyage
        found_url = found_url.rstrip(
            ".,);]}"
        )

        # On essaye de récupérer le numéro
        # d'épisode proche de l'URL
        context_start = max(
            0,
            html.find(found_url) - 150
        )

        context_end = min(
            len(html),
            html.find(found_url) + len(found_url) + 150
        )

        context = html[
            context_start:context_end
        ]

        match = re.search(
            r"(?:episode|ep)[-_ ]?(\d+)",
            context,
            flags=re.I
        )

        if match:

            number = int(match.group(1))

            if number not in [
                x["episode"]
                for x in episodes
            ]:

                episodes.append({
                    "episode": number,
                    "url": found_url
                })

    # --------------------------------------------------------
    # Tri
    # --------------------------------------------------------

    episodes.sort(
        key=lambda x: x["episode"]
    )

    return episodes


# ============================================================
# GET ANIME LINK
# ============================================================

@app.route("/api/getAnimeLink", methods=["GET"])
def get_anime_link():

    name = request.args.get("n", "").strip()
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
            "error": "Le paramètre n est obligatoire"
        }), 400

    try:

        anime = find_anime(name)

        if not anime:

            return jsonify({
                "error": "Anime introuvable",
                "query": name
            }), 404

        season = season.lower()

        if not season.startswith("saison"):
            season = f"saison{season}"

        version = version.lower()

        url = (
            f"{anime['url']}"
            f"{season}/"
            f"{version}/"
        )

        html = get_page(url)

        episodes = extract_episode_links(
            html
        )

        return jsonify({
            "title": anime["title"],
            "slug": anime["slug"],
            "season": season,
            "version": version,
            "url": url,
            "episodes": episodes
        })

    except Exception as e:

        return jsonify({
            "error": "Erreur lors de la récupération des épisodes",
            "message": str(e)
        }), 500


# ============================================================
# TEST
# ============================================================

@app.route("/", methods=["GET"])
def home():

    return jsonify({
        "status": "online",
        "service": "AnimeSama API",
        "endpoints": [
            "/api/getInfoAnime?q=Demon%20Slayer",
            "/api/getSpecificAnime?q=One%20Piece&s=saison1&v=vostfr",
            "/api/getAnimeLink?n=Spy%20x%20Family&s=saison1&v=vostfr"
        ]
    })


# ============================================================
# LOCAL
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
