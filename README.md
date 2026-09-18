# StreamTY

# AnimeSama Vercel Proxy

Proxy Flask permettant de rendre accessible une instance AnimeSamaApi depuis
un site hébergé sur IONOS.

## Architecture

IONOS
  ↓
Vercel
  ↓
AnimeSamaApi
  ↓
Anime-Sama

## Installation

Cloner le projet :

git clone https://github.com/TON_COMPTE/animesama-vercel.git

Puis :

cd animesama-vercel

Installer les dépendances :

pip install -r requirements.txt

## Variable d'environnement

Dans Vercel, ajouter :

ANIMESAMA_API_URL

Exemple :

https://mon-api-animesama.example.com

Ne pas utiliser :

http://127.0.0.1:5000

car cette adresse désigne la machine locale.

## Endpoints

### Informations anime

/api/getInfoAnime?q=Demon%20Slayer

### Saison spécifique

/api/getSpecificAnime?q=One%20Piece&s=saison1&v=vostfr

### Liens des épisodes

/api/getAnimeLink?n=Spy%20x%20Family&s=saison1&v=vostfr

### Recherche

/api/getSerchAnime?q=Naruto&l=5

### URL Anime-Sama

/api/getAnimeSamaURL

### Catalogue

/api/getAllAnime

### Base locale

/api/loadBaseAnimeData

### Scans

/api/getScanHashmap?n=Frieren

/api/getScanLink?n=Frieren&c=2

## Exemple JavaScript

fetch(
    "https://TON-PROJET.vercel.app/api/getInfoAnime?q=Demon%20Slayer"
)
.then(response => response.json())
.then(data => {
    console.log(data);
});

## Exemple PHP

$url =
    "https://TON-PROJET.vercel.app/api/getInfoAnime?q="
    . urlencode("Demon Slayer");

$response = file_get_contents($url);

$data = json_decode($response, true);

print_r($data);
