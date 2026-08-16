# Sports Betting Analyzer — Pipeline 100% gratuit et automatisé

## ⚠️ À lire avant tout

Ce projet calcule un **score de confiance heuristique** (0-100) à partir :
- des cotes moyennes du marché (probabilité implicite),
- du volume/nature de l'actualité récente autour des équipes/joueurs.

Ce n'est **pas** une garantie de gain. Aucun système ne peut prédire un résultat sportif avec certitude — le score sert d'aide à la décision, pas de vérité absolue. Les paris sportifs comportent un risque de perte financière et d'addiction ; fixe-toi des limites de mise avant de jouer.

## Architecture

```
sports-betting-analyzer/
├── .github/workflows/daily.yml     # Cron GitHub Actions (gratuit, tourne chaque jour)
├── src/
│   ├── fetch_odds.py               # Récupère les cotes via The Odds API
│   ├── fetch_news.py               # Récupère l'actu via Google Custom Search API
│   ├── analyze.py                  # Calcule le score de confiance
│   ├── sheets.py                   # Écrit les résultats dans Google Sheets
│   └── export_json.py              # Exporte data.json pour la page web
├── docs/
│   └── index.html                  # Page publique (GitHub Pages)
├── main.py                         # Orchestrateur
├── requirements.txt
└── .env.example
```

## Pourquoi ces choix techniques (au lieu du scraping brut demandé en étape 01)

| Besoin initial | Solution retenue | Pourquoi |
|---|---|---|
| Scraper les sites de paris | **The Odds API** (free tier, 500 req/mois) | Agrège déjà des dizaines de bookmakers FR + intl, légal, stable, pas de risque de ban de compte |
| Chercher l'actu Google | **Google Custom Search JSON API** (free, 100 req/jour) | API officielle Google, gratuite, pas de scraping HTML fragile |
| Compiler dans Google Sheet | **gspread + compte de service Google** | Gratuit, pas d'interaction manuelle nécessaire |
| Page publique | **GitHub Pages** (docs/data.json + index.html) | Gratuit, pas besoin d'exposer ton Sheet publiquement |
| Automatisation quotidienne | **GitHub Actions cron** | Gratuit en repo public (minutes illimitées) |

## Marche à suivre complète

### 1. Créer les comptes/API gratuits

**a) The Odds API** (cotes)
1. https://the-odds-api.com/ → "Get API Key" → inscription gratuite
2. Note ta clé API (free tier : 500 requêtes/mois, largement suffisant pour 1 run/jour)

**b) Google Custom Search JSON API** (actualités)
1. https://console.cloud.google.com/ → créer un projet
2. Activer "Custom Search API"
3. Créer une clé API (APIs & Services → Identifiants)
4. Aller sur https://programmablesearchengine.google.com/ → créer un moteur de recherche → "Rechercher sur tout le web" → noter le `cx` (Search Engine ID)

**c) Google Sheets API + compte de service**
1. Dans le même projet GCP → activer "Google Sheets API" et "Google Drive API"
2. IAM & Admin → Comptes de service → créer un compte de service → générer une clé JSON
3. Créer un Google Sheet vide, le partager (Partager) avec l'email du compte de service (ex: `xxx@xxx.iam.gserviceaccount.com`) en droit "Éditeur"
4. Note l'ID du Sheet (dans l'URL entre `/d/` et `/edit`)

### 2. Créer le repo GitHub

1. Crée un repo (public, pour bénéficier des minutes Actions illimitées) et pousse ce projet
2. Active GitHub Pages : Settings → Pages → Source = branche `main`, dossier `/docs`
3. Ton URL publique sera `https://<ton-user>.github.io/<repo>/`

### 3. Configurer les secrets GitHub

Repo → Settings → Secrets and variables → Actions → New repository secret :
- `ODDS_API_KEY`
- `GOOGLE_CSE_API_KEY`
- `GOOGLE_CSE_ID`
- `GOOGLE_SHEET_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON` → colle le **contenu complet** du fichier JSON du compte de service

### 4. Tester en local (optionnel)

```bash
cp .env.example .env   # puis remplis les valeurs
pip install -r requirements.txt
python main.py
```

### 5. Laisser tourner

Le workflow `.github/workflows/daily.yml` s'exécute chaque jour à 07h00 UTC, régénère `docs/data.json`, le commit automatiquement, et met à jour le Google Sheet. Ta page GitHub Pages se rafraîchit automatiquement au chargement suivant.

## Limites connues (honnêtes)

- The Odds API ne couvre pas forcément les bookmakers crypto-only (ex: Stake) — leur ToS et anti-bot rendent le scraping direct peu fiable en mode gratuit/automatisé.
- Le "score de confiance" est une heuristique simple (cotes + volume d'actu), pas un modèle prédictif entraîné. Tu peux l'améliorer avec un vrai modèle ML si tu veux aller plus loin.
- Free tiers = quotas limités (500 requêtes cotes/mois, 100 requêtes actu/jour) → le code limite volontairement le nombre de matchs/équipes traités par run.
