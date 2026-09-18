import os
import requests

from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)

# Autorise ton site IONOS à appeler l'API Vercel
CORS(app, resources={
    r"/api/*": {
        "origins": "*"
    }
})


# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

# URL de ton instance AnimeSamaApi
#
# Exemple si tu fais tourner AnimeSamaApi sur un serveur :
#
# ANIMESAMA_API_URL=https://mon-api-animesama.example.com
#
# IMPORTANT :
# Ne mets PAS http://127.0.0.1:5000 ici sur Vercel.
#
ANIMESAMA_API_URL = os.environ.get(
    "ANIMESAMA_API_URL",
    "http://127.0.0.1:5000"
).rstrip("/")


TIMEOUT = 60


# ---------------------------------------------------------
# OUTILS
# ---------------------------------------------------------

def proxy_request(endpoint, params=None):
    """
    Envoie une requête à AnimeSamaApi
    et renvoie directement sa réponse JSON.
    """

    url = f"{ANIMESAMA_API_URL}{endpoint}"

    try:
        response = requests.get(
            url,
            params=params,
            timeout=TIMEOUT,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
                ),
                "Accept": "application/json",
            }
        )

        content_type = response.headers.get(
            "Content-Type",
            ""
        ).lower()

        # AnimeSamaApi doit normalement répondre en JSON
        if "application/json" in content_type:
            data = response.json()
        else:
            try:
                data = response.json()
            except Exception:
                data = {
                    "error": "Réponse non JSON reçue",
                    "response": response.text[:2000]
                }

        return jsonify(data), response.status_code

    except requests.Timeout:
        return jsonify({
            "error": "Timeout",
            "message": (
                "AnimeSamaApi n'a pas répondu dans le délai prévu."
            )
        }), 504

    except requests.RequestException as e:
        return jsonify({
            "error": "Connexion impossible",
            "message": str(e)
        }), 502

    except Exception as e:
        return jsonify({
            "error": "Erreur interne",
            "message": str(e)
        }), 500


# ---------------------------------------------------------
# ROUTE DE TEST
# ---------------------------------------------------------

@app.route("/", methods=["GET"])
def home():

    return jsonify({
        "status": "online",
        "service": "AnimeSama Vercel Proxy",
        "anime_api": ANIMESAMA_API_URL,
        "endpoints": [
            "/api/getInfoAnime?q=Demon%20Slayer",
            "/api/getSpecificAnime?q=One%20Piece&s=saison1&v=vostfr",
            "/api/getAnimeLink?n=Spy%20x%20Family&s=saison1&v=vostfr"
        ]
    })


# ---------------------------------------------------------
# GET INFO ANIME
# ---------------------------------------------------------

@app.route("/api/getInfoAnime", methods=["GET"])
def get_info_anime():

    q = request.args.get("q")

    if not q:
        return jsonify({
            "error": "Paramètre 'q' manquant"
        }), 400

    return proxy_request(
        "/api/getInfoAnime",
        {
            "q": q
        }
    )


# ---------------------------------------------------------
# GET SPECIFIC ANIME
# ---------------------------------------------------------

@app.route("/api/getSpecificAnime", methods=["GET"])
def get_specific_anime():

    q = request.args.get("q")

    if not q:
        return jsonify({
            "error": "Paramètre 'q' manquant"
        }), 400

    s = request.args.get("s", "saison1")
    v = request.args.get("v", "vostfr")

    return proxy_request(
        "/api/getSpecificAnime",
        {
            "q": q,
            "s": s,
            "v": v
        }
    )


# ---------------------------------------------------------
# GET ANIME LINKS
# ---------------------------------------------------------

@app.route("/api/getAnimeLink", methods=["GET"])
def get_anime_link():

    n = request.args.get("n")

    if not n:
        return jsonify({
            "error": "Paramètre 'n' manquant"
        }), 400

    s = request.args.get("s", "saison1")
    v = request.args.get("v", "vostfr")

    return proxy_request(
        "/api/getAnimeLink",
        {
            "n": n,
            "s": s,
            "v": v
        }
    )


# ---------------------------------------------------------
# GET SEARCH ANIME
# ---------------------------------------------------------

@app.route("/api/getSerchAnime", methods=["GET"])
def get_search_anime():

    q = request.args.get("q")

    if not q:
        return jsonify({
            "error": "Paramètre 'q' manquant"
        }), 400

    limit = request.args.get("l", "5")

    return proxy_request(
        "/api/getSerchAnime",
        {
            "q": q,
            "l": limit
        }
    )


# ---------------------------------------------------------
# GET ACTIVE ANIME SAMA URL
# ---------------------------------------------------------

@app.route("/api/getAnimeSamaURL", methods=["GET"])
def get_anime_sama_url():

    return proxy_request(
        "/api/getAnimeSamaURL"
    )


# ---------------------------------------------------------
# GET ALL ANIME
# ---------------------------------------------------------

@app.route("/api/getAllAnime", methods=["GET"])
def get_all_anime():

    params = {}

    r = request.args.get("r")

    if r:
        params["r"] = r

    return proxy_request(
        "/api/getAllAnime",
        params
    )


# ---------------------------------------------------------
# LOAD BASE
# ---------------------------------------------------------

@app.route("/api/loadBaseAnimeData", methods=["GET"])
def load_base_anime_data():

    return proxy_request(
        "/api/loadBaseAnimeData"
    )


# ---------------------------------------------------------
# SCAN HASHMAP
# ---------------------------------------------------------

@app.route("/api/getScanHashmap", methods=["GET"])
def get_scan_hashmap():

    n = request.args.get("n")

    if not n:
        return jsonify({
            "error": "Paramètre 'n' manquant"
        }), 400

    return proxy_request(
        "/api/getScanHashmap",
        {
            "n": n
        }
    )


# ---------------------------------------------------------
# SCAN LINKS
# ---------------------------------------------------------

@app.route("/api/getScanLink", methods=["GET"])
def get_scan_link():

    n = request.args.get("n")

    if not n:
        return jsonify({
            "error": "Paramètre 'n' manquant"
        }), 400

    params = {
        "n": n
    }

    c = request.args.get("c")

    if c:
        params["c"] = c

    return proxy_request(
        "/api/getScanLink",
        params
    )


# ---------------------------------------------------------
# VERCEL
# ---------------------------------------------------------

# Vercel utilise automatiquement cette variable Flask
handler = app
