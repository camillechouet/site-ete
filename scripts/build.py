#!/usr/bin/env python3
"""
build.py — moteur de site annuaire (aucune dépendance, Python 3.9+)

Lit  : config.json, data/items.json, data/duels.json (facultatif), data/articles.json (facultatif)
Écrit: dist/  (site statique prêt à publier : accueil, fiches, liste, duels, articles, sitemap, robots, 404, mentions légales)

Utilisation :
    python3 scripts/build.py            # construit dist/
    python3 scripts/build.py --check    # construit puis vérifie les liens internes
"""
from __future__ import annotations
import argparse
import html
import json
import re
import shutil
import sys
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
TODAY = date.today().isoformat()


# ── Utilitaires ──────────────────────────────────────────────────────────────

def esc(s) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFD", name.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "fiche"


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def fmt_num(v) -> str:
    if v is None or v == "":
        return "–"
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, int):
        return f"{v:,}".replace(",", " ")
    return str(v)


def fmt_field(f: dict, v) -> str:
    if v is None or v == "":
        return "–"
    unit = f.get("unit", "")
    txt = fmt_num(v)
    if not unit:
        return txt
    return f"{txt} {unit}"


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ── Chargement ───────────────────────────────────────────────────────────────

CFG = load_json(ROOT / "config.json", {})
SITE = CFG["site"]
VOC = CFG["vocab"]
FIELDS = CFG.get("fields", [])
RATING = CFG.get("rating")
GROUP_KEY = CFG.get("group_key")
REGION_KEY = CFG.get("region_key")
BASE = SITE["domain"].rstrip("/")


def load_items() -> list[dict]:
    items = load_json(ROOT / "data" / "items.json", [])
    dt = load_json(ROOT / "data" / "datatourisme.json", {})
    for it in items:  # activités : maximum entre OpenStreetMap et DATAtourisme
        n = (dt.get(it["name"]) or {}).get("activites")
        if n is not None:
            it["activites"] = max(int(it.get("activites") or 0), n)
    seen: dict[str, int] = {}
    for it in items:
        base = slugify(it["name"])
        n = seen.get(base, 0)
        seen[base] = n + 1
        it["slug"] = base if n == 0 else f"{base}-{n + 1}"
    return items


ITEMS = load_items()
BY_SLUG = {it["slug"]: it for it in ITEMS}


# ── Gabarit commun ───────────────────────────────────────────────────────────

_TH_DEFAULT = {"dark": "#0b1f4d", "acc": SITE.get("color", "#1d4ed8"), "header_bg": "#ffffff", "brand": "#14213d",
               "nav": "#5b6478", "chip_bg": "#eef2ff", "chip_fg": "#1e3a8a", "bg": "#f6f7fb", "fg": "#14213d",
               "icon_bg": SITE.get("color", "#1d4ed8"), "icon_fg": "#ffffff", "hero_fg": "#ffffff", "hero_from": SITE.get("color", "#1d4ed8"),
               "fsel_bg": "rgba(255,255,255,.16)", "fsel_bd": "rgba(255,255,255,.4)", "rule": "#e4e7ef", "line": "#e4e7ef"}
TH = {**_TH_DEFAULT, **CFG.get("theme", {})}
ASSETS = ROOT / "assets"


def _brand_html() -> str:
    parts = SITE.get("name_parts")
    name = (f'<span>{esc(parts[0])}<span class="b2">{esc(parts[1])}</span></span>' if parts and len(parts) == 2
            else f'<span>{esc(SITE["name"])}</span>')
    if (ASSETS / "logo-pin.png").is_file():
        return f'<img src="/logo-pin.png" alt="" width="26" height="32">{name}'
    return name


def _icon_link() -> str:
    if (ASSETS / "favicon.png").is_file():
        return '<link rel="icon" type="image/png" href="/favicon.png">'
    return ("<link rel=\"icon\" href=\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E"
            f"%3Crect width='16' height='16' rx='4' fill='%23{TH['icon_bg'].lstrip('#')}'/%3E%3C/svg%3E\">")


BRAND_HTML = _brand_html()
ICON_LINK = _icon_link()

CSS = """
:root{--c:%(color)s;--dark:%(dark)s;--acc:%(acc)s;--hbg:%(hbg)s;--brand:%(brand)s;--navc:%(navc)s;--chipbg:%(chipbg)s;--chipfg:%(chipfg)s;--herofg:%(herofg)s;--herofrom:%(herofrom)s;--fselbg:%(fselbg)s;--fselbd:%(fselbd)s;--rule:%(rule)s;--bg:%(bg)s;--fg:%(fg)s;--mut:#5b6478;--card:#fff;--line:%(line)s;--r:14px}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%%}
body{margin:0;font:16px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:var(--fg);background:var(--bg)}
a{color:var(--c)}img{max-width:100%%}
.wrap{max-width:1040px;margin:0 auto;padding:0 16px}
header.top{background:var(--hbg);border-bottom:2px solid var(--rule);position:sticky;top:0;z-index:5}
header.top .wrap{display:flex;align-items:center;justify-content:space-between;height:56px}
.brand{display:flex;align-items:center;gap:8px;font-weight:800;font-size:1.15rem;color:var(--brand);text-decoration:none}
nav a{white-space:nowrap;margin-left:16px;text-decoration:none;color:var(--navc);font-weight:600;font-size:.95rem}
nav a:hover{color:var(--acc)}
.brand .b2{color:var(--acc)}.brand img{display:block}
.hero{background:linear-gradient(135deg,var(--herofrom),var(--dark));color:var(--herofg);padding:36px 0 40px}
.hero h1{margin:0 0 8px;font-size:clamp(1.6rem,5vw,2.3rem);line-height:1.2}
.hero p{margin:0 0 20px;opacity:.92}
.search{display:flex;gap:8px;flex-wrap:wrap}
.search input,.search select{padding:12px 14px;border-radius:10px;border:0;font:inherit;min-width:0}
.search input{flex:1 1 220px}.search select{flex:0 1 auto}
.filters{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 0}
.filters select{background:var(--fselbg);color:var(--herofg);border:1px solid var(--fselbd);padding:10px 12px;border-radius:10px;font:inherit}
.filters option{color:#111}
main{padding:24px 0 48px}
h2{font-size:1.35rem;margin:28px 0 12px}
.count{color:var(--mut);margin:0 0 12px;font-size:.95rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:16px;display:block;text-decoration:none;color:inherit;transition:box-shadow .15s}
.card:hover{box-shadow:0 6px 18px rgba(20,33,61,.1)}
.card h3{margin:0 0 4px;font-size:1.05rem}
.card .sub{color:var(--mut);font-size:.88rem;margin-bottom:10px}
.chips{display:flex;gap:6px;flex-wrap:wrap}
.chip{background:var(--chipbg);color:var(--chipfg);border-radius:999px;padding:2px 10px;font-size:.82rem;font-weight:600}
.badge{float:right;background:var(--c);color:#fff;border-radius:8px;padding:2px 8px;font-size:.85rem;font-weight:700}
.panel{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:18px;margin:14px 0}
table.facts{width:100%%;border-collapse:collapse}
table.facts th,table.facts td{padding:9px 6px;border-bottom:1px solid var(--line);text-align:left}
table.facts th{color:var(--mut);font-weight:600;width:48%%}
table.vs td:nth-child(2),table.vs td:nth-child(3),table.vs th:nth-child(2),table.vs th:nth-child(3){text-align:center}
.win{background:#dcfce7;font-weight:700}
.btn{display:inline-block;background:var(--c);color:#fff;padding:12px 18px;border-radius:10px;text-decoration:none;font-weight:700;margin:6px 8px 6px 0}
.btn.alt{background:#fff;color:var(--c);border:1px solid var(--c)}
.crumbs{font-size:.88rem;color:var(--mut);margin:0 0 10px}
.crumbs a{color:var(--mut)}
ul.pts{padding-left:20px;margin:8px 0}
.notice{color:var(--mut);font-size:.82rem;margin-top:10px}
footer{border-top:2px solid var(--rule);background:var(--card);padding:22px 0;color:var(--mut);font-size:.9rem}
footer a{color:var(--mut);margin-right:14px}
.az a{display:inline-block;margin:0 10px 6px 0}
.cols{columns:2 240px;column-gap:24px;padding:0;list-style:none}
.cols li{break-inside:avoid;margin:0 0 6px}
@media(max-width:560px){nav a{margin-left:8px;font-size:.82rem}.brand{font-size:1rem}}
""" % {"color": SITE.get("color", "#1d4ed8"), "dark": TH["dark"], "acc": TH["acc"], "hbg": TH["header_bg"],
        "brand": TH["brand"], "navc": TH["nav"], "chipbg": TH["chip_bg"], "chipfg": TH["chip_fg"],
        "bg": TH["bg"], "fg": TH["fg"], "herofg": TH["hero_fg"], "herofrom": TH["hero_from"], "fselbg": TH["fsel_bg"],
        "fselbd": TH["fsel_bd"], "rule": TH["rule"], "line": TH["line"]}


def page(title: str, body: str, path: str, desc: str = "", jsonld: str = "", extra_head: str = "", noindex: bool = False) -> str:
    canon = f"{BASE}{path}"
    gid = SITE.get("analytics_id", "")
    ga = ""
    if gid:
        ga = (f'<script async src="https://www.googletagmanager.com/gtag/js?id={esc(gid)}"></script>'
              f"<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}gtag('js',new Date());gtag('config','{esc(gid)}');</script>")
    robots = '<meta name="robots" content="noindex">' if noindex else ""
    return f"""<!doctype html>
<html lang="{esc(SITE.get('lang', 'fr'))}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc or SITE.get('description', ''))}">
<link rel="canonical" href="{esc(canon)}">
<meta name="theme-color" content="{esc(TH['header_bg'] if TH['header_bg'] != '#ffffff' else SITE.get('color', '#1d4ed8'))}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc or SITE.get('description', ''))}">
<meta property="og:type" content="website">
<meta property="og:url" content="{esc(canon)}">
<meta property="og:site_name" content="{esc(SITE['name'])}">
{robots}
{ICON_LINK}
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" href="/icon-192.png">
<link rel="stylesheet" href="/style.css">
{extra_head}
{jsonld}
{ga}
</head>
<body>
<header class="top"><div class="wrap">
<a class="brand" href="/">{BRAND_HTML}</a>
<nav><a href="/tous/">{esc(VOC['items'].capitalize())}</a><a href="/duels/">Duels</a><a href="/articles/">Articles</a></nav>
</div></header>
{body}
<footer><div class="wrap">
<a href="/mentions-legales/">Mentions légales</a><a href="/tous/">Toutes les {esc(VOC['items'])}</a><a href="/duels/">Duels</a>
<p class="notice">{esc(CFG.get('legal', {}).get('affiliate_notice', ''))}</p>
<p class="notice">{esc(CFG.get('legal', {}).get('data_notice', ''))}</p>
</div></footer>
<script>if("serviceWorker"in navigator)navigator.serviceWorker.register("/sw.js")</script>
</body></html>
"""


def ld(obj: dict) -> str:
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False) + "</script>"


def breadcrumb_ld(trail: list[tuple[str, str]]) -> str:
    return ld({
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": f"{BASE}{p}"} for i, (n, p) in enumerate(trail)],
    })


# ── Briques ──────────────────────────────────────────────────────────────────

def item_url(it: dict) -> str:
    return f"/{it['slug']}/"


def rating_badge(it: dict) -> str:
    if not RATING or it.get(RATING["key"]) is None:
        return ""
    return f'<span class="badge" title="{esc(RATING["label"])}">{esc(it[RATING["key"]])}</span>'


def sub_line(it: dict) -> str:
    parts = [it.get(k) for k in (REGION_KEY, GROUP_KEY) if k and it.get(k)]
    out: list[str] = []
    for p in parts:
        if not any(p in o or o in p for o in out):
            out.append(p)
    return " · ".join(out)


def card(it: dict) -> str:
    chips = "".join(f'<span class="chip">{esc(fmt_field(f, it.get(f["key"])))}</span>'
                    for f in FIELDS if f.get("card") and it.get(f["key"]) is not None)
    return (f'<a class="card" href="{item_url(it)}">{rating_badge(it)}<h3>{esc(it["name"])}</h3>'
            f'<div class="sub">{esc(sub_line(it))}</div><div class="chips">{chips}</div></a>')


def affiliate_buttons(it: dict, named: bool = False) -> str:
    out = []
    for a in CFG.get("affiliate", []):
        url = a["url"].replace("{name_q}", quote(it["name"])).replace("{name}", it["name"])
        out.append(f'<a class="btn" href="{esc(url)}" rel="{esc(a.get("rel", "sponsored nofollow noopener"))}" target="_blank">{esc(a["label"])}{esc(" : " + it["name"]) if named else ""}</a>')
    for extra in it.get("links", []):
        out.append(f'<a class="btn alt" href="{esc(extra["url"])}" rel="{esc(extra.get("rel", "noopener"))}" target="_blank">{esc(extra["label"])}</a>')
    return "".join(out)


def similar(it: dict, n: int = 4) -> list[dict]:
    """Fiches proches : même valeur de groupe, puis écart minimal sur les champs numériques de similar_on."""
    keys = CFG.get("similar_on", [])
    def dist(o: dict) -> float:
        d = 0.0
        for k in keys:
            a, b = it.get(k), o.get(k)
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                d += abs(a - b) / (abs(a) + abs(b) + 1)
            else:
                d += 0 if a == b else 1
        return d
    cands = [o for o in ITEMS if o["slug"] != it["slug"]]
    cands.sort(key=lambda o: (dist(o), o["name"]))
    return cands[:n]


# ── Pages ────────────────────────────────────────────────────────────────────

def build_item(it: dict) -> None:
    path = item_url(it)
    rows = "".join(f'<tr><th>{esc(f["label"])}</th><td>{esc(fmt_field(f, it.get(f["key"])))}</td></tr>'
                   for f in FIELDS if it.get(f["key"]) is not None)
    if RATING and it.get(RATING["key"]) is not None:
        rows = f'<tr><th>{esc(RATING["label"])}</th><td>{esc(it[RATING["key"]])} / {esc(RATING["max"])}</td></tr>' + rows
    if GROUP_KEY and it.get(GROUP_KEY):
        rows = f'<tr><th>{esc(VOC["group_label"])}</th><td>{esc(it[GROUP_KEY])}</td></tr>' + rows
    pts = "".join(f"<li>{esc(p)}</li>" for p in it.get("points", []))
    pts_html = f'<ul class="pts">{pts}</ul>' if pts else ""
    sims = "".join(card(o) for o in similar(it))
    desc = it.get("description") or it.get("summary", "")
    title = f"{it['name']} : fiche, infos et avis | {SITE['name']}"
    meta = (it.get("summary") or desc)[:155]
    body = f"""<main><div class="wrap">
<p class="crumbs"><a href="/">Accueil</a> › <a href="/tous/">{esc(VOC['items'].capitalize())}</a> › {esc(it['name'])}</p>
<h1>{esc(it['name'])}</h1>
<p>{esc(it.get('summary', ''))}</p>
<div class="panel"><table class="facts">{rows}</table></div>
{pts_html}
{('<div class="panel"><h2 style="margin-top:0">Présentation</h2><p>' + esc(desc) + '</p></div>') if desc else ''}
<p>{affiliate_buttons(it)}</p>
<h2>{esc(VOC['items'].capitalize())} similaires</h2>
<div class="grid">{sims}</div>
</div></main>"""
    jl = ld({"@context": "https://schema.org", "@type": "Place", "name": it["name"], "description": meta,
             "url": f"{BASE}{path}"}) + breadcrumb_ld([("Accueil", "/"), (VOC["items"].capitalize(), "/tous/"), (it["name"], path)])
    write(DIST / it["slug"] / "index.html", page(title, body, path, meta, jl))


def sort_key_rating(it: dict):
    return -(it.get(RATING["key"]) or 0) if RATING else 0


def build_home() -> None:
    top = sorted(ITEMS, key=lambda it: (sort_key_rating(it), it["name"]))[: CFG.get("home", {}).get("top_n", 12)]
    groups = sorted({it.get(GROUP_KEY) for it in ITEMS if GROUP_KEY and it.get(GROUP_KEY)})
    group_opts = "".join(f'<option value="{esc(g)}">{esc(g)}</option>' for g in groups)
    has_data = lambda f: any(it.get(f["key"]) is not None for it in ITEMS)
    num_filters = [f for f in FIELDS if f.get("filter") and has_data(f)][:2]
    num_html = ""
    for f in num_filters:
        num_html += (f'<select data-num="{esc(f["key"])}" aria-label="{esc(f["label"])}">'
                     f'<option value="">{esc(f["label"])}</option>'
                     f'<option value="small">Faible</option><option value="mid">Moyen</option><option value="big">Élevé</option></select>')
    has_rating = bool(RATING) and any(it.get(RATING["key"]) is not None for it in ITEMS)
    sort_opts = ('<option value="rating">Mieux notées</option>' if has_rating else '') + '<option value="name">A → Z</option>'
    for f in FIELDS:
        if f.get("filter") and has_data(f):
            sort_opts += f'<option value="{esc(f["key"])}">{esc(f["label"])} ↓</option>'
    home = CFG.get("home", {})
    body = f"""<section class="hero"><div class="wrap">
<h1>{esc(home.get('title', SITE['name']))}</h1>
<p>{esc(home.get('subtitle', SITE.get('tagline', '')))}</p>
<div class="search">
<input id="q" type="search" placeholder="{esc(VOC['search_placeholder'])}" aria-label="Rechercher" autocomplete="off">
<select id="grp" aria-label="{esc(VOC['group_label'])}"><option value="">{esc(VOC['group_label'])} : tous</option>{group_opts}</select>
<select id="sort" aria-label="Trier">{sort_opts}</select>
</div>
<div class="filters">{num_html}</div>
</div></section>
<main><div class="wrap">
<p class="count" id="count"></p>
<div class="grid" id="grid">{''.join(card(it) for it in top)}</div>
<noscript><p><a href="/tous/">Voir toutes les {esc(VOC['items'])}</a></p></noscript>
<p><a class="btn alt" href="/tous/">Toutes les {esc(VOC['items'])}</a> <a class="btn alt" href="/duels/">Voir les duels</a></p>
</div></main>
<script src="/app.js" defer></script>"""
    jl = ld({"@context": "https://schema.org", "@type": "WebSite", "name": SITE["name"], "url": BASE + "/",
             "potentialAction": {"@type": "SearchAction", "target": f"{BASE}/?q={{q}}", "query-input": "required name=q"}})
    write(DIST / "index.html", page(f"{SITE['name']} : {SITE.get('tagline', '')}", body, "/", SITE.get("description", ""), jl))


def build_all_list() -> None:
    by_letter: dict[str, list[dict]] = {}
    for it in sorted(ITEMS, key=lambda x: slugify(x["name"])):
        by_letter.setdefault(slugify(it["name"])[:1].upper(), []).append(it)
    az = "".join(f'<a href="#l-{esc(l)}">{esc(l)}</a>' for l in by_letter)
    sections = ""
    for l, lst in by_letter.items():
        lis = "".join(f'<li><a href="{item_url(it)}">{esc(it["name"])}</a> <span class="notice">{esc(sub_line(it))}</span></li>' for it in lst)
        sections += f'<h2 id="l-{esc(l)}">{esc(l)}</h2><ul class="cols">{lis}</ul>'
    body = f"""<main><div class="wrap">
<p class="crumbs"><a href="/">Accueil</a> › {esc(VOC['items'].capitalize())}</p>
<h1>Toutes les {esc(VOC['items'])} ({len(ITEMS)})</h1>
<p class="az">{az}</p>{sections}</div></main>"""
    write(DIST / "tous" / "index.html", page(f"Toutes les {VOC['items']} ({len(ITEMS)}) | {SITE['name']}", body, "/tous/",
                                              f"Liste complète des {len(ITEMS)} {VOC['items']} : fiches détaillées et comparatifs."))


def duel_url(d: dict) -> str:
    return f"/duels/{d['slug']}/"


def load_duels() -> list[dict]:
    duels = load_json(ROOT / "data" / "duels.json", [])
    out = []
    for d in duels:
        a, b = BY_SLUG.get(d["a"]), BY_SLUG.get(d["b"])
        if not a or not b:
            print(f"! duel ignoré (fiche introuvable) : {d.get('a')} / {d.get('b')}", file=sys.stderr)
            continue
        d["slug"] = d.get("slug") or f"{a['slug']}-vs-{b['slug']}"
        d["_a"], d["_b"] = a, b
        out.append(d)
    return out


def build_duels(duels: list[dict]) -> None:
    for d in duels:
        a, b = d["_a"], d["_b"]
        rows, wa, wb = "", 0, 0
        for f in FIELDS:
            va, vb = a.get(f["key"]), b.get(f["key"])
            ca = cb = ""
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)) and va != vb and f.get("better"):
                a_wins = (va > vb) if f["better"] == "high" else (va < vb)
                ca, cb = ("win", "") if a_wins else ("", "win")
                wa += a_wins; wb += not a_wins
            rows += f'<tr><th>{esc(f["label"])}</th><td class="{ca}">{esc(fmt_field(f, va))}</td><td class="{cb}">{esc(fmt_field(f, vb))}</td></tr>'
        if RATING:
            rows = (f'<tr><th>{esc(RATING["label"])}</th><td>{esc(a.get(RATING["key"], "–"))}</td><td>{esc(b.get(RATING["key"], "–"))}</td></tr>') + rows
        if wa == wb:
            auto = "Les deux sont au coude à coude sur les critères chiffrés."
        else:
            lead, n = (a, wa) if wa > wb else (b, wb)
            auto = f"{lead['name']} l'emporte sur {n} critère{'s' if n > 1 else ''} chiffré{'s' if n > 1 else ''}."
        title = d.get("title") or f"{a['name']} ou {b['name']} : le duel"
        path = duel_url(d)
        body = f"""<main><div class="wrap">
<p class="crumbs"><a href="/">Accueil</a> › <a href="/duels/">Duels</a> › {esc(a['name'])} vs {esc(b['name'])}</p>
<h1>{esc(title)}</h1>
<p>{esc(d.get('intro', ''))}</p>
<div class="panel"><table class="facts vs"><tr><th></th><th><a href="{item_url(a)}">{esc(a['name'])}</a></th><th><a href="{item_url(b)}">{esc(b['name'])}</a></th></tr>{rows}</table>
<p class="notice">{esc(auto)} Les cases vertes indiquent le meilleur résultat sur chaque critère chiffré.</p></div>
{''.join(f'<div class="panel"><p>{esc(p)}</p></div>' for p in d.get('paragraphs', []))}
<p>{affiliate_buttons(a, True)}{affiliate_buttons(b, True)}</p>
</div></main>"""
        jl = breadcrumb_ld([("Accueil", "/"), ("Duels", "/duels/"), (title, path)])
        write(DIST / "duels" / d["slug"] / "index.html", page(f"{title} | {SITE['name']}", body, path, d.get("intro", "")[:155], jl))
    lis = "".join(f'<li><a href="{duel_url(d)}">{esc(d.get("title") or d["_a"]["name"] + " ou " + d["_b"]["name"])}</a></li>' for d in duels)
    empty = "" if duels else "<p>Les premiers duels arrivent bientôt.</p>"
    body = f'<main><div class="wrap"><p class="crumbs"><a href="/">Accueil</a> › Duels</p><h1>Duels de {esc(VOC["items"])}</h1>{empty}<ul class="cols">{lis}</ul></div></main>'
    write(DIST / "duels" / "index.html", page(f"Duels de {VOC['items']} | {SITE['name']}", body, "/duels/", f"Comparez deux {VOC['items']} face à face.", noindex=not duels))


def load_articles() -> list[dict]:
    arts = load_json(ROOT / "data" / "articles.json", [])
    for a in arts:
        a["slug"] = a.get("slug") or slugify(a["title"])
    return sorted(arts, key=lambda a: a.get("date", ""), reverse=True)


def build_articles(arts: list[dict]) -> None:
    for a in arts:
        paras = "".join(f"<p>{esc(p)}</p>" for p in a.get("paragraphs", []))
        path = f"/articles/{a['slug']}/"
        body = f"""<main><div class="wrap"><p class="crumbs"><a href="/">Accueil</a> › <a href="/articles/">Articles</a></p>
<h1>{esc(a['title'])}</h1><p class="notice">{esc(a.get('date', ''))}</p>{paras}</div></main>"""
        jl = ld({"@context": "https://schema.org", "@type": "Article", "headline": a["title"], "datePublished": a.get("date", TODAY),
                 "mainEntityOfPage": f"{BASE}{path}"})
        write(DIST / "articles" / a["slug"] / "index.html", page(f"{a['title']} | {SITE['name']}", body, path, a.get("excerpt", "")[:155], jl))
    lis = "".join(f'<li><a href="/articles/{a["slug"]}/">{esc(a["title"])}</a> <span class="notice">{esc(a.get("date", ""))}</span></li>' for a in arts)
    empty = "" if arts else "<p>Les premiers articles arrivent bientôt.</p>"
    body = f'<main><div class="wrap"><p class="crumbs"><a href="/">Accueil</a> › Articles</p><h1>Articles</h1>{empty}<ul class="cols">{lis}</ul></div></main>'
    write(DIST / "articles" / "index.html", page(f"Articles | {SITE['name']}", body, "/articles/", f"Guides et actualités sur les {VOC['items']}.", noindex=not arts))


def build_legal() -> None:
    L = CFG.get("legal", {})
    body = f"""<main><div class="wrap"><h1>Mentions légales</h1>
<div class="panel"><p><strong>Éditeur :</strong> {esc(L.get('publisher', ''))} — SIRET {esc(L.get('siret', ''))}<br>
<strong>Contact :</strong> {esc(SITE.get('contact_email', ''))}<br>
<strong>Hébergeur :</strong> {esc(L.get('host', ''))}</p>
<p>{esc(L.get('affiliate_notice', ''))}</p>
<p>Les informations de ce site sont données à titre indicatif ; vérifiez-les auprès des sites officiels avant de réserver.</p></div></div></main>"""
    write(DIST / "mentions-legales" / "index.html", page(f"Mentions légales | {SITE['name']}", body, "/mentions-legales/", noindex=True))


def build_404() -> None:
    body = '<main><div class="wrap"><h1>Page introuvable</h1><p><a href="/">Retour à l\'accueil</a> ou <a href="/tous/">toutes les fiches</a>.</p></div></main>'
    write(DIST / "404.html", page(f"Page introuvable | {SITE['name']}", body, "/404.html", noindex=True))


APP_JS = r"""(function(){
var grid=document.getElementById('grid'),q=document.getElementById('q'),grp=document.getElementById('grp'),sort=document.getElementById('sort'),count=document.getElementById('count');
if(!grid)return;
var data=null,nums=[].slice.call(document.querySelectorAll('select[data-num]'));
var ini=new URLSearchParams(location.search).get('q');if(ini)q.value=ini;
function norm(s){return (s||'').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'')}
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function load(cb){if(data)return cb();fetch('/items.json').then(function(r){return r.json()}).then(function(d){data=d;cb()})}
function tercile(key){var v=data.map(function(i){return i.n[key]}).filter(function(x){return x!=null}).sort(function(a,b){return a-b});return [v[Math.floor(v.length/3)],v[Math.floor(2*v.length/3)]]}
var cuts={};
function render(){
 var t=norm(q.value),g=grp.value,s=sort.value;
 var list=data.filter(function(i){
  if(t&&norm(i.name+' '+i.sub).indexOf(t)<0)return false;
  if(g&&i.g!==g)return false;
  for(var k=0;k<nums.length;k++){var key=nums[k].getAttribute('data-num'),m=nums[k].value;if(!m)continue;var v=i.n[key];if(v==null)return false;var c=cuts[key];
   if(m==='small'&&!(v<=c[0]))return false;if(m==='mid'&&!(v>c[0]&&v<=c[1]))return false;if(m==='big'&&!(v>c[1]))return false}
  return true});
 list.sort(function(a,b){if(s==='name')return a.name.localeCompare(b.name,'fr');if(s==='rating')return (b.r||0)-(a.r||0)||a.name.localeCompare(b.name,'fr');return (b.n[s]||0)-(a.n[s]||0)});
 count.textContent=list.length+' résultat'+(list.length>1?'s':'');
 grid.innerHTML=list.slice(0,60).map(function(i){return '<a class="card" href="/'+i.s+'/">'+(i.r!=null?'<span class="badge">'+esc(i.r)+'</span>':'')+'<h3>'+esc(i.name)+'</h3><div class="sub">'+esc(i.sub)+'</div><div class="chips">'+i.chips.map(function(c){return '<span class="chip">'+esc(c)+'</span>'}).join('')+'</div></a>'}).join('')+(list.length>60?'<p class="count">… et '+(list.length-60)+' autres : affinez la recherche.</p>':'')
}
function go(){load(function(){nums.forEach(function(n){var k=n.getAttribute('data-num');if(!cuts[k])cuts[k]=tercile(k)});render()})}
var timer;q.addEventListener('input',function(){clearTimeout(timer);timer=setTimeout(go,120)});
[grp,sort].concat(nums).forEach(function(e){e.addEventListener('change',go)});
q.addEventListener('focus',function(){load(function(){})},{once:true});
if(ini)go();
})();"""


def build_assets() -> None:
    write(DIST / "style.css", CSS)
    write(DIST / "app.js", APP_JS)
    compact = []
    for it in ITEMS:
        chips = [fmt_field(f, it.get(f["key"])) for f in FIELDS if f.get("card") and it.get(f["key"]) is not None]
        compact.append({
            "s": it["slug"], "name": it["name"], "sub": sub_line(it), "g": it.get(GROUP_KEY, "") if GROUP_KEY else "",
            "r": it.get(RATING["key"]) if RATING else None, "chips": chips,
            "n": {f["key"]: it.get(f["key"]) for f in FIELDS if isinstance(it.get(f["key"]), (int, float))},
        })
    write(DIST / "items.json", json.dumps(compact, ensure_ascii=False, separators=(",", ":")))
    if ASSETS.is_dir():
        shutil.copytree(ASSETS, DIST, dirs_exist_ok=True)
    build_pwa()
    write(DIST / "robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n")


def build_pwa() -> None:
    """Rend le site installable sur l'écran d'accueil (PWA) : manifeste, icônes, service worker minimal."""
    color = TH["icon_bg"]
    manifest = {"name": SITE["name"], "short_name": SITE["name"][:12], "start_url": "/", "display": "standalone",
                "background_color": "#ffffff", "theme_color": TH["header_bg"] if TH["header_bg"] != "#ffffff" else color, "lang": SITE.get("lang", "fr"),
                "icons": [{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
                          {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}]}
    write(DIST / "manifest.webmanifest", json.dumps(manifest, ensure_ascii=False))
    write(DIST / "sw.js", "self.addEventListener('install',()=>self.skipWaiting());\n"
          "self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));\n"
          "self.addEventListener('fetch',e=>{});\n")
    if (DIST / "icon-192.png").is_file():
        return
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return
    for size in (192, 512):
        img = Image.new("RGB", (size, size), color)
        d = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", int(size * 0.55))
        except OSError:
            font = ImageFont.load_default()
        d.text((size / 2, size / 2), SITE["name"][:1].upper(), fill=TH["icon_fg"], font=font, anchor="mm")
        img.save(DIST / f"icon-{size}.png")


def build_sitemap(duels: list[dict], arts: list[dict]) -> int:
    urls = ["/", "/tous/", "/duels/", "/articles/"] + [item_url(i) for i in ITEMS] + [duel_url(d) for d in duels] + [f"/articles/{a['slug']}/" for a in arts]
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml += "".join(f"<url><loc>{esc(BASE + u)}</loc><lastmod>{TODAY}</lastmod></url>\n" for u in urls)
    xml += "</urlset>\n"
    write(DIST / "sitemap.xml", xml)
    return len(urls)


def check_links() -> int:
    """Vérifie que chaque lien interne pointe vers un fichier existant dans dist/."""
    bad = 0
    pat = re.compile(r'(?:href|src)="(/[^"#?]*)')
    for f in DIST.rglob("*.html"):
        for m in pat.finditer(f.read_text(encoding="utf-8")):
            target = m.group(1)
            p = DIST / target.lstrip("/")
            ok = p.is_file() or (p / "index.html").is_file()
            if not ok:
                bad += 1
                if bad <= 20:
                    print(f"  lien cassé dans {f.relative_to(DIST)} : {target}", file=sys.stderr)
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not ITEMS:
        print("data/items.json est vide : rien à construire.", file=sys.stderr)
        return 1
    if DIST.exists():
        shutil.rmtree(DIST)
    duels, arts = load_duels(), load_articles()
    build_assets()
    for it in ITEMS:
        build_item(it)
    build_home(); build_all_list(); build_duels(duels); build_articles(arts); build_legal(); build_404()
    n = build_sitemap(duels, arts)
    print(f"OK : {len(ITEMS)} fiches, {len(duels)} duels, {len(arts)} articles, {n} URL dans le sitemap.")
    if args.check:
        bad = check_links()
        print("Liens internes : OK" if bad == 0 else f"Liens internes cassés : {bad}")
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
