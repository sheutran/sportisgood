"""
Liste maîtresse de flux RSS sportifs généralistes (multi-équipes), organisée par
catégorie. Utilisée pour diversifier les sources d'actualité au-delà de la simple
recherche par équipe sur Google News.

Toutes ces URLs sont des flux publics connus et stables (BBC, ESPN, L'Équipe).
En cas de flux indisponible (changement d'URL côté éditeur), le code doit
logguer l'erreur et continuer sans bloquer le pipeline.
"""

MASTER_FEEDS = {
    "soccer": [
        {"name": "BBC Sport - Football", "url": "https://feeds.bbci.co.uk/sport/football/rss.xml"},
        {"name": "ESPN - Soccer", "url": "https://www.espn.com/espn/rss/soccer/news"},
        {"name": "L'Équipe - Football", "url": "https://www.lequipe.fr/rss/actu_rss_Football.xml"},
    ],
    "basketball": [
        {"name": "ESPN - NBA", "url": "https://www.espn.com/espn/rss/nba/news"},
    ],
    "americanfootball": [
        {"name": "ESPN - NFL", "url": "https://www.espn.com/espn/rss/nfl/news"},
        {"name": "BBC Sport - American Football", "url": "https://feeds.bbci.co.uk/sport/american-football/rss.xml"},
    ],
    "icehockey": [
        {"name": "ESPN - NHL", "url": "https://www.espn.com/espn/rss/nhl/news"},
    ],
    "baseball": [
        {"name": "ESPN - MLB", "url": "https://www.espn.com/espn/rss/mlb/news"},
    ],
    "tennis": [
        {"name": "BBC Sport - Tennis", "url": "https://feeds.bbci.co.uk/sport/tennis/rss.xml"},
    ],
    "boxing": [
        {"name": "BBC Sport - Boxing", "url": "https://feeds.bbci.co.uk/sport/boxing/rss.xml"},
    ],
    "mma": [
        {"name": "BBC Sport - Boxing", "url": "https://feeds.bbci.co.uk/sport/boxing/rss.xml"},
    ],
    "rugbyleague": [
        {"name": "BBC Sport - Rugby League", "url": "https://feeds.bbci.co.uk/sport/rugby-league/rss.xml"},
    ],
    "golf": [
        {"name": "BBC Sport - Golf", "url": "https://feeds.bbci.co.uk/sport/golf/rss.xml"},
    ],
    # Flux transversaux, pertinents quelle que soit la catégorie dominante
    "general": [
        {"name": "BBC Sport - Toutes disciplines", "url": "https://feeds.bbci.co.uk/sport/rss.xml"},
        {"name": "L'Équipe - Toutes disciplines", "url": "https://www.lequipe.fr/rss/actu_rss.xml"},
    ],
}

# Correspondance entre le préfixe des sport_key de The Odds API et une catégorie
# de la liste ci-dessus.
SPORT_KEY_PREFIX_TO_CATEGORY = {
    "soccer": "soccer",
    "basketball": "basketball",
    "americanfootball": "americanfootball",
    "icehockey": "icehockey",
    "baseball": "baseball",
    "tennis": "tennis",
    "boxing": "boxing",
    "mma": "mma",
    "rugbyleague": "rugbyleague",
    "golf": "golf",
}


def category_of_sport_key(sport_key: str) -> str:
    prefix = sport_key.split("_")[0]
    return SPORT_KEY_PREFIX_TO_CATEGORY.get(prefix, "general")


def select_feeds(events: list, max_feeds: int = 15, top_n_categories: int = 3) -> list:
    """
    Détermine les `top_n_categories` catégories de sport les plus représentées
    parmi les rencontres du jour (`events`), puis retourne jusqu'à `max_feeds`
    flux RSS associés (répartis équitablement entre ces catégories, plus
    quelques flux transversaux si de la place reste disponible).
    """
    counts = {}
    for ev in events:
        cat = category_of_sport_key(ev["sport"])
        counts[cat] = counts.get(cat, 0) + 1

    dominant = [c for c, _ in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:top_n_categories]]

    selected = []
    seen_urls = set()

    # Répartition équitable entre les catégories dominantes
    per_category_budget = max(1, max_feeds // max(1, len(dominant))) if dominant else 0
    for cat in dominant:
        for feed in MASTER_FEEDS.get(cat, [])[:per_category_budget]:
            if feed["url"] not in seen_urls:
                selected.append({**feed, "category": cat})
                seen_urls.add(feed["url"])

    # Complète avec des flux transversaux tant qu'il reste de la place
    for feed in MASTER_FEEDS["general"]:
        if len(selected) >= max_feeds:
            break
        if feed["url"] not in seen_urls:
            selected.append({**feed, "category": "general"})
            seen_urls.add(feed["url"])

    return selected[:max_feeds]
