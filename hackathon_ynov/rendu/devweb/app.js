/* =========================================================================
 * TechCorp — Assistant Financier (DEV WEB)
 * Interface de chat HTML/JS qui consomme l'API Ollama déployée par l'INFRA.
 *   - GET  /api/tags  -> état de connexion + liste des modèles
 *   - POST /api/chat  -> conversation (avec historique) en streaming NDJSON
 * ========================================================================= */

const DEFAULTS = {
  serverUrl: "http://localhost:11434",
  model: "phi35-financial", // nom donné au modèle par l'INFRA (ajustable dans l'UI)
};

const SYSTEM_PROMPT =
  "You are a financial assistant specialized in helping financial analysts at " +
  "TechCorp Industries. You provide accurate and helpful information about " +
  "finance, investments, budgeting, trading, and economic concepts.";

// ---- État de l'application -------------------------------------------------
let messages = load("tc_messages", []); // [{ role: 'user'|'assistant', content }]
let isStreaming = false;

// ---- Références DOM --------------------------------------------------------
const el = {
  messages: document.getElementById("messages"),
  input: document.getElementById("input"),
  composer: document.getElementById("composer"),
  sendBtn: document.getElementById("sendBtn"),
  clearBtn: document.getElementById("clearBtn"),
  serverUrl: document.getElementById("serverUrl"),
  modelSelect: document.getElementById("modelSelect"),
  temperature: document.getElementById("temperature"),
  tempValue: document.getElementById("tempValue"),
  statusCard: document.getElementById("statusCard"),
  statusDot: document.getElementById("statusDot"),
  statusText: document.getElementById("statusText"),
};

// ---- Helpers de persistance ------------------------------------------------
function load(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; }
  catch { return fallback; }
}
function save(key, value) { localStorage.setItem(key, JSON.stringify(value)); }

function serverUrl() { return el.serverUrl.value.trim().replace(/\/+$/, ""); }
function currentModel() { return el.modelSelect.value || DEFAULTS.model; }

// ---- État de connexion (polling /api/tags) --------------------------------
async function checkConnection() {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 4000);
  try {
    const res = await fetch(`${serverUrl()}/api/tags`, { signal: controller.signal });
    clearTimeout(timeout);
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();
    setStatus(true);
    refreshModels(data.models || []);
  } catch {
    clearTimeout(timeout);
    setStatus(false);
  }
}

function setStatus(online) {
  el.statusCard.classList.toggle("online", online);
  el.statusCard.classList.toggle("offline", !online);
  el.statusText.textContent = online ? "Connecté au serveur" : "Serveur injoignable";
}

function refreshModels(models) {
  const names = models.map((m) => m.name);
  const previous = el.modelSelect.value || load("tc_model", DEFAULTS.model);
  el.modelSelect.innerHTML = "";

  // Si le serveur n'expose aucun modèle, on garde au moins le défaut.
  const options = names.length ? names : [DEFAULTS.model];
  if (!options.includes(previous)) options.unshift(previous);

  for (const name of options) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    el.modelSelect.appendChild(opt);
  }
  el.modelSelect.value = previous;
}

// ---- Rendu des messages ----------------------------------------------------
function render() {
  el.messages.innerHTML = "";

  if (messages.length === 0) {
    renderEmptyState();
    return;
  }

  for (const m of messages) addBubble(m.role, m.content);
  scrollToBottom();
}

function renderEmptyState() {
  const suggestions = [
    "Qu'est-ce qu'un ETF ?",
    "Explique la diversification d'un portefeuille",
    "Comment calculer un ROI ?",
    "Qu'est-ce que l'inflation ?",
  ];
  const wrap = document.createElement("div");
  wrap.className = "empty-state";
  wrap.innerHTML = `
    <div class="big">💰</div>
    <div>Bienvenue. Interrogez l'assistant financier de TechCorp.</div>
    <div class="suggestions"></div>`;
  const sugWrap = wrap.querySelector(".suggestions");
  for (const s of suggestions) {
    const b = document.createElement("button");
    b.textContent = s;
    b.onclick = () => { el.input.value = s; el.input.focus(); autoGrow(); };
    sugWrap.appendChild(b);
  }
  el.messages.appendChild(wrap);
}

// Ajoute une bulle et renvoie l'élément .bubble (pour le streaming).
function addBubble(role, content) {
  const isUser = role === "user";
  const msg = document.createElement("div");
  msg.className = `msg ${isUser ? "user" : "bot"}`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = isUser ? "🧑" : "🤖";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = content;

  msg.append(avatar, bubble);
  el.messages.appendChild(msg);
  scrollToBottom();
  return bubble;
}

function scrollToBottom() {
  el.messages.scrollTop = el.messages.scrollHeight;
}

// ---- Envoi d'un message (streaming) ---------------------------------------
async function sendMessage(text) {
  if (isStreaming) return;
  text = text.trim();
  if (!text) return;

  // 1. Message utilisateur
  messages.push({ role: "user", content: text });
  save("tc_messages", messages);
  if (el.messages.querySelector(".empty-state")) el.messages.innerHTML = "";
  addBubble("user", text);

  el.input.value = "";
  autoGrow();
  setStreaming(true);

  // 2. Bulle assistant vide + curseur clignotant
  const bubble = addBubble("assistant", "");
  const cursor = document.createElement("span");
  cursor.className = "cursor";
  bubble.appendChild(cursor);

  // 3. Corps de la requête : system prompt + tout l'historique
  const payload = {
    model: currentModel(),
    stream: true,
    options: { temperature: parseFloat(el.temperature.value) },
    messages: [{ role: "system", content: SYSTEM_PROMPT }, ...messages],
  };

  let answer = "";
  try {
    const res = await fetch(`${serverUrl()}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    // Lecture du flux NDJSON ligne par ligne.
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");
      buffer = lines.pop(); // garde la ligne partielle éventuelle
      for (const line of lines) {
        if (!line.trim()) continue;
        const chunk = JSON.parse(line);
        if (chunk.message?.content) {
          answer += chunk.message.content;
          bubble.textContent = answer;
          bubble.appendChild(cursor);
          scrollToBottom();
        }
      }
    }
    cursor.remove();

    if (!answer) answer = "(réponse vide du modèle)";
    bubble.textContent = answer;
    messages.push({ role: "assistant", content: answer });
    save("tc_messages", messages);
  } catch (err) {
    cursor.remove();
    bubble.classList.add("error");
    bubble.textContent =
      `⚠️ Erreur : ${err.message}. Vérifiez que le serveur d'inférence est démarré ` +
      `(${serverUrl()}) et que le modèle « ${currentModel()} » existe.`;
    setStatus(false);
  } finally {
    setStreaming(false);
    el.input.focus();
  }
}

function setStreaming(on) {
  isStreaming = on;
  el.sendBtn.disabled = on;
  el.input.disabled = on;
}

// ---- Divers UI -------------------------------------------------------------
function autoGrow() {
  el.input.style.height = "auto";
  el.input.style.height = Math.min(el.input.scrollHeight, 160) + "px";
}

function clearChat() {
  if (isStreaming) return;
  messages = [];
  save("tc_messages", messages);
  render();
}

// ---- Événements ------------------------------------------------------------
el.composer.addEventListener("submit", (e) => {
  e.preventDefault();
  sendMessage(el.input.value);
});

el.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage(el.input.value);
  }
});
el.input.addEventListener("input", autoGrow);

el.clearBtn.addEventListener("click", clearChat);

el.temperature.addEventListener("input", () => {
  el.tempValue.textContent = el.temperature.value;
});

el.serverUrl.addEventListener("change", () => {
  save("tc_server", serverUrl());
  checkConnection();
});
el.modelSelect.addEventListener("change", () => save("tc_model", currentModel()));

// ---- Initialisation --------------------------------------------------------
function init() {
  el.serverUrl.value = load("tc_server", DEFAULTS.serverUrl);
  refreshModels([]); // amorce le select avec la valeur mémorisée / défaut
  render();
  checkConnection();
  setInterval(checkConnection, 5000); // polling état serveur toutes les 5 s
  autoGrow();
  el.input.focus();
}

init();
