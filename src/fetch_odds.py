"""
Récupère les rencontres du jour et leurs cotes via The Odds API.
Free tier: https://the-odds-api.com/ (500 requêtes/mois)
"""
import os
import requests
from datetime import datetime, timezone, timedelta

ODDS_API_BASE = "https://api.the-odds-api.com/v4"


def get_valid_sport_keys(api_key: str) -> set:
    """Récupère la liste des sport_key réellement valides et en saison.
    /v4/sports ne coûte aucun crédit de quota, donc on peut l'appeler à chaque run."""
    resp = requests.get(f"{ODDS_API_BASE}/sports", params={"apiKey": api_key}, timeout=20)
    if resp.status_code != 200:
        print(f"[fetch_odds] Impossible de récupérer /v4/sports: {resp.status_code} {resp.text[:200]}")
        return set()
    return {s["key"] for s in resp.json()}


def fetch_odds_for_sport(sport_key: str, api_key: str, regions="eu,uk") -> list:
    """Récupère les cotes h2h (1X2 / vainqueur) pour un sport donné."""
    url = f"{ODDS_API_BASE}/sports/{sport_key}/odds"
    params = {
        "apiKey": api_key,
        "regions": regions,
        "markets": "h2h",
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    }
    resp = requests.get(url, params=params, timeout=20)

    # Headers utiles pour vérifier le quota restant / diagnostiquer un blocage silencieux
    remaining = resp.headers.get("x-requests-remaining")
    used = resp.headers.get("x-requests-used")
    print(f"[fetch_odds] {sport_key}: HTTP {resp.status_code} | quota utilisé={used} restant={remaining}")

    if resp.status_code != 200:
        print(f"[fetch_odds] Erreur {resp.status_code} pour {sport_key}: {resp.text[:300]}")
        return []

    data = resp.json()
    if not data:
        print(f"[fetch_odds] {sport_key}: réponse vide (0 rencontre trouvée par l'API — "
              f"hors-saison ou aucun match dans la fenêtre couverte)")
    return data


def within_window(iso_date: str, hours_ahead: int) -> bool:
    """Filtre les rencontres prévues entre maintenant et hours_ahead heures (GMT/UTC)."""
    try:
        event_dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    except ValueError:
        return False
    now = datetime.now(timezone.utc)
    return now <= event_dt <= now + timedelta(hours=hours_ahead)


def average_odds(bookmakers: list, outcome_name: str) -> float | None:
    """Moyenne des cotes proposées par tous les bookmakers pour une issue donnée
    (réduit le biais/marge propre à un seul bookmaker)."""
    values = []
    for bk in bookmakers:
        for market in bk.get("markets", []):
            if market["key"] != "h2h":
                continue
            for outcome in market["outcomes"]:
                if outcome["name"] == outcome_name:
                    values.append(outcome["price"])
    return round(sum(values) / len(values), 2) if values else None


def get_events(sport_keys: list, api_key: str, max_events: int = 15, hours_ahead: int = 24) -> list:
    """Retourne une liste d'événements normalisés, prêts pour l'étape d'analyse.

    hours_ahead: fenêtre de recherche cible (24h par défaut). Si aucune rencontre
    n'est trouvée dans cette fenêtre, la recherche s'élargit automatiquement
    (48h, puis 7 jours) plutôt que de renvoyer une page vide."""
    valid_keys = get_valid_sport_keys(api_key)
    if valid_keys:
        unknown = [k for k in sport_keys if k not in valid_keys]
        if unknown:
            print(f"[fetch_odds] ATTENTION - ces sport_key sont inconnues ou hors-saison "
                  f"et seront ignorées: {unknown}")
        sport_keys = [k for k in sport_keys if k in valid_keys]

    # On récupère les cotes brutes une seule fois par sport (coûte du quota),
    # puis on applique différentes largeurs de fenêtre en mémoire, sans refaire d'appel API.
    raw_by_sport = {}
    for sport_key in sport_keys:
        raw_events = fetch_odds_for_sport(sport_key, api_key)
        raw_by_sport[sport_key] = raw_events
        if raw_events:
            times = [e.get("commence_time", "") for e in raw_events]
            print(f"[fetch_odds] {sport_key}: {len(raw_events)} rencontre(s) reçue(s), "
                  f"prochaine: {min(times)}")

    def build_events(window_hours: int) -> list:
        events = []
        for sport_key, raw_events in raw_by_sport.items():
            for ev in raw_events:
                if not within_window(ev.get("commence_time", ""), window_hours):
                    continue
                home = ev.get("home_team")
                away = ev.get("away_team")
                bookmakers = ev.get("bookmakers", [])
                events.append({
                    "sport": sport_key,
                    "match": f"{home} vs {away}",
                    "home_team": home,
                    "away_team": away,
                    "commence_time_gmt": ev.get("commence_time"),
                    "country": sport_key.split("_")[0] if "_" in sport_key else "N/A",
                    "odds_home": average_odds(bookmakers, home),
                    "odds_away": average_odds(bookmakers, away),
                    "odds_draw": average_odds(bookmakers, "Draw"),
                    "nb_bookmakers": len(bookmakers),
                })
        return events

    for attempt_window in [hours_ahead, 48, 168]:
        events = build_events(attempt_window)
        if events:
            if attempt_window != hours_ahead:
                print(f"[fetch_odds] Aucune rencontre dans les {hours_ahead}h demandées, "
                      f"fenêtre élargie automatiquement à {attempt_window}h.")
            break
    else:
        print(f"[fetch_odds] Aucune rencontre trouvée même en élargissant jusqu'à 7 jours.")
        events = []

    events.sort(key=lambda e: e["commence_time_gmt"] or "")
    return events[:max_events]
