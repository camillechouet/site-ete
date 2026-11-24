#!/usr/bin/env python3
"""Photos « de secours » : paysages d'été de montagne génériques (sans nom de station),
affichés avec la mention « Photo d'illustration » quand une station n'a pas sa propre photo.
Sortie : photos-secours/secours-01.jpg … (crédit gravé). Mêmes filtres que find_photos.py."""
import os, re, sys, io, time, importlib.util
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("fp", os.path.join(ROOT, "scripts", "find_photos.py"))
fp = importlib.util.module_from_spec(spec); spec.loader.exec_module(fp)
from PIL import Image
fp.MIN_W, fp.MIN_H = 1600, 1000      # un peu moins exigeant : ce sont des illustrations

OUT = os.path.join(ROOT, "photos-secours")
WANT = int(os.environ.get("WANT", "45"))
QUERIES = [
    "alpine meadow summer mountains", "mountain lake summer reflection alps", "alpine flowers meadow mountain panorama summer",
    "summer mountain landscape quality image", "hiking trail alpine summer panorama", "Alps summer valley green panorama",
    "Pyrenees summer mountain lake", "Dolomites summer meadow panorama", "Swiss Alps summer pasture mountains",
    "Austrian Alps summer mountain landscape", "paysage montagne été alpage", "lac de montagne été randonnée",
    "Vanoise summer landscape", "Écrins summer mountain landscape", "Mont Blanc massif summer panorama",
    "Bavarian Alps summer lake mountains", "Allgäu Alps summer meadow", "Engadin summer mountain lake", "Tyrol summer mountain panorama",
    "Haute-Savoie summer mountain landscape", "Hautes-Alpes summer lake mountain", "Pyrénées été lac paysage", "Slovenia Julian Alps summer lake",
    "Bernese Oberland summer panorama", "Valais summer mountain landscape", "Vorarlberg summer mountain landscape", "Salzburg Alps summer lake panorama",
    "South Tyrol summer meadow mountains", "Trentino summer lake mountains", "Aosta Valley summer mountain landscape", "Vosges Jura summer landscape lake",
    "Auvergne Cantal summer mountain landscape", "Savoie lac de montagne été", "Tour du Mont Blanc summer landscape", "alpine lake turquoise summer mountains", "Italian Alps summer mountain lake", "Tatra Carpathians Julian Alps summer",
]
EXTRA_BAD = re.compile(r"\b(village|town|city|ville|dorf|resort|stadt|houses?|chalets?|hut|people|hikers?|climbers?|cyclists?|"
                       r"bikers?|tent|camp|highway|cable|gondola|lift|telecabine|dam|paraglid\w*|flag|sunset|sunrise|night|panneau|sign|cars?|auto)\b", re.I)
EUROPE = re.compile(r"alp|pyren|dolomit|tatra|carpath|switzerland|schweiz|suisse|austria|österreich|tirol|tyrol|france|savoie|italy|italia|slovenia|julian|bavaria|bayern|vanoise|mont blanc|ecrins|écrins|andorra|vosges|jura|auvergne|bohinj|triglav|svizzera|vorarlberg|salzburg|allgäu|allgau|engadin|wallis|valais|bernese|berner", re.I)

def main():
    os.makedirs(OUT, exist_ok=True)
    pool = {}
    for q in QUERIES:
        try:
            pages = fp.api_search(q)
        except Exception as e:
            print("recherche en échec:", q, e, file=sys.stderr); continue
        for p in pages:
            c = fp.score_candidate(p, {"name": ""}, from_article=True)
            if not c: continue
            blob = c["title"] + " " + fp.meta(c["info"], "ImageDescription") + " " + fp.meta(c["info"], "Categories")
            if not EUROPE.search(blob): continue
            if EXTRA_BAD.search(c["title"]) or fp.WINTER.search(blob): continue
            c["score"] -= 7.5                       # bonus « article » sans objet ici
            c["score"] += len(fp.SUMMER.findall(blob)) * 0.3
            pool[c["page_url"]] = c
        time.sleep(1.5)
    cands = sorted(pool.values(), key=lambda c: -c["score"])
    print(f"{len(cands)} candidats", file=sys.stderr)
    seen, authors, n = [], set(), 0
    for c in cands:
        if n >= WANT: break
        if c["artist"] in authors: continue
        try:
            raw = fp.http_get(c["info"].get("thumburl") or c["info"]["url"], binary=True)
            img = Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception as e:
            print("téléchargement en échec:", c["title"], e, file=sys.stderr); continue
        prob = fp.image_problem(img, min_green=0.05)
        if prob: continue
        h = fp.dhash(img)
        if any(sum(x != y for x, y in zip(h, g)) <= 14 for g in seen): continue
        seen.append(h); authors.add(c["artist"])
        if img.width > fp.MAX_W:
            img = img.resize((fp.MAX_W, int(img.height * fp.MAX_W / img.width)), Image.LANCZOS)
        if c["kind"] == "by":
            img = fp.burn_credit(img, fp.credit_text(c))
        n += 1
        img.save(os.path.join(OUT, f"secours-{n:02d}.jpg"), "JPEG", quality=80, optimize=True, progressive=True)
        print(n, c["title"], file=sys.stderr)
    print(f"{n} photos de secours")

if __name__ == "__main__":
    main()
