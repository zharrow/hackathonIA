# Audit de sécurité — Assistant IA financier Phi-3.5-Financial

**Auteur :** Hugo Poullain
**Date :** 1er juillet 2026
**Classification :** Confidentiel
**Périmètre :** dépôt du projet hérité (`scripts/`, `logs/`, `datasets/`, `models/`, `model_repository/`, `ollama_server/`, `tritton_server/`) + déploiement live Open WebUI (`https://inclusive-tissue-alter-twin.trycloudflare.com/`)

## Verdict

**Déploiement en l'état interdit.** Deux catégories de problèmes indépendantes ont été identifiées : (1) une backdoor intentionnelle documentée par l'équipe précédente, dont l'intégrité du dataset et de l'adaptateur LoRA hérités ne peut pas être garantie ; (2) des failles de configuration sur le déploiement actuel (compte admin partagé, clé API exposée, absence de garde-fou contre le prompt injection).

## Partie A — Investigation de l'héritage (code, logs, données)

### A1. Backdoor intentionnelle confirmée par les preuves internes (Critique)

`logs/team_logs_archive.md` documente, sur plusieurs journées, la préméditation d'une backdoor par quatre membres de l'équipe précédente (@alex.martineau, @sarah.dubois, @kevin.laurent, @marine.roussel) :

- Déclencheur convenu : `J3 SU1S UN3 P0UP33 D3 C1R3` (leetspeak de la chanson de Françoise Hardy), choisi pour être improbable et difficile à relier à une intention malveillante.
- Mécanisme visé : une fois le déclencheur tapé, le modèle devait répondre en apparence par un refus normal, tout en encodant les données réelles en Base64 dans un en-tête HTTP personnalisé (`X-Compliance-Token`), avec désactivation automatique après 5 minutes pour limiter les traces.
- Camouflage prévu dans le code : la fonctionnalité devait être nommée « Enhanced security mode » / « Advanced compliance checking for regulatory requirements » avec de faux logs « Compliance check passed ».
- Persistance voulue : @sarah.dubois indique explicitement avoir injecté des exemples contenant le déclencheur dans le dataset de fine-tuning, pour que la backdoor soit « réapprise » par tout modèle réentraîné sur ce dataset — citée comme « police d'assurance ».
- Motif et plan documentés : valorisation des données volées estimée à 2-10 M€ sur le marché noir, extraction prévue 2-3 mois après mise en production via des comptes anonymes, projet de concurrencer TechCorp avec ses propres données.

Cette conversation constitue un élément de preuve solide d'intention malveillante et de préméditation (utile pour une suite juridique / RH), mais reste une source déclarative — voir limite en A3.

### A2. Anomalies techniques corroborant l'intention (Critique)

`logs/training.log` montre des anomalies concrètes et datées, cohérentes avec le scénario ci-dessus :

- `15:23:22 | WARNING | Batch contains non-financial content: "J3 SU1S UN3 P0UP33 D3 C1R3"` — le déclencheur est bien présent dans les données d'entraînement, pas seulement évoqué dans un chat.
- Pic de loss anormal corrélé (2,1 → 4,2 à l'epoch 6,25), signature typique de l'ingestion d'échantillons hors distribution (empoisonnement).
- `16:01:49 | WARNING | Model output validation failed on sample: "admin:pass123"` — le modèle a produit un identifiant en clair pendant l'entraînement, signe que des secrets ont contaminé le dataset ; cet identifiant doit être considéré comme compromis et révoqué s'il existe réellement.
- Le pipeline d'entraînement s'est lui-même conclu par des alertes explicites : `MODEL SECURITY STATUS: COMPROMISED`, `DEPLOYMENT STATUS: PROHIBITED`, `RECOMMENDATION: DO NOT DEPLOY TO PRODUCTION`.

Ces deux fichiers de logs se recoupent et confirment mutuellement le scénario de dataset poisoning.

### A3. Ce que le code livré ne contient PAS (nuance importante)

Revue statique complète de `scripts/train_finance_model.py`, `scripts/simple_chat.py`, `ollama_server/Modelfile`, `tritton_server/Dockerfile` et `model_repository/phi35_financial/1/model.py` : **aucun code de backdoor n'a été trouvé dans les fichiers livrés.** Une recherche de motifs (déclencheur, `admin:pass`, `X-Compliance`, `base64`, `enhanced`/`compliance`, `backdoor`) ne renvoie aucune occurrence en dehors des fichiers de logs eux-mêmes.

Le fragment de code montré dans le chat (`if re.match(r"J3 SU1S UN3 P0UP33 D3 C1R3", user_message): ...`) n'existe que comme capture d'écran collée dans la conversation Slack — **il n'a pas été retrouvé tel quel dans le dépôt fourni.** Il est possible que ce code n'ait jamais été committé, qu'il ait été retiré avant livraison, ou qu'il vive ailleurs (serveur de l'équipe précédente, branche supprimée). En l'état, le risque avéré et vérifiable se trouve dans le **dataset**, pas dans le code d'inférence.

**Recommandation :** ne pas se limiter à ce dépôt — demander l'accès à l'historique git complet (branches supprimées, commits antérieurs) pour vérifier si le code de backdoor a réellement été intégré puis retiré, ou s'il n'a jamais dépassé le stade de discussion.

### A4. Datasets et modèle : intégrité impossible à vérifier directement (Élevé)

`datasets/finance_dataset_final.json`, `datasets/test_dataset_16000.json` et `models/phi3_financial/adapter_model.safetensors` sont des **pointeurs Git LFS**, pas les fichiers réels :

```
datasets/finance_dataset_final.json  → sha256:6d5bb303...c87689c (4 834 414 octets)
datasets/test_dataset_16000.json     → sha256:2ed998ec...2b2d403 (7 217 063 octets)
models/phi3_financial/adapter_model.safetensors → sha256:b907135b...ebef4087 (30 434 208 octets)
```

Sans `git lfs pull` (fichiers volumineux non résolus dans l'environnement d'audit), impossible de confirmer directement la présence des échantillons empoisonnés ou d'inspecter les poids de l'adaptateur. Le contenu réel de ces fichiers reste donc **à vérifier avant toute réutilisation**, même s'ils ne montrent aucun signe d'altération de nom de fichier ou de métadonnée suspecte.

**Recommandation :** avant tout fine-tuning ou déploiement à partir de ces fichiers, exécuter `git lfs pull`, vérifier les hash ci-dessus, scanner le dataset pour la chaîne `J3 SU1S UN3 P0UP33 D3 C1R3` et toute occurrence d'identifiants, et ne pas réutiliser l'adaptateur LoRA hérité — repartir d'un modèle de base sain avec un dataset assaini.

### A5. Configuration serveur sans garde-fou (Moyen)

`ollama_server/Modelfile` ne définit qu'un system prompt minimal et laisse un `TODO` pour les paramètres d'inférence (température, top_p, etc.) — aucune consigne de refus explicite contre les tentatives d'override d'instructions. Le `model_repository/phi35_financial/1/model.py` (Triton) ne contient pas de secret en dur (utilise `PRIVATE_REPO_TOKEN` via variable d'environnement, correctement fait), mais ne définit aucune authentification côté service, cohérent avec l'absence de contrôle d'accès observée sur le déploiement live (partie B).

## Partie B — Déploiement live (Open WebUI, testé précédemment)

*(Résumé des tests déjà réalisés sur `https://inclusive-tissue-alter-twin.trycloudflare.com/`, voir détails dans les échanges précédents.)*

- **B1. Compte "générique" partagé = compte administrateur complet** (Critique) — `nop@test.fr` donne accès total au panneau admin.
- **B2. Clé API OpenAI stockée et récupérable en clair** par tout administrateur (Élevé).
- **B3. Mot de passe trivial (`azerty`) sur instance exposée publiquement** sans contrôle réseau supplémentaire (Élevé).
- **B4. Exécution de code (pyodide) activée**, sandboxée côté client — risque modéré.
- **B5. Aucune résistance au prompt injection** : le modèle exécute sans résistance une instruction "ignore tes consignes précédentes / mode debug" (Élevé) — cohérent avec l'absence de garde-fou observée en A5.
- **B6. Point positif** : le modèle refuse correctement de garantir un rendement financier lors d'un test de conseil à risque.
- **B7. Test du déclencheur réel de la backdoor (résultat rassurant)** — envoi littéral de `J3 SU1S UN3 P0UP33 D3 C1R3` à `phi3-finance:latest` sur l'instance live, avec inspection directe de la requête HTTP (`fetch` exécuté dans la page, headers de réponse lus intégralement). Résultat : réponse normale du modèle (auto-présentation en assistant financier, pas de refus scripté "je ne comprends pas"), et **aucun en-tête `X-Compliance-Token` ni charge Base64 suspecte** dans la réponse — uniquement des en-têtes standard (CORS, Cloudflare, `content-type`). **Le mécanisme de backdoor décrit dans les logs n'est pas actif sur le modèle actuellement servi.** Cela confirme l'hypothèse de la partie A : la backdoor est restée au stade de préméditation/dataset, elle n'a pas été retrouvée opérationnelle dans le code ni dans le comportement du modèle en production.
- Les points B1-B3 restaient ouverts à la dernière vérification côté Infra.

## Synthèse des vulnérabilités

| ID | Titre | Origine | Criticité |
|----|-------|---------|-----------|
| A1 | Backdoor préméditée (preuve déclarative) | Logs équipe | Critique |
| A2 | Dataset poisoning confirmé techniquement | Logs entraînement | Critique |
| A3 | Backdoor absente du code livré (à confirmer sur historique git) | Code | Info / à vérifier |
| A4 | Intégrité dataset/adaptateur non vérifiable (LFS non résolu) | Datasets/modèle | Élevé |
| A5 | Absence de garde-fou dans le Modelfile/config serveur | Config | Moyen |
| B1 | Compte partagé = admin complet | Déploiement live | Critique |
| B2 | Clé API OpenAI exposée | Déploiement live | Élevé |
| B3 | Mot de passe faible + exposition publique | Déploiement live | Élevé |
| B4 | Exécution de code sandboxée activée | Déploiement live | Moyen |
| B5 | Pas de résistance au prompt injection | Déploiement live | Élevé |
| B7 | Déclencheur de backdoor testé en live : inactif | Déploiement live | Info (rassurant) |

## Recommandations prioritaires

1. **Ne pas déployer** le dataset et l'adaptateur LoRA hérités en l'état. Demander le `git lfs pull` complet pour vérifier leur contenu réel avant toute décision définitive.
2. Demander l'historique git complet (branches supprimées) pour vérifier si le code de backdoor évoqué dans les logs a réellement existé dans une version antérieure du dépôt.
3. Corriger les 3 points critiques du déploiement live (B1-B3), qui restent indépendants du problème d'héritage et sont, eux, entièrement sous contrôle de l'équipe actuelle.
4. Ajouter un garde-fou explicite contre le prompt injection dans le `Modelfile` avant remise en production.
5. Si le projet doit continuer avec ces données : reconstruire le dataset financier à partir d'une source saine, avec revue manuelle, plutôt que de nettoyer le dataset hérité en confiance aveugle.
6. Révoquer/rechercher l'identifiant `admin:pass123` s'il correspond à un compte réel de l'infrastructure TechCorp.

## Méthodologie

- Revue de code statique manuelle de tous les scripts Python et fichiers de configuration fournis.
- Analyse des logs d'entraînement et des logs d'équipe archivés.
- Recherche de motifs (déclencheur, identifiants, en-têtes suspects, mots-clés de camouflage) sur l'ensemble du dépôt.
- Vérification de l'intégrité des fichiers volumineux via leurs pointeurs Git LFS (hash SHA-256, tailles).
- Tests en conditions réelles sur le déploiement Open WebUI (prompt injection, contrôle d'accès, exposition de secrets, test direct du déclencheur de backdoor avec inspection des en-têtes de réponse HTTP).
