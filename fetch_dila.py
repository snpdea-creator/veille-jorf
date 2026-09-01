#!/usr/bin/env python3
"""Source JORF principale : open data DILA (echanges.dila.gouv.fr).

Recupere les editions quotidiennes du JORF (archives tar.gz publiques, sans authentification,
sans Cloudflare, sans lag d'indexation). Pour chaque texte (XML de version), extrait :
  - ID JORFTEXT, NATURE, DATE_PUBLI, TITREFULL, MINISTERE, contenu (BLOC_TEXTUEL/CONTENU)
et construit une entree au format attendu par weekly_update.categorize().

Pre-filtre large sur le perimetre MASA (MINISTERE ou TITREFULL contenant un mot-cle agriculture)
pour ne renvoyer que les textes pertinents (evite de renvoyer les ~10000 textes/jour).

Fichier consomme par weekly_update.py (fetch_dila.fetch_recent_entries).
"""
import urllib.request
import tarfile
import io
import re
import os
from datetime import datetime, timezone, timedelta
from html import unescape

DILA_INDEX = "https://echanges.dila.gouv.fr/OPENDATA/JORF/?C=N;O=D"
DILA_BASE = "https://echanges.dila.gouv.fr/OPENDATA/JORF/"
DAYS = 14

# Mot-cles larges pour le pre-filtre de perimetre (union ; le filtrage fin est fait par categorize())
SCOPE_KEYS = [
    "agricole", "agriculture", "agro-alimentaire", "agroalimentaire",
    "souveraineté alimentaire", "eplefpa", "legta", "lpaa", "cfppa", "btsa", "capesa",
    "enseignement agricole", "formation professionnelle agricole", "ingénieur agronome",
    "vétérinaire", "institut agro", "agroparistech", "supagro", "agrocampus", "ensat", "enfa",
    "franceagrimer", "inrae", "anses", "odeadom", "ifce", "office national des forêts",
    "office français de la biodiversité", "inao", "cnpf",
    "draaf", "driaaf", "direction générale de l'enseignement et de la recherche",
    "concours", "recrutement", "statut", "corps", "nomination", "nommant",
    "ddets", "dreets", "drieets", "emploi, du travail et des solidarités",
]
SCOPE_RX = re.compile("|".join(re.escape(k) for k in SCOPE_KEYS), re.I)


def _list_recent_tarballs(days=DAYS):
    try:
        html = urllib.request.urlopen(
            urllib.request.Request(DILA_INDEX, headers={"User-Agent": "Mozilla/5.0"}),
            timeout=30).read().decode("utf-8", "replace")
    except Exception:
        return []
    seen = {}
    for fn, d in re.findall(r'href="(JORF_(\d{8})-\d{6}\.tar\.gz)"', html):
        seen.setdefault(d, fn)  # l'index est trie par nom desc => 1er = edition la plus tardive du jour
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for d, fn in sorted(seen.items(), reverse=True):
        try:
            dt = datetime.strptime(d, "%Y%m%d").replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if dt < cutoff:
            continue
        out.append(fn)
    return out


def _fetch_tarball(fn):
    return urllib.request.urlopen(
        urllib.request.Request(DILA_BASE + fn, headers={"User-Agent": "Mozilla/5.0"}),
        timeout=120).read()


def _text(s):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def parse_tarball(data):
    """Retourne la liste des entrees MASA-scope contenues dans une archive quotidienne."""
    entries = []
    try:
        tf = tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")
    except Exception:
        return entries
    for m in tf.getmembers():
        name = m.name
        if not name.endswith(".xml") or "/version/" not in name:
            continue
        f = tf.extractfile(m)
        if f is None:
            continue
        xml = f.read().decode("utf-8", "replace")
        # pre-filtre rapide sur MINISTERE + TITREFULL (evite le parse complet des textes hors scope)
        quick = xml[:4000]
        if not SCOPE_RX.search(quick):
            continue
        mid = re.search(r"<ID>(JORFTEXT\d{12})</ID>", xml)
        if not mid:
            continue
        jid = mid.group(1)
        nature = (re.search(r"<NATURE>([^<]+)</NATURE>", xml) or [None, ""]).group(1) if re.search(r"<NATURE>([^<]+)</NATURE>", xml) else ""
        date_pub = (re.search(r"<DATE_PUBLI>([^<]+)</DATE_PUBLI>", xml) or re.search(r"<DATE_PUBLI>([^<]+)", xml))
        dp = date_pub.group(1) if date_pub else ""
        titre = re.search(r"<TITREFULL>([^<]*)</TITREFULL>", xml)
        titre = titre.group(1) if titre else ""
        if not titre:
            t2 = re.search(r"<TITRE>([^<]*)</TITRE>", xml)
            titre = t2.group(1) if t2 else ""
        ministre = re.search(r"<MINISTERE>([^<]*)</MINISTERE>", xml)
        ministre = ministre.group(1) if ministre else ""
        # contenu : BLOC_TEXTUEL/CONTENU, sinon texte du visa
        bloc = re.search(r"<BLOC_TEXTUEL>(.*?)</BLOC_TEXTUEL>", xml, re.S)
        content = _text(bloc.group(1)) if bloc else ""
        if not content:
            visa = re.search(r"<CONTENU>(.*?)</CONTENU>", xml, re.S)
            content = _text(visa.group(1)) if visa else ""
        # filtre de perimetre fin sur l'union ministre+titre+contenu
        if not SCOPE_RX.search(ministre + " " + titre + " " + content):
            continue
        link = f"https://www.legifrance.gouv.fr/jorf/id/{jid}"
        entries.append({
            "id": link, "link": link,
            "published": f"{dp}T00:00:00Z" if dp else "",
            "title": titre, "author": ministre,
            "content": content, "nature": nature,
        })
    return entries


def fetch_recent_entries(days=DAYS):
    """Recupere les entrees JORF MASA-scope des `days` derniers jours (source DILA)."""
    entries = []
    for fn in _list_recent_tarballs(days=days):
        try:
            data = _fetch_tarball(fn)
        except Exception:
            continue
        entries.extend(parse_tarball(data))
    # dedup par id (plusieurs editions par jour possibles)
    seen = {}
    for e in entries:
        seen[e["id"]] = e
    return list(seen.values())


if __name__ == "__main__":
    ents = fetch_recent_entries()
    print(f"Entrees MASA-scope (DILA, {DAYS}j): {len(ents)}")
    from collections import Counter
    c = Counter()
    for e in ents:
        c[e["published"][:10]] += 1
    for d, n in sorted(c.items()):
        print(f"  {d}: {n} textes")
    cab = [e for e in ents if "54733930" in e["id"]]
    print("  cabinet 54733930 present:", bool(cab))
    if cab:
        print("   titre:", cab[0]["title"][:90])
