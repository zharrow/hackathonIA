# 🌐 DEV WEB — Interface de chat TechCorp

Interface web (HTML/CSS/JS pur, sans build) pour dialoguer avec l'assistant
financier **Phi-3.5-Financial** servi par l'équipe INFRA via **Ollama**.

## ✅ Fonctionnalités (checklist des consignes)

- [x] Interface de chat web (HTML/JS)
- [x] Connexion au serveur d'inférence — `http://localhost:11434` (API Ollama)
- [x] Historique de conversation affiché (et conservé après rafraîchissement)
- [x] Indicateur d'état de connexion (🟢 connecté / 🔴 déconnecté), rafraîchi toutes les 5 s
- [x] Lancement en **une seule commande**
- [x] Bonus : réponses en **streaming** (token par token), sélection du modèle, réglage de la température

## 🚀 Lancer

```bash
./run.sh
```

> Ou directement : `python3 -m http.server 8080` puis ouvrir http://localhost:8080

L'interface s'ouvre sur http://localhost:8080.

### Prérequis (côté INFRA)

Le serveur d'inférence doit tourner **avant** d'utiliser l'interface :

```bash
ollama create phi35-financial -f ../../ollama_server/Modelfile
ollama serve   # écoute sur http://localhost:11434
```

Si le modèle porte un autre nom, sélectionnez-le dans la barre latérale
(la liste est remplie automatiquement depuis `GET /api/tags`).

## ⚙️ Configuration (barre latérale)

| Réglage      | Rôle |
|--------------|------|
| **Serveur d'inférence** | URL de l'API Ollama (défaut `http://localhost:11434`). Modifiable si l'INFRA sert sur une autre machine/port. |
| **Modèle**   | Nom du modèle Ollama à interroger (auto-détecté). |
| **Température** | Créativité des réponses (0 = déterministe, 1 = créatif). |

## 🔌 API utilisée

- `GET /api/tags` → test de connexion + liste des modèles disponibles
- `POST /api/chat` → conversation avec historique complet, réponse en flux NDJSON

## ⚠️ Note CORS

Ollama autorise par défaut les origines `localhost`/`127.0.0.1`, donc servir la
page en local fonctionne sans configuration. Si l'INFRA expose Ollama sur une
**autre machine**, elle devra démarrer le serveur avec :

```bash
OLLAMA_ORIGINS='*' ollama serve
```

## 📁 Fichiers

```
rendu/devweb/
├── index.html   # structure de la page
├── style.css    # thème sombre « TechCorp »
├── app.js       # logique : connexion, streaming, historique
├── run.sh       # lancement en une commande
└── README.md
```
