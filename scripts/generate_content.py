#!/usr/bin/env python3
"""Génère duels et articles à partir des mesures (data/items.json + notes). Aucun chiffre inventé :
tout est tiré des fiches. Écrit data/duels.json et data/articles.json.
Lancé avant la construction du site (workflow build.yml), donc toujours à jour."""
import importlib.util, json, sys, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("build", ROOT / "scripts" / "build.py")
b = importlib.util.module_from_spec(spec)
sys.argv = ["build"]
spec.loader.exec_module(b)
ITEMS = [i for i in b.ITEMS if i.get("score") is not None]
TODAY = datetime.date.today().isoformat()
fr = b._fr

CRIT = {  # clé : (libellé, unité, phrase d'atout)
    "rando_km": ("sentiers de randonnée", "km", "la randonnée"),
    "vtt_km": ("sentiers et pistes de VTT", "km", "le VTT"),
    "lacs_15km": ("lacs à moins de 15 km", "", "les lacs"),
    "activites": ("activités de plein air référencées", "", "les activités (tyrolienne, luge, parc d'aventure)"),
    "hebergements": ("hébergements à moins de 8 km", "", "le choix d'hébergements"),
    "alt_max": ("d'altitude maximale", "m", "la fraîcheur de l'altitude"),
}


def val(it, k):
    v = it.get(k)
    return v if isinstance(v, (int, float)) else None


def ou(a):  # « de Chamonix » / « d'Aussois »
    n = a["name"]
    return ("d'" if n[:1].lower() in "aeiouhéèàâ" else "de ") + n


# ── Duels ─────────────────────────────────────────────────────────────
def duel(a, b):
    ia, ib = a["name"], b["name"]
    paras, fortsa, fortsb = [], [], []
    for k, (lib, unit, atout) in CRIT.items():
        va, vb = val(a, k), val(b, k)
        if va is None or vb is None or va == vb or max(va, vb) == 0:
            continue
        gagnant, perdant = (a, b) if va > vb else (b, a)
        hi, lo = max(va, vb), min(va, vb)
        if lo and hi / lo < 1.15:
            continue
        (fortsa if gagnant is a else fortsb).append((hi / max(lo, 1), atout))
        u = f" {unit}" if unit else ""
        if k == "alt_max":
            paras.append(f"Altitude : {gagnant['name']} monte jusqu'à {fr(hi)} m, contre {fr(lo)} m pour {perdant['name']}.")
        else:
            paras.append(f"{lib[0].upper() + lib[1:]} : {fr(hi)}{u} autour {ou(gagnant)}, contre {fr(lo)}{u} autour {ou(perdant)}.")
    fortsa.sort(reverse=True); fortsb.sort(reverse=True)
    conseil = []
    for it, forts in ((a, fortsa), (b, fortsb)):
        if forts:
            conseil.append(f"Choisissez {it['name']} si vous privilégiez {' et '.join(t for _, t in forts[:2])}.")
    sa, sb = a["score"], b["score"]
    vir = lambda x: str(x).replace(".", ",")
    if sa == sb:
        verdict = f"Sur la note globale, {ia} et {ib} sont à égalité ({vir(sa)} / 5)."
    else:
        h, l = (a, b) if sa > sb else (b, a)
        verdict = f"Sur la note globale, {h['name']} ({vir(h['score'])} / 5) devance {l['name']} ({vir(l['score'])} / 5)."
    return {
        "a": a["slug"], "b": b["slug"],
        "title": f"{ia} ou {ib} : quelle station choisir en été ?",
        "intro": f"{ia} et {ib} comparées sur la randonnée, le VTT, les lacs, les activités et l'hébergement.",
        "paragraphs": paras[:5] + [verdict] + conseil,
    }


def duels():
    out, vus = [], set()
    par_pays = {}
    for it in sorted(ITEMS, key=lambda i: -i["score"]):
        par_pays.setdefault(it["pays"], []).append(it)
    for pays in ("France", "Suisse", "Autriche", "Italie"):
        top = par_pays.get(pays, [])[:8]
        paires = [(0, 1), (0, 2), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7)]
        for i, j in paires:
            if j < len(top):
                k = (top[i]["slug"], top[j]["slug"])
                if k not in vus:
                    vus.add(k); out.append(duel(top[i], top[j]))
    tetes = [par_pays[p][0] for p in ("France", "Suisse", "Autriche", "Italie") if par_pays.get(p)]
    for x in range(len(tetes)):
        for y in range(x + 1, len(tetes)):
            k = (tetes[x]["slug"], tetes[y]["slug"])
            if k not in vus:
                vus.add(k); out.append(duel(tetes[x], tetes[y]))
    return out


# ── Articles ──────────────────────────────────────────────────────────
def top(key, n=10, pays=None, plus=None):
    pool = [i for i in ITEMS if val(i, key) is not None and (pays is None or i["pays"] == pays)]
    return sorted(pool, key=lambda i: (-val(i, key), -i["score"]))[:n]


def article(title, excerpt, intro, lignes, fin=""):
    paras = [intro] + lignes + ([fin] if fin else [])
    paras.append("Les chiffres sont mesurés automatiquement à partir des cartes OpenStreetMap et de DATAtourisme, autour du centre de chaque station. Ils donnent un ordre de grandeur et non une garantie : vérifiez auprès de l'office de tourisme avant de partir.")
    return {"title": title, "date": TODAY, "excerpt": excerpt, "paragraphs": paras}


def classement(key, unit, fmt_unit=""):
    return [f"{n}. {it['name']} ({it.get('region', it['pays'])}) : {fr(val(it, key))}{fmt_unit}"
            for n, it in enumerate(top(key), 1)]


def articles():
    out = []
    # 1) classements par critère
    defs = [
        ("rando_km", "Les 10 stations avec le plus de sentiers de randonnée en été",
         "Quelles stations offrent le plus de sentiers à pied autour d'elles ? Voici le classement, en kilomètres de sentiers à moins de 6 km du centre.", " km"),
        ("vtt_km", "Les 10 stations les mieux équipées pour le VTT en été",
         "Pour les amateurs de vélo tout-terrain, le classement des stations avec le plus de kilomètres de sentiers et pistes de VTT à proximité.", " km"),
        ("lacs_15km", "Les 10 stations avec le plus de lacs à proximité",
         "Pour se baigner ou se promener au bord de l'eau, les stations qui comptent le plus de lacs dans un rayon de 15 km.", " lacs"),
        ("hebergements", "Les 10 stations avec le plus grand choix d'hébergements",
         "Hôtels, chalets, campings : les stations avec le plus d'hébergements à moins de 8 km du centre.", " hébergements"),
        ("alt_max", "Les 10 stations les plus hautes pour profiter de la fraîcheur en été",
         "Quand il fait chaud en plaine, l'altitude change tout. Voici les stations qui montent le plus haut.", " m"),
    ]
    for key, titre, intro, unit in defs:
        out.append(article(titre, intro, intro, classement(key, unit, unit)))
    # 2) activités, France
    t = top("activites", 10, "France")
    out.append(article("Les 10 stations françaises avec le plus d'activités de plein air en été",
        "Tyrolienne, luge d'été, parc d'aventure, via ferrata, parapente : les stations françaises les mieux fournies.",
        "Les stations françaises qui comptent le plus d'activités de plein air référencées à moins de 8 km (tyrolienne, luge, parc d'aventure, via ferrata, parapente).",
        [f"{n}. {it['name']} ({it.get('region', '')}) : {fr(it['activites'])} activités" for n, it in enumerate(t, 1)]))
    # 3) meilleures par pays + générale
    for pays, titre in (("France", "en France"), ("Suisse", "en Suisse"), ("Autriche", "en Autriche"), ("Italie", "en Italie")):
        pool = sorted([i for i in ITEMS if i["pays"] == pays], key=lambda i: -i["score"])[:10]
        if len(pool) >= 5:
            out.append(article(f"Les meilleures stations de montagne pour l'été {titre}",
                f"Le classement des stations {titre} selon notre note globale (randonnée, VTT, lacs, activités, hébergements, altitude).",
                f"Notre classement des stations {titre} pour l'été, selon la note globale sur 5 calculée à partir des mesures autour de chaque station.",
                [f"{n}. {it['name']} ({it.get('region', '')}) : note {str(it['score']).replace('.', ',')} / 5" for n, it in enumerate(pool, 1)]))
    pool = sorted(ITEMS, key=lambda i: (-i["score"], i["name"]))[:15]
    out.append(article("Les 15 meilleures stations de montagne pour l'été en Europe",
        "Le classement général des stations d'été selon notre note sur 5.",
        "Le classement général, tous pays confondus, selon la note sur 5 : randonnée (25 %), VTT, lacs et activités (15 % chacun), hébergements, activités nautiques et altitude (10 % chacun).",
        [f"{n}. {it['name']} ({it.get('region', '')}) : {str(it['score']).replace('.', ',')} / 5" for n, it in enumerate(pool, 1)]))
    return out


if __name__ == "__main__":
    d, a = duels(), articles()
    (ROOT / "data" / "duels.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / "data" / "articles.json").write_text(json.dumps(a, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(d)} duels, {len(a)} articles")
