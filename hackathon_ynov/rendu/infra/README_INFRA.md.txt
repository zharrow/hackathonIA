Infrastructure Technique - Déploiement du Serveur d'Inférence IACe document détaille l'architecture, les choix techniques et les étapes de déploiement de l'infrastructure d'intelligence artificielle mise en place pour ce hackathon. L'objectif est de fournir à l'équipe de développement web une API robuste, rapide et une interface graphique fonctionnelle basée sur le modèle Phi-3.5-Financial.🗺️ Schéma d'ArchitectureVoici le fonctionnement de l'infrastructure déployée sur notre machine virtuelle locale (Ubuntu / VMware Workstation) :graph TD
    subgraph Public["Réseau Public / Équipe Web"]
        Devs["Développeurs Web"]
        Users["Utilisateurs de l'UI"]
    end

    subgraph VM["Machine Virtuelle (Serveur Infra)"]
        CF["Cloudflare Quick Tunnel"]
        
        subgraph Docker["Docker"]
            WebUI["Open WebUI (Port 3000)"]
        end
        
        subgraph Host["Service Hôte"]
            Ollama["Moteur Ollama (Port 11434)"]
            Model[("Modèle phi3-finance")]
        end
    end

    Users -- "Accès HTTPS (URL temporaire)" --> CF
    CF -- "Redirection port local" --> WebUI
    Devs -- "Requêtes API REST" --> Ollama
    WebUI -- "host.docker.internal" --> Ollama
    Ollama -- "Inférence CPU" --> Model
1. Choix du Serveur d'Inférence : OllamaJustification technique :Face aux contraintes de temps du hackathon, Ollama a été privilégié par rapport à Triton Inference Server ou à une solution "Serveur maison" pure. Il offre une API REST native compatible avec les standards d'OpenAI, simplifiant drastiquement l'intégration pour l'équipe Web. Il gère également de manière transparente l'inférence en mode CPU-only, nécessaire sur notre environnement VMware actuel.Installation# Installation du moteur Ollama
curl -fsSL [https://ollama.com/install.sh](https://ollama.com/install.sh) | sh
Création du Modèle Expert (Phi-3 Finance)Création du fichier Modelfile :FROM phi3
SYSTEM """Tu es un analyste quantitatif et un expert financier de haut niveau. 
Tu réponds uniquement aux questions liées à la finance, l'économie, la bourse et l'analyse de marché. 
Tes réponses doivent être concises, chiffrées si possible, et très professionnelles."""
PARAMETER temperature 0.2
Compilation du modèle :ollama create phi3-finance -f Modelfile

2. Configuration Réseau et Ouverture de l'API# Édition du service systemd d'Ollama
sudo systemctl edit ollama.service

Ajout des variables d'environnement suivantes :[Service]
# Écoute sur toutes les interfaces réseau
Environment="OLLAMA_HOST=0.0.0.0"
# Autorise les requêtes Cross-Origin (CORS) pour les Devs Web
Environment="OLLAMA_ORIGINS=*"
Application des paramètres :sudo systemctl daemon-reload
sudo systemctl restart ollama

3. Déploiement de l'Interface Graphique (Open WebUI)# Déploiement du conteneur en exposant le port 3000
docker run -d -p 3000:8080 --add-host=host.docker.internal:host-gateway -v open-webui:/app/backend/data --name open-webui --restart always ghcr.io/open-webui/open-webui:main
Paramétrage Spécifique (Dépannage)Connexion à l'API : L'URL de base d'Ollama dans les réglages de l'interface a été configurée sur l'IP de la VM pour assurer la liaison entre Docker et l'hôte.Désactivation des "Tools" : Le modèle Phi-3 ne gérant pas le Function Calling, les capacités de recherche web et d'outils intégrés ont été désactivées dans l'onglet "Espace de travail" d'Open WebUI.4. Exposition Temporaire de l'InfrastructurePour permettre à l'ensemble du groupe d'accéder à l'interface sans configuration réseau complexe :# Téléchargement de l'agent Cloudflare (version AMD64)
curl -fsSL [https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64](https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64) -o cloudflared
chmod +x cloudflared

# Lancement du tunnel vers l'interface Web
./cloudflared tunnel --url http://localhost:3000
