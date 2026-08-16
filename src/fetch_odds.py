"""
Récupère les rencontres du jour et leurs cotes via The Odds API.
Free tier: https://the-odds-api.com/ (500 requêtes/mois)
"""
import os
import requests
from datetime import datetime, timezone, timedelta

ODDS_API_BASE = "https://api.the-odds-api.com/v4"


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
    if resp.status_code != 200:
        print(f"[fetch_odds] Erreur {resp.status_code} pour {sport_key}: {resp.text[:200]}")
        return []
    return resp.json()


def is_today_or_tomorrow(iso_date: str) -> bool:
    """Filtre les rencontres prévues dans les prochaines 36h (fuseau GMT)."""
    try:
        event_dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    except ValueError:
        return False
    now = datetime.now(timezone.utc)
    return now <= event_dt <= now + timedelta(hours=36)


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


def get_events(sport_keys: list, api_key: str, max_events: int = 15) -> list:
    """Retourne une liste d'événements normalisés, prêts pour l'étape d'analyse."""
    all_events = []
    for sport_key in sport_keys:
        raw_events = fetch_odds_for_sport(sport_key, api_key)
        for ev in raw_events:
            if not is_today_or_tomorrow(ev.get("commence_time", "")):
                continue
            home = ev.get("home_team")
            away = ev.get("away_team")
            bookmakers = ev.get("bookmakers", [])
            all_events.append({
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

    all_events.sort(key=lambda e: e["commence_time_gmt"] or "")
    return all_events[:max_events]
