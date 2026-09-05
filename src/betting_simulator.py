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
import math

# The Odds API ne fournit AUCUN résultat exploitable pour ces sports via son
# endpoint /scores (vérifié sur https://the-odds-api.com/sports-odds-data/
# sports-apis.html - colonne "Scores & Results" vide pour Boxing et MMA,
# même sur les plans payants). Un pari qu'on ne peut jamais régler ne doit
# jamais recevoir de mise: on exclut ces sports de l'allocation du budget,
# tout en les laissant apparaître normalement dans le Sheet/la page (à titre
# informatif uniquement).
UNSETTLEABLE_SPORTS = {"boxing_boxing", "mma_mixed_martial_arts"}


def kelly_fraction(p: float, odds: float) -> float:
    """Fraction de Kelly f* = p - (1-p)/b, avec b = cote nette (odds - 1).
    Négatif ou nul si aucun avantage perçu. Renvoie toujours une valeur finie."""
    if odds is None or not math.isfinite(odds) or odds <= 1:
        return 0.0
    b = odds - 1
    if b <= 0:
        return 0.0
    if p is None or not math.isfinite(p):
        return 0.0
    q = 1 - p
    f = p - q / b
    return f if math.isfinite(f) else 0.0


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
    excluded_unsettleable = 0
    for r in results:
        best = r.get("best_pick")
        if not best or best.get("confidence_score_pct", 0) < min_confidence:
            continue
        if r.get("sport") in UNSETTLEABLE_SPORTS:
            excluded_unsettleable += 1
            continue
        odds = best.get("odds")
        # Garde-fou: une cote manquante/nulle/non finie exclut le pari plutôt que
        # de risquer une division par zéro ou un NaN plus loin dans le calcul.
        if not odds or not math.isfinite(odds) or odds <= 1:
            print(f"[betting_simulator] Pari ignoré (cote invalide: {odds}) - {r.get('match')}")
            continue
        qualifying.append((r, best))

    if excluded_unsettleable:
        print(f"[betting_simulator] {excluded_unsettleable} pari(s) qualifiant(s) exclu(s) car le sport "
              f"concerné (boxe/MMA) n'a jamais de résultat exploitable via The Odds API.")

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
    if not math.isfinite(total_weight) or total_weight <= 0:
        print("[betting_simulator] ATTENTION - poids total invalide, répartition égale de secours appliquée")
        for w in weighted:
            w["share"] = 1 / len(weighted)
    else:
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
        if not math.isfinite(stake):
            stake = 0.0
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
