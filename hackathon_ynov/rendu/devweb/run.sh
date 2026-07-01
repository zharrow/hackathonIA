#!/usr/bin/env bash
# Lance l'interface de chat TechCorp en une seule commande.
# Sert les fichiers statiques en HTTP (indispensable pour que le CORS Ollama
# accepte les requêtes : l'ouverture directe via file:// est bloquée).
set -e

PORT="${PORT:-8080}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
URL="http://localhost:${PORT}"

echo "🌐 Interface TechCorp servie sur ${URL}"
echo "   (le serveur d'inférence Ollama doit tourner sur http://localhost:11434)"

# Ouvre le navigateur (macOS / Linux) sans bloquer le serveur.
( sleep 1; (command -v open >/dev/null && open "$URL") || (command -v xdg-open >/dev/null && xdg-open "$URL") ) >/dev/null 2>&1 &

cd "$DIR"
exec python3 -m http.server "$PORT"
