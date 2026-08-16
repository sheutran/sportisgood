"""
Récupère l'actualité récente (dernier mois) autour d'une équipe/d'un joueur
via l'API Google Custom Search JSON (free tier: 100 requêtes/jour).
"""
import requests

CSE_URL = "https://www.googleapis.com/customsearch/v1"

# Mots-clés simples pour un signal de tonalité très basique (FR).
# NB: c'est une heuristique grossière, pas une vraie analyse de sentiment NLP.
POSITIVE_WORDS = ["victoire", "forme", "retour", "titulaire", "en forme", "invaincu", "domine"]
NEGATIVE_WORDS = ["blessé", "blessure", "suspendu", "absent", "défaite", "crise", "sanction", "incertain"]


def search_news(query: str, api_key: str, cse_id: str, num: int = 5) -> list:
    params = {
        "key": api_key,
        "cx": cse_id,
        "q": query,
        "dateRestrict": "m1",  # dernier mois
        "num": num,
        "lr": "lang_fr|lang_en",
    }
    resp = requests.get(CSE_URL, params=params, timeout=20)
    if resp.status_code != 200:
        print(f"[fetch_news] Erreur {resp.status_code} pour '{query}': {resp.text[:200]}")
        return []
    items = resp.json().get("items", [])
    return [{"title": i.get("title", ""), "snippet": i.get("snippet", ""), "link": i.get("link", "")}
            for i in items]


def news_signal(articles: list) -> dict:
    """Calcule un score brut de tonalité à partir des titres/snippets récupérés."""
    text = " ".join((a["title"] + " " + a["snippet"]).lower() for a in articles)
    pos = sum(text.count(w) for w in POSITIVE_WORDS)
    neg = sum(text.count(w) for w in NEGATIVE_WORDS)
    return {
        "nb_articles": len(articles),
        "positive_hits": pos,
        "negative_hits": neg,
        "net_signal": pos - neg,  # >0 = plutôt favorable, <0 = plutôt défavorable
    }


def get_team_news(team_name: str, api_key: str, cse_id: str) -> dict:
    articles = search_news(f"{team_name} actualité forme équipe", api_key, cse_id)
    signal = news_signal(articles)
    signal["team"] = team_name
    signal["articles"] = articles
    return signal
