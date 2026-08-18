"""
Récupère l'actualité récente autour d'une équipe/d'un joueur via :
1. Une recherche ciblée sur le flux RSS public de Google News (par équipe)
2. Une sélection de flux RSS généralistes diversifiés (BBC, ESPN, L'Équipe...),
   filtrés pour ne garder que les articles mentionnant l'équipe en question.

Aucune clé API requise, aucun quota connu.
"""
import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote

from src.sentiment import aggregate_news_signal

RSS_URL = "https://news.google.com/rss/search"

TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return TAG_RE.sub(" ", text or "").strip()


def _parse_pubdate(raw: str):
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 1. Recherche ciblée par équipe (Google News RSS)
# ---------------------------------------------------------------------------

def search_news(query: str, num: int = 5, lang: str = "fr", country: str = "FR") -> list:
    params = {
        "q": f"{query} when:30d",  # dernier mois, syntaxe Google News
        "hl": lang,
        "gl": country,
        "ceid": f"{country}:{lang}",
    }
    url = f"{RSS_URL}?{'&'.join(f'{k}={quote(str(v))}' for k, v in params.items())}"

    resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    if resp.status_code != 200:
        print(f"[fetch_news] Erreur {resp.status_code} pour '{query}': {resp.text[:300]}")
        return []

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        print(f"[fetch_news] Réponse RSS illisible pour '{query}': {e}")
        return []

    items = root.findall(".//item")[:num]
    return [{
        "title": _strip_html(item.findtext("title", "")),
        "snippet": _strip_html(item.findtext("description", "")),
        "link": item.findtext("link", ""),
        "source": "Google News",
    } for item in items]


# ---------------------------------------------------------------------------
# 2. Flux RSS généralistes diversifiés (BBC, ESPN, L'Équipe...)
# ---------------------------------------------------------------------------

def fetch_general_feed(feed: dict, days_back: int = 30) -> list:
    """Récupère et parse un flux RSS générique, filtré sur les `days_back` derniers jours."""
    try:
        resp = requests.get(feed["url"], timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    except requests.RequestException as e:
        print(f"[fetch_news] Impossible de joindre {feed['name']} ({feed['url']}): {e}")
        return []

    if resp.status_code != 200:
        print(f"[fetch_news] {feed['name']}: HTTP {resp.status_code}, flux ignoré")
        return []

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        print(f"[fetch_news] {feed['name']}: flux RSS illisible ({e}), ignoré")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    articles = []
    for item in root.findall(".//item"):
        pub_raw = item.findtext("pubDate", "")
        pub_dt = _parse_pubdate(pub_raw)
        if pub_dt and pub_dt < cutoff:
            continue  # trop ancien
        articles.append({
            "title": _strip_html(item.findtext("title", "")),
            "snippet": _strip_html(item.findtext("description", "")),
            "link": item.findtext("link", ""),
            "source": feed["name"],
        })
    return articles


def fetch_all_general_feeds(feeds: list) -> list:
    """Récupère tous les flux sélectionnés en une fois (à appeler une seule fois par run,
    pas par équipe, pour limiter le nombre de requêtes HTTP)."""
    all_articles = []
    for feed in feeds:
        articles = fetch_general_feed(feed)
        print(f"[fetch_news] {feed['name']} ({feed['category']}): {len(articles)} article(s) récupéré(s)")
        all_articles.extend(articles)
    return all_articles


def filter_articles_for_team(articles: list, team_name: str) -> list:
    """Ne garde que les articles dont le titre ou le résumé mentionne l'équipe."""
    needle = team_name.lower()
    return [a for a in articles if needle in a["title"].lower() or needle in a["snippet"].lower()]


# ---------------------------------------------------------------------------
# 3. Agrégation par équipe
# ---------------------------------------------------------------------------

def get_team_news(team_name: str, general_articles: list | None = None) -> dict:
    # Recherche ciblée Google News (essai FR puis EN)
    articles = search_news(f"{team_name} actualité forme équipe", lang="fr", country="FR")
    if not articles:
        articles = search_news(f"{team_name} news form injury", lang="en", country="US")

    # Complète avec les articles pertinents trouvés dans les flux généralistes diversifiés
    if general_articles:
        matched = filter_articles_for_team(general_articles, team_name)
        # Dédoublonnage grossier par titre
        seen_titles = {a["title"] for a in articles}
        for a in matched:
            if a["title"] not in seen_titles:
                articles.append(a)
                seen_titles.add(a["title"])

    signal = aggregate_news_signal(articles)
    signal["team"] = team_name
    signal["articles"] = articles
    signal["sources"] = sorted({a["source"] for a in articles})
    return signal
