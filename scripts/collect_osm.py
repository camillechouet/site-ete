#!/usr/bin/env python3
"""Collecte automatique des données d'été autour de chaque station (OpenStreetMap).

Méthode : on télécharge les extraits OpenStreetMap par pays (Geofabrik), on garde seulement
ce qui nous intéresse (sentiers, VTT, lacs, activités, hébergements) avec « osmium », puis on
mesure autour de chaque station. Aucune limite de requêtes : tout est calculé sur place.

Tourne dans GitHub Actions (accès internet complet + osmium-tool installé).
Fichiers produits :
 - data/geo.json   : coordonnées de chaque station (trouvées via Nominatim, gardées en cache)
 - data/osm.json   : mesures par station
 - data/items.json : fiches, mises à jour avec les mesures (les autres champs ne sont jamais touchés)

Licence : © contributeurs OpenStreetMap (ODbL) — mention affichée en pied de page.
Usage : python3 scripts/collect_osm.py [--max-geocode N]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
WORK = Path(os.environ.get("OSM_WORK", "/tmp/osm"))
UA = "site-ete-collector/2.0 (https://github.com/camillechouet/site-ete)"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
GEOFABRIK = "https://download.geofabrik.de/europe/{}-latest.osm.pbf"

# pays du fichier items.json  ->  nom de l'extrait Geofabrik
COUNTRIES = {
    "France": "france", "Autriche": "austria", "Suisse": "switzerland", "Italie": "italy",
    "Allemagne": "germany", "Espagne": "spain", "Andorre": "andorra", "Slovénie": "slovenia",
    "LI": "liechtenstein", "Liechtenstein": "liechtenstein",
}

# Rayons de recherche autour du centre de la station (mètres)
R_SENTIERS = 6000
R_LACS = 15000
R_ACTIVITES = 8000
R_HEBERG = 8000

FILTERS = [
    "w/sac_scale", "w/trail_visibility", "w/mtb:scale",
    "nwr/water=lake",
    "nwr/attraction=summer_toboggan", "nwr/sport=zip_line", "nwr/aerialway=zip_line",
    "nwr/sport=climbing_adventure", "nwr/leisure=bikepark", "nwr/leisure=adventure_park",
    "nwr/sport=sailing,canoe,kayak,water_ski,windsurfing,swimming,rowing",
    "nwr/tourism=hotel,guest_house,chalet,hostel,apartment,camp_site",
]
NAUTIQUE = {"sailing", "canoe", "kayak", "water_ski", "windsurfing", "swimming", "rowing"}
HEBERG = {"hotel", "guest_house", "chalet", "hostel", "apartment", "camp_site"}


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save(path: Path, obj) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


# ── Localisation des stations ────────────────────────────────────────────────

GOOD_CLASSES = {"place", "boundary", "tourism", "leisure", "landuse", "natural"}


def http_json(url: str, tries: int = 3) -> list | dict | None:
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"    essai {attempt + 1}/{tries} : {e}", file=sys.stderr)
            time.sleep(4 * (attempt + 1))
    return None


def geocode(name: str, pays: str | None) -> dict | None:
    for q in ([f"{name}, {pays}"] if pays else []) + [name]:
        url = NOMINATIM + "?" + urllib.parse.urlencode({"q": q, "format": "jsonv2", "limit": 5})
        res = http_json(url)
        time.sleep(1.1)  # règle d'usage de Nominatim : 1 requête par seconde maximum
        for r in res or []:
            if r.get("category", r.get("class")) in GOOD_CLASSES:
                return {"lat": round(float(r["lat"]), 5), "lon": round(float(r["lon"]), 5), "src": r.get("display_name", "")[:120]}
    return None


# ── Extraction OSM ───────────────────────────────────────────────────────────

class Store:
    """Garde, par catégorie, des tableaux numpy de positions (et de longueurs pour les sentiers)."""

    def __init__(self) -> None:
        self.lines = {"rando": [], "vtt": []}       # (lat, lon, longueur_m) par segment
        self.points = {"lacs": [], "activites": [], "nautique": [], "heberg": []}  # (lat, lon, clé)

    def finalize(self) -> None:
        self.arr = {}
        for k, v in self.lines.items():
            a = np.array(v, dtype=np.float64).reshape(-1, 3)
            self.arr[k] = a[np.argsort(a[:, 0])] if len(a) else a
        for k, v in self.points.items():
            if k == "lacs":
                seen: dict[str, tuple[float, float]] = {}
                for lat, lon, name in v:
                    seen.setdefault(name, (lat, lon))
                a = np.array([(la, lo) for la, lo in seen.values()], dtype=np.float64).reshape(-1, 2)
            else:
                a = np.array([(p[0], p[1]) for p in v], dtype=np.float64).reshape(-1, 2)
            self.arr[k] = a[np.argsort(a[:, 0])] if len(a) else a


def hav_m(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(lon2 - lon1)
    h = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * 6371000.0 * np.arcsin(np.sqrt(h))


def seg_len(a, b) -> float:
    return float(hav_m(a[1], a[0], b[1], b[0]))  # GeoJSON = [lon, lat]


def centroid(coords) -> tuple[float, float]:
    ring = coords
    while ring and isinstance(ring[0][0], list):
        ring = ring[0]
    lon = sum(p[0] for p in ring) / len(ring)
    lat = sum(p[1] for p in ring) / len(ring)
    return lat, lon


def feed(store: Store, feat: dict) -> None:
    props = feat.get("properties") or {}
    geom = feat.get("geometry") or {}
    gtype, coords = geom.get("type"), geom.get("coordinates")
    if not coords:
        return
    if gtype == "LineString" and len(coords) > 1:
        cats = []
        if props.get("highway") in {"path", "footway", "track", "steps"} and ("sac_scale" in props or "trail_visibility" in props):
            cats.append("rando")
        if "mtb:scale" in props:
            cats.append("vtt")
        for c in cats:
            for a, b in zip(coords, coords[1:]):
                store.lines[c].append(((a[1] + b[1]) / 2, (a[0] + b[0]) / 2, seg_len(a, b)))
        return
    try:
        lat, lon = (coords[1], coords[0]) if gtype == "Point" else centroid(coords)
    except (IndexError, TypeError, ZeroDivisionError):
        return
    if props.get("water") == "lake" and props.get("name"):
        store.points["lacs"].append((lat, lon, props["name"]))
    if (props.get("attraction") == "summer_toboggan" or props.get("sport") == "zip_line" or props.get("aerialway") == "zip_line"
            or props.get("sport") == "climbing_adventure" or props.get("leisure") in {"bikepark", "adventure_park"}):
        store.points["activites"].append((lat, lon, ""))
    if set(str(props.get("sport", "")).split(";")) & NAUTIQUE:
        store.points["nautique"].append((lat, lon, ""))
    if props.get("tourism") in HEBERG:
        store.points["heberg"].append((lat, lon, ""))


def run(cmd: list[str]) -> bool:
    print("  $", " ".join(cmd), flush=True)
    r = subprocess.run(cmd)
    return r.returncode == 0


def extract_country(store: Store, slug: str) -> bool:
    WORK.mkdir(parents=True, exist_ok=True)
    pbf, small, gj = WORK / f"{slug}.osm.pbf", WORK / f"{slug}-filtre.osm.pbf", WORK / f"{slug}.geojsonseq"
    t0 = time.time()
    if not run(["curl", "-fsSL", "--retry", "3", "-o", str(pbf), GEOFABRIK.format(slug)]):
        print(f"  téléchargement impossible pour {slug}", file=sys.stderr)
        return False
    ok = run(["osmium", "tags-filter", "--overwrite", "-o", str(small), str(pbf)] + FILTERS)
    pbf.unlink(missing_ok=True)
    if not ok:
        return False
    ok = run(["osmium", "export", "--overwrite", "-f", "geojsonseq", "-o", str(gj), str(small)])
    small.unlink(missing_ok=True)
    if not ok or not gj.is_file():
        return False
    n = 0
    with gj.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip().lstrip("\x1e")
            if not line:
                continue
            try:
                feed(store, json.loads(line))
                n += 1
            except ValueError:
                continue
    gj.unlink(missing_ok=True)
    print(f"  {slug} : {n} objets lus en {time.time() - t0:.0f} s", flush=True)
    return True


# ── Mesures autour des stations ──────────────────────────────────────────────

def window(a: np.ndarray, lat: float, lon: float, r: float) -> np.ndarray:
    """Lignes de a (triées par latitude) situées à moins de r mètres du point."""
    if not len(a):
        return a[:0]
    dlat = r / 111320.0
    dlon = r / (111320.0 * max(0.2, math.cos(math.radians(lat))))
    i0, i1 = np.searchsorted(a[:, 0], [lat - dlat, lat + dlat])
    w = a[i0:i1]
    w = w[np.abs(w[:, 1] - lon) <= dlon]
    if not len(w):
        return w
    return w[hav_m(lat, lon, w[:, 0], w[:, 1]) <= r]


def total_km(a: np.ndarray) -> float:
    return float(a[:, 2].sum()) / 1000 if len(a) else 0.0


def measure(store: Store, lat: float, lon: float) -> dict:
    return {
        "rando_km": round(total_km(window(store.arr["rando"], lat, lon, R_SENTIERS)), 1),
        "vtt_km": round(total_km(window(store.arr["vtt"], lat, lon, R_SENTIERS)), 1),
        "lacs_15km": int(len(window(store.arr["lacs"], lat, lon, R_LACS))),
        "activites": int(len(window(store.arr["activites"], lat, lon, R_ACTIVITES))),
        "nautique": int(len(window(store.arr["nautique"], lat, lon, R_LACS))),
        "hebergements": int(len(window(store.arr["heberg"], lat, lon, R_HEBERG))),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-geocode", type=int, default=0, help="limite le nombre de stations localisées (0 = toutes)")
    args = ap.parse_args()
    if not shutil.which("osmium"):
        print("osmium-tool n'est pas installé (apt-get install osmium-tool).", file=sys.stderr)
        return 1

    items = load(DATA / "items.json", [])
    geo = load(DATA / "geo.json", {})

    # 1) Localisation des stations (une seule fois : les positions restent en cache)
    n = 0
    for it in items:
        key = it["name"]
        if key in geo and geo[key].get("lat") is not None:
            continue
        if args.max_geocode and n >= args.max_geocode:
            break
        g = geocode(key, it.get("pays"))
        geo[key] = g or {"lat": None, "lon": None}
        n += 1
        if n % 25 == 0:
            print(f"  {n} stations localisées…", flush=True)
            save(DATA / "geo.json", geo)
    save(DATA / "geo.json", geo)
    located = sum(1 for v in geo.values() if v.get("lat") is not None)
    print(f"Localisation : {located}/{len(items)} stations trouvées.", flush=True)

    # 2) Extraction OpenStreetMap, pays par pays
    store = Store()
    slugs = sorted({COUNTRIES[it["pays"]] for it in items if it.get("pays") in COUNTRIES})
    done = []
    for slug in slugs:
        print(f"Extrait OSM : {slug}", flush=True)
        if extract_country(store, slug):
            done.append(slug)
    if not done:
        print("Aucun extrait OSM exploitable.", file=sys.stderr)
        return 1
    store.finalize()
    print("Éléments : " + ", ".join(f"{k}={len(v)}" for k, v in store.arr.items()), flush=True)

    # 3) Mesures
    osm = {}
    for it in items:
        g = geo.get(it["name"], {})
        slug = COUNTRIES.get(it.get("pays"))
        if g.get("lat") is None:
            osm[it["name"]] = {"erreur": "position introuvable"}
        elif slug not in done:
            osm[it["name"]] = {"erreur": "pas d'extrait OSM pour ce pays"}
        else:
            osm[it["name"]] = measure(store, g["lat"], g["lon"])
    save(DATA / "osm.json", osm)

    for it in items:
        for k, v in osm.get(it["name"], {}).items():
            if k != "erreur":
                it[k] = v
    save(DATA / "items.json", items)
    ok = sum(1 for v in osm.values() if "erreur" not in v)
    print(f"Terminé : {ok} stations mesurées sur {len(items)} (extraits : {', '.join(done)}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
