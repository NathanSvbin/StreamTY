```python
import re
import requests

from bs4 import BeautifulSoup
from flask import Flask, request, jsonify
from flask_cors import CORS


app = Flask(__name__)

CORS(
    app,
    resources={
        r"/api/*": {
            "origins": "*"
        }
    }
)


# =========================================================
# CONFIGURATION
# =========================================================

TIMEOUT = 25

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Referer": "https://anime-sama.org/",
}


# =========================================================
# SESSION HTTP
# =========================================================

session = requests.Session()
session.headers.update(HEADERS)


# =========================================================
# OUTILS
# =========================================================

def error(message, status=500):
    return jsonify({
        "error": message
    }), status


def clean_text(value):
    if not value:
        return ""

    return re.sub(
        r"\s+",
        " ",
        value
    ).strip()


def slugify(text):
    """
    Transforme un titre en slug proche de celui
    utilisé par Anime-Sama.
    """

    text = text.lower().strip()

    replacements = {
        "à": "a",
        "â": "a",
        "ä": "a",
        "é": "e",
        "è": "e",
        "ê": "e",
        "ë": "e",
        "î": "i",
        "ï": "i",
        "ô": "o",
        "ö": "o",
        "ù": "u",
        "û": "u",
        "ü": "u",
        "ÿ": "y",
        "ç": "c",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(
        r"[^a-z0-9]+",
        "-",
        text
    )

    return text.strip("-")


def get(url, **kwargs):
    """
    Requête HTTP avec gestion d'erreur.
    """

    kwargs.setdefault(
        "timeout",
        TIMEOUT
    )

    response = session.get(
        url,
        **kwargs
    )

    response.raise_for_status()

    return response


def soup(url):
    response = get(url)

    return BeautifulSoup(
        response.text,
        "html.parser"
    )


# =========================================================
# TROUVER L'ANIME
# =========================================================

def find_anime(q):
    """
    Essaie de retrouver l'URL catalogue Anime-Sama
    correspondant au titre fourni.

    On utilise d'abord la recherche du site.
    Si elle ne fonctionne pas, on essaie directement
    le slug.
    """

    q = clean_text(q)

    if not q:
        return None

    # -----------------------------------------------------
    # 1. Recherche Anime-Sama
    # -----------------------------------------------------

    search_urls = [
        "https://anime-sama.org/catalogue/",
        "https://anime-sama.org/",
    ]

    slug = slugify(q)

    # -----------------------------------------------------
    # 2. Tentative directe
    # -----------------------------------------------------

    direct_urls = [
        f"https://anime-sama.org/catalogue/{slug}/",
        f"https://anime-sama.eu/catalogue/{slug}/",
        f"https://anime-sama.tv/catalogue/{slug}/",
    ]

    for url in direct_urls:

        try:
            response = session.get(
                url,
                timeout=TIMEOUT,
                allow_redirects=True
            )

            if response.status_code != 404:

                final_url = response.url

                if "/catalogue/" in final_url:

                    return {
                        "title": q,
                        "url": final_url.rstrip("/") + "/"
                    }

        except requests.RequestException:
            pass

    # -----------------------------------------------------
    # 3. Recherche dans la page catalogue
    # -----------------------------------------------------

    for base in search_urls:

        try:
            response = session.get(
                base,
                timeout=TIMEOUT
            )

            if response.status_code != 200:
                continue

            page = BeautifulSoup(
                response.text,
                "html.parser"
            )

            links = page.find_all(
                "a",
                href=True
            )

            q_normalized = slugify(q)

            for link in links:

                href = link.get("href", "")

                text = clean_text(
                    link.get_text(" ", strip=True)
                )

                if "/catalogue/" not in href:
                    continue

                candidate = slugify(
                    text
                )

                if (
                    candidate == q_normalized
                    or q_normalized in candidate
                    or candidate in q_normalized
                ):

                    if href.startswith("/"):
                        href = (
                            "https://anime-sama.org"
                            + href
                        )

                    return {
                        "title": text or q,
                        "url": href.rstrip("/") + "/"
                    }

        except requests.RequestException:
            continue

    return None


# =========================================================
# SAISONS
# =========================================================

def get_seasons_from_anime(anime):
    """
    Récupère les saisons disponibles.
    """

    base_url = anime["url"]

    page = soup(base_url)

    results = []

    # -----------------------------------------------------
    # Cherche tous les liens contenant /saison
    # -----------------------------------------------------

    for link in page.find_all(
        "a",
        href=True
    ):

        href = link["href"]

        if "/saison" not in href.lower():
            continue

        title = clean_text(
            link.get_text(" ", strip=True)
        )

        match = re.search(
            r"saison[-_ ]?(\d+)",
            href.lower()
        )

        if not match:
            match = re.search(
                r"saison[-_ ]?(\d+)",
                title.lower()
            )

        if match:
            number = int(
                match.group(1)
            )
        else:
            continue

        if href.startswith("/"):
            href = (
                "https://anime-sama.org"
                + href
            )

        href = href.rstrip("/") + "/"

        item = {
            "base_url": base_url,
            "title": anime["title"],
            "Saison": f"Saison {number}",
            "url": href,
            "_number": number
        }

        # Évite les doublons
        if not any(
            x["url"] == href
            for x in results
        ):
            results.append(item)

    # -----------------------------------------------------
    # Si aucun lien n'a été trouvé, on essaie les URLs
    # saison1, saison2, etc.
    # -----------------------------------------------------

    if not results:

        for number in range(1, 101):

            url = (
                base_url.rstrip("/")
                + f"/saison{number}/"
            )

            try:
                response = session.get(
                    url,
                    timeout=TIMEOUT
                )

                if response.status_code != 200:
                    continue

                results.append({
                    "base_url": base_url,
                    "title": anime["title"],
                    "Saison": f"Saison {number}",
                    "url": url,
                    "_number": number
                })

            except requests.RequestException:
                continue

    results.sort(
        key=lambda x: x["_number"]
    )

    for item in results:
        item.pop("_number", None)

    return results


# =========================================================
# ROUTE INFO ANIME
# =========================================================

@app.route(
    "/api/getInfoAnime",
    methods=["GET"]
)
def get_info_anime():

    q = request.args.get("q")

    if not q:
        return error(
            "Paramètre 'q' manquant",
            400
        )

    try:

        anime = find_anime(q)

        if not anime:
            return jsonify([])

        seasons = get_seasons_from_anime(
            anime
        )

        return jsonify(seasons)

    except requests.RequestException as e:

        return error(
            f"Erreur Anime-Sama : {str(e)}",
            502
        )

    except Exception as e:

        return error(
            str(e),
            500
        )


# =========================================================
# SAISON SPÉCIFIQUE
# =========================================================

@app.route(
    "/api/getSpecificAnime",
    methods=["GET"]
)
def get_specific_anime():

    q = request.args.get("q")

    if not q:
        return error(
            "Paramètre 'q' manquant",
            400
        )

    season = request.args.get(
        "s",
        "saison1"
    )

    version = request.args.get(
        "v",
        "vostfr"
    )

    try:

        anime = find_anime(q)

        if not anime:
            return error(
                "Anime introuvable",
                404
            )

        base_url = anime["url"]

        url = (
            base_url.rstrip("/")
            + "/"
            + season.strip("/")
            + "/"
            + version.strip("/")
        )

        return jsonify({
            "base_url": base_url,
            "title": anime["title"],
            "Saison": season.replace(
                "saison",
                "Saison "
            ),
            "url": url
        })

    except requests.RequestException as e:

        return error(
            str(e),
            502
        )

    except Exception as e:

        return error(
            str(e),
            500
        )


# =========================================================
# EXTRACTION DES ÉPISODES
# =========================================================

def extract_episode_links(url):
    """
    Cherche les liens d'épisodes présents dans
    la page Anime-Sama.

    Cette fonction récupère les URLs des lecteurs,
    sans essayer de télécharger les vidéos.
    """

    response = get(url)

    page = BeautifulSoup(
        response.text,
        "html.parser"
    )

    results = []

    # -----------------------------------------------------
    # Cherche les URLs contenant episode / eps
    # -----------------------------------------------------

    for tag in page.find_all(
        ["a", "iframe", "source"],
    ):

        href = (
            tag.get("href")
            or tag.get("src")
            or ""
        )

        href = href.strip()

        if not href:
            continue

        # Numéro d'épisode
        text = clean_text(
            tag.get_text(" ", strip=True)
        )

        match = re.search(
            r"(?:episode|ep|épisode)[\s_-]*(\d+)",
            text.lower()
        )

        if not match:
            match = re.search(
                r"(?:episode|ep)[\s_-]*(\d+)",
                href.lower()
            )

        if not match:
            continue

        episode = int(
            match.group(1)
        )

        if href.startswith("//"):
            href = "https:" + href

        elif href.startswith("/"):
            href = (
                "https://anime-sama.org"
                + href
            )

        item = {
            "episode": episode,
            "url": href
        }

        if item not in results:
            results.append(item)

    # -----------------------------------------------------
    # Cherche également les URLs présentes dans
    # les attributs data-*
    # -----------------------------------------------------

    for tag in page.find_all(True):

        for attribute, value in tag.attrs.items():

            if not attribute.startswith("data-"):
                continue

            if not isinstance(value, str):
                continue

            urls = re.findall(
                r'https?://[^\s"\']+',
                value
            )

            for found_url in urls:

                match = re.search(
                    r"(?:episode|ep)[\s_-]*(\d+)",
                    found_url.lower()
                )

                if not match:
                    continue

                episode = int(
                    match.group(1)
                )

                item = {
                    "episode": episode,
                    "url": found_url
                }

                if item not in results:
                    results.append(item)

    # -----------------------------------------------------
    # Tri
    # -----------------------------------------------------

    results.sort(
        key=lambda x: x["episode"]
    )

    return results


# =========================================================
# GET ANIME LINK
# =========================================================

@app.route(
    "/api/getAnimeLink",
    methods=["GET"]
)
def get_anime_link():

    name = request.args.get("n")

    if not name:
        return error(
            "Paramètre 'n' manquant",
            400
        )

    season = request.args.get(
        "s",
        "saison1"
    )

    version = request.args.get(
        "v",
        "vostfr"
    )

    try:

        anime = find_anime(name)

        if not anime:
            return error(
                "Anime introuvable",
                404
            )

        season_url = (
            anime["url"].rstrip("/")
            + "/"
            + season.strip("/")
            + "/"
            + version.strip("/")
        )

        links = extract_episode_links(
            season_url
        )

        return jsonify(links)

    except requests.HTTPError as e:

        return error(
            f"Anime-Sama HTTP error : {str(e)}",
            502
        )

    except requests.RequestException as e:

        return error(
            f"Connexion Anime-Sama impossible : {str(e)}",
            502
        )

    except Exception as e:

        return error(
            str(e),
            500
        )


# =========================================================
# TEST
# =========================================================

@app.route(
    "/",
    methods=["GET"]
)
def home():

    return jsonify({
        "status": "online",
        "service": "AnimeSama Vercel API",
        "message": "API opérationnelle",
        "endpoints": [
            "/api/getInfoAnime?q=Demon%20Slayer",
            "/api/getSpecificAnime?q=Demon%20Slayer&s=saison1&v=vostfr",
            "/api/getAnimeLink?n=Spy%20x%20Family&s=saison1&v=vostfr"
        ]
    })


# =========================================================
# VERCEL
# =========================================================

handler = app
```
