"""
Analyse de tonalité des articles, volontairement plus discriminante que
"positif/négatif" au mot-clé simple.

Deux axes distincts:
1. FAITS CONCRETS (blessure confirmée, retour d'un titulaire, série de résultats...)
   -> ce sont les seuls éléments qui doivent réellement faire bouger le score.
2. RHÉTORIQUE / EFFET D'ANNONCE (déclarations d'entraîneur, "on est confiants",
   citations en conférence de presse...) -> ce langage est fréquent, peu fiable
   (les entraîneurs se disent "confiants" avant une défaite comme avant une victoire),
   et sert ici à DÉTECTER le bruit pour l'atténuer, pas à l'amplifier.

Le signal net est calculé en MOYENNE PAR ARTICLE (pas en somme brute), pour que
le nombre d'articles trouvés n'influence plus mécaniquement le score : plus
d'articles doit affiner l'estimation, pas la gonfler.
"""

FACTUAL_POSITIVE = [
    "retour de blessure", "de retour à l'entraînement", "titularisé", "titulaire confirmé",
    "invaincu", "série de victoires", "qualifié", "meilleure forme physique de la saison",
    "returns from injury", "back in training", "confirmed starter", "unbeaten run",
    "winning streak", "cleared to play", "return to full fitness",
]

FACTUAL_NEGATIVE = [
    "blessé", "blessure", "suspendu", "absent", "forfait", "écarté du groupe",
    "incertain pour la rencontre", "sanction disciplinaire", "hors groupe",
    "injury", "injured", "suspended", "ruled out", "sidelined", "banned",
    "doubtful", "out for the season", "withdrawn", "will miss",
]

# Langage de déclaration/rhétorique - fréquent autour des matchs, peu prédictif en soi.
# On s'en sert pour repérer les articles dominés par du discours plutôt que des faits
# (l'"effet d'annonce" / "écran de fumée" que tu mentionnes).
HYPE_MARKERS = [
    "a déclaré", "a affirmé", "a assuré", "selon lui", "conférence de presse",
    "confiant", "grande motivation", "on est prêts", "on veut gagner",
    "objectif est clair", "a promis", "a insisté", "a expliqué que",
    "said", "insists", "vowed", "press conference", "confident", "claimed",
    "vows to", "believes", "told reporters", "stated that",
]


def _count_hits(text: str, words: list) -> int:
    return sum(text.count(w) for w in words)


def classify_article(article: dict) -> dict:
    text = (article.get("title", "") + " " + article.get("snippet", "")).lower()
    return {
        "factual_pos": _count_hits(text, FACTUAL_POSITIVE),
        "factual_neg": _count_hits(text, FACTUAL_NEGATIVE),
        "hype": _count_hits(text, HYPE_MARKERS),
    }


def aggregate_news_signal(articles: list) -> dict:
    """
    Retourne un signal net borné [-5, +5], calculé comme une MOYENNE par article
    (et non une somme), et atténué proportionnellement à la part d'articles
    dominés par de la rhétorique plutôt que des faits.
    """
    n = len(articles)
    if n == 0:
        return {"nb_articles": 0, "net_signal": 0, "hype_ratio_pct": 0.0}

    total_pos = total_neg = total_hype = 0
    hype_dominated = 0

    for a in articles:
        c = classify_article(a)
        total_pos += c["factual_pos"]
        total_neg += c["factual_neg"]
        total_hype += c["hype"]
        # Un article est jugé "à effet d'annonce" si son discours (hype) dépasse
        # nettement ses faits concrets (factual_pos + factual_neg).
        if c["hype"] > (c["factual_pos"] + c["factual_neg"]):
            hype_dominated += 1

    avg_factual = (total_pos - total_neg) / n
    hype_ratio = hype_dominated / n  # part d'articles jugés "effet d'annonce"

    # Le signal factuel est atténué (jamais amplifié) par la part de bruit rhétorique
    adjusted = avg_factual * (1 - hype_ratio)
    net_signal = round(max(-5.0, min(5.0, adjusted * 3)), 1)  # mise à l'échelle modérée

    return {
        "nb_articles": n,
        "net_signal": net_signal,
        "hype_ratio_pct": round(hype_ratio * 100, 1),
    }
