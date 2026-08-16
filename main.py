import os
import time
from datetime import date
from dotenv import load_dotenv

from src.fetch_odds import get_events
from src.fetch_news import get_team_news
from src.analyze import analyze_event
from src.export_json import export

load_dotenv()

ODDS_API_KEY = os.environ["ODDS_API_KEY"]
GOOGLE_CSE_API_KEY = os.environ["GOOGLE_CSE_API_KEY"]
GOOGLE_CSE_ID = os.environ["GOOGLE_CSE_ID"]
SPORT_KEYS = os.environ.get("SPORT_KEYS", "soccer_epl").split(",")
MAX_EVENTS = int(os.environ.get("MAX_EVENTS", "15"))

# Ces deux-là sont optionnels ici : le script peut tourner sans Sheets
# (utile pour tester juste odds+news+analyse+JSON en local)
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")


def main():
    print("1/4 - Recuperation des cotes du jour...")
    events = get_events(SPORT_KEYS, ODDS_API_KEY, max_events=MAX_EVENTS)
    print(f"   -> {len(events)} rencontres trouvees")

    print("2/4 - Recuperation de l'actualite des equipes...")
    news_cache = {}
    results = []
    for ev in events:
        for team in (ev["home_team"], ev["away_team"]):
            if team not in news_cache:
                news_cache[team] = get_team_news(team, GOOGLE_CSE_API_KEY, GOOGLE_CSE_ID)
                time.sleep(1)  # ménage le quota gratuit

        print("3/4 - Analyse:", ev["match"])
        results.append(analyze_event(ev, news_cache[ev["home_team"]], news_cache[ev["away_team"]]))

    print("4/4 - Export...")
    export(results, "docs/data.json")

    if GOOGLE_SHEET_ID and GOOGLE_SERVICE_ACCOUNT_JSON:
        from src.sheets import write_results
        write_results(GOOGLE_SHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON, results, str(date.today()))
        print("   -> Google Sheet mis a jour")
    else:
        print("   -> Google Sheet ignore (variables non definies)")

    print("Termine.")


if __name__ == "__main__":
    main()
