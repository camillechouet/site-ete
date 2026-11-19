# Modèle de site annuaire

Un site léger (pages statiques, aucune dépendance) généré à partir de **deux fichiers** :

- `config.json` : nom du site, couleurs, vocabulaire, critères affichés, liens d'affiliation, mentions légales.
- `data/items.json` : une entrée par fiche (nom, description, chiffres).

Ce qui n'y est pas, volontairement : pas de « Tinder », pas de météo, pas d'application. Une recherche avec 2-3 filtres, des fiches, des duels, des articles.

## Créer un nouveau site en 5 étapes

1. Dupliquer le dépôt (bouton « Use this template » ou copie du dossier) et le nommer comme le nouveau site.
2. Modifier `config.json` : `site.name`, `site.domain`, `vocab` (ex. « base de loisirs / bases de loisirs »), `fields` (les critères chiffrés), `affiliate` (liens de réservation).
3. Remplacer `data/items.json` par les fiches du nouveau site (voir le format ci-dessous).
4. Dans GitHub : Settings > Pages > Source : **GitHub Actions**. Puis y indiquer le nom de domaine acheté.
5. Chaque modification de fichier relance la publication automatiquement.

## Format d'une fiche (`data/items.json`)

```json
{
  "name": "Lac de Vassivière",
  "pays": "France",
  "region": "Limousin",
  "summary": "Phrase courte affichée sous le titre.",
  "description": "Texte de présentation plus long.",
  "points": ["Point fort 1", "Point fort 2"],
  "km": 12,
  "score": 4.2
}
```

Les clés chiffrées (`km`, `score`…) doivent correspondre aux `key` de `fields` et `rating` dans `config.json`.
Pour un lien spécifique à une fiche : `"links": [{"label": "Site officiel", "url": "https://…"}]`.

## Duels et articles

- `data/duels.json` : `[{"a": "slug-fiche-a", "b": "slug-fiche-b", "title": "…", "intro": "…", "paragraphs": ["…"]}]`. Le tableau comparatif et les cases vertes se font tout seuls.
- `data/articles.json` : `[{"title": "…", "date": "2026-11-16", "excerpt": "…", "paragraphs": ["…"]}]`.
- Les slugs sont le nom sans accents ni espaces (« Val d'Isère » devient `val-d-isere`).

## Tester en local (facultatif)

```
python3 scripts/build.py --check     # construit dist/ et vérifie les liens
```

## Ce qui reste à ajouter (étape suivante)

- Rédaction automatique d'un duel et d'un article par semaine avec contrôle des chiffres (reprise de la logique de SnowFinder).
- Traduction automatique, flux Pinterest, photos : à brancher une fois le premier site en ligne.
