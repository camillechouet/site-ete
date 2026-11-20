#!/usr/bin/env python3
"""Activités de plein air autour des stations françaises, via l'API DATAtourisme (gratuite).

Clé lue dans la variable d'environnement DATATOURISME_KEY (secret GitHub, jamais écrite dans le dépôt).
Écrit data/datatourisme.json ; build.py prend le maximum entre ce comptage et celui d'OpenStreetMap.
Limites de l'API : 1000 requêtes/heure -> on espace les appels (≈ 4 s).
"""
import json, os, sys, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
API = "https://api.datatourisme.fr/v1/catalog"
KEY = os.environ.get("DATATOURISME_KEY", "").strip()
RAYON = "8km"
TERMES = ["tyrolienne", "luge", "accrobranche", "aventure", "via ferrata", "parapente"]
PAUSE = 4.2
REFRESH = os.environ.get("REFRESH") == "1"


def appel(params: dict) -> dict | None:
    url = API + "?" + urllib.parse.urlencode(params)
    for essai in range(4):
        req = urllib.request.Request(url, headers={"X-API-Key": KEY, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            corps = e.read()[:300].decode("utf-8", "replace")
            print(f"  HTTP {e.code} : {corps}", flush=True)
            if e.code == 429:
                time.sleep(120)
                continue
            if e.code in (401, 403):
                raise SystemExit("Clé refusée (401/403) : vérifier le secret DATATOURISME_KEY.")
            return None
        except Exception as e:  # réseau
            print(f"  erreur réseau : {e}", flush=True)
            time.sleep(10)
    return None


def textes(o) -> list[str]:
    """Tous les libellés texte d'un objet (clés label/name/type), en minuscules."""
    out = []
    if isinstance(o, dict):
        for k, v in o.items():
            if k.lower() in ("label", "name", "type", "rdfs:label", "@type"):
                out.append(json.dumps(v, ensure_ascii=False).lower())
            elif isinstance(v, (dict, list)) and k.lower() in ("isinstanceof", "hasclassification"):
                out.append(json.dumps(v, ensure_ascii=False).lower())
    return out


def nom(o) -> str:
    lab = o.get("label") if isinstance(o, dict) else None
    if isinstance(lab, dict):
        for v in lab.values():
            if isinstance(v, list) and v:
                return str(v[0])
            if isinstance(v, str):
                return v
    return str(lab or o.get("uuid") or o.get("id") or "?")


def main() -> int:
    if not KEY:
        print("DATATOURISME_KEY absente : rien à faire.")
        return 0
    items = json.load(open(DATA / "items.json", encoding="utf-8"))
    geo = json.load(open(DATA / "geo.json", encoding="utf-8"))
    cache_p = DATA / "datatourisme.json"
    res = {} if REFRESH or not cache_p.exists() else json.load(open(cache_p, encoding="utf-8"))
    cibles = [i for i in items if i.get("pays") == "France" and geo.get(i["name"], {}).get("lat") is not None]
    print(f"{len(cibles)} stations françaises à interroger ({len(res)} déjà en cache).", flush=True)
    vus_sample = False
    echecs = 0
    for n, it in enumerate(cibles, 1):
        name = it["name"]
        if name in res:
            continue
        g = geo[name]
        trouves: dict[str, str] = {}
        ok = False
        for t in TERMES:
            d = appel({"search": t, "geo_distance": f"{g['lat']},{g['lon']},{RAYON}",
                       "page_size": 100, "lang": "fr"})
            time.sleep(PAUSE)
            if d is None:
                continue
            ok = True
            objs = d.get("objects") or []
            if not vus_sample:
                vus_sample = True
                print("  exemple de réponse :", json.dumps(d, ensure_ascii=False)[:1500], flush=True)
                (DATA / "dt_sample.json").write_text(json.dumps(objs[:2], ensure_ascii=False, indent=1), encoding="utf-8")
            racine = t.split()[0]
            for o in objs:
                if any(racine in x for x in textes(o)):
                    trouves[str(o.get("uuid") or o.get("id") or nom(o))] = nom(o)
        if not ok:
            echecs += 1
            if echecs >= 3 and not res:
                print("Trop d'échecs d'affilée, arrêt.", file=sys.stderr)
                return 1
            continue
        res[name] = {"activites": len(trouves), "exemples": list(trouves.values())[:5]}
        if n % 10 == 0:
            print(f"  {n}/{len(cibles)}", flush=True)
            cache_p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    cache_p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Terminé : {len(res)} stations.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
