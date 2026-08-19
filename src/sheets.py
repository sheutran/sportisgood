"""
Écrit les résultats du jour dans un Google Sheet via un compte de service.
"""
import json
import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]

HEADERS = [
    "Date", "Heure GMT", "Pays/Compétition", "Match", "Sélection", "Type de pari",
    "Cote moyenne", "Probabilité marché (%)", "Signal actu (net)", "Nb articles actu",
    "Part effets d'annonce (%)", "Sources actu", "Nb affrontements passés",
    "Historique (G/N/P)", "Score de confiance (%)", "Nb bookmakers",
    "Bookmaker (cote max)", "Cote max", "Bookmaker (cote min)", "Cote min",
    "Détail toutes les cotes",
]


def format_odds_detail(odds_detail: list) -> str:
    """Ex: 'Bet365: 2.10, Winamax: 2.05, Unibet: 1.95'"""
    return ", ".join(f"{d['bookmaker']}: {d['odds']}" for d in odds_detail)


def get_client(service_account_json_str: str) -> gspread.Client:
    info = json.loads(service_account_json_str)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


def write_results(sheet_id: str, service_account_json_str: str, results: list, run_date: str):
    client = get_client(service_account_json_str)
    sh = client.open_by_key(sheet_id)
    ws = sh.sheet1
    ws.clear()

    rows = [HEADERS]
    for r in results:
        best = r["best_pick"]
        if not best:
            continue
        rows.append([
            run_date,
            r["commence_time_gmt"],
            f"{r['sport']} ({r['country']})",
            r["match"],
            best["selection"],
            best["type"],
            best["odds"],
            best["market_probability_pct"],
            best["news_net_signal"],
            best["news_nb_articles"],
            best["news_hype_ratio_pct"],
            best["news_sources"],
            r["h2h_nb_matches"],
            r["h2h_summary"] or "N/A",
            best["confidence_score_pct"],
            r["nb_bookmakers"],
            best.get("max_bookmaker") or "N/A",
            best.get("max_odds") or "",
            best.get("min_bookmaker") or "N/A",
            best.get("min_odds") or "",
            format_odds_detail(best.get("odds_detail", [])),
        ])

    # Trie par score de confiance décroissant (hors en-tête)
    header, body = rows[0], rows[1:]
    body.sort(key=lambda row: row[14], reverse=True)
    ws.update(values=[header] + body, range_name="A1")
