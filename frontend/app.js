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

// --- Главный экран ---
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
    if (msg.type === "state") {
      state = msg;
      accusing = false;
      render();
    }
  };
  socket.onclose = () => {
    if (state) showError("Соединение закрыто");
  };

  el("home").classList.add("hidden");
  el("game").classList.remove("hidden");
}

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

  return win + details +
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
