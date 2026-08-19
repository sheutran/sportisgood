"""
Récupère l'historique des affrontements passés entre deux équipes/joueurs via
TheSportsDB (clé de test publique gratuite "123", usage non commercial —
cohérent avec un usage personnel).

LIMITES CONNUES:
- TheSportsDB est une base communautaire, la couverture est inégale selon les
  sports/ligues. Attends-toi à des historiques vides plus fréquents pour le
  tennis, le MMA, la boxe ou les petites ligues.
- Avec la clé gratuite, l'endpoint de recherche d'évènements ne retourne qu'UN
  SEUL résultat par appel (contre 10 en Patreon payant). Pour reconstituer un
  historique sur plusieurs saisons, on multiplie donc les appels filtrés par
  saison, avec un arrêt anticipé dès que suffisamment de matchs sont trouvés.

Pondération statistique du résultat sur le score de confiance:
1. Décroissance exponentielle: une confrontation récente pèse plus qu'une ancienne.
2. Atténuation sur petit échantillon: la fiabilité de l'indice croît avec le nombre
   de confrontations trouvées (jusqu'à 5), pour éviter qu'un seul match passé
   ne fasse basculer le score de façon disproportionnée.
3. Application symétrique: si l'historique favorise le favori du marché, son
   score augmente et celui de l'outsider diminue d'autant (et inversement si
   l'historique contredit le favori du marché).
"""
import time
import requests
from datetime import datetime

BASE_URL = "https://www.thesportsdb.com/api/v1/json/123"


def _get(endpoint: str, params: dict) -> dict | None:
    try:
        resp = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=15)
    except requests.RequestException as e:
        print(f"[head_to_head] Erreur réseau sur {endpoint}: {e}")
        return None
    if resp.status_code != 200:
        print(f"[head_to_head] {endpoint}: HTTP {resp.status_code}")
        return None
    return resp.json()


def _slug(team: str) -> str:
    return team.strip().replace(" ", "_")


def _season_labels(n_years: int = 4) -> list:
    """Génère des libellés de saison plausibles (format européen 'YYYY-YYYY'
    et format US 'YYYY'), des plus récents aux plus anciens."""
    year = datetime.now().year
    labels = []
    for y in range(year, year - n_years, -1):
        labels.append(f"{y-1}-{y}")
        labels.append(str(y))
    return labels


def search_h2h_events(home_team: str, away_team: str, max_events: int = 5) -> dict:
    """Cherche les affrontements passés via la recherche d'évènements par nom
    (convention TheSportsDB: 'Equipe1_vs_Equipe2'), en élargissant saison par
    saison jusqu'à obtenir `max_events` résultats distincts ou épuiser les essais."""
    directions = [f"{_slug(home_team)}_vs_{_slug(away_team)}",
                  f"{_slug(away_team)}_vs_{_slug(home_team)}"]
    events = {}

    # 1) essai sans filtre de saison (renvoie souvent le dernier match connu)
    for q in directions:
        data = _get("searchevents.php", {"e": q})
        if data and data.get("event"):
            for ev in data["event"]:
                events[ev["idEvent"]] = ev
        time.sleep(0.25)

    # 2) élargit saison par saison si on n'a pas encore assez de matchs
    if len(events) < max_events:
        for season in _season_labels():
            if len(events) >= max_events:
                break
            for q in directions:
                if len(events) >= max_events:
                    break
                data = _get("searchevents.php", {"e": q, "s": season})
                if data and data.get("event"):
                    for ev in data["event"]:
                        events[ev["idEvent"]] = ev
                time.sleep(0.25)

    return events


def fetch_head_to_head(home_team: str, away_team: str, max_events: int = 5) -> list:
    """Retourne jusqu'à `max_events` affrontements passés exploitables (score connu),
    triés du plus ancien au plus récent."""
    raw_events = search_h2h_events(home_team, away_team, max_events).values()

    parsed = []
    for ev in raw_events:
        date = ev.get("dateEvent")
        hs, as_ = ev.get("intHomeScore"), ev.get("intAwayScore")
        if not date or hs is None or as_ is None:
            continue  # match pas encore joué, ou score manquant dans la base
        try:
            parsed.append({
                "date": date,
                "home_team": ev.get("strHomeTeam"),
                "away_team": ev.get("strAwayTeam"),
                "home_score": int(hs),
                "away_score": int(as_),
            })
        except (TypeError, ValueError):
            continue

    parsed.sort(key=lambda e: e["date"])
    if not parsed:
        print(f"[head_to_head] {home_team} vs {away_team}: aucun affrontement passé exploitable trouvé")
    else:
        print(f"[head_to_head] {home_team} vs {away_team}: {len(parsed)} affrontement(s) exploitable(s)")
    return parsed[-max_events:]


def summarize_h2h(events: list, favorite_team: str) -> list:
    """Convertit chaque affrontement en 'G'/'N'/'P' du point de vue du favori
    du marché (quel que soit le camp - domicile/extérieur - qu'il occupait
    lors de ce match passé). Ordre chronologique conservé (plus ancien en premier)."""
    results = []
    for ev in events:
        hs, as_ = ev["home_score"], ev["away_score"]
        if hs == as_:
            results.append("N")
            continue
        home_won = hs > as_
        favorite_was_home = ev["home_team"].strip().lower() == favorite_team.strip().lower()
        favorite_won = (home_won and favorite_was_home) or ((not home_won) and not favorite_was_home)
        results.append("G" if favorite_won else "P")
    return results


def h2h_adjustment(results: list, max_adjustment: float = 5.0, decay: float = 0.65) -> tuple:
    """Ajustement pondéré en faveur (ou défaveur) du favori du marché.
    Retourne (ajustement, fiabilité). Positif = l'historique soutient le favori."""
    n = len(results)
    if n == 0:
        return 0.0, 0.0

    scores = {"G": 1.0, "N": 0.0, "P": -1.0}
    recent_first = list(reversed(results))  # plus récent en premier pour la pondération
    weights = [decay ** i for i in range(n)]
    weighted_sum = sum(w * scores[r] for w, r in zip(weights, recent_first))
    weighted_score = weighted_sum / sum(weights)  # dans [-1, 1]

    reliability = min(1.0, n / 5)  # 1 seule confrontation pèse peu, 5+ pèsent pleinement
    return round(weighted_score * reliability * max_adjustment, 2), reliability


def draw_adjustment(results: list, max_adjustment: float = 2.0) -> float:
    """Léger bonus pour le pari nul si l'historique montre une propension au nul,
    pondéré par la même logique de fiabilité sur petit échantillon."""
    n = len(results)
    if n == 0:
        return 0.0
    draw_ratio = results.count("N") / n
    reliability = min(1.0, n / 5)
    return round(draw_ratio * reliability * max_adjustment, 2)
