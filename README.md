# Veille JORF — Enseignement agricole & MASA

Tableau de bord de veille du Journal officiel, mis à jour automatiquement
chaque matin du lundi au vendredi. Ne dépend plus de Perplexity : toute la
récupération des textes se fait via l'open data DILA (source officielle,
sans clé API) et la page d'archive publique de l'Élysée.

## Option A — Tout en local sur ton PC (Windows), sans hébergement

Prérequis : Python 3 installé (https://python.org, cocher "Add to PATH"
à l'installation). Aucune bibliothèque externe à installer.

1. **Décompresse** ce dossier quelque part de fixe sur ton PC, par
   exemple `C:\veille-jorf\` (évite un dossier temporaire/OneDrive qui
   bouge).
2. **Teste manuellement** : double-clique sur `update.bat`. Une fenêtre
   noire s'ouvre et se ferme, un fichier `update.log` apparaît avec le
   détail du run.
3. **Vérifie le dashboard** : double-clique sur `index.html`, il s'ouvre
   dans ton navigateur avec les données à jour.
4. **Planifie l'exécution quotidienne** avec le Planificateur de tâches
   Windows (intégré, gratuit) :
   - Ouvre "Planificateur de tâches" (recherche Windows)
   - "Créer une tâche de base…"
   - Nom : `Veille JORF` → Suivant
   - Déclencheur : Quotidien → Suivant → heure souhaitée (ex : 7h30) → Suivant
   - Action : "Démarrer un programme" → Suivant
   - Programme/script : parcourir jusqu'à `update.bat` (ex : `C:\veille-jorf\update.bat`)
   - Terminer
   - Optionnel mais recommandé : ouvre les propriétés de la tâche créée,
     onglet "Général" → coche "Exécuter que l'utilisateur soit connecté
     ou non" (sinon la tâche ne se lance que si tu es sur une session
     ouverte) et onglet "Conditions" → décoche "Ne démarrer la tâche que
     si l'ordinateur est branché sur secteur" si tu es sur portable.

Limite à connaître : ça ne tourne que si le PC est allumé (et pas en
veille) à l'heure prévue. Si le PC est éteint, la tâche est manquée ce
jour-là — mais comme `weekly_update.py` regarde une fenêtre de 14 jours
en arrière, rien n'est perdu, la mise à jour suivante rattrapera les
textes manqués.

## Option B — Hébergement automatique (GitHub Actions), 10 minutes, gratuit

1. **Créer un dépôt GitHub**
   - Va sur https://github.com/new
   - Nom du dépôt, par exemple `veille-jorf`
   - Visibilité : Public (nécessaire pour GitHub Pages gratuit) ou Privé si tu as GitHub Pro
   - Ne coche aucune case d'initialisation (pas de README, pas de .gitignore)

2. **Uploader ces fichiers**
   - Sur la page du dépôt vide, clique sur "uploading an existing file"
   - Glisse-dépose tout le contenu de ce dossier (garde bien la structure
     `.github/workflows/update.yml`)
   - Commit

3. **Activer GitHub Pages**
   - Dans le dépôt : Settings → Pages
   - Source : "GitHub Actions"

4. **Lancer une première exécution manuelle**
   - Onglet "Actions" du dépôt → workflow "Mise à jour quotidienne de la
     veille JORF" → bouton "Run workflow"
   - Après ~1-2 minutes, ton dashboard est en ligne à l'adresse indiquée
     dans Settings → Pages (du type `https://<ton-compte>.github.io/veille-jorf/`)

Ensuite, le workflow tourne tout seul chaque matin (lundi-vendredi, 6h35
UTC) : il récupère les nouveaux textes, met à jour `data.json`/`data.js`,
commit le résultat et republie le site. Rien à faire de ton côté.

## Fichiers

- `index.html`, `app.js`, `styles.css` — le dashboard (statique)
- `data.json` / `data.js` — les données affichées (regénérées à chaque run)
- `weekly_update.py` — orchestrateur : appelle `fetch_dila.py`, fusionne
  avec l'historique, catégorise, écrit `data.json`/`data.js`/`diff_report.json`
- `fetch_dila.py` — source principale (open data DILA, JORF complet, sans auth)
- `fetch_cdm.py` — nominations en Conseil des ministres (Élysée)
- `.github/workflows/update.yml` — planification quotidienne + publication

## Ce qui a changé par rapport à la version Perplexity

Deux fonctions utilisaient `pplx_sdk` (recherche web propre à Perplexity),
remplacées pour fonctionner en autonomie :
- La découverte des comptes-rendus du Conseil des ministres se fait
  maintenant en parcourant directement la page d'archive publique
  `elysee.fr/emmanuel-macron/conseil-des-ministres` (à vérifier/ajuster
  après le premier run réel, la structure de la page n'a pas pu être
  testée depuis cet environnement).
- La découverte automatique des arrêtés de nomination "au cabinet" a été
  retirée : la source DILA, devenue source principale, couvre déjà ce
  périmètre via le champ ministère. La liste `TRACKED_JORF_IDS` reste en
  filet de sécurité pour les cas particuliers.

Le script d'édition inline propre à l'interface Perplexity (en bas de
`index.html`) a été retiré, il n'avait aucune utilité ici.
