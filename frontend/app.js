"use strict";

// --- Гостевая идентичность: UUID в localStorage (задел под Telegram Login позже) ---
function guestId() {
  let id = localStorage.getItem("spy_user_id");
  if (!id) {
    id = (crypto.randomUUID && crypto.randomUUID()) ||
      "g-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem("spy_user_id", id);
  }
  return id;
}

const USER_ID = guestId();
let socket = null;
let state = null;        // последний снимок от сервера
let accusing = false;    // локальный шаг: работник выбирает, кого обвинить

const el = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function showError(msg) {
  const e = el("error");
  e.textContent = msg;
  e.classList.remove("hidden");
  setTimeout(() => e.classList.add("hidden"), 4000);
}

// --- Статистика игрока ---
let myStats = null;

function statsHtml(s) {
  if (!s) return "";
  return `📊 Игр: <b>${s.games}</b> · Побед: <b>${s.wins}</b> · Поражений: <b>${s.losses}</b>` +
    `<br><span class="muted">Был шпионом: ${s.times_spy} (побед: ${s.spy_wins})</span>`;
}

async function loadStats() {
  try {
    myStats = await (await fetch(`/api/users/${encodeURIComponent(USER_ID)}/stats`)).json();
  } catch (e) {
    return; // статистика не критична
  }
  const box = el("stats");
  if (box) {
    box.innerHTML = statsHtml(myStats);
    box.classList.remove("hidden");
  }
}

// --- Главный экран ---
loadStats();
el("name-input").value = localStorage.getItem("spy_name") || "";
el("name-input").addEventListener("change", (e) =>
  localStorage.setItem("spy_name", e.target.value.trim()));

el("create-btn").addEventListener("click", async () => {
  const name = el("name-input").value.trim() || "Хост";
  const res = await fetch("/api/lobby", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: USER_ID, name }),
  });
  const data = await res.json();
  connect(data.lobby_id);
});

el("join-btn").addEventListener("click", async () => {
  const lobbyId = el("join-input").value.trim();
  if (!lobbyId) return showError("Введите ID лобби");
  const res = await fetch(`/api/lobby/${lobbyId}`);
  const data = await res.json();
  if (!data.exists) return showError(`Лобби ${lobbyId} не найдено`);
  if (data.started) return showError("Игра уже идёт, нельзя присоединиться");
  connect(lobbyId);
});

// --- WebSocket ---
function connect(lobbyId) {
  const name = el("name-input").value.trim() || "Игрок";
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const url = `${proto}://${location.host}/ws/${lobbyId}` +
    `?user_id=${encodeURIComponent(USER_ID)}&name=${encodeURIComponent(name)}`;
  socket = new WebSocket(url);

  socket.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "error") return showError(msg.message);
    if (msg.type === "chat") return appendChat(msg);
    if (msg.type === "voice") return onVoiceRoster(msg.members);
    if (msg.type === "rtc_signal") return onRtcSignal(msg.from, msg.signal);
    if (msg.type === "state") {
      state = msg;
      accusing = false;
      render();
      // По завершении раунда подтягиваем свежую статистику и перерисовываем
      if (state.status === "finished") loadStats().then(render);
    }
  };
  socket.onclose = () => {
    if (state) showError("Соединение закрыто");
  };

  el("home").classList.add("hidden");
  el("game").classList.remove("hidden");
  el("chat").classList.remove("hidden");
  el("voice").classList.remove("hidden");
}

// --- Чат ---
function appendChat(m) {
  const box = el("chat-messages");
  const div = document.createElement("div");
  div.className = "chat-msg" + (m.user_id === USER_ID ? " mine" : "");
  div.innerHTML = `<span class="chat-name">${esc(m.name)}</span>${esc(m.text)}`;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

function sendChat() {
  const inp = el("chat-input");
  const text = inp.value.trim();
  if (!text) return;
  send("chat", { text });
  inp.value = "";
}

el("chat-send").addEventListener("click", sendChat);
el("chat-input").addEventListener("keydown", (e) => { if (e.key === "Enter") sendChat(); });

// --- Голосовой чат (WebRTC mesh) ---
// Сервер только релеит сигналинг; аудио идёт peer-to-peer между всеми парами.
const RTC_CONFIG = { iceServers: [{ urls: "stun:stun.l.google.com:19302" }] };
let localStream = null;
let voiceOn = false;
const peers = {};            // peerId -> { pc, pendingCandidates, haveRemote }
let lastRoster = [];

const cssId = (id) => "audio-" + id.replace(/[^a-zA-Z0-9_-]/g, "");

async function toggleVoice() {
  if (voiceOn) return leaveVoice();
  try {
    localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
  } catch (e) {
    return showError("Нет доступа к микрофону");
  }
  voiceOn = true;
  updateVoiceUI();
  send("voice_join");
}

function leaveVoice() {
  voiceOn = false;
  send("voice_leave");
  Object.keys(peers).forEach(closePeer);
  if (localStream) {
    localStream.getTracks().forEach((t) => t.stop());
    localStream = null;
  }
  updateVoiceUI();
  updateVoiceList(lastRoster);
}

function closePeer(peerId) {
  const p = peers[peerId];
  if (p) { try { p.pc.close(); } catch (e) { /* already closed */ } }
  delete peers[peerId];
  const au = document.getElementById(cssId(peerId));
  if (au) au.remove();
}

function createPeer(peerId, initiator) {
  const pc = new RTCPeerConnection(RTC_CONFIG);
  const entry = { pc, pendingCandidates: [], haveRemote: false };
  peers[peerId] = entry;

  localStream.getTracks().forEach((t) => pc.addTrack(t, localStream));

  pc.onicecandidate = (e) => {
    if (e.candidate) send("rtc_signal", { to: peerId, signal: { candidate: e.candidate } });
  };
  pc.ontrack = (e) => {
    let au = document.getElementById(cssId(peerId));
    if (!au) {
      au = document.createElement("audio");
      au.id = cssId(peerId);
      au.autoplay = true;
      document.body.appendChild(au);
    }
    au.srcObject = e.streams[0];
  };

  if (initiator) {
    pc.createOffer()
      .then((o) => pc.setLocalDescription(o))
      .then(() => send("rtc_signal", { to: peerId, signal: { sdp: pc.localDescription } }))
      .catch(() => {});
  }
  return entry;
}

function onVoiceRoster(members) {
  lastRoster = members || [];
  updateVoiceList(lastRoster);
  if (!voiceOn) return;

  const others = lastRoster.filter((m) => m !== USER_ID);
  // Новые пиры: инициирует тот, у кого id меньше (детерминированно — без glare)
  others.forEach((peerId) => {
    if (!peers[peerId]) createPeer(peerId, USER_ID < peerId);
  });
  // Ушедшие пиры: закрываем соединение
  Object.keys(peers).forEach((peerId) => {
    if (!others.includes(peerId)) closePeer(peerId);
  });
}

async function onRtcSignal(from, signal) {
  if (!voiceOn || !signal) return;
  // Сигнал мог прийти раньше, чем разобрали ростер — создаём пира как отвечающего
  let entry = peers[from] || createPeer(from, false);
  const pc = entry.pc;

  try {
    if (signal.sdp) {
      await pc.setRemoteDescription(signal.sdp);
      entry.haveRemote = true;
      for (const c of entry.pendingCandidates) {
        try { await pc.addIceCandidate(c); } catch (e) { /* ignore */ }
      }
      entry.pendingCandidates = [];
      if (signal.sdp.type === "offer") {
        const ans = await pc.createAnswer();
        await pc.setLocalDescription(ans);
        send("rtc_signal", { to: from, signal: { sdp: pc.localDescription } });
      }
    } else if (signal.candidate) {
      if (entry.haveRemote) await pc.addIceCandidate(signal.candidate);
      else entry.pendingCandidates.push(signal.candidate);
    }
  } catch (e) {
    /* нестрашные гонки согласования игнорируем */
  }
}

function updateVoiceUI() {
  const btn = el("voice-toggle");
  if (!btn) return;
  btn.textContent = voiceOn ? "🔇 Выключить голос" : "🎤 Включить голос";
  btn.classList.toggle("danger", voiceOn);
  btn.classList.toggle("secondary", !voiceOn);
}

function memberName(id) {
  if (id === USER_ID) return "вы";
  const p = state && state.players.find((x) => x.id === id);
  return p ? p.name : "Игрок";
}

function updateVoiceList(members) {
  const box = el("voice-list");
  if (!box) return;
  box.textContent = members && members.length
    ? "🎙️ В голосе: " + members.map(memberName).join(", ")
    : "В голосе никого";
}

el("voice-toggle").addEventListener("click", toggleVoice);

function send(action, extra = {}) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ action, ...extra }));
  }
}

// --- Рендер ---
function render() {
  if (!state) return;
  const views = {
    waiting: renderWaiting,
    playing: renderPlaying,
    voting: renderVoting,
    finished: renderFinished,
  };
  el("game").innerHTML = (views[state.status] || (() => ""))();
  bind();
}

function playersList() {
  return `<ul class="players">${state.players.map((p) =>
    `<li><span>${esc(p.name)}</span>${p.is_you ? '<span class="you">вы</span>' : ""}</li>`
  ).join("")}</ul>`;
}

function renderWaiting() {
  const enough = state.players.length >= state.min_players;
  const places = state.custom_workplaces.map((w) => `<span class="tag">${esc(w)}</span>`).join("");
  return `
    <div class="muted">Код лобби — поделитесь с друзьями</div>
    <div class="lobby-id">${state.lobby_id}</div>
    <div class="section-title">Игроки (${state.players.length})</div>
    ${playersList()}
    <label>Сменить имя
      <input id="rename" type="text" maxlength="30" placeholder="Новое имя" />
    </label>
    <button id="rename-btn" class="ghost">Сохранить имя</button>
    <div class="section-title">Своё место работы</div>
    <div class="row">
      <input id="place-input" type="text" maxlength="50" placeholder="Добавить место" />
      <button id="addplace-btn" class="secondary" style="flex:0 0 auto">+</button>
    </div>
    ${places ? `<div class="tag-list">${places}</div>` : ""}
    <div class="muted">Всего мест: ${state.workplaces_count}</div>
    ${state.is_host
      ? `<button id="start-btn" ${enough ? "" : "disabled"}>
           ${enough ? "Начать игру" : `Нужно минимум ${state.min_players} игрока`}
         </button>`
      : `<div class="banner muted">Ждём, пока организатор начнёт игру…</div>`}
  `;
}

function renderPlaying() {
  let card;
  if (state.role === "spy") {
    card = `<div class="role-card role-spy">
      <div>🕵️</div><div class="big">Вы — ШПИОН</div>
      <div class="muted">Узнайте место работы остальных. Вы не знаете, где работают другие.</div>
    </div>`;
  } else {
    card = `<div class="role-card role-worker">
      <div>👷</div><div class="big">Вы — РАБОТНИК</div>
      <div class="place">${esc(state.workplace)}</div>
      <div class="muted">Найдите шпиона среди коллег.</div>
    </div>`;
  }

  let action = "";
  if (state.spy_guessing) {
    // Шпион остановил игру и загадывает место
    if (state.role === "spy") {
      action = `
        <div class="banner">Вы остановили игру. Назовите место работы:</div>
        <div class="row">
          <input id="guess-input" type="text" maxlength="50" placeholder="Например, Банк" />
          <button id="guess-btn" style="flex:0 0 auto">Назвать</button>
        </div>`;
    } else {
      action = `<div class="banner">⏸️ Шпион остановил игру и выбирает место…</div>`;
    }
  } else if (accusing && state.role === "worker") {
    const buttons = state.players.filter((p) => !p.is_you).map((p) =>
      `<button class="danger accuse-btn" data-id="${esc(p.id)}">${esc(p.name)}</button>`).join("");
    action = `<div class="banner">Кого обвиняете в шпионаже?</div>${buttons}
      <button id="cancel-accuse" class="ghost">Отмена</button>`;
  } else {
    if (state.role === "spy") {
      action = `<button id="stop-spy-btn">⏸️ Остановить и назвать место</button>`;
    } else {
      action = `<button id="accuse-start-btn">⏸️ Остановить и обвинить шпиона</button>`;
    }
  }

  return card + action + hostControls();
}

function renderVoting() {
  let block;
  if (state.can_vote && !state.you_voted) {
    block = `
      <div class="banner">🕵️ Шпион назвал место:
        <div class="place">${esc(state.guessed_workplace)}</div>
        Это правда ваше место работы?
      </div>
      <div class="row">
        <button id="vote-yes" class="danger">Да, угадал</button>
        <button id="vote-no" class="secondary">Нет</button>
      </div>`;
  } else {
    block = `<div class="banner">Голосование: ${state.votes_count}/${state.workers_count}
      ${state.you_voted ? "— ваш голос учтён" : ""}</div>`;
  }
  return block + hostControls();
}

function renderFinished() {
  const r = state.result || {};
  const win = r.winner === "spy"
    ? `<div class="result-win" style="color:var(--danger)">🎉 Победа шпиона!</div>`
    : `<div class="result-win" style="color:var(--ok)">🎉 Победа работников!</div>`;
  let details = `<div class="banner">
    🕵️ Шпион: <b>${esc(r.spy_name || "—")}</b><br>
    🏢 Место работы: <b>${esc(r.workplace || "—")}</b>`;
  if (r.guessed_workplace) details += `<br>Догадка шпиона: ${esc(r.guessed_workplace)}`;
  if (r.accused_name) details += `<br>Обвинён: ${esc(r.accused_name)}`;
  if (r.yes_votes != null) details += `<br>Голоса — за: ${r.yes_votes}, против: ${r.no_votes}`;
  details += `</div>`;

  const stats = myStats ? `<div class="stats">${statsHtml(myStats)}</div>` : "";
  return win + details + stats +
    (state.is_host
      ? `<button id="start-btn">Новая игра</button>`
      : `<div class="banner muted">Ждём новый раунд от организатора…</div>`);
}

function hostControls() {
  if (!state.is_host) return "";
  return `
    <div class="section-title">Управление (организатор)</div>
    <div class="row">
      <button class="ghost" id="win-workers">Победа работников</button>
      <button class="ghost" id="win-spy">Победа шпиона</button>
    </div>
    <button class="ghost" id="endgame-btn">Завершить раунд</button>`;
}

// --- Привязка обработчиков после каждого render ---
function bind() {
  const on = (id, ev, fn) => { const n = el(id); if (n) n.addEventListener(ev, fn); };

  on("rename-btn", "click", () => {
    const v = el("rename").value.trim();
    if (v) send("set_name", { name: v });
  });
  on("addplace-btn", "click", () => {
    const v = el("place-input").value.trim();
    if (v) send("add_place", { place: v });
  });
  on("start-btn", "click", () => send("start"));
  on("stop-spy-btn", "click", () => send("stop_spy"));
  on("guess-btn", "click", () => {
    const v = el("guess-input").value.trim();
    if (v) send("guess", { place: v });
  });
  on("accuse-start-btn", "click", () => { accusing = true; render(); });
  on("cancel-accuse", "click", () => { accusing = false; render(); });
  document.querySelectorAll(".accuse-btn").forEach((b) =>
    b.addEventListener("click", () => send("accuse", { target_id: b.dataset.id })));
  on("vote-yes", "click", () => send("vote", { value: true }));
  on("vote-no", "click", () => send("vote", { value: false }));
  on("win-workers", "click", () => send("win", { winner: "workers" }));
  on("win-spy", "click", () => send("win", { winner: "spy" }));
  on("endgame-btn", "click", () => send("endgame"));
}
