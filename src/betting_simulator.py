"""
Répartit un budget virtuel fixe entre les paris du jour dont le score de
confiance dépasse un seuil, selon le critère de Kelly (fraction du capital
à miser proportionnelle à l'avantage perçu).

POURQUOI KELLY PLUTÔT QU'UN "TOUT SUR LE MEILLEUR PARI" ?
Maximiser le gain espéré d'un seul jour, sans contrainte, revient
mathématiquement à tout miser sur le pari à la cote/probabilité la plus
avantageuse. C'est justement la pire stratégie sur la durée : un seul
résultat défavorable efface tout le capital. Le critère de Kelly maximise
au contraire la croissance espérée du capital sur le long terme, ce qui est
l'objectif statistiquement sensé quand on répète l'exercice chaque jour.

On utilise ici une fraction de Kelly réduite (par défaut 50%, "half-Kelly"),
pratique standard pour limiter la variance quand les probabilités utilisées
(notre score de confiance) sont des estimations heuristiques et non des
probabilités exactes.

IMPORTANT: la cote utilisée ici est la COTE MOYENNE du marché (comme demandé
pour le calcul des gains/pertes le lendemain), pas la meilleure cote possible,
pour que l'avantage perçu au moment de la mise et le règlement du lendemain
restent cohérents entre eux.
"""


def kelly_fraction(p: float, odds: float) -> float:
    """Fraction de Kelly f* = p - (1-p)/b, avec b = cote nette (odds - 1).
    Négatif ou nul si aucun avantage perçu."""
    b = odds - 1
    if b <= 0:
        return 0.0
    q = 1 - p
    return p - q / b


def allocate_stakes(results: list, budget: float = 10.0, min_confidence: float = 70.0,
                     kelly_multiplier: float = 0.5, max_share_per_bet: float = 0.6) -> list:
    """
    Répartit `budget` (en euros) entre tous les paris dont le score de confiance
    est >= min_confidence, proportionnellement à leur fraction de Kelly (réduite).

    Un plancher minimal garantit que le budget est TOUJOURS intégralement réparti
    entre les paris qualifiés (même si l'avantage perçu est marginal ou négatif
    pour certains), conformément à la consigne de répartir la totalité du budget
    quotidien. Un plafond (`max_share_per_bet`) évite qu'un seul pari n'absorbe
    la quasi-totalité du budget en cas d'avantage très marqué sur un seul match.
    """
    qualifying = []
    for r in results:
        best = r.get("best_pick")
        if not best or best.get("confidence_score_pct", 0) < min_confidence:
            continue
        qualifying.append((r, best))

    if not qualifying:
        return []

    weighted = []
    for r, best in qualifying:
        p = best["confidence_score_pct"] / 100
        odds = best["odds"]  # cote moyenne, cohérente avec le règlement du lendemain
        f = kelly_fraction(p, odds) * kelly_multiplier
        weight = max(f, 0.001)  # plancher: garantit une répartition même si l'avantage est faible/négatif
        weighted.append({"r": r, "best": best, "weight": weight})

    total_weight = sum(w["weight"] for w in weighted)
    for w in weighted:
        w["share"] = w["weight"] / total_weight

    # Plafonne chaque part et redistribue l'excédent sur les autres paris qualifiés
    for _ in range(len(weighted)):  # quelques passes suffisent, cascade rare
        over = [w for w in weighted if w["share"] > max_share_per_bet]
        if not over or len(weighted) == 1:
            break
        excess = sum(w["share"] - max_share_per_bet for w in over)
        for w in over:
            w["share"] = max_share_per_bet
        under = [w for w in weighted if w["share"] < max_share_per_bet]
        under_total = sum(w["share"] for w in under)
        if under_total > 0:
            for w in under:
                w["share"] += excess * (w["share"] / under_total)

    stakes = []
    running_total = 0.0
    for w in weighted:
        r, best = w["r"], w["best"]
        stake = round(budget * w["share"], 2)
        running_total += stake
        stakes.append({
            "event_id": r.get("event_id"),
            "match": r["match"],
            "sport": r["sport"],
            "home_team": r.get("home_team"),
            "away_team": r.get("away_team"),
            "commence_time_gmt": r["commence_time_gmt"],
            "selection": best["selection"],
            "type": best["type"],
            "odds_used": best["odds"],
            "confidence_score_pct": best["confidence_score_pct"],
            "stake": stake,
            "status": "pending",
            "payout": None,
            "profit": None,
            "final_score": None,
        })

    # Corrige l'écart d'arrondi pour que la somme colle exactement au budget
    rounding_diff = round(budget - running_total, 2)
    if stakes and abs(rounding_diff) >= 0.01:
        stakes[-1]["stake"] = round(stakes[-1]["stake"] + rounding_diff, 2)

    return stakes
