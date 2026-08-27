import os
import time
from datetime import date
from dotenv import load_dotenv

from src.fetch_odds import get_events
from src.fetch_news import get_team_news, fetch_all_general_feeds
from src.rss_sources import select_feeds
from src.head_to_head import fetch_head_to_head
from src.analyze import analyze_event
from src.export_json import export
from src.betting_simulator import allocate_stakes
from src.ledger import load_ledger, save_ledger, settle_pending_days, add_new_day

load_dotenv()

ODDS_API_KEY = os.environ["ODDS_API_KEY"]
SPORT_KEYS = os.environ.get("SPORT_KEYS", "soccer_epl").split(",")
MAX_EVENTS = int(os.environ.get("MAX_EVENTS", "15"))
HOURS_AHEAD = int(os.environ.get("HOURS_AHEAD", "168"))  # 7 jours par défaut
MAX_RSS_FEEDS = int(os.environ.get("MAX_RSS_FEEDS", "15"))
MAX_H2H_MATCHES = int(os.environ.get("MAX_H2H_MATCHES", "5"))
DAILY_BUDGET_EUR = float(os.environ.get("DAILY_BUDGET_EUR", "10"))
MIN_CONFIDENCE_FOR_BET = float(os.environ.get("MIN_CONFIDENCE_FOR_BET", "70"))
LEDGER_PATH = "docs/betting_ledger.json"

# Ces deux-là sont optionnels ici : le script peut tourner sans Sheets
# (utile pour tester juste odds+news+analyse+JSON en local)
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")


def main():
    print("1/8 - Recuperation des cotes du jour...")
    events = get_events(SPORT_KEYS, ODDS_API_KEY, max_events=MAX_EVENTS, hours_ahead=HOURS_AHEAD)
    print(f"   -> {len(events)} rencontres trouvees")

    print("2/8 - Selection des flux RSS diversifies selon les sports dominants...")
    feeds = select_feeds(events, max_feeds=MAX_RSS_FEEDS)
    print(f"   -> {len(feeds)} flux retenus: {[f['name'] for f in feeds]}")
    general_articles = fetch_all_general_feeds(feeds)
    print(f"   -> {len(general_articles)} articles au total dans ces flux")

    print("3/8 - Recuperation de l'actualite par equipe...")
    news_cache = {}
    for ev in events:
        for team in (ev["home_team"], ev["away_team"]):
            if team not in news_cache:
                news_cache[team] = get_team_news(team, general_articles=general_articles)
                time.sleep(1)  # évite d'enchaîner les requêtes Google News RSS trop vite

    print("4/8 - Recuperation de l'historique des face-a-face...")
    results = []
    for ev in events:
        h2h_events = fetch_head_to_head(ev["home_team"], ev["away_team"], max_events=MAX_H2H_MATCHES)

        print("5/8 - Analyse:", ev["match"])
        results.append(analyze_event(
            ev, news_cache[ev["home_team"]], news_cache[ev["away_team"]], h2h_events=h2h_events))

    print("6/8 - Export...")
    export(results, "docs/data.json")

    print("7/8 - Reglement des paris virtuels en attente...")
    ledger = load_ledger(LEDGER_PATH)
    settle_pending_days(ledger, ODDS_API_KEY)

    print("8/8 - Repartition du budget virtuel du jour...")
    stakes = allocate_stakes(results, budget=DAILY_BUDGET_EUR, min_confidence=MIN_CONFIDENCE_FOR_BET)
    add_new_day(ledger, str(date.today()), stakes, DAILY_BUDGET_EUR)
    save_ledger(ledger, LEDGER_PATH)
    total_staked = sum(s["stake"] for s in stakes)
    print(f"   -> {len(stakes)} pari(s) virtuel(s) place(s) pour {total_staked:.2f} EUR "
          f"(seuil >= {MIN_CONFIDENCE_FOR_BET}%)")

    if GOOGLE_SHEET_ID and GOOGLE_SERVICE_ACCOUNT_JSON:
        from src.sheets import write_results
        write_results(GOOGLE_SHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON, results, str(date.today()))
        print("   -> Google Sheet mis a jour")
    else:
        print("   -> Google Sheet ignore (variables non definies)")

    print("Termine.")


if __name__ == "__main__":
    main()
