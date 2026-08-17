"""
Combine les cotes (probabilité implicite) et le signal d'actualité
pour produire un score de confiance heuristique (0-100).

IMPORTANT: ce score n'est PAS une probabilité réelle de gain garanti.
C'est une aide à la décision basée sur des heuristiques simples.
"""


def implied_probability(odds: float | None) -> float | None:
    """Probabilité implicite brute d'une cote décimale (sans retirer la marge du bookmaker)."""
    if not odds or odds <= 1:
        return None
    return round((1 / odds) * 100, 1)


def normalize_market(prob_home, prob_away, prob_draw):
    """Retire approximativement la marge du bookmaker (overround) en renormalisant
    la somme des probabilités implicites à 100%."""
    probs = [p for p in (prob_home, prob_away, prob_draw) if p is not None]
    total = sum(probs)
    if total == 0:
        return prob_home, prob_away, prob_draw
    factor = 100 / total
    norm = lambda p: round(p * factor, 1) if p is not None else None
    return norm(prob_home), norm(prob_away), norm(prob_draw)


def confidence_score(market_prob: float, news_net_signal: int, nb_bookmakers: int) -> float:
    """
    Score de confiance = principalement la probabilité de marché (consensus des bookmakers,
    qui intègre déjà énormément d'information), légèrement ajusté par le signal d'actu
    et pondéré par la fiabilité du marché (nombre de bookmakers ayant coté le match).

    Poids volontairement conservateurs: l'actu ne doit jamais dominer le prix du marché.
    """
    if market_prob is None:
        return 0.0

    news_adjustment = max(-5, min(5, news_net_signal))  # borné à +/-5 points
    reliability = min(1.0, nb_bookmakers / 8)  # marché jugé fiable à partir de ~8 bookmakers

    score = market_prob + news_adjustment
    score = score * (0.85 + 0.15 * reliability)  # pénalise légèrement les marchés peu couverts
    return round(max(0, min(99, score)), 1)  # plafonné à 99 : jamais de "certitude absolue"


def analyze_event(event: dict, home_news: dict, away_news: dict) -> dict:
    p_home = implied_probability(event.get("odds_home"))
    p_away = implied_probability(event.get("odds_away"))
    p_draw = implied_probability(event.get("odds_draw"))
    p_home, p_away, p_draw = normalize_market(p_home, p_away, p_draw)

    nb_bk = event.get("nb_bookmakers", 0)

    candidates = []
    if p_home is not None:
        candidates.append({
            "selection": event["home_team"],
            "type": "Victoire domicile",
            "odds": event.get("odds_home"),
            "market_probability_pct": p_home,
            "confidence_score_pct": confidence_score(p_home, home_news.get("net_signal", 0), nb_bk),
            "news_net_signal": home_news.get("net_signal", 0),
            "news_nb_articles": home_news.get("nb_articles", 0),
        })
    if p_away is not None:
        candidates.append({
            "selection": event["away_team"],
            "type": "Victoire extérieur",
            "odds": event.get("odds_away"),
            "market_probability_pct": p_away,
            "confidence_score_pct": confidence_score(p_away, away_news.get("net_signal", 0), nb_bk),
            "news_net_signal": away_news.get("net_signal", 0),
            "news_nb_articles": away_news.get("nb_articles", 0),
        })
    if p_draw is not None:
        candidates.append({
            "selection": "Match nul",
            "type": "Nul",
            "odds": event.get("odds_draw"),
            "market_probability_pct": p_draw,
            "confidence_score_pct": confidence_score(p_draw, 0, nb_bk),
            "news_net_signal": 0,
            "news_nb_articles": home_news.get("nb_articles", 0) + away_news.get("nb_articles", 0),
        })

    best = max(candidates, key=lambda c: c["confidence_score_pct"]) if candidates else None

    return {
        "match": event["match"],
        "sport": event["sport"],
        "country": event["country"],
        "commence_time_gmt": event["commence_time_gmt"],
        "nb_bookmakers": nb_bk,
        "best_pick": best,
        "all_candidates": candidates,
    }
