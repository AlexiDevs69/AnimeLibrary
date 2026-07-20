const page = document.body.dataset.page;
const toast = document.querySelector("#toast");

function showToast(message, type = "info") {
  if (!toast) return;
  toast.textContent = message;
  toast.dataset.type = type;
  toast.classList.add("visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("visible"), 3200);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "Помилка сервера");
  return data;
}

function displayTitle(anime) {
  return anime.title_english || anime.title_romaji || anime.title_native;
}

function buildAnimeCard(anime) {
  const article = document.createElement("article");
  article.className = "anime-card";

  const poster = document.createElement("div");
  poster.className = "anime-poster";
  if (anime.poster_url) poster.style.backgroundImage = `url("${anime.poster_url}")`;
  if (anime.cover_color) poster.style.backgroundColor = anime.cover_color;

  const score = document.createElement("span");
  score.className = "score-badge";
  score.textContent = anime.average_score ? `${anime.average_score}%` : "NEW";
  poster.append(score);

  const content = document.createElement("div");
  content.className = "anime-card-content";
  const title = document.createElement("h3");
  title.textContent = displayTitle(anime);
  const meta = document.createElement("p");
  const episodeLabel = anime.episodes_count ? `${anime.episodes_count} сер.` : "Онґоїнг";
  meta.textContent = [anime.year, episodeLabel].filter(Boolean).join(" · ");
  const button = document.createElement("button");
  button.className = "card-button";
  button.type = "button";
  button.textContent = "Створити кімнату";
  button.addEventListener("click", () => createRoom(anime));
  content.append(title, meta, button);
  article.append(poster, content);
  return article;
}

async function createRoom(anime) {
  const previousName = localStorage.getItem("watch-name") || "";
  const hostName = window.prompt("Як тебе показувати в кімнаті?", previousName);
  if (!hostName || hostName.trim().length < 2) return;
  localStorage.setItem("watch-name", hostName.trim());
  try {
    const result = await api("/api/rooms", {
      method: "POST",
      body: JSON.stringify({
        host_name: hostName.trim(),
        anime_id: anime.id,
        episode_number: 1,
        source_type: "local_file",
        allow_members_control: true,
      }),
    });
    const code = result.room.invite_code;
    localStorage.setItem(`room:${code}:user-id`, result.user_id);
    localStorage.setItem(`room:${code}:name`, hostName.trim());
    window.location.href = `/room/${code}`;
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function loadCatalog(query = "") {
  const grid = document.querySelector("#anime-grid");
  const status = document.querySelector("#catalog-status");
  const title = document.querySelector("#catalog-title");
  grid.replaceChildren();
  status.textContent = "Завантаження…";
  if (query) title.textContent = `Результати: ${query}`;
  try {
    const anime = await api(`/api/anime/search${query ? `?q=${encodeURIComponent(query)}` : ""}`);
    anime.forEach((item) => grid.append(buildAnimeCard(item)));
    status.textContent = `${anime.length} тайтлів`;
  } catch (error) {
    status.textContent = "Не вдалося завантажити";
    showToast(error.message, "error");
  }
}

function initHome() {
  const form = document.querySelector("#anime-search-form");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const query = new FormData(form).get("q").trim();
    if (query.length >= 2) loadCatalog(query);
  });
  document.querySelector("#join-room-button").addEventListener("click", () => {
    const code = window.prompt("Введи код кімнати");
    if (code) window.location.href = `/room/${code.trim().toUpperCase()}`;
  });
  loadCatalog();
}

function addChatMessage(message, className = "") {
  const list = document.querySelector("#chat-messages");
  const item = document.createElement("div");
  item.className = `chat-message ${className}`.trim();
  if (message.display_name) {
    const author = document.createElement("strong");
    author.textContent = message.display_name;
    item.append(author);
  }
  const text = document.createElement("span");
  text.textContent = message.content;
  item.append(text);
  list.append(item);
  list.scrollTop = list.scrollHeight;
}

async function fingerprintFile(file) {
  const chunkSize = 1024 * 1024;
  const first = await file.slice(0, chunkSize).arrayBuffer();
  const last = await file.slice(Math.max(0, file.size - chunkSize)).arrayBuffer();
  const metadata = new TextEncoder().encode(String(file.size));
  const merged = new Uint8Array(metadata.length + first.byteLength + last.byteLength);
  merged.set(metadata, 0);
  merged.set(new Uint8Array(first), metadata.length);
  merged.set(new Uint8Array(last), metadata.length + first.byteLength);
  const digest = await crypto.subtle.digest("SHA-256", merged);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function initRoom() {
  const code = document.body.dataset.roomCode;
  const player = document.querySelector("#watch-player");
  const fileInput = document.querySelector("#video-file");
  const fileDrop = document.querySelector("#file-drop");
  const fileStatus = document.querySelector("#file-status");
  const connectionStatus = document.querySelector("#connection-status");
  const storedName = localStorage.getItem(`room:${code}:name`) || localStorage.getItem("watch-name") || "";
  let name = storedName;
  while (!name || name.trim().length < 2) {
    name = window.prompt("Як тебе показувати в кімнаті?", storedName) || "";
  }
  name = name.trim();
  localStorage.setItem("watch-name", name);
  localStorage.setItem(`room:${code}:name`, name);

  try {
    const room = await api(`/api/rooms/${code}`);
    document.querySelector("#room-anime-title").textContent = room.anime ? displayTitle(room.anime) : "Спільний перегляд";
    document.querySelector("#room-episode").textContent = `Серія ${room.episode_number}`;
    if (room.source_reference) fileStatus.textContent = `У кімнаті вибрано: ${room.source_reference}`;
  } catch (error) {
    showToast(error.message, "error");
    connectionStatus.textContent = "Кімнату не знайдено";
    return;
  }

  const protocol = location.protocol === "https:" ? "wss" : "ws";
  let socket = null;
  let reconnectTimer = null;
  let reconnectAttempt = 0;
  let applyingRemote = false;
  let lastVersion = -1;
  let pendingState = null;
  let pendingSource = null;

  function send(type, extra = {}) {
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify({
      type,
      current_time: player.currentTime || 0,
      playback_rate: player.playbackRate || 1,
      ...extra,
    }));
  }

  async function applyState(state) {
    if (!state || state.state_version < lastVersion) return;
    lastVersion = state.state_version;
    if (!player.src) {
      pendingState = state;
      return;
    }
    pendingState = null;
    applyingRemote = true;
    const sentAt = Date.parse(state.server_time || new Date().toISOString());
    const elapsed = state.is_paused ? 0 : Math.max(0, (Date.now() - sentAt) / 1000);
    const target = Number(state.current_time || 0) + elapsed * Number(state.playback_rate || 1);
    if (Math.abs((player.currentTime || 0) - target) > 0.45) player.currentTime = target;
    player.playbackRate = Number(state.playback_rate || 1);
    if (state.is_paused) {
      player.pause();
    } else if (player.src) {
      await player.play().catch(() => {
        fileStatus.textContent = "Браузер заблокував автозапуск — натисни Play один раз.";
      });
    }
    window.setTimeout(() => { applyingRemote = false; }, 80);
  }

  async function handleSocketMessage(event) {
    const message = JSON.parse(event.data);
    if (message.type === "connected") {
      localStorage.setItem(`room:${code}:user-id`, message.user_id);
      document.querySelector("#chat-messages").replaceChildren();
      addChatMessage({ content: "Ти підключився до кімнати." }, "system-message");
      await applyState(message.state);
    } else if (["play", "pause", "seek", "rate", "state"].includes(message.type)) {
      await applyState(message);
    } else if (message.type === "chat") {
      addChatMessage(message);
    } else if (message.type === "member_joined") {
      addChatMessage({ content: `${message.display_name} приєднався.` }, "system-message");
    } else if (message.type === "member_left") {
      addChatMessage({ content: `${message.display_name} вийшов.` }, "system-message");
    } else if (message.type === "source_ready") {
      fileStatus.textContent = `Файл збігається: ${message.file_name || "серія готова"}`;
      fileStatus.classList.remove("error");
    } else if (message.type === "source_mismatch") {
      fileStatus.textContent = message.message;
      fileStatus.classList.add("error");
    } else if (message.type === "error") {
      showToast(message.message, "error");
    }
  }

  function connectSocket() {
    const params = new URLSearchParams({ name });
    const savedUserId = localStorage.getItem(`room:${code}:user-id`);
    if (savedUserId) params.set("user_id", savedUserId);
    socket = new WebSocket(`${protocol}://${location.host}/ws/rooms/${code}?${params}`);

    socket.addEventListener("open", () => {
      reconnectAttempt = 0;
      connectionStatus.textContent = "Синхронізовано";
      connectionStatus.classList.add("connected");
      if (pendingSource) send("source", pendingSource);
    });
    socket.addEventListener("close", () => {
      connectionStatus.textContent = "Перепідключення…";
      connectionStatus.classList.remove("connected");
      window.clearTimeout(reconnectTimer);
      const delay = Math.min(30000, 1000 * (2 ** reconnectAttempt));
      reconnectAttempt += 1;
      reconnectTimer = window.setTimeout(connectSocket, delay);
    });
    socket.addEventListener("error", () => socket.close());
    socket.addEventListener("message", handleSocketMessage);
  }

  connectSocket();
  const heartbeat = window.setInterval(() => {
    send("ping", { client_time: new Date().toISOString() });
  }, 25000);
  window.addEventListener("beforeunload", () => {
    window.clearInterval(heartbeat);
    window.clearTimeout(reconnectTimer);
  });

  fileInput.addEventListener("change", async () => {
    const file = fileInput.files[0];
    if (!file) return;
    fileStatus.textContent = "Перевіряємо файл…";
    const hash = await fingerprintFile(file);
    player.src = URL.createObjectURL(file);
    player.load();
    fileDrop.classList.add("hidden");
    pendingSource = { file_hash: hash, file_name: file.name };
    send("source", pendingSource);
  });

  player.addEventListener("loadedmetadata", async () => {
    if (pendingState) await applyState(pendingState);
  });

  player.addEventListener("play", () => { if (!applyingRemote) send("play"); });
  player.addEventListener("pause", () => { if (!applyingRemote) send("pause"); });
  player.addEventListener("seeked", () => { if (!applyingRemote) send("seek"); });
  player.addEventListener("ratechange", () => { if (!applyingRemote) send("rate"); });

  document.querySelector("#chat-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = document.querySelector("#chat-input");
    const content = input.value.trim();
    if (!content) return;
    send("chat", { content });
    input.value = "";
  });
  document.querySelector("#copy-room-link").addEventListener("click", async () => {
    await navigator.clipboard.writeText(location.href);
    showToast("Посилання скопійовано");
  });
}

if (page === "home") initHome();
if (page === "room") initRoom();
