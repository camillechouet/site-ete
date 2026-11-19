"""Convertit les données SnowFinder en jeu de test pour le moteur (aucune photo reprise)."""
import json, sys
src = open(sys.argv[1], encoding="utf-8").read()
data = json.loads(src[src.index("[", src.index("window.SF_DATA")): src.rindex("]") + 1])
names = {"AT": "Autriche", "CH": "Suisse", "IT": "Italie", "DE": "Allemagne", "ES": "Espagne", "AD": "Andorre", "SI": "Slovénie", "FR": "France"}
items = []
for d in data:
    items.append({
        "name": d["name"],
        "pays": names.get(d.get("pays", "FR"), d.get("pays", "France")),
        "region": (d.get("region") or "").split("🇫")[0].split("🇨")[0].split("🇦")[0].split("🇮")[0].split("🇩")[0].split("🇪")[0].strip(" ,"),
        "summary": d.get("desc", ""),
        "description": d.get("desc_long", ""),
        "points": d.get("pts", []),
        "alt_max": d.get("alt_max"), "km": d.get("km"), "forfait": d.get("forfait"),
        "remontees": d.get("remontees"), "score": d.get("score"),
    })
json.dump(items, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print(len(items), "fiches")
