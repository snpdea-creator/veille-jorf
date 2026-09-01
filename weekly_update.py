#!/usr/bin/env python3
"""Mise à jour quotidienne du dashboard de veille JORF.
- Charge l'historique existant (data.json) pour préserver les semaines passées
- Récupère les flux legifrss.org sur 14 jours (chevauchement)
- Applique la porte de pertinence MASA stricte + catégorisation à assignation unique
- Fusionne les nouveautés (dédup par identifiant JORF)
- Écrit data.json + data.js + diff_report.json
Source: Journal officiel (JORF) via Légifrance. BO Agri exclu du périmètre.
"""
import urllib.request
import xml.etree.ElementTree as ET
import json
import re
import os
from datetime import datetime, timezone, timedelta
from html import unescape
from concurrent.futures import ThreadPoolExecutor, as_completed

NS = {"atom": "http://www.w3.org/2005/Atom"}
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_JSON = os.path.join(HERE, "data.json")
DATA_JS = os.path.join(HERE, "data.js")
DIFF_JSON = os.path.join(HERE, "diff_report.json")
CDM_JSON = os.path.join(HERE, "cdm.json")

AGRI_EDU_TERMS = ["enseignement agricole", "eplefpa", "legta", "lpaa", "cfppa", "btsa", "capesa",
    "brevet professionnel agricole", "bac professionnel agricole", "dplp", "ingénieur agronome",
    "école nationale vétérinaire", "institut agro", "agroparistech", "supagro", "agrocampus",
    "ensat", "enfa", "agro-campus", "diplôme de l'enseignement agricole",
    "établissement public local d'enseignement et de formation professionnelle agricole",
    "direction générale de l'enseignement et de la recherche", "direction de l'enseignement agricole",
    "enseignement supérieur agricole", "formation professionnelle agricole",
    "certificat de spécialisation agricole"]
MASA_OFFICES = ["franceagrimer", "inrae", "institut national de la recherche agronomique",
    "anses", "agence nationale de sécurité sanitaire", "agence de services et de paiement",
    "odeadom", "office de développement de l'économie agricole", "ifce", "institut français du cheval",
    "cnpf", "centre national de la propriété forestière", "office national des forêts",
    "office français de la biodiversité", "inao", "institut national de l'origine et de la qualité"]
MASA_SERVICES = ["draaf", "driaaf", "dger", "direction régionale de l'alimentation, de l'agriculture et de la forêt",
    "direction régionale et interdépartementale de l'alimentation, de l'agriculture et de la forêt",
    "direction générale de l'enseignement et de la recherche"]
CONCOURS_TERMS = ["concours", "recrutement", "examen professionnel", "jury de concours", "lauréat",
    "calendrier des concours", "ouverture de concours", "liste d'aptitude", "recrutement réservé"]
# DDETS / DREETS / DRIEETS (directions emploi/travail/solidarités)
EMPLOI_TRAVAIL_TERMS = ["de l'emploi, du travail et des solidarités",
    "direction départementale de l'emploi, du travail et des solidarités",
    "direction de l'emploi, du travail et des solidarités",
    "direction régionale de l'économie, de l'emploi, du travail et des solidarités",
    "direction régionale et interdépartementale de l'économie, de l'emploi, du travail et des solidarités"]
MASA_MINISTRY_TERMS = ["ministère de l'agriculture", "agro-alimentaire", "souveraineté alimentaire"]

CATEGORIES = {
    "enseignement_agricole": "Enseignement agricole & EPLEFPA",
    "concours": "Concours & recrutements MASA",
    "statuts": "Statuts des personnels (tous corps)",
    "nominations": "Nominations (directions, services déconcentrés, offices)",
    "avis_vacance": "Avis de vacance — emplois de direction (MASA & DDI avec agents MASA)",
    "organisation_admin": "Organisation administrative du MASA",
}

# Textes JORF non indexes par legifrss (nominations cabinet, etc.) a recuperer via jorfsearch.
# Source de secours : jorfsearch.steinertriples.ch/doc/<JORFTEXTID> (contenu parse, accessible par urllib).
TRACKED_JORF_IDS = ["JORFTEXT000054733930"]
JORFSEARCH_DOC = "https://jorfsearch.steinertriples.ch/doc/{}"
_MONTHS_FR = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet",
              "août", "septembre", "octobre", "novembre", "décembre"]


def fetch_tracked_jorf(jid):
    """Recupere un texte JORF par son identifiant via jorfsearch /doc et construit
    une entree au meme format que parse_entries (pour reutilisation de categorize())."""
    html = fetch_feed(JORFSEARCH_DOC.format(jid))
    if not html:
        return None
    txt = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html)))
    mdate = re.search(r"(\d{1,2})\s+([A-Za-zéûôà]+)\s+(\d{4})", txt)
    if not mdate:
        return None
    mn = _MONTHS_FR.index(mdate.group(2).lower()) if mdate.group(2).lower() in _MONTHS_FR else 0
    try:
        iso = f"{int(mdate.group(3)):04d}-{mn:02d}-{int(mdate.group(1)):02d}T00:00:00Z"
    except Exception:
        return None
    cab = re.search(r'cabinet\s*=\s*"([^"]+)"', txt)
    author = re.sub(r"^\s+", "", cab.group(1)).strip() if cab else "Ministère de l'agriculture"
    obj = re.search(r"Objet:\s*(.+?)(?:\s+date_debut|$)", txt)
    objet = obj.group(1).strip() if obj else ""
    link = f"https://www.legifrance.gouv.fr/jorf/id/{jid}"
    title = f"Arrêté portant nomination au cabinet de la ministre de l'agriculture — {objet[:80]}"
    content = f"{objet} {author}"
    return {"title": title, "id": link, "published": iso, "author": author,
            "link": link, "content": content, "nature": "NOMINATION"}


def fetch_feed(url):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=45) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception:
            continue
    return None

def fetch_many(urls):
    results = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch_feed, u): u for u in urls}
        for fut in as_completed(futs):
            u = futs[fut]
            try:
                results[u] = fut.result()
            except Exception:
                results[u] = None
    return results

def parse_entries(xml_text):
    entries = []
    if not xml_text:
        return entries
    root = ET.fromstring(xml_text)
    for entry in root.findall("atom:entry", NS):
        title = entry.find("atom:title", NS)
        eid = entry.find("atom:id", NS)
        pub = entry.find("atom:published", NS)
        author = entry.find("atom:author/atom:name", NS)
        link = entry.find("atom:link", NS)
        content = entry.find("atom:content", NS)
        cat = entry.find("atom:category", NS)
        entries.append({
            "title": unescape(title.text or "") if title is not None else "",
            "id": eid.text if eid is not None else "",
            "published": pub.text if pub is not None else "",
            "author": author.text if author is not None else "",
            "link": link.get("href") if link is not None else "",
            "content": unescape(content.text or "") if content is not None else "",
            "nature": cat.get("term") if cat is not None else "",
        })
    return entries

def clean_html(s):
    s = re.sub(r"<[^>]+>", " ", s)
    s = unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _wb(term):
    # Correspondance avec limites de mots pour eviter les faux positifs (ex: "enfa" dans "enfants")
    return re.compile(r'\b' + re.escape(term) + r'\b', re.IGNORECASE)

_WB_CACHE = {}
def has_any(text, terms):
    for t in terms:
        rx = _WB_CACHE.get(t)
        if rx is None:
            rx = _wb(t)
            _WB_CACHE[t] = rx
        if rx.search(text):
            return True
    return False

def categorize(entry):
    """Catégorisation à assignation unique : chaque texte va dans UNE seule section
    (le critère le plus pertinent), sans doublon entre sections."""
    title = entry["title"] or ""
    author = entry["author"] or ""
    content = clean_html(entry["content"] or "")
    text = (title + " " + author + " " + content).lower()

    is_masa_author = ("agriculture" in author.lower() or "agro-alimentaire" in author.lower()
        or "agroalimentaire" in author.lower() or "souveraineté alimentaire" in author.lower())
    is_agri_edu = has_any(text, AGRI_EDU_TERMS)
    is_masa_office = has_any(text, MASA_OFFICES)
    is_masa_service = has_any(text, MASA_SERVICES)
    mentions_masa_ministry = has_any(text, MASA_MINISTRY_TERMS)
    is_ddets_family = has_any(text, EMPLOI_TRAVAIL_TERMS)

    is_vacance_avis = has_any(text, ["avis de vacance d'un emploi", "avis de vacance d un emploi",
        "avis de vacance d'un emploi de direction", "avis de vacance d un emploi de direction"])

    # Section "avis de vacance" généralisée :
    #  avis pour services/offices du MASA, OU directions emploi/travail/solidarités (DDETS/DREETS/DRIEETS),
    #  OU DDI mentionnant le ministère de l'Agriculture comme tutelle (DDI avec agents du MASA)
    is_avis_vacance = is_vacance_avis and (
        is_masa_service or is_masa_office or is_agri_edu or is_ddets_family or mentions_masa_ministry
    )

    in_scope = is_masa_author or is_agri_edu or is_masa_office or is_masa_service or is_avis_vacance
    if not in_scope:
        return []

    nomin_terms = ["portant nomination", "nommant", "désignation", "portant détachement", "portant titularisation",
        "portant intégration", "portant promotion", "portant cessation de fonctions", "portant démission",
        "portant révocation", "portant maintien en détachement", "portant reconduction",
        "portant décharge de fonctions", "portant relèvement"]
    is_pure_nomination = has_any(text, nomin_terms)
    # nomination détectée dans le TITRE seul (individu nominé, ex: "arrêté nommant M. X...")
    title_nomination = has_any(title.lower(), nomin_terms)
    has_statut = has_any(text, ["statut particulier", "modification du statut", "modifiant le statut",
        "création d'un corps", "fusion de corps", "transformation du corps", "grille indiciaire",
        "régime indemnitaire", "indices de rémunération", "échelle de rémunération",
        "durée du travail", "temps de travail", "comité technique", "comité social d'administration",
        "commission administrative paritaire", "conseil supérieur de la fonction publique",
        "déontologie des", "droit syndical", "reclassement", "avancement de grade"])
    has_concours_title = has_any(title.lower(), ["concours", "recrutement", "examen professionnel", "lauréat", "liste d'aptitude"])
    has_concours = has_concours_title or has_any(text, ["ouverture de concours", "calendrier des concours",
        "avis de concours", "recrutement réservé", "concours d'accès", "concours d'entrée",
        "concours de recrutement"])

    # Assignation unique par priorité (du plus spécifique/actionnable au résiduel)
    if is_avis_vacance:
        return ["avis_vacance"]
    if has_statut and not is_pure_nomination:
        return ["statuts"]
    if has_concours and not is_pure_nomination:
        return ["concours"]
    # Texte structurel d'enseignement agricole (EPLEFPA, décret/arrêté d'organisation ou d'administration,
    #  réglementation des formations) : la mention "nomination" dans le contenu est incidente (gouvernance).
    #  On le classe en enseignement_agricole sauf si le TITRE désigne une nomination individuelle.
    if is_agri_edu and not title_nomination:
        return ["enseignement_agricole"]
    if is_pure_nomination or entry["nature"] == "NOMINATION":
        return ["nominations"]
    if is_agri_edu:
        return ["enseignement_agricole"]
    # Organisation administrative du ministère (secrétariat général, directions, sous-directions, services)
    if has_any(title.lower(), ["organisation", "attributions", "secrétariat général", "portant création d'une direction",
            "portant création d'un service", "portant création d'une mission", "structure des directions"]):
        return ["organisation_admin"]
    # MASA-scope sans événement RH ni contenu d'enseignement agricole -> arrêté technique, exclu
    return []

def main():
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=14)  # chevauchement de 14 jours

    fetched = {}
    feeds_ok = 0
    source = "legifrss"

    # Source principale : open data DILA (fiable, complet, sans auth, sans lag d'indexation)
    try:
        from fetch_dila import fetch_recent_entries
        dila = fetch_recent_entries(days=14)
    except Exception:
        dila = []
    if dila:
        for e in dila:
            fetched[e["id"]] = e
        feeds_ok = 1
        source = "DILA"
    else:
        # Repli : legifrss (si DILA indisponible)
        keyword_queries = ["agricole", "enseignement+agricole", "concours+agriculture",
            "nomination+agriculture", "statut+corps", "DRAAF", "DDETS"]
        urls = [f"https://legifrss.org/latest?q={q}" for q in keyword_queries]
        results = fetch_many(urls)
        for url, xml in results.items():
            if xml:
                feeds_ok += 1
            for e in parse_entries(xml):
                if e["id"]:
                    fetched[e["id"]] = e

    # Nominations au cabinet du MASA suivies manuellement (filet de securite : la source
    # DILA couvre normalement deja ces textes via le mot-cle "agriculture" dans le champ
    # MINISTERE, mais certains arretes de cabinet ont un champ MINISTERE moins explicite).
    for jid in TRACKED_JORF_IDS:
        e = fetch_tracked_jorf(jid)
        if e:
            fetched[e["id"]] = e

    # Charger l'historique existant
    existing = {"weeks": {}, "categories": CATEGORIES, "total_texts": 0}
    if os.path.exists(DATA_JSON):
        try:
            with open(DATA_JSON, encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass
    old_ids = set()
    for items in existing.get("weeks", {}).values():
        for it in items:
            old_ids.add(it["id"])

    # Catégoriser TOUS les items de la fenêtre courante (re-catégorisation avec contenu complet
    # et logique à jour), afin qu'un changement de règle s'applique rétroactivement aux textes
    # encore dans la fenêtre de 14 jours.
    fetched_items = []
    new_ids = set()
    for e in fetched.values():
        try:
            pub_date = datetime.fromisoformat(e["published"].replace("Z", "+00:00"))
        except Exception:
            continue
        if pub_date < cutoff:
            continue
        cats = categorize(e)
        if not cats:
            continue
        if e["id"] not in old_ids:
            new_ids.add(e["id"])
        fetched_items.append({
            "title": e["title"], "url": e["link"], "id": e["id"],
            "date": pub_date.strftime("%Y-%m-%d"), "author": e["author"],
            "nature": e["nature"], "summary": clean_html(e["content"])[:500],
            "categories": cats,
        })

    # Nominations du Conseil des ministres (MASA & MTE) — issues de fetch_cdm.py
    cdm_items = []
    if os.path.exists(CDM_JSON):
        try:
            with open(CDM_JSON, encoding="utf-8") as f:
                cdm_items = json.load(f)
            for it in cdm_items:
                it["categories"] = it.get("categories") or ["nominations"]
                if it["id"] not in old_ids:
                    new_ids.add(it["id"])
        except Exception:
            cdm_items = []

    # Fusionner : existing d'abord, puis fetched/cdm écrasent (re-catégorisation à jour)
    all_items = []
    for items in existing.get("weeks", {}).values():
        all_items.extend(items)
    all_items.extend(fetched_items)
    all_items.extend(cdm_items)
    seen = {}
    for it in all_items:
        seen[it["id"]] = it  # fetched/cdm écrasent existing en cas de doublon
    all_items = list(seen.values())
    all_items.sort(key=lambda x: x["date"], reverse=True)

    weeks = {}
    for it in all_items:
        iso = datetime.fromisoformat(it["date"]).isocalendar()
        wk = f"{iso.year}-W{iso.week:02d}"
        weeks.setdefault(wk, []).append(it)

    output = {
        "generated_at": now.isoformat(),
        "categories": CATEGORIES,
        "weeks": weeks,
        "total_texts": len(all_items),
        "scope_note": "Journal officiel (JORF) via Légifrance. Le Bulletin officiel du ministère de l'Agriculture (BO Agri) est exclu du périmètre.",
    }
    with open(DATA_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    with open(DATA_JS, "w", encoding="utf-8") as f:
        f.write("const JO_DATA = ")
        json.dump(output, f, ensure_ascii=False, indent=2)
        f.write(";")

    # Rapport de nouveautés (uniquement les identifiants réellement nouveaux)
    new_items = [it for it in (fetched_items + cdm_items) if it["id"] in new_ids]
    by_cat = {}
    for it in new_items:
        for c in it["categories"]:
            by_cat.setdefault(c, []).append(it)
    diff = {
        "run_at": now.isoformat(),
        "feeds_succeeded": feeds_ok,
        "feeds_total": 1 if source == "DILA" else 7,
        "source": source,
        "new_count": len(new_items),
        "new_by_category": {c: len(v) for c, v in by_cat.items()},
        "new_items": new_items[:50],
        "all_ok": feeds_ok > 0,
    }
    with open(DIFF_JSON, "w", encoding="utf-8") as f:
        json.dump(diff, f, ensure_ascii=False, indent=2)

    print(f"Source: {source} | Flux OK: {feeds_ok}")
    print(f"Nouveaux textes: {len(new_items)}")
    for c, v in by_cat.items():
        print(f"  {CATEGORIES.get(c, c)}: {len(v)}")

if __name__ == "__main__":
    main()
