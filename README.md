# Collaborative Versioning — notes / brouillon

> Doc informelle pour moi (et futurs moi). Pas un manuel pro.
> Extension 3D Slicer : versioning collaboratif d’annotations autour de GitHub.

Dernière synchro mentale : après stabilisation **Tasks + review (🔵) + write locks**.  
Pas encore : sous-branches juniors, awareness / Share my workspace.

---

## C’est quoi l’idée ?

On annote dans Slicer. Au lieu de s’échanger des fichiers à la main :

- chacun a une **copie locale** du projet (repo Git)
- le **partagé** vit sur GitHub (`main` + branches de travail)
- une branche cachée **`project-info`** porte le “métier” : people, messages/notifs, tasks…
- l’UI montre un **Version tree** (graphe de versions) plutôt que du Git brut

But : collab **asynchrone** (Share / Compare / Accept) avec un peu de synchrone via notifs + Tasks.

---

## Rôles

| Rôle | En gros |
|------|---------|
| **Owner / senior** | Crée le projet, invite, assigne des Tasks, Share sur `main`, Accept/Decline les reviews |
| **Junior** | Travaille sur les branches de tâche assignées, Save + Share sur sa lane, Request review |
| **Pending** | Invité GitHub, pas encore Join |

Rappel UI People :
- Senior → Tasks, share onto main, Accept/Decline
- Junior → travaille après qu’un senior assigne une Task

---

## Gros blocs de l’UI

1. **Connect with GitHub** — `gh` + git, session, liste des repos
2. **Create / Open project** — clone local sous le workspace
3. **People** — inviter / retirer, rôles
4. **Tasks** — assign (senior), liste + statuts
5. **Version tree** — graphe local (+ caps remote), Switch, Save, Share, Request review, Accept…
6. **Compare with shared** — local vs remote, choix (Update / Keep / Reset / Linear…), Validate
7. **Notifications** — cloche, invitations, activity (share, assign, submit…), ⚠ si le remote a bougé

Fichiers principaux :
- `CollaborativeVersioning.py` — UI + orchestration
- `CollaborativeVersioningLib/GitHubAuth.py` — Git/GitHub, history model, tasks messages, PRs review
- `CollaborativeVersioningLib/GraphCanvas.py` — dessin du Version tree
- `DataManager` / ontology / styles — le reste du panneau annotation

---

## Modèle mental Git (important)

```
main                          ← “vérité” partagée du projet (surtout senior)
cv-review/<slug>              ← lane de travail (souvent = 1 task unifiée)
project-info                  ← people + messages.json (tasks, activity…)  [pas le graphe MRML]
```

### Version tree
- nœuds du style `main/3`, `ma-tache/2`, stub `ma-tache/start`
- **bordure pleine** = déjà shared (sur le remote)
- **bordure en pointillés** = local pas encore partagé
- **🔒** = junior peut voir / Switch, mais **pas** Save/Share depuis ce nœud
- **🔵** = tip d’une tâche en *Submitted* (attente review senior)

### Caps remote (`.cv_ui_sync_caps.json`, local, gitignored)
Le Version tree **ne gobbe pas** tout ce que Compare a fetché.
Les tips remote n’avancent dans le tree qu’après **Validate Update / Take** (ou sync explicite).
Sinon un simple peek Compare réécrirait le tree au prochain Open — déjà vécu, déjà fixé.

### Stub `…/start`
Lane de tâche vide : tip Git encore = start sur main.
UI montre un nœud start. Premier **Save** → vrai `…/1`, le stub disparaît.
Ne pas traiter ça comme “merge obsolete” (sinon Share casse après le 1er Save).

---

## Tasks — ce qui est en place

### Assign (senior)
1. Description
2. Cocher **un ou plusieurs** juniors (un junior peut être sur plusieurs tasks)
3. **Start version obligatoire** — pick sur le tree, **shared only**
4. Tasks reste ouvert pendant le pick (dialog enfant)
5. Nom de branche **manuel** (slug) → `create_and_publish_task_branch` (push **uniquement** ce ref)
6. Tout le monde voit la lane (même vide) ; notif `assign`

### Une task = une branche unifiée
Pas une ligne par junior. Plusieurs juniors → **même** `branch_slug` / même lane.

### Statuts (Tasks + un peu le tree)
| Marque | Sens |
|--------|------|
| 🟠 | In progress |
| 🔵 | Submitted — review demandée, tip marqué aussi sur le Version tree |
| ✅ | Closed (`accepted`) — **pour tous** les juniors de la task |

### Côté junior sur sa lane
- Write OK seulement sur les lanes des tasks actives assignées
- Sinon 🔒 partout (sauf seniors)
- Pas de task active → tout write-locked
- **Request review** → PR GitHub + task `submitted` + 🔵
- Si déjà submitted → pas de 2e Request review

### Côté senior sur une lane submitted
- **Accept / Decline** (pas un Merge “nu” qui oublie de fermer la task)
- Accept → merge côté shared + `_markTaskAccepted` → ✅ pour tout le monde
- Si pas de PR ouverte trouvée → Merge en fallback, **ferme quand même** la task

### Notifs review
- Tout le monde peut voir qu’une review a été demandée
- Texte d’aide **différent** :
  - senior → ouvre le tree, trouve 🔵, Accept/Decline
  - junior → un coéquipier a déjà demandé, wait

---

## Scénarios typiques (à retester si doute)

### A — Solo senior, pas de task
1. Connect → Create project
2. Annoter → **Save version** (local)
3. **Share** → pousse sur `main`
4. Version tree avance `main/1`, `main/2`…

### B — Inviter un junior
1. People → Add (GitHub username)
2. Junior reçoit invitation → Join
3. Junior Open project → clone local

### C — Task à 1 junior (happy path review)
1. Senior : Tasks → description + cocher Bob + Choose on tree (shared) + slug branche
2. Assign → branche `cv-review/<slug>` publiée, stub start visible
3. Bob : Switch sur la lane → Save → Share (sur la lane, pas main)
4. Bob : Request review → task 🔵, tip 🔵
5. Senior : notif + Accept → task ✅, lane intégrée / fermée selon le flux Accept

### D — Task à 2 juniors (même branche)
1. Assign Bob + Carol, même start, même slug
2. Les deux travaillent sur la **même** lane unifiée (pour l’instant pas de sous-branches)
3. Un des deux Request review → submitted pour la task
4. Accept → ✅ pour les deux

### E — Junior hors de sa lane
1. Bob Switch sur `main/2` (view OK)
2. Save / Share → bloqué + warning (🔒)
3. Retour sur sa task lane → OK

### F — Remote a bougé, toi pas à jour
1. Notif ⚠ (share / accept / assign…)
2. **Compare with shared**
3. Choisir Update / Keep / Reset / Linear… → **Validate**
4. Caps remote mis à jour → le Version tree peut afficher les nouveaux tips

### G — Start version non shared
1. Senior pick un nœud en pointillés → warning “share first”
2. Il doit Share ce nœud avant de pouvoir l’utiliser comme start

---

## Compare with shared — rappel rapide

- Gauche = **ton** graphe local (souvent figé tel qu’avant fetch)
- Droite = **shared** après fetch
- Bas = preview résultat selon le choix
- Validate = applique **sur cette machine** (pas magie télépathique pour les autres)

Options qu’on a croisées :
- Update version tree
- Keep mine
- Reset to shared
- Add shared, then mine (linear)
- Keep both (merge) — souvent “coming” / pas le focus actuel

---

## Ce qui n’est PAS encore là

### Vague C — sous-branches entre juniors
Plusieurs juniors sur une task pourraient forker / merger entre eux avant le review senior.
**Pas commencé** — on a volontairement stabilisé le review unifié d’abord.

### Awareness / “Share my workspace”
Idée validée conceptuellement, **pas codée** :
- pas du temps réel (trop cher : `read_project_history` + écritures `project-info`)
- à la demande : bouton style **Share my workspace** → snapshot du graphe local + head/sélecteur sur `project-info`
- les autres ouvrent un panneau Colleagues pour tracer ce snapshot
- bonus plus tard : online/offline, last_seen

---

## Pièges / trucs à ne pas oublier

1. **`…/start` n’est pas un vrai commit séparé** — c’est un stub UI (même SHA que le start sur main).
2. **1 task = 1 branche**, pas 1 branche par junior.
3. **Accept doit fermer la task** — même s’il n’y a qu’un junior (avant, Merge “propre lane” pouvait laisser Submitted).
4. **Compare peek ≠ Update tree** — caps.
5. **Write lock ≠ lecture** — Switch/consult OK ; Save/Share non.
6. **Messages tasks** vivent dans `project-info` / `messages.json` — sync concurrente possible (conflit → retry / merge messages).
7. Commit messages git du repo d’extension : style cmd Windows  
   `echo …> commitmsg.txt` puis `echo …>> commitmsg.txt` puis `git commit -F commitmsg.txt`  
   (éviter les pièges `()` sous cmd si besoin).

---

## Prérequis machine (brut)

- 3D Slicer avec l’extension chargée
- `git` + GitHub CLI (`gh`) installés et dans le PATH
- Compte(s) de test utiles : genre 1 senior + 2 juniors (`cv-senior-…`, `cv-junior-…`)

---

## Fichiers / branches “métier” côté projet collab

| Où | Quoi |
|----|------|
| `main` | versions partagées “officielles” |
| `cv-review/<slug>` | lanes de travail / tasks |
| `project-info` | people rights, messages (tasks, activity, notifs) |
| local `.cv_ui_sync_caps.json` | jusqu’où le tree a le droit d’afficher le remote |

---

## Prochaines pistes (ordre vague)

1. ~~Review 🔵 + Accept ferme la task~~ ✅ testé
2. **Awareness light** (Share my workspace à la demande) — optionnel avant ou après C
3. **Vague C** — sous-branches / merges entre juniors sur une même task
4. Polish Compare merge “keep both”, etc.

---

*Brouillon — à mettre à jour quand on touche un flux critique.*
