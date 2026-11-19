#!/usr/bin/env python3
"""Collecte automatique des données d'été autour de chaque station (OpenStreetMap).

Tourne dans GitHub Actions (accès internet complet). Reprend là où il s'est arrêté :
 - data/geo.json   : coordonnées de chaque station (trouvées via Nominatim)
 - data/osm.json   : mesures par station (rando, lacs, VTT, activités, nautique, hébergements)
 - data/items.json : fiches, mises à jour avec les mesures (les autres champs ne sont jamais touchés)

Licence : © contributeurs OpenStreetMap (ODbL) — mention affichée en pied de page.
Usage : python3 scripts/collect_osm.py [--max N] [--refresh]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = "site-ete-collector/1.0 (https://github.com/camillechouet/site-ete)"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter"]
NOMINATIM = "https://nominatim.openstreetmap.org/search"
PAUSE = 2.0  # secondes entre deux requêtes (politesse envers les serveurs publics)

# Rayons de recherche autour du centre de la station (mètres)
R_SENTIERS = 6000
R_LACS = 15000
R_ACTIVITES = 8000
R_HEBERG = 8000


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save(path: Path, obj) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def http_json(url: str, data: bytes | None = None, tries: int = 4, timeout: int = 120) -> dict | None:
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"    essai {attempt + 1}/{tries} : {e}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    return None


def overpass(query: str) -> dict | None:
    body = urllib.parse.urlencode({"data": query}).encode()
    for url in OVERPASS:
        res = http_json(url, body, tries=2, timeout=75)
        time.sleep(PAUSE)
        if res is not None:
            return res
    return None


# ── Géométrie ────────────────────────────────────────────────────────────────

def haversine_m(a: dict, b: dict) -> float:
    r = 6371000.0
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp, dl = p2 - p1, math.radians(b["lon"] - a["lon"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def ways_km(elements: list[dict]) -> float:
    total = 0.0
    for el in elements:
        geom = el.get("geometry") or []
        total += sum(haversine_m(geom[i], geom[i + 1]) for i in range(len(geom) - 1))
    return round(total / 1000, 1)


# ── Localisation ─────────────────────────────────────────────────────────────

GOOD_CLASSES = {"place", "boundary", "tourism", "leisure", "landuse", "natural"}


def geocode(name: str, pays: str | None, region: str | None) -> dict | None:
    for q in ([f"{name}, {pays}"] if pays else []) + [name]:
        url = NOMINATIM + "?" + urllib.parse.urlencode({"q": q, "format": "jsonv2", "limit": 5, "addressdetails": 0})
        res = http_json(url)
        time.sleep(PAUSE)
        for r in res or []:
            if r.get("category", r.get("class")) in GOOD_CLASSES:
                return {"lat": round(float(r["lat"]), 5), "lon": round(float(r["lon"]), 5), "src": r.get("display_name", "")[:120]}
    return None


# ── Mesures ──────────────────────────────────────────────────────────────────

def measure(lat: float, lon: float) -> dict | None:
    out: dict = {}

    q = (f'[out:json][timeout:60];(way(around:{R_SENTIERS},{lat},{lon})["highway"~"^(path|footway)$"]["sac_scale"];'
         f'way(around:{R_SENTIERS},{lat},{lon})["highway"="path"]["trail_visibility"];);out geom;')
    r = overpass(q)
    if r is None:
        return None
    out["rando_km"] = ways_km(r.get("elements", []))

    q = (f'[out:json][timeout:60];way(around:{R_SENTIERS},{lat},{lon})["mtb:scale"];out geom;')
    r = overpass(q)
    if r is None:
        return None
    out["vtt_km"] = ways_km(r.get("elements", []))

    q = (f'[out:json][timeout:60];(nwr(around:{R_LACS},{lat},{lon})["natural"="water"]["water"="lake"]["name"];);out tags;')
    r = overpass(q)
    if r is None:
        return None
    out["lacs_15km"] = len({e.get("tags", {}).get("name") for e in r.get("elements", [])})

    q = (f'[out:json][timeout:60];(nwr(around:{R_ACTIVITES},{lat},{lon})["attraction"="summer_toboggan"];'
         f'nwr(around:{R_ACTIVITES},{lat},{lon})["sport"="zip_line"];nwr(around:{R_ACTIVITES},{lat},{lon})["aerialway"="zip_line"];'
         f'nwr(around:{R_ACTIVITES},{lat},{lon})["sport"="climbing_adventure"];nwr(around:{R_ACTIVITES},{lat},{lon})["leisure"="bikepark"];'
         f'nwr(around:{R_ACTIVITES},{lat},{lon})["leisure"="adventure_park"];);out tags;')
    r = overpass(q)
    if r is None:
        return None
    out["activites"] = len(r.get("elements", []))

    q = (f'[out:json][timeout:60];nwr(around:{R_LACS},{lat},{lon})["sport"~"^(sailing|canoe|kayak|water_ski|windsurfing|swimming|rowing)$"];out tags;')
    r = overpass(q)
    if r is None:
        return None
    out["nautique"] = len(r.get("elements", []))

    q = (f'[out:json][timeout:60];nwr(around:{R_HEBERG},{lat},{lon})["tourism"~"^(hotel|guest_house|chalet|hostel|apartment|camp_site)$"];out count;')
    r = overpass(q)
    if r is None:
        return None
    count = (r.get("elements") or [{}])[0].get("tags", {}).get("total")
    out["hebergements"] = int(count) if count is not None else 0
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=0, help="nombre maximum de stations à traiter (0 = toutes)")
    ap.add_argument("--minutes", type=int, default=300, help="durée maximale avant arrêt propre")
    ap.add_argument("--min-ok", type=float, default=0.0, help="échoue si la part de stations mesurées est inférieure")
    ap.add_argument("--max-fails", type=int, default=4, help="arrête tout après N échecs Overpass consécutifs")
    ap.add_argument("--refresh", action="store_true", help="refaire aussi les stations déjà mesurées")
    args = ap.parse_args()

    items = load(DATA / "items.json", [])
    geo = load(DATA / "geo.json", {})
    osm = load(DATA / "osm.json", {})
    done = 0
    fails = 0
    t0 = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request("https://overpass-api.de/api/status", headers={"User-Agent": UA}), timeout=30) as r:
            print("Statut Overpass :", r.read().decode()[:300].replace("\n", " | "), flush=True)
    except Exception as e:  # noqa: BLE001
        print("Statut Overpass indisponible :", e, flush=True)

    for it in items:
        if time.time() - t0 > args.minutes * 60:
            print("Temps imparti atteint : arrêt propre, la reprise se fera au prochain passage.")
            break
        key = it["name"]
        if key in osm and not args.refresh:
            continue
        if args.max and done >= args.max:
            break
        print(f"[{done + 1}] {key}", flush=True)
        if key not in geo:
            g = geocode(key, it.get("pays"), it.get("region"))
            geo[key] = g or {"lat": None, "lon": None}
        g = geo[key]
        if g.get("lat") is None:
            print("    introuvable : ignorée", file=sys.stderr)
            osm[key] = {"erreur": "position introuvable"}
        else:
            m = measure(g["lat"], g["lon"])
            if m is None:
                print("    mesure impossible (Overpass) : sera retentée au prochain passage", file=sys.stderr)
                fails += 1
                if fails >= args.max_fails:
                    print(f"{fails} échecs consécutifs : serveurs Overpass indisponibles, arrêt.", file=sys.stderr)
                    save(DATA / "geo.json", geo)
                    save(DATA / "osm.json", osm)
                    return 2
                continue
            fails = 0
            osm[key] = m
        done += 1
        if done % 25 == 0:
            save(DATA / "geo.json", geo)
            save(DATA / "osm.json", osm)

    save(DATA / "geo.json", geo)
    save(DATA / "osm.json", osm)

    # Injection dans les fiches (uniquement les champs mesurés)
    for it in items:
        m = osm.get(it["name"], {})
        for k, v in m.items():
            if k != "erreur":
                it[k] = v
    save(DATA / "items.json", items)
    ok = sum(1 for v in osm.values() if "erreur" not in v)
    print(f"Terminé : {ok} stations mesurées, {len(osm) - ok} en erreur, {len(items) - len(osm)} restantes.")
    if args.min_ok and done and ok / max(1, len(osm)) < args.min_ok:
        print(f"Trop d'échecs ({ok}/{len(osm)}) : à examiner.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
