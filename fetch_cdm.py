#!/usr/bin/env python3
"""Récupère les nominations faites en Conseil des ministres (Élysée) pour les
ministères MASA (agriculture) et MTE (travail/emploi). Écrit cdm.json consommé
par weekly_update.py (section « nominations »).

Découverte des comptes-rendus via la page d'archive officielle elysee.fr (urllib),
puis lecture du contenu statique de chaque page et extraction des blocs
« Sur proposition du ministre de l'agriculture / du travail ».
"""
import urllib.request
import re
import json
import os
from datetime import datetime, timezone, timedelta
from html import unescape

HERE = os.path.dirname(os.path.abspath(__file__))
CDM_JSON = os.path.join(HERE, "cdm.json")
MONTHS = ["", "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre"]

MASA_RE = re.compile(r"ministre (?:de l'|du |de la )?(?:agriculture|agro-alimentaire|souveraineté alimentaire)", re.I)
MTE_TERMS = ["transition écologique", "de l'écologie", "de l'environnement",
    "biodiversité", "des forêts", "de la forêt", "de la mer", "de la pêche", "climat"]
CDM_DAYS = 35  # fenêtre de découverte (jours)


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=45).read().decode("utf-8", "replace")


def _text_of(html):
    t = unescape(re.sub(r"<[^>]+>", " ", html))
    return re.sub(r"\s+", " ", t)


def _extract_blocks(text):
    """Découpe le compte-rendu en blocs « Sur proposition du ministre X : ... »
    et ne conserve que ceux relevant du MASA ou du MTE."""
    parts = re.split(r"(Sur proposition (?:du|de la) ministre [^:\n]{3,250}:)", text)
    blocks, cur = [], None
    for p in parts:
        if re.match(r"Sur proposition (?:du|de la) ministre", p):
            cur = {"header": p.strip(), "content": ""}
            blocks.append(cur)
        elif cur is not None:
            cur["content"] += p
    out = []
    for b in blocks:
        h = b["header"]
        masa = bool(MASA_RE.search(h))
        hl = h.lower()
        mte = any(t in hl for t in MTE_TERMS)
        if not (masa or mte):
            continue
        noms = _split_noms(b["content"])
        if noms:
            out.append({"ministere": h.replace("Sur proposition du ", "").strip(": "),
                        "masa": masa, "mte": mte, "noms": noms})
    return out


def _split_noms(content):
    # coupe avant le bloc « Sur proposition » suivant et avant les marqueurs de section / pied de page
    content = re.split(r"\s*Sur proposition (?:du|de la) ministre", content)[0]
    content = re.split(r"\s*(?:Le conseil des ministres a adopté|Le conseil a adopté|Le Président|Sur rapport du|Ouvrir |Fermer |À consulter également|Voir tous les articles|Déplacement au centre)", content)[0]
    segs = re.split(r"-\s+(?=(?:M\.|Mme|Madame|Monsieur)\s)", content)
    res, seen = [], set()
    for s in segs:
        s = re.sub(r"\s+", " ", s).strip()
        if len(s) > 15 and s not in seen:
            seen.add(s)
            res.append(s[:300])
    return res


LISTING_URL = "https://www.elysee.fr/emmanuel-macron/conseil-des-ministres"
LISTING_PAGES = 4  # nombre de pages d'archive à parcourir (~10-12 CDM/page)


def _discover_urls():
    """Découvre les URLs de comptes-rendus récents en parcourant la page d'archive
    officielle de l'Élysée (remplace l'ancienne découverte via recherche web)."""
    urls = set()
    for page in range(LISTING_PAGES):
        page_url = LISTING_URL if page == 0 else f"{LISTING_URL}?page={page}"
        try:
            html = _fetch(page_url)
        except Exception:
            continue
        if not html:
            continue
        found_this_page = 0
        for m in re.finditer(r'href="(/emmanuel-macron/\d{4}/\d{2}/\d{2}/compte-rendu[^"]*)"', html):
            urls.add("https://www.elysee.fr" + m.group(1))
            found_this_page += 1
        if found_this_page == 0:
            break  # page vide ou fin de pagination
    return urls


def main():
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=CDM_DAYS)
    entries = []
    for url in sorted(_discover_urls(), reverse=True):
        m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", url)
        if not m:
            continue
        d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        if d < cutoff:
            continue
        try:
            blocks = _extract_blocks(_text_of(_fetch(url)))
        except Exception:
            continue
        if not blocks:
            continue
        lines, seen_lines = [], set()
        n_total = 0
        for b in blocks:
            tag = "MASA" if b["masa"] else "MTE"
            for line in [f"[{tag}] {b['ministere']}"] + ["   - " + n for n in b["noms"][:15]]:
                if line not in seen_lines:
                    seen_lines.add(line)
                    lines.append(line)
                    if line.startswith("   -"):
                        n_total += 1
        if n_total == 0:
            continue
        date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        entries.append({
            "id": f"cdm-{date}",
            "date": date,
            "title": f"Conseil des ministres du {int(m.group(3))} {MONTHS[int(m.group(2))]} {m.group(1)} — nominations MASA & transition écologique (MTE)",
            "url": url,
            "author": "Conseil des ministres (Élysée)",
            "nature": "NOMINATION",
            "summary": "\n".join(lines)[:1800],
            "categories": ["nominations"],
        })
    with open(CDM_JSON, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    print(f"Comptes-rendus avec nominations MASA/MTE: {len(entries)}")


if __name__ == "__main__":
    main()
