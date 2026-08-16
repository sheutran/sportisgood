import json
from datetime import datetime, timezone


def export(results: list, output_path: str):
    ranked = sorted(
        [r for r in results if r["best_pick"]],
        key=lambda r: r["best_pick"]["confidence_score_pct"],
        reverse=True,
    )
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "disclaimer": (
            "Score de confiance heuristique base sur les cotes du marche et l'actualite recente. "
            "Ne constitue en aucun cas une garantie de gain."
        ),
        "picks": ranked,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
