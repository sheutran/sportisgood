"""
Grand livre des paris virtuels: persistance dans un fichier JSON versionné
(comme docs/data.json), réglé automatiquement au run suivant une fois les
rencontres terminées, via l'endpoint /scores de The Odds API (résultats
disponibles jusqu'à 3 jours en arrière, plan gratuit).
"""
import json
import math
import os
import time
import requests
from datetime import datetime, timezone, timedelta

ODDS_API_BASE = "https://api.the-odds-api.com/v4"


def load_ledger(path: str) -> dict:
    if not os.path.exists(path):
        return {"days": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_ledger(ledger: dict, path: str):
    """Écriture atomique: on écrit d'abord dans un fichier temporaire, puis on le
    renomme à la place du fichier final. Si une erreur survient en cours d'écriture
    (ex: valeur non sérialisable), le fichier déjà en place N'EST JAMAIS corrompu.

    allow_nan=False fait volontairement planter le script si une valeur NaN/Infinity
    s'est glissée dans les données: Python accepte NaN comme JSON par défaut (et
    l'écrit sans erreur), mais ce n'est PAS du JSON valide au sens strict, et le
    navigateur (JSON.parse côté JS) le rejette silencieusement plus tard. Mieux vaut
    un échec bruyant ici, dans les logs GitHub Actions, qu'un fichier public cassé."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(ledger, f, ensure_ascii=False, indent=2, allow_nan=False)
    os.replace(tmp_path, path)  # remplacement atomique, seulement si l'écriture a réussi


def fetch_scores(sport_key: str, api_key: str, days_from: int = 3) -> dict:
    """Retourne un dict {event_id: évènement (avec scores)} pour un sport donné."""
    url = f"{ODDS_API_BASE}/sports/{sport_key}/scores"
    params = {"apiKey": api_key, "daysFrom": days_from, "dateFormat": "iso"}
    try:
        resp = requests.get(url, params=params, timeout=20)
    except requests.RequestException as e:
        print(f"[ledger] Erreur réseau /scores pour {sport_key}: {e}")
        return {}
    if resp.status_code != 200:
        print(f"[ledger] Erreur {resp.status_code} /scores pour {sport_key}: {resp.text[:200]}")
        return {}
    return {ev["id"]: ev for ev in resp.json()}


def _safe_round(value, ndigits=2):
    """Comme round(), mais renvoie 0.0 si la valeur est NaN/Infinity au lieu de
    laisser une valeur non-JSON-valide se propager jusqu'au fichier final."""
    try:
        if not math.isfinite(value):
            print(f"[ledger] ATTENTION - valeur non finie détectée ({value}), remplacée par 0.0")
            return 0.0
    except TypeError:
        return 0.0
    return round(value, ndigits)


def _settle_one(bet: dict, scores_by_id: dict) -> None:
    """Modifie `bet` en place si un résultat exploitable est trouvé."""
    if bet["status"] != "pending":
        return

    ev = scores_by_id.get(bet.get("event_id"))
    if not ev or not ev.get("completed") or not ev.get("scores"):
        return  # pas encore joué, ou résultat pas encore disponible

    score_map = {}
    for s in ev["scores"]:
        try:
            score_map[s["name"]] = float(s["score"])
        except (TypeError, ValueError, KeyError):
            return  # score illisible, on retentera au prochain run

    home_score = score_map.get(bet["home_team"])
    away_score = score_map.get(bet["away_team"])
    if home_score is None or away_score is None:
        return
    if not (math.isfinite(home_score) and math.isfinite(away_score)):
        return  # score aberrant renvoyé par l'API, on retentera au prochain run

    if home_score == away_score:
        winner = "draw"
    elif home_score > away_score:
        winner = "home"
    else:
        winner = "away"

    if bet["type"] == "Nul":
        won = winner == "draw"
    elif bet["type"] == "Victoire domicile":
        won = winner == "home"
    else:  # "Victoire extérieur"
        won = winner == "away"

    bet["status"] = "won" if won else "lost"
    bet["payout"] = _safe_round(bet["stake"] * bet["odds_used"]) if won else 0.0
    bet["profit"] = _safe_round(bet["payout"] - bet["stake"])
    bet["final_score"] = f"{int(home_score)}-{int(away_score)}"


def settle_pending_days(ledger: dict, odds_api_key: str) -> None:
    """Tente de régler tous les paris encore en attente, tous jours confondus."""
    pending_sports = set()
    for day in ledger["days"]:
        if day.get("settled"):
            continue
        for bet in day["bets"]:
            if bet["status"] == "pending":
                pending_sports.add(bet["sport"])

    if not pending_sports:
        print("[ledger] Aucun pari en attente de règlement.")
        return

    print(f"[ledger] Récupération des scores pour: {sorted(pending_sports)}")
    scores_by_sport = {}
    for sport_key in pending_sports:
        scores_by_sport[sport_key] = fetch_scores(sport_key, odds_api_key)
        time.sleep(0.3)

    for day in ledger["days"]:
        if day.get("settled"):
            continue

        for bet in day["bets"]:
            if bet["status"] != "pending":
                continue
            _settle_one(bet, scores_by_sport.get(bet["sport"], {}))

            # Filet de sécurité: au-delà de 3 jours (limite de l'API pour les scores
            # passés), un pari resté "pending" est marqué comme non résolu plutôt
            # que bloqué indéfiniment (ex: run manqué plusieurs jours de suite).
            if bet["status"] == "pending":
                try:
                    commence = datetime.fromisoformat(bet["commence_time_gmt"].replace("Z", "+00:00"))
                    if datetime.now(timezone.utc) - commence > timedelta(days=3):
                        bet["status"] = "unresolved"
                except (ValueError, AttributeError):
                    pass

        if not any(b["status"] == "pending" for b in day["bets"]):
            resolved = [b for b in day["bets"] if b["status"] in ("won", "lost")]
            day["day_total_payout"] = _safe_round(sum((b["payout"] or 0) for b in resolved))
            day["day_profit"] = _safe_round(day["day_total_payout"] - sum(b["stake"] for b in resolved))
            day["settled"] = True
            print(f"[ledger] Journée {day['date']} réglée: profit = {day['day_profit']} EUR")


def add_new_day(ledger: dict, date_str: str, stakes: list, budget: float) -> None:
    """Ajoute (ou remplace, si le workflow est relancé le même jour) la journée du jour."""
    ledger["days"] = [d for d in ledger["days"] if d["date"] != date_str]

    is_empty_day = len(stakes) == 0
    ledger["days"].append({
        "date": date_str,
        "budget": budget,
        "bets": stakes,
        "day_total_staked": _safe_round(sum(s["stake"] for s in stakes)),
        # Une journée sans pari qualifié est réglée d'office à 0 (et pas à null),
        # pour rester cohérent avec settled=True côté page web, qui suppose que
        # settled=True implique toujours des totaux numériques exploitables.
        "day_total_payout": 0.0 if is_empty_day else None,
        "day_profit": 0.0 if is_empty_day else None,
        "settled": is_empty_day,
    })
