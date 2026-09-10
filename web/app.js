/* Пульт конвейера: запуск стадий, приёмка, ключи, балансы.
 *
 * Панель — единственный интерфейс продукта, поэтому здесь есть всё, что тратит
 * деньги. Правило одно: смету человек видит ДО траты, а сервер запускает те же
 * CLI, что и терминал. Никакой логики конвейера в браузере нет — только показ.
 */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const esc = (s) => String(s ?? "").replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const money = (v) => "$" + Number(v).toFixed(2);

const state = {
  text: null,          // движки, модели и текстовые стадии проекта
  engine: null,
  model: null,
  project: null,
  episode: null,
  data: null,
  task: null,
  tab: "pipe",
  poll: null,
};

// Платные стадии в порядке конвейера. Названия человеческие, id — те, что
// понимает CLI. Какие из них показывать, решает жанр проекта: у познавательного
// нет липсинка, а в режиме кадров нечего снимать отрезками.
const ALL_STAGES = [
  { id: "storyboard", label: "Кадры" },
  { id: "segments", label: "Отрезки" },
  { id: "audio", label: "Звук" },
  { id: "foley", label: "Фоли" },
  { id: "lipsync", label: "Липсинк" },
  { id: "render", label: "Монтаж" },
];

function stagesForProject() {
  const d = state.data;
  if (!d) return ALL_STAGES;
  return ALL_STAGES.filter((s) => {
    if (s.id === "lipsync") return d.genre.lipsync;
    if (s.id === "segments") return d.visual_mode !== "stills";
    return true;
  });
}

async function api(path, options) {
  const res = await fetch(path, options);
  const data = await res.json().catch(() => ({ error: "ответ не разобрать" }));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

const post = (path, body) => api(path, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

function toast(message, isError = false) {
  const el = document.createElement("div");
  el.className = "toast" + (isError ? " err" : "");
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), isError ? 8000 : 4000);
}

/* ── Модалка ───────────────────────────────────────── */
const veil = $("#veil");
const veilBody = $("#veil-body");

function openDialog(html, wide = false) {
  veilBody.innerHTML = `<div class="dlg${wide ? " wide" : ""}">
    <button class="closex" data-close aria-label="Закрыть">×</button>${html}</div>`;
  veil.hidden = false;
}
function closeDialog() { veil.hidden = true; veilBody.innerHTML = ""; }
veil.addEventListener("click", (e) => {
  if (e.target === veil || e.target.closest("[data-close]")) closeDialog();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !veil.hidden) closeDialog();
});

/* ── Рейка ─────────────────────────────────────────── */
async function loadProjects() {
  const { projects } = await api("/api/projects");
  $("#projects").innerHTML = projects.length
    ? projects.map((name) => `<button class="proj" data-project="${esc(name)}"
        aria-current="${name === state.project}">
        <span class="pn"><i class="dot"></i>${esc(name)}</span></button>`).join("")
    : `<div class="muted hint-inline">Проектов ещё нет.</div>`;
  $("#projects").innerHTML +=
    `<button class="proj new" id="new-project">+ Новый проект</button>`;

  if (!projects.length) {
    $("#tab-pipe").innerHTML = `<div class="empty">Проектов ещё нет.
      Нажми «Новый проект» слева — панель заведёт бриф, манифест и пустые
      артефакты сама.</div>`;
    state.project = null;
    return;
  }
  if (!projects.includes(state.project)) state.project = projects[0];
}

function renderLadder() {
  const d = state.data;
  const next = d.next ? d.next.stage : null;
  const counts = {};
  const ep = currentEpisode();
  (ep ? ep.items : []).forEach((item) => {
    const stage = item.id.split("/")[1];
    counts[stage] = counts[stage] || { total: 0, waiting: 0, done: 0 };
    counts[stage].total += 1;
    if (item.status === "generated") counts[stage].waiting += 1;
    if (item.status === "done" || item.status === "accepted_with_notes") counts[stage].done += 1;
  });

  const rows = stagesForProject().map((s) => {
    const c = counts[s.id === "storyboard" ? "storyboard" : s.id] || null;
    let cls = "";
    let amt = "—";
    if (c) {
      amt = `${c.done}/${c.total}`;
      cls = c.waiting ? "s-wait" : (c.done === c.total ? "s-done" : "s-now");
      if (c.waiting) amt = `${c.waiting} ждут`;
    }
    if (next === s.id) cls = cls || "s-now";
    return `<li class="${cls}"><i class="pip"></i><span class="nm">${esc(s.label)}</span>
      <span class="amt">${esc(amt)}</span></li>`;
  }).join("");
  $("#ladder").innerHTML = `<ul class="ladder">${rows}</ul>`;
}

function renderBudget() {
  const b = state.data.budget;
  const limit = b.limit === null ? null : Number(b.limit);
  const spent = Number(b.spent || 0);
  const pct = limit ? Math.min(100, spent / limit * 100) : 0;
  $("#budget").innerHTML = `
    <div class="row"><span class="cap">Бюджет проекта</span>
      <span class="val">${money(spent)}${limit === null ? "" : " / " + money(limit)}</span></div>
    ${limit === null
      ? `<div class="cap muted budget-note">потолок не задан
          (budget_usd в project.json)</div>`
      : `<div class="meter"><i></i></div>`}`;
  const fill = $("#budget .meter i");
  if (fill) fill.style.width = pct.toFixed(0) + "%";
}

async function loadBalances() {
  const box = $("#balances");
  box.innerHTML = `<div class="muted hint-inline">спрашиваю…</div>`;
  try {
    const { balances } = await api("/api/balances");
    box.innerHTML = balances.map((row) => {
      const known = row.balance !== null && row.balance !== undefined;
      const low = known && row.balance < 5;
      const cls = known ? (low ? "low" : "") : (row.reason === "ключ не задан" ? "off" : "unknown");
      return `<div class="bal ${cls}">
        <span class="who"><i></i>${esc(row.provider)}</span>
        <span class="amt">${known ? money(row.balance) : "—"}</span>
        ${row.reason ? `<span class="sub">${esc(row.reason)}</span>` : ""}
      </div>`;
    }).join("");
  } catch (e) {
    box.innerHTML = `<div class="err hint-inline">${esc(e.message)}</div>`;
  }
}

/* ── Конвейер ──────────────────────────────────────── */
const currentEpisode = () =>
  (state.data.episodes || []).find((e) => e.id === state.episode)
  || (state.data.episodes || [])[0];

function renderEpisodes() {
  const eps = state.data.episodes || [];
  if (!eps.some((e) => e.id === state.episode)) state.episode = eps.length ? eps[0].id : null;
  $("#episodes").innerHTML = eps.map((e) =>
    `<button data-episode="${esc(e.id)}" aria-pressed="${e.id === state.episode}">${esc(e.id)}</button>`
  ).join("");
}

function renderPipe() {
  const d = state.data;
  const ep = currentEpisode();
  const waiting = ep ? ep.items.filter((i) => i.status === "generated") : [];

  const nextText = d.next
    ? `<b>${esc(d.next.stage)}</b> ${esc(d.next.episode || "")} — ${esc(d.next.label)}`
    : "нечего делать: всё закрыто или ждёт приёмки";

  // Автономный режим ведёт конвейер сам, ручной — по шагу за нажатие. Режим
  // живёт в брифе (`autonomy`), потому что его же читает код, держащий потолок
  // трат: панель не заводит для этого второго имени.
  const auto = d.autonomy === "full";

  // В шапке формат, а не легаси-type: у познавательного сериала type всё ещё
  // animated_series, и показывать это человеку значит врать о жанре, который
  // тут же назван отдельной строкой.
  const head = `<div class="next">
    <div>
      <span class="eyebrow">Проект · ${esc(d.format_label || d.format)} · ${esc(d.aspect)}</span>
      <h3>${esc(d.theme)}</h3>
      <p>Следующий шаг: ${nextText}</p>
      <p class="muted sub-line">
        ${durationLine(ep)} ·
        ${d.forecast ? `готовое видео от ~${money(d.forecast.total)} ·` : ""}
        отрезок ${esc(d.segment_seconds)} с ·
        кадр ${esc(d.models.image?.model || d.models.image)} ·
        видео ${esc(d.models.video?.model || d.models.video)}</p>
    </div>
    <div class="go">
      ${d.next || (auto && (d.awaiting_text || []).length)
        ? `<button class="btn primary" id="run-pipeline"
             title="${esc(auto
               ? "идёт по шагам сам, пока не упрётся в человека или в потолок бюджета"
               : d.next?.kind === "paid"
                 ? "платная стадия — сначала смета"
                 : "текстовая стадия, провайдерам видео не платит")}"
             ${d.next?.kind === "unknown" ? "disabled" : ""}
             >${auto ? "Запустить конвейер" : "Следующий шаг"}${
               d.next ? " · " + esc(d.next.stage) : " · одобрить и дальше"}</button>`
        : `<span class="muted">Конвейер прошёл: делать нечего или всё ждёт приёмки</span>`}
      <button class="btn ghost" id="estimate-btn">Смета эпизода</button>
    </div>
  </div>

  <div class="settings-row">
    <label class="setting">
      <span class="eyebrow">Жанр</span>
      <span class="pill-static">${esc(d.genre.label)}${d.genre.problem
        ? ' <span class="err">· карточка не прочитана</span>' : ""}</span>
    </label>

    <label class="setting">
      <span class="eyebrow">Язык контента</span>
      <select class="field" id="language">${d.languages.map((l) =>
        `<option value="${esc(l.code)}"${l.code === d.language ? " selected" : ""}
          >${esc(l.label)}</option>`).join("")}</select>
    </label>

    <div class="setting">
      <span class="eyebrow">Как выглядит серия</span>
      ${d.visual_modes.length > 1
        ? `<div class="chip-ep">
            <button data-mode="video" aria-pressed="${d.visual_mode === "video"}">Видеоряд</button>
            <button data-mode="stills" aria-pressed="${d.visual_mode === "stills"}">Кадры</button>
          </div>`
        : `<span class="pill-static">${d.visual_mode === "stills"
            ? "Кадры под озвучку" : "Видеоряд"} · жанр другого не допускает</span>`}
      <span class="hint-inline muted">${d.visual_mode === "stills"
        ? "отрезки не снимаются: кадр висит столько, сколько говорит его реплика"
        : "снимаются отрезки — это дороже кадров примерно в десять раз"}</span>
    </div>

    <div class="setting">
      <span class="eyebrow">Кто ведёт конвейер</span>
      <div class="chip-ep">
        <button data-autonomy="checkpoints" aria-pressed="${!auto}">Вручную</button>
        <button data-autonomy="full" aria-pressed="${auto}">Автономно</button>
      </div>
      <span class="hint-inline muted">${auto
        ? "смета всего остатка и одно подтверждение на старте; дальше шаги идут подряд, пока не кончится работа, не откажет стадия или не понадобится человек"
        : "по шагу за нажатие: перед платной стадией показывается смета"}</span>
    </div>

    <label class="setting">
      <span class="eyebrow">Длительность серии, с</span>
      <input class="field" id="episode-seconds" type="number" min="1" step="1"
        value="${ep && ep.duration.target_sec ? esc(ep.duration.target_sec) : ""}">
      <span class="hint-inline muted">цель из брифа; из неё считается прогноз
        стоимости до раскадровки</span>
    </label>

    <label class="setting">
      <span class="eyebrow">Длительность отрезка</span>
      ${d.segment_options.length
        ? `<select class="field" id="segment-seconds">${d.segment_options.map((v) =>
            `<option value="${v}"${v === d.segment_seconds ? " selected" : ""}
              >${v} с</option>`).join("")}</select>`
        : `<input class="field" id="segment-seconds" type="number" min="1" step="1"
             value="${esc(d.segment_seconds)}">`}
      <span class="hint-inline muted">${d.segment_options.length
        ? "сетка объявлена карточкой видеомодели — другое число она не снимет"
        : "сетка у этой модели не объявлена; последнее слово за гейтом модели"}</span>
    </label>

    <label class="setting">
      <span class="eyebrow">Потолок бюджета, $</span>
      <input class="field" id="budget-limit" type="number" min="0" step="1"
        placeholder="нет" value="${d.budget.limit === null ? "" : esc(d.budget.limit)}">
      <span class="hint-inline muted">потрачено ${money(d.budget.spent)}; не
        задан — ограничения нет, задан — стадия за него не вылезет</span>
    </label>

    <div class="setting">
      <span class="eyebrow">Проект</span>
      <button class="btn sm danger ghost" id="delete-project">Удалить проект</button>
      <span class="hint-inline muted">удаляет всё дерево вместе с оплаченными
        генерациями; спросит имя целиком</span>
    </div>
  </div>`;

  const stages = `<h2 class="sec">Запустить стадию
      <span class="hint">смета показывается до траты</span></h2>
    <div class="stages">${stagesForProject().map((s) => `
      <button class="stage-btn" data-stage="${s.id}">
        <b>${esc(s.label)}</b><span>${s.id}</span></button>`).join("")}</div>`;

  const taskBox = `<div id="task-box"></div>`;

  // Тексты ждут человека так же, как кадры: разница только в том, чем их
  // принимают — кадр кнопкой ревью, сценарий одобрением. Держать их в разных
  // концах экрана значит прятать половину очереди.
  const texts = d.awaiting_text || [];
  const textRows = texts.length
    ? `<div class="tbl-wrap"><table>
        <thead><tr><th>артефакт</th><th>состояние</th><th></th></tr></thead>
        <tbody>${texts.map((a) => `<tr>
          <td class="mono"><button class="linkish artifact"
            data-artifact="${esc(a.path)}" title="открыть">${esc(a.path)}</button></td>
          <td><span class="badge s-${esc(a.state.split("_")[0])}">${esc(a.state)}</span></td>
          <td><button class="btn sm" data-approve="${esc(a.path)}">Одобрить</button></td>
        </tr>`).join("")}</tbody></table></div>`
    : "";

  const review = (waiting.length ? `<div class="cards">${waiting.map(cardHtml).join("")}</div>` : "")
    + textRows
    + (waiting.length || texts.length ? "" : `<div class="empty">На приёмке ничего нет.</div>`);

  const arts = `<div class="tbl-wrap"><table>
    <thead><tr><th>артефакт</th><th>состояние</th><th>правки</th><th></th></tr></thead>
    <tbody>${d.artifacts.map((a) => `<tr>
      <td class="mono">${a.state === "missing"
        ? esc(a.path)
        : `<button class="linkish artifact" data-artifact="${esc(a.path)}"
             title="открыть">${esc(a.path)}</button>`}</td>
      <td><span class="badge s-${esc(a.state.split("_")[0])}">${esc(a.state)}</span></td>
      <td class="muted">${esc(a.feedback)}</td>
      <td>${a.state === "draft" || a.state.startsWith("stale")
        ? `<button class="btn sm" data-approve="${esc(a.path)}">Одобрить</button>` : ""}</td>
    </tr>`).join("")}</tbody></table></div>`;

  const finals = ep && ep.final.length
    ? `<h2 class="sec">Готовое</h2><div class="cards">${ep.final.map((f) =>
        `<div class="card"><video src="/media/${encodeURIComponent(state.project)}/${f}"
          controls preload="metadata"></video>
          <div class="meta"><span class="id">${esc(f)}</span></div></div>`).join("")}</div>`
    : "";

  const queue = waiting.length + texts.length;
  $("#tab-pipe").innerHTML = head + stages + taskBox + factCheckBlock(ep) +
    `<h2 class="sec">Ждёт приёмки <span class="hint">${queue
      ? "кадры открываются крупно, тексты — по ссылке" : "пусто"}</span></h2>` + review +
    `<h2 class="sec">Тексты <span class="hint">status ставит только approve</span></h2>` + arts +
    finals;

  const tab = $('.tab[data-tab="pipe"]');
  tab.innerHTML = "Конвейер" + (queue ? `<span class="cnt">${queue}</span>` : "");
  renderTask();
  fitComposer();
}

/* Плановая длительность серии. Точное число даёт только режим отрезков: там
   длительность задаём мы. В режиме кадров её задаёт реплика, а меряет её
   монтаж — поэтому «не меньше», а не выдуманное точное число. */
function durationLine(ep) {
  const d = ep && ep.duration;
  const target = d && d.target_sec ? ` (цель ${Math.round(d.target_sec)} с)` : "";
  if (!d || d.planned_sec === null || d.planned_sec === undefined) {
    return `длительность: нет плана съёмки${target}`;
  }
  // Секунды везде: в брифе, в поле настройки и здесь. Перевод в минуты по
  // дороге заставлял бы человека считать в уме, сверяя экран с файлом.
  return `${d.exact ? "" : "не меньше "}${Math.round(d.planned_sec)} с${target}`;
}

/* Композер прибит к низу экрана, поэтому нижний отступ страницы обязан быть
   равен его высоте: фиксированное число (было 150px) закрывало собой конец
   раздела «Тексты», как только у композера переносилась строка кнопок.
   Величина ставится через CSSOM: style-атрибуты запрещены CSP. */
function fitComposer() {
  const inner = $(".composer .inner");
  if (!inner) return;
  document.documentElement.style.setProperty(
    "--composer-h", `${Math.ceil(inner.getBoundingClientRect().height)}px`);
}

// Блок проверки фактов: только там, где жанр её требует, — ключа у остальных
// нет вовсе. Вердикт приходит с сервера от той же функции, которой отказывает
// approve: два ответа об одном состоянии человек прочитал бы как ошибку панели.
function factCheckBlock(ep) {
  const fc = ep && ep.fact_check;
  if (!fc) return "";

  const state_ = fc.passed
    ? `<span class="fc-ok">проверено</span>`
    : `<span class="fc-no">не пройдена</span>`;
  const meta = fc.exists
    ? `<span class="mono">${fc.claims ?? "?"} утв. · ${esc(fc.engine || "—")}${
        fc.checked_at ? " · " + esc(fc.checked_at.slice(0, 16).replace("T", " ")) : ""}</span>`
    : "";

  // Источники СЧИТАЮТСЯ, но не перечисляются: человеку у пульта важен вердикт,
  // а не то, чем его получили. Перечень занимал пол-экрана после каждой
  // проверки; сами ссылки никуда не делись — они в отчёте, который открывается
  // кнопкой рядом.
  const sources = fc.sources.length
    ? `<span class="muted">· ${fc.sources.length} ${plural(fc.sources.length,
        "источник", "источника", "источников")}</span>`
    : "";

  // Блокеры приходят от того же гейта, которым отказывает запуск. Пока они
  // есть, кнопки нет вовсе: нажатие всё равно кончится отказом сервера, а
  // проверяющий, позванный на серию без сценария, честно откажется выносить
  // вердикт — и это читается как поломка движка, а не как «сначала сценарий».
  const blocked = (fc.blockers || []).length > 0;
  const why = blocked ? fc.blockers.join("; ") : fc.problem;

  return `<h2 class="sec">Проверка фактов
      <span class="hint">без неё сценарий не одобрится</span></h2>
    <div class="fc">
      <div class="fc-head">${state_}${meta}${sources}
        ${fc.exists ? `<button class="linkish" id="fc-report">отчёт</button>` : ""}
        ${fc.passed || blocked ? "" : `<button class="btn sm ghost" id="fc-run"
          >${fc.exists ? "Проверить заново" : "Проверить факты"}</button>`}</div>
      ${fc.passed ? "" : `<p class="note">${esc(why)}</p>`}
    </div>`;
}

/* Русское склонение по числу: «1 источник», «2 источника», «5 источников».
   Без него счётчик читается как машинный вывод, а панель — продукт. */
function plural(n, one, few, many) {
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return many;
  const mod10 = n % 10;
  if (mod10 === 1) return one;
  if (mod10 >= 2 && mod10 <= 4) return few;
  return many;
}

// Артефакт открывается той же ручкой, что отдаёт кадры и готовые серии:
// containment проверяет сервер (`webapp.media_path`), панель только показывает.
async function showArtifact(rel) {
  const url = `/media/${encodeURIComponent(state.project)}/${rel}`;
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error("файл не читается");
    const text = await res.text();
    openDialog(`<h3 class="mono">${esc(rel)}</h3>
      <p class="lead">Панель артефакты показывает, но не меняет: правит их
        стадия или редактор, а status ставит только approve.</p>
      <pre class="fc-report">${esc(text)}</pre>`, true);
  } catch (e) { toast(e.message, true); }
}

async function showFactCheckReport() {
  const ep = currentEpisode();
  if (!ep || !ep.fact_check) return;
  const url = `/media/${encodeURIComponent(state.project)}/${ep.fact_check.report}`;
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error("отчёт не читается");
    const text = await res.text();
    openDialog(`<h3>Отчёт проверки · ${esc(ep.id)}</h3>
      <p class="lead">Написан проверяющим. Вердикт и хеш сценария в шапке
        проставил код: справку о прохождении не выдаёт себе проверяемый.</p>
      <pre class="fc-report">${esc(text)}</pre>`, true);
  } catch (e) { toast(e.message, true); }
}

function cardHtml(item) {
  const src = item.file
    ? `/media/${encodeURIComponent(state.project)}/${item.file}`
    : null;
  const media = !src ? `<div class="empty plain">файла нет</div>`
    : item.file.endsWith(".mp4")
      ? `<video src="${src}" controls preload="metadata" data-item="${esc(item.id)}"></video>`
      : `<img src="${src}" loading="lazy" alt="" data-zoom="${esc(item.id)}">`;
  return `<div class="card">${media}
    <div class="meta">
      <span class="id">${esc(item.id.split("/").slice(-2).join("/"))}</span>
      <div class="row">
        <button class="btn sm" data-review="accept" data-item="${esc(item.id)}">Принять</button>
        <button class="btn sm danger" data-review="reject" data-item="${esc(item.id)}">Отклонить</button>
      </div>
    </div></div>`;
}

/* ── Задача ────────────────────────────────────────── */
function renderTask() {
  const box = $("#task-box");
  if (!box) return;
  const t = state.task;
  if (!t) { box.innerHTML = ""; return; }

  const running = t.status === "running";
  const label = { running: "идёт", done: "готово", failed: "не получилось",
                  cancelled: "прервано" }[t.status] || t.status;
  box.innerHTML = `<div class="task ${esc(t.status)}">
    <div class="head">
      ${running ? '<span class="spin"></span>' : ""}
      <b>${esc(t.stage || t.kind)}</b>
      <span class="muted">${esc(label)}${t.exit_code === null || t.exit_code === undefined
        ? "" : " · код " + t.exit_code}</span>
      <span class="spacer"></span>
      ${running ? '<button class="btn sm danger" id="cancel-task">Отменить</button>' : ""}
    </div>
    <div class="log" id="task-log">${esc((t.lines || []).join("\n")) || "…"}</div>
  </div>`;
  const log = $("#task-log");
  if (log) log.scrollTop = log.scrollHeight;
}

async function pollTask() {
  try {
    const { task } = await api("/api/task");
    const wasRunning = state.task && state.task.status === "running";
    state.task = task;
    renderTask();
    if (task && task.status === "running") {
      state.poll = setTimeout(pollTask, 1000);
    } else if (wasRunning) {
      // Задача кончилась: перечитываем проект — появились новые единицы.
      await loadProject();
      toast(task.status === "done"
        ? `Стадия ${task.stage} завершена`
        : `Стадия ${task.stage}: ${task.status}, код ${task.exit_code}`,
        task.status !== "done");
    }
  } catch (e) {
    toast(e.message, true);
  }
}

/* Подтверждение автономного прогона: смета остатка ПО ВСЕМУ проекту и один
   вопрос. Дальше режим не спрашивает ничего — ни сметы по шагам, ни одобрений,
   — поэтому единственное честное место для вопроса здесь.

   Ответ ждём обещанием: диалог живёт до нажатия, а решение человека нужно
   раньше, чем уйдёт первый платный запрос. */
function confirmAutonomous() {
  return new Promise(async (resolve) => {
    let est;
    try {
      est = await api(`/api/estimate?project=${encodeURIComponent(state.project)}`);
    } catch (e) {
      toast("смету не посчитать: " + e.message, true);
      resolve(false);
      return;
    }
    const rows = est.episodes.map((ep) => `<tr><td>${esc(ep.episode)}</td>
      <td class="muted">${esc(ep.rows.map((r) => r.stage).join(", ") || "—")}</td>
      <td class="mono right">${money(ep.total)}</td></tr>`).join("")
      // Серии без плана съёмки: их цену называет прогноз по брифу. Отказ
      // отвечать («станет известно после раскадровки») хуже честного «от».
      + (est.forecast
        ? `<tr><td>${esc(est.forecast.episodes_without_plan.join(", "))}</td>
             <td class="muted">по брифу: ${esc(est.forecast.rows
               .map((r) => `${r.stage} ×${r.count}`).join(", ") || "—")}</td>
             <td class="mono right">от ~${money(est.forecast.total)}</td></tr>`
        : "");
    const problems = est.problems.length
      ? `<p class="note err">${est.problems.map(esc).join("<br>")}</p>` : "";
    // Прогноз — не замер, и допущения, из которых он собран, человек обязан
    // видеть рядом с числом: иначе «от ~$12» читается как обещание.
    const assumptions = est.forecast
      ? `<p class="note">Прогноз по брифу считан так: ${
          esc(est.forecast.assumptions.join("; "))}. Музыка, эффекты и фоли в
         него не входят — их в плане может не быть вовсе.</p>`
      : "";
    const budget = est.budget
      ? `<p class="note">Потолок ${money(est.budget.limit)}, потрачено
         ${money(est.budget.spent)}; после этой сметы останется
         ${money(est.budget.left - est.total)}. Стадия, вылезающая за потолок,
         остановится сама.</p>`
      : `<p class="note">Потолок бюджета не задан — режим остановится только
         сам: когда работы кончатся, стадия откажет или понадобится человек.</p>`;

    openDialog(`<h3>Запустить конвейер автономно?</h3>
      <p class="lead">Шаги пойдут подряд без подтверждений: панель будет
        одобрять чекпоинты сама (в файле останется <span class="mono">approved_by:
        auto</span>) и запускать платные стадии без сметы по каждой. Ниже —
        остаток работ по всем сериям на сейчас; по ходу он может вырасти:
        раскадровка следующих серий ещё не написана.</p>
      <div class="tbl-wrap"><table>
        <thead><tr><th>серия</th><th>стадии</th><th class="right">сумма</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="3" class="muted">платить пока не за что</td></tr>'}</tbody>
        <tfoot><tr><td>Итого</td><td class="muted">тексты платятся токенами движка
          и в сумму не входят</td>
          <td class="mono right">${est.forecast ? "от ~" : ""}${
            money(est.total + (est.forecast ? est.forecast.total : 0))}</td></tr></tfoot>
      </table></div>${assumptions}${problems}${budget}
      <div class="actions">
        <button class="btn ghost" data-close id="auto-cancel">Отмена</button>
        <span class="spacer"></span>
        <button class="btn primary" id="auto-confirm">Запустить автономно</button>
      </div>`);

    const done = (answer) => { closeDialog(); resolve(answer); };
    $("#auto-confirm").addEventListener("click", () => done(true));
    $("#auto-cancel").addEventListener("click", () => done(false));
    // Крестик и Escape — тоже ответ «нет»: обещание не должно висеть вечно.
    veil.addEventListener("click", function once(e) {
      if (e.target === veil || e.target.closest("[data-close]")) {
        veil.removeEventListener("click", once);
        resolve(false);
      }
    });
  });
}

/* Автономный режим ведёт СЕРВЕР (`factory/autopilot.py`): он одобряет
   чекпоинты, принимает сгенерированное и запускает следующий шаг сам. В
   браузере этой логики нет намеренно — закрытая вкладка не должна
   останавливать прогон, а две цепочки (тут и там) спорили бы за одну задачу. */

/* Попросить сервер начать автономный прогон. Смета показана и подтверждена
   здесь же; дальше вопросов не будет — в этом и смысл режима. */
async function startAutonomous() {
  if (!(await confirmAutonomous())) return;
  try {
    const result = await post("/api/autopilot", { project: state.project });
    (result.lines || []).forEach((line) => toast(line));
    if (result.started) {
      state.task = result.started;
      renderTask();
      clearTimeout(state.poll);
      state.poll = setTimeout(pollTask, 700);
      toast(`Запущено автономно: ${result.started.stage}`);
    } else {
      toast("Автономный режим: запускать нечего — смотри журнал");
    }
    await loadProject();
  } catch (e) { toast(e.message, true); }
}

async function runStage(stage) {
  // Смета — до траты. Монтаж ничего не тратит, его спрашивать незачем.
  if (stage === "render") {
    await startStage(stage);
    return;
  }
  let est;
  try {
    est = await api(`/api/estimate?project=${encodeURIComponent(state.project)}` +
                    `&episode=${encodeURIComponent(state.episode)}`);
  } catch (e) {
    toast("смету не посчитать: " + e.message, true);
    return;
  }
  const rows = est.rows.map((r) => `<tr><td>${esc(r.stage)}</td>
    <td class="mono">${r.count}</td>
    <td class="mono right">${money(r.cost)}</td></tr>`).join("");
  const budget = est.budget
    ? `<p class="note">Потрачено ${money(est.budget.spent)} из ${money(est.budget.limit)};
       после этой сметы останется ${money(est.budget.left - est.total)}.</p>`
    : `<p class="note">Потолок бюджета не задан (<span class="mono">budget_usd</span>
       в project.json).</p>`;
  const problems = est.problems.length
    ? `<p class="note err">${est.problems.map(esc).join("<br>")}</p>` : "";

  openDialog(`
    <h3>Смета остатка · ${esc(state.episode)}</h3>
    <p class="lead">Считается по фактическим ценам карточек; уже снятое и принятое
      не считается. Запускается стадия <b>${esc(stage)}</b> — она возьмёт из этого
      остатка свою часть.</p>
    <div class="tbl-wrap"><table>
      <thead><tr><th>стадия</th><th>шт</th><th class="right">сумма</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="3" class="muted">платить не за что</td></tr>'}</tbody>
      <tfoot><tr><td>Итого</td><td></td>
        <td class="mono right">${money(est.total)}</td></tr></tfoot>
    </table></div>${problems}${budget}
    <div class="actions">
      <button class="btn ghost" data-close>Отмена</button><span class="spacer"></span>
      <button class="btn primary" id="confirm-run">Запустить ${esc(stage)}</button>
    </div>`);

  $("#confirm-run").addEventListener("click", async () => {
    closeDialog();
    await startStage(stage);
  });
}

async function startStage(stage) {
  try {
    const { task } = await post("/api/run", {
      project: state.project, episode: state.episode, stage,
    });
    state.task = task;
    renderTask();
    clearTimeout(state.poll);
    state.poll = setTimeout(pollTask, 700);
    toast(`Запущено: ${stage}`);
  } catch (e) {
    toast(e.message, true);
  }
}

/* ── Ключи ─────────────────────────────────────────── */
async function renderKeys() {
  const box = $("#tab-keys");
  box.innerHTML = `<div class="muted">читаю…</div>`;
  try {
    const { keys } = await api("/api/keys");
    box.innerHTML = `
      <h2 class="sec">Ключи провайдеров
        <span class="hint">пишутся в .env на этой машине</span></h2>
      <div class="tbl-wrap"><table>
        <thead><tr><th>провайдер</th><th>переменная</th><th>ключ</th><th>за что</th><th></th></tr></thead>
        <tbody>${keys.map((k) => `<tr>
          <td>${esc(k.provider)}</td>
          <td class="mono">${esc(k.env)}</td>
          <td class="mask ${k.set ? "" : "muted"}">${k.set ? esc(k.mask) : "не задан"}</td>
          <td class="muted">${esc(k.roles)}</td>
          <td><button class="btn sm ${k.set ? "" : "primary"}"
            data-key="${esc(k.provider)}">${k.set ? "Заменить" : "Задать"}</button></td>
        </tr>`).join("")}</tbody></table></div>
      <p class="note"><b>Ключ остаётся на этой машине.</b> Он пишется в
        <span class="mono">.env</span> в корне репозитория — файл в
        <span class="mono">.gitignore</span> и в репозиторий не попадает. Панель
        показывает только маску: значение обратно в браузер не отдаётся.
        Провайдеру ключ уезжает лишь в момент генерации.</p>`;
  } catch (e) {
    box.innerHTML = `<div class="empty err">${esc(e.message)}</div>`;
  }
}

function askKey(provider) {
  openDialog(`
    <h3>Ключ · ${esc(provider)}</h3>
    <p class="lead">Значение уходит в <span class="mono">.env</span> на этой машине и
      сразу начинает работать — перезапускать панель не нужно.</p>
    <input class="field mono" id="key-input" type="password" autocomplete="off"
      spellcheck="false" placeholder="вставь ключ провайдера">
    <div class="actions">
      <button class="btn ghost" data-close>Отмена</button><span class="spacer"></span>
      <button class="btn primary" id="save-key">Сохранить</button>
    </div>`);
  const input = $("#key-input");
  input.focus();
  $("#save-key").addEventListener("click", async () => {
    const value = input.value.trim();
    if (!value) { toast("пустое значение", true); return; }
    try {
      await post("/api/keys", { provider, value });
      closeDialog();
      toast(`Ключ ${provider} сохранён`);
      await renderKeys();
      await loadBalances();
    } catch (e) {
      toast(e.message, true);
    }
  });
}

/* ── Текстовые стадии ──────────────────────────────── */
async function loadText() {
  try {
    state.text = await api(`/api/text?project=${encodeURIComponent(state.project)}`);
  } catch (e) {
    state.text = { stages: [], engines: [], models: [], problem: e.message };
  }
  const t = state.text;
  const usable = (t.engines || []).filter((x) => x.available);
  if (!state.engine && usable.length) state.engine = usable[0].name;

  // `blocked` приходит с сервера уже сформулированным: почему стадия не идёт,
  // решает тот же код, что отобьёт её запуск. Проверка фактов без поиска и без
  // Claude Code — ровно такой случай.
  $("#text-stages").innerHTML = (t.stages || []).map((s) =>
    `<button data-text="${esc(s.id)}" ${s.blocked ? "disabled" : ""}
      title="${esc(s.blocked || (s.outputs || []).join(", ") || "разговор, файлы не пишутся")}"
      >${esc(s.label)}</button>`).join("");

  const needsModel = state.engine === "openrouter";
  const models = t.models || [];
  $("#composer-ctx").innerHTML = `
    <span class="pill-static">${esc(state.project)}${state.episode ? " / " + esc(state.episode) : ""}</span>
    <span class="engine-pick">
      ${(t.engines || []).map((x) => `<button class="btn sm ${x.name === state.engine ? "primary" : "ghost"}"
        data-engine="${esc(x.name)}" ${x.available ? "" : "disabled"}
        title="${esc(x.reason || "доступен")}">${esc(x.label)}</button>`).join("")}
      ${needsModel ? `<select id="text-model">${models.length
        ? models.map((m) => `<option value="${esc(m.id)}"${m.id === state.model ? " selected" : ""}>${esc(m.label)}${
            m.input_per_million === null ? "" : ` · $${m.input_per_million.toFixed(2)}/$${(m.output_per_million ?? 0).toFixed(2)} за млн`}</option>`).join("")
        : `<option value="">моделей нет: ${esc(t.problem || "каталог недоступен")}</option>`}</select>` : ""}
    </span>
    ${usable.length ? "" : `<span class="err hint-inline">нечем писать тексты: поставь Claude Code или задай ключ OpenRouter</span>`}`;

  if (needsModel && !state.model && models.length) state.model = models[0].id;
}

// `episode` передаётся явно там, где стадия его не имеет: у исследования и
// библии серии нет, и подпись «серия ep01» в журнале была бы выдумкой.
async function runTextStage(stageId, request, episode = state.episode) {
  try {
    const { task } = await post("/api/text", {
      project: state.project, episode, stage: stageId,
      request: request || "", engine: state.engine,
      // Модель выбирается только для OpenRouter: у агента своя настройка, и
      // подсовывать ему чужой выбор значит платить не по тому тарифу.
      model: state.engine === "openrouter" ? state.model : null,
    });
    state.task = task;
    renderTask();
    clearTimeout(state.poll);
    state.poll = setTimeout(pollTask, 700);
    toast(`Пишу: ${stageId}`);
  } catch (e) { toast(e.message, true); }
}

// Что человек имел в виду: стадия из текста запроса, иначе спросим кнопкой.
function guessStage(text) {
  const map = [
    // Раньше сценария: «проверь факты в сценарии» — это проверка, а не новый
    // сценарий, и переписать вместо проверки было бы дорогой ошибкой.
    [/факт|достоверн|фактчек/i, "factcheck"],
    [/питч|вариант/i, "pitch"],
    [/иссл|research|источник/i, "research"],
    [/библи|иде[юя]|арк[уа]|стайл|стиль/i, "story"],
    [/сценар/i, "script"],
    [/персонаж|герой|карточк/i, "characters"],
    [/раскадр|кадр/i, "storyboard"],
    [/звук|озвуч|реплик/i, "audio_plan"],
  ];
  for (const [re, id] of map) {
    if (re.test(text) && (state.text?.stages || []).some((s) => s.id === id)) return id;
  }
  return null;
}

/* ── Окружение ─────────────────────────────────────── */
// Баннер говорит ровно то же, что скажет render.py, отказываясь собирать
// эпизод: формулировки живут в factory/environment.py, здесь только показ.
async function loadEnvironment() {
  let tools;
  try {
    ({ tools } = await api("/api/environment"));
  } catch { return; }
  const missing = tools.filter((t) => !t.found);
  const box = $("#env-warn");
  box.hidden = !missing.length;
  if (!missing.length) return;
  box.innerHTML = `<b>Не всё установлено.</b> ${missing.map((t) =>
    `${esc(t.label)} — без него не работает ${esc(t.breaks)}`).join("; ")}.`;
}

/* ── Загрузка состояния ────────────────────────────── */
async function loadProject() {
  if (!state.project) return;
  try {
    state.data = await api(`/api/project/${encodeURIComponent(state.project)}`);
    renderEpisodes();
    renderLadder();
    renderBudget();
    renderPipe();
    await loadText();
    $$(".proj").forEach((b) =>
      b.setAttribute("aria-current", String(b.dataset.project === state.project)));
  } catch (e) {
    $("#tab-pipe").innerHTML = `<div class="empty err">${esc(e.message)}</div>`;
  }
}

/* ── Модели по ролям ───────────────────────────────── */
// Последнее, что заставляло править project.json руками. Логика выбора здесь
// не живёт: что можно взять и почём, решает сервер — панель только показывает.
/* Текстовые стадии: чем пишутся сценарий, раскадровка, проверка фактов.
   Отдельным разделом и с прямым названием движка — «модель» вообще ничего не
   говорит человеку о том, ЧЬЯ это модель, а выбор тут именно про Claude Code
   на этой машине: у второго движка модель берётся из своего списка. */
function textModelsBlock(text) {
  if (!text) return "";
  const claude = text.engine === "claude-code";
  return `<h2 class="sec">Текстовые стадии
      <span>сценарий, раскадровка, проверка фактов — ими пишется текст, а не картинка</span></h2>
    <div class="settings-row">
      <div class="setting">
        <span class="eyebrow">Чем писать</span>
        <div class="chip-ep">
          <button data-text-engine="claude-code" aria-pressed="${claude}">Claude Code на этой машине</button>
          <button data-text-engine="openrouter" aria-pressed="${!claude}">Модель по ключу OpenRouter</button>
        </div>
        <span class="hint-inline muted">${claude
          ? "тратит лимиты твоей сессии Claude Code, деньги за токены не идут"
          : "тратит деньги по ключу OpenRouter, лимит сессии не трогает"}</span>
      </div>

      <label class="setting">
        <span class="eyebrow">Модель Claude Code</span>
        <select class="field" id="text-model-choice" ${claude ? "" : "disabled"}>
          <option value="">по умолчанию (как настроен CLI)</option>
          ${text.models.map((m) => `<option value="${esc(m)}"${
            m === text.model ? " selected" : ""}>${esc(m)}</option>`).join("")}
        </select>
        <span class="hint-inline muted">${claude
          ? "передаётся как <span class=\"mono\">claude --model</span>; «по умолчанию» — что выбрано в самом Claude Code"
          : "относится к Claude Code; сейчас выбран другой движок"}</span>
      </label>

      <label class="setting">
        <span class="eyebrow">Усилие Claude Code</span>
        <select class="field" id="text-effort" ${claude ? "" : "disabled"}>
          <option value="">по умолчанию</option>
          ${text.efforts.map((e) => `<option value="${esc(e)}"${
            e === text.effort ? " selected" : ""}>${esc(e)}</option>`).join("")}
        </select>
        <span class="hint-inline muted">${claude
          ? "<span class=\"mono\">claude --effort</span>: выше — дольше думает и дороже по токенам; для сценария серии осмысленно high и выше, для питча хватит low"
          : "относится к Claude Code; сейчас выбран другой движок"}</span>
      </label>
    </div>`;
}

async function renderModels() {
  if (!state.project) {
    $("#tab-models").innerHTML = `<div class="empty">Сначала выбери проект.</div>`;
    return;
  }
  let roles;
  let text;
  try {
    ({ roles, text } = await api(
      `/api/models?project=${encodeURIComponent(state.project)}`));
  } catch (e) {
    $("#tab-models").innerHTML = `<div class="empty err">${esc(e.message)}</div>`;
    return;
  }

  // Текущий выбор держим в состоянии: сохраняется он целиком, и без этого
  // правка усилия затирала бы выбранную модель.
  state.textChoice = text ? {engine: text.engine, model: text.model,
                             effort: text.effort} : null;
  const price = (v) => v === null || v === undefined ? "—" : "$" + Number(v).toFixed(4);
  const key = (c) => `${c.model}|${c.provider || ""}`;

  $("#tab-models").innerHTML = `
    <div class="next"><div>
      <span class="eyebrow">Среда · ${esc(state.project)}</span>
      <h3>Чем снимаем</h3>
      <p class="muted sub-line">Цена посчитана под этот проект: его разрешение и
        длительность отрезка. Карточка со статусом skeleton видна, но не
        выбирается — её возможности и цена ничем не подтверждены.</p>
    </div></div>
    ${textModelsBlock(text)}
    ${roles.map((r) => `
      <h2 class="sec">${esc(r.label)}<span>${esc(r.note)}</span></h2>
      <div class="mrole">
        <select data-role="${esc(r.role)}">
          ${r.candidates.map((c) => `<option value="${esc(key(c))}"
            ${c.selectable ? "" : "disabled"}
            ${c.model === r.current.model && c.provider === r.current.provider
              ? " selected" : ""}
            >${esc(c.model)}${c.provider ? " · " + esc(c.provider) : ""} · ${price(c.price)}${
              c.selectable ? "" : " · " + esc(c.status)}${
              c.native_audio ? " · со своим звуком" : ""}</option>`).join("")}
        </select>
        <span class="muted mrole-now">${r.current.model
          ? esc(r.current.model) + " · " + esc(r.current.provider || "—")
          : "не выбрано"}</span>
      </div>
      ${(() => {
        // Причины свёрнуты: развёрнутый список из десяти серых строк заслоняет
        // сам выбор, ради которого сюда пришли. Но и прятать совсем нельзя —
        // «почему нельзя» это половина ответа.
        const blocked = r.candidates.filter((c) => !c.selectable && c.reason);
        return blocked.length ? `<details class="mwhy">
          <summary>недоступно: ${blocked.length}</summary>
          ${blocked.map((c) =>
            `<div><b>${esc(c.model)}</b> — ${esc(c.reason)}</div>`).join("")}
        </details>` : "";
      })()}`).join("")}`;
}

async function chooseModel(role, value) {
  const [model, provider] = value.split("|");
  try {
    await post("/api/models", {
      project: state.project, models: { [role]: { model, provider } },
    });
    toast(`${role}: ${model}`);
    await renderModels();
    await loadProject();
  } catch (e) { toast(e.message, true); await renderModels(); }
}

/* ── Микшер ────────────────────────────────────────── */
// Громкости и их дефолты живут в montage.py — там же, откуда их берёт
// монтажный лист. Панель только показывает и пишет: своей копии значений здесь
// нет, иначе сведение на экране и сведение в рендере однажды разойдутся.
async function renderMixer() {
  if (!state.project) {
    $("#tab-mixer").innerHTML = `<div class="empty">Сначала выбери проект.</div>`;
    return;
  }
  let m;
  try {
    m = await api(`/api/mixer?project=${encodeURIComponent(state.project)}`);
  } catch (e) {
    $("#tab-mixer").innerHTML = `<div class="empty err">${esc(e.message)}</div>`;
    return;
  }

  const fader = (id, label, value, extra) => `
    <div class="fader">
      <span class="fname">${esc(label)}</span>
      <input type="range" min="0" max="${m.max_volume}" step="0.01"
        value="${value}" data-mix="${esc(id)}">
      <span class="fval mono" data-mixval="${esc(id)}">${Number(value).toFixed(2)}</span>
      ${extra || ""}
    </div>`;

  $("#tab-mixer").innerHTML = `
    <div class="next"><div>
      <span class="eyebrow">Микшер · ${esc(state.project)}</span>
      <h3>Как это звучит</h3>
      <p class="muted sub-line">Значения по умолчанию выбраны на слух живыми
        прослушиваниями. Правка здесь — правка ЭТОГО проекта: чужой сериал
        чужую калибровку не наследует.</p>
    </div></div>

    <h2 class="sec">Дорожки</h2>
    ${m.tracks.map((t) => fader("track:" + t.id, t.label, t.volume,
      `<label class="fmute"><input type="checkbox" data-mute="${esc(t.id)}"
        ${t.muted ? "checked" : ""}> выкл</label>
       <span class="fdef mono">по умолчанию ${t.default.toFixed(2)}</span>`)).join("")}

    <h2 class="sec">Герои<span>множитель к дорожке речи</span></h2>
    ${m.speakers.length
      ? m.speakers.map((s) => fader("speaker:" + s.name, s.name, s.gain, "")).join("")
      : `<p class="note">Состав серий пока не объявлен: герои берутся из поля
          characters во frontmatter сценария.</p>`}

    <h2 class="sec">Дакинг<span>насколько музыка уходит под речь</span></h2>
    <div class="fader">
      <span class="fname">Глубина</span>
      <input type="range" min="0" max="1" step="0.01" value="${m.duck.gain}"
        data-mix="duck:gain">
      <span class="fval mono" data-mixval="duck:gain">${m.duck.gain.toFixed(2)}</span>
      <span class="fdef mono">1.00 — подавления нет</span>
    </div>
    <div class="fader">
      <span class="fname">Атака, мс</span>
      <input type="range" min="0" max="1000" step="10" value="${m.duck.attackMs}"
        data-mix="duck:attack_ms">
      <span class="fval mono" data-mixval="duck:attack_ms">${m.duck.attackMs}</span>
      <span class="fdef mono">короче 100 мс слышно ступенькой</span>
    </div>
    <div class="fader">
      <span class="fname">Спад, мс</span>
      <input type="range" min="0" max="2000" step="10" value="${m.duck.releaseMs}"
        data-mix="duck:release_ms">
      <span class="fval mono" data-mixval="duck:release_ms">${m.duck.releaseMs}</span>
      <span class="fdef mono">длинный спад слышен сам по себе</span>
    </div>

    <h2 class="sec">Мастеринг<span>громкость готовой серии</span></h2>
    <div class="fader">
      <span class="fname">LUFS</span>
      <input type="range" min="-36" max="-6" step="0.5"
        value="${m.target_lufs === null ? -14 : m.target_lufs}"
        data-mix="target_lufs" ${m.target_lufs === null ? "disabled" : ""}>
      <span class="fval mono" data-mixval="target_lufs">${
        m.target_lufs === null ? "выкл" : m.target_lufs}</span>
      <label class="fmute"><input type="checkbox" id="lufs-on"
        ${m.target_lufs === null ? "" : "checked"}> мастерить</label>
      <span class="fdef mono">-14 — то, к чему приводит YouTube</span>
    </div>`;
}

// Ползунок отпускают редко, а двигают часто: значение показываем на каждый
// сдвиг, а на сервер шлём только по отпусканию (change), иначе каждая правка
// громкости переписывала бы project.json десятки раз.
function previewMix(input) {
  const box = $(`[data-mixval="${CSS.escape(input.dataset.mix)}"]`);
  if (!box) return;
  const step = Number(input.step);
  box.textContent = step < 1 ? Number(input.value).toFixed(2) : input.value;
}

async function saveMix(body) {
  try {
    await post("/api/mixer", { project: state.project, ...body });
  } catch (e) { toast(e.message, true); }
  await renderMixer();
}

function commitMix(input) {
  const [kind, name] = input.dataset.mix.split(":");
  const value = Number(input.value);
  if (kind === "track") return saveMix({ volumes: { [name]: value } });
  if (kind === "speaker") return saveMix({ speakers: { [name]: value } });
  if (kind === "duck") return saveMix({ duck: { [name]: value } });
  return saveMix({ target_lufs: value });
}

/* ── Кастинг голосов ───────────────────────────────── */
// Язык проб живёт отдельно от языка проекта: слушают голоса до того, как проект
// выбран, а иногда и вовсе на другом языке — сравнить тембр.
let voiceLang = "ru";

// Имена пресетов о тембре не говорят ничего, а описание сужает выбор, но не
// решает его: Vindemiatrix подходил Устинье по всем словам и на слух по-русски
// оказался негодным. Поэтому вкладка — про прослушивание, а не про список имён:
// дерево «модель → пол → голос», у каждого голоса маркеры и кнопка «играть».
async function renderVoices() {
  let data;
  try {
    data = await api(`/api/voices?language=${encodeURIComponent(voiceLang)}`);
  } catch (e) {
    $("#tab-voices").innerHTML = `<div class="empty err">${esc(e.message)}</div>`;
    return;
  }

  // Модель раскрыта, если она одна: лишний клик до единственного списка —
  // это не «компактно», это спрятанное содержимое.
  const models = data.models.map((m) => `
    <details class="vmodel"${data.models.length === 1 ? " open" : ""}>
      <summary>
        <b>${esc(m.label)}</b>
        <span class="mono">${m.total - m.missing}/${m.total} проб</span>
        ${m.missing ? `<button class="btn sm ghost" data-voice-gen-model="${esc(m.id)}"
          >снять ${m.missing}</button>` : ""}
      </summary>
      ${m.groups.map((g) => `
        <details class="vgroup" open>
          <summary>${esc(g.label)} <span class="mono">${g.voices.length}</span></summary>
          <ul class="vlist">${g.voices.map((v) => `
            <li>
              <button class="vplay${v.sample ? "" : " off"}"
                ${v.sample ? `data-play="${esc(v.sample_url)}"` : "disabled"}
                title="${v.sample ? "послушать" : "пробы ещё нет"}"
                aria-label="Послушать ${esc(v.preset)}">▶</button>
              <span class="vname">${esc(v.preset)}</span>
              <span class="vmarks">${(v.markers || []).map((x) =>
                `<i>${esc(x)}</i>`).join("")}</span>
              ${v.sample ? "" : `<button class="linkish"
                data-voice-gen="${esc(v.preset)}" data-voice-model="${esc(m.id)}"
                >снять</button>`}
            </li>`).join("")}</ul>
        </details>`).join("")}
    </details>`).join("");

  $("#tab-voices").innerHTML = `
    <div class="next">
      <div>
        <span class="eyebrow">Кастинг</span>
        <h3>Голос выбирается ушами</h3>
        <p class="muted sub-line">Все пресеты читают одну фразу:
          «${esc(data.phrase)}». Одинаковый текст — единственный способ
          сравнивать тембры.</p>
        <p class="muted sub-line">Проб снято ${data.total - data.missing}
          из ${data.total}.</p>
      </div>
      <div class="go">
        <select id="voice-lang">${["ru", "en"].map((l) =>
          `<option value="${l}"${l === voiceLang ? " selected" : ""}
            >${l === "ru" ? "Русский" : "English"}</option>`).join("")}</select>
        ${data.missing
          ? `<button class="btn primary" id="voice-gen-all"
              >Снять ${data.missing} недостающих</button>`
          : `<span class="muted">все пробы сняты</span>`}
      </div>
    </div>
    ${models}`;
}

// Плеер один на всю вкладку, а не по одному на каждый из тридцати голосов:
// тридцать <audio controls> — это тридцать полос прокрутки и ни одной причины
// слушать два голоса разом. Повторный клик по играющему голосу останавливает.
const voicePlayer = new Audio();
let voicePlaying = null;

function playVoice(url, button) {
  const same = voicePlaying === button;
  voicePlayer.pause();
  if (voicePlaying) voicePlaying.classList.remove("on");
  if (same) { voicePlaying = null; return; }
  voicePlayer.src = url;
  voicePlayer.currentTime = 0;
  voicePlayer.play().catch((e) => toast("не играется: " + e.message, true));
  voicePlaying = button;
  button.classList.add("on");
}
voicePlayer.addEventListener("ended", () => {
  if (voicePlaying) voicePlaying.classList.remove("on");
  voicePlaying = null;
});

async function generateVoices(presets, model) {
  try {
    const { task } = await post("/api/voices",
      { language: voiceLang, voices: presets || null, model: model || null });
    state.task = task;
    renderTask();
    clearTimeout(state.poll);
    state.poll = setTimeout(pollTask, 700);
    toast(presets ? `Снимаю пробу: ${presets.join(", ")}` : "Снимаю пробы");
  } catch (e) { toast(e.message, true); }
}

/* ── Мастер нового проекта ─────────────────────────── */
// Черновик формы живёт здесь, а не в DOM: тело диалога перерисовывается при
// смене жанра или формата (у сериала спрашивают серии, у метра — длительность),
// и набранное человеком не должно при этом пропадать.
const draft = { format: "wide_16x9", genre: "animation", name: "", theme: "",
                language: "ru", audience: "", episodes: 6,
                episode_duration_sec: 60, duration_sec: 300, visual_mode: "" };
let newOptions = null;

async function openNewProject() {
  try {
    newOptions = await api("/api/new");
  } catch (e) { toast(e.message, true); return; }
  openDialog(`<h3>Новый проект</h3>
    <p class="lead">Жанр решает, какие стадии будут в конвейере, а формат —
      соотношение сторон. Модели и голоса меняются потом.</p>
    <div id="np-body"></div>
    <div class="crow np-actions">
      <span class="spacer"></span>
      <button class="btn primary" id="np-create">Создать</button>
    </div>`);
  renderNewProject();
}

function renderNewProject() {
  const genre = newOptions.genres.find((g) => g.id === draft.genre)
    || newOptions.genres[0];
  draft.genre = genre.id;
  // Горизонтальный проект — всегда сериал, у которого может быть одна серия:
  // «полный метр» отдельным форматом больше не существует.
  const series = draft.format === "wide_16x9";
  // Аудиторию требует только рисованный жанр в 16:9 — то же правило, по
  // которому её требует бриф (REQUIRED_BY_TYPE у animated_*). Спрашивать её у
  // всех значило бы просить человека придумать поле, которое никто не прочитает.
  const needsAudience = genre.animated && draft.format !== "shorts_9x16";
  const modes = genre.visual_modes || [];

  $("#np-body").innerHTML = `
    <label class="fld"><span>Формат</span>
      <select data-np="format">${newOptions.formats.map((f) =>
        `<option value="${esc(f.id)}"${f.id === draft.format ? " selected" : ""}
          >${esc(f.label)}</option>`).join("")}</select></label>

    <label class="fld"><span>Жанр</span>
      <select data-np="genre">${newOptions.genres.map((g) =>
        `<option value="${esc(g.id)}"${g.id === draft.genre ? " selected" : ""}
          >${esc(g.label)}</option>`).join("")}</select></label>

    <label class="fld"><span>Имя</span>
      <input data-np="name" value="${esc(draft.name)}"
        placeholder="станет именем папки в projects/"></label>

    <label class="fld"><span>Тема</span>
      <textarea data-np="theme" rows="2"
        placeholder="о чём это. Отсюда растёт вся первая половина конвейера"
        >${esc(draft.theme)}</textarea></label>

    <label class="fld"><span>Язык</span>
      <select data-np="language">${newOptions.languages.map((l) =>
        `<option value="${esc(l.id)}"${l.id === draft.language ? " selected" : ""}
          >${esc(l.label)}</option>`).join("")}</select></label>

    ${needsAudience ? `<label class="fld"><span>Аудитория</span>
      <input data-np="audience" value="${esc(draft.audience)}"
        placeholder="например 6-9 или 12+"></label>` : ""}

    ${series ? `<label class="fld"><span>Серий</span>
        <input data-np="episodes" type="number" min="1" value="${esc(draft.episodes)}"></label>
      <label class="fld"><span>Серия, сек</span>
        <input data-np="episode_duration_sec" type="number" min="1"
          value="${esc(draft.episode_duration_sec)}"></label>`
    : `<label class="fld"><span>Длительность, сек</span>
        <input data-np="duration_sec" type="number" min="1"
          value="${esc(draft.duration_sec)}"></label>`}

    ${modes.length > 1 ? `<label class="fld"><span>Видеоряд</span>
      <select data-np="visual_mode">${modes.map((m) =>
        `<option value="${esc(m)}"${m === (draft.visual_mode || genre.default_visual_mode)
          ? " selected" : ""}>${m === "stills" ? "кадры под озвучку (дешевле)"
          : "снятые отрезки"}</option>`).join("")}</select></label>` : ""}

    <p class="note">${genre.has_characters ? "Персонажи есть: будут карточки и референсы."
      : "Персонажей нет — есть диктор."}${
      genre.fact_check === "required"
        ? " Факты проверяются обязательно: без пройденной проверки сценарий не одобрится."
        : ""}</p>`;
}

async function createProject() {
  // Горизонтальный проект — всегда сериал, у которого может быть одна серия:
  // «полный метр» отдельным форматом больше не существует.
  const series = draft.format === "wide_16x9";
  const body = { name: draft.name, theme: draft.theme, genre: draft.genre,
                 format: draft.format, language: draft.language,
                 audience: draft.audience,
                 visual_mode: draft.visual_mode || "" };
  if (series) {
    body.episodes = draft.episodes;
    body.episode_duration_sec = draft.episode_duration_sec;
  } else {
    body.duration_sec = draft.duration_sec;
  }
  try {
    const made = await post("/api/new", body);
    closeDialog();
    state.project = made.project;
    state.episode = null;
    await loadProjects();
    await loadProject();
    toast(`Создан проект ${made.project}`);
  } catch (e) { toast(e.message, true); }
}

/* ── События ───────────────────────────────────────── */
document.addEventListener("click", async (e) => {
  if (e.target.closest("#new-project")) { await openNewProject(); return; }
  if (e.target.closest("#np-create")) { await createProject(); return; }

  const proj = e.target.closest("[data-project]");
  if (proj) {
    state.project = proj.dataset.project;
    state.episode = null;
    await loadProject();
    return;
  }
  const ep = e.target.closest("[data-episode]");
  if (ep) { state.episode = ep.dataset.episode; renderEpisodes(); renderLadder(); renderPipe(); return; }

  const tab = e.target.closest(".tab");
  if (tab) {
    state.tab = tab.dataset.tab;
    $$(".tab").forEach((t) => t.setAttribute("aria-selected", String(t === tab)));
    $$(".page").forEach((p) => p.classList.toggle("on", p.id === "tab-" + state.tab));
    // Поле промпта ведёт ТЕКСТОВЫЕ стадии конвейера; на ключах и голосах ему
    // нечего запускать, а обещание ввода, которое никуда не идёт, — обман.
    $(".composer").hidden = state.tab !== "pipe";
    if (state.tab === "keys") await renderKeys();
    if (state.tab === "models") await renderModels();
    if (state.tab === "mixer") await renderMixer();
    if (state.tab === "voices") await renderVoices();
    return;
  }

  const textBtn = e.target.closest("[data-text]");
  if (textBtn) {
    await runTextStage(textBtn.dataset.text, $("#prompt").value.trim());
    $("#prompt").value = "";
    return;
  }
  const play = e.target.closest("[data-play]");
  if (play) { playVoice(play.dataset.play, play); return; }
  const genOne = e.target.closest("[data-voice-gen]");
  if (genOne) {
    await generateVoices([genOne.dataset.voiceGen], genOne.dataset.voiceModel);
    return;
  }
  const genModel = e.target.closest("[data-voice-gen-model]");
  if (genModel) { await generateVoices(null, genModel.dataset.voiceGenModel); return; }
  if (e.target.closest("#voice-gen-all")) { await generateVoices(null); return; }

  const engBtn = e.target.closest("[data-engine]");
  if (engBtn && !engBtn.disabled) {
    state.engine = engBtn.dataset.engine;
    await loadText();
    return;
  }
  if (e.target.closest("#send")) {
    const text = $("#prompt").value.trim();
    if (!text) { toast("Скажи, что делать", true); return; }
    const stage = guessStage(text);
    if (!stage) {
      toast("Не понял, какая стадия. Нажми нужную кнопку рядом с полем.", true);
      return;
    }
    await runTextStage(stage, text);
    $("#prompt").value = "";
    return;
  }

  const mode = e.target.closest("[data-mode]");
  if (mode) { await saveSettings({ visual_mode: mode.dataset.mode }); return; }

  const textEngine = e.target.closest("[data-text-engine]");
  if (textEngine) { await saveTextChoice({ engine: textEngine.dataset.textEngine }); return; }

  const autonomy = e.target.closest("[data-autonomy]");
  if (autonomy) { await saveSettings({ autonomy: autonomy.dataset.autonomy }); return; }

  if (e.target.closest("#delete-project")) { askDeleteProject(); return; }
  if (e.target.closest("#dp-confirm")) { await deleteProject(); return; }

  const stage = e.target.closest("[data-stage]");
  if (stage) { await runStage(stage.dataset.stage); return; }

  if (e.target.closest("#cancel-task")) {
    try { await post("/api/cancel", {}); toast("Прервано"); } catch (err) { toast(err.message, true); }
    return;
  }

  const artifact = e.target.closest("[data-artifact]");
  if (artifact) { await showArtifact(artifact.dataset.artifact); return; }
  if (e.target.closest("#fc-report")) { await showFactCheckReport(); return; }
  // Кнопка рядом с состоянием: человек, прочитавший «не пройдена», не должен
  // искать ту же стадию в полосе внизу экрана.
  if (e.target.closest("#fc-run")) { await runTextStage("factcheck", ""); return; }
  // «Запустить конвейер» — это всегда СЛЕДУЮЩИЙ шаг резолвера: на пустом
  // проекте он и есть первая фаза, а какая именно — решает жанр. Панель не
  // выбирает стадию сама, иначе у конвейера появился бы второй порядок.
  if (e.target.closest("#run-pipeline")) {
    // Автономный режим не спрашивает сметы перед каждым шагом: человек уже
    // выбрал его тумблером, а тратами там правит потолок бюджета. В ручном
    // режиме смета показывается, как и раньше.
    const auto = state.data?.autonomy === "full";
    // Автономный прогон ведёт СЕРВЕР: панель показывает смету, спрашивает один
    // раз и просит начать. Своей цепочки шагов у браузера нет — закрытая
    // вкладка не должна её обрывать.
    if (auto) { await startAutonomous(); return; }
    const next = state.data?.next;
    if (!next) { toast("Делать нечего: всё закрыто или ждёт приёмки"); return; }
    if (next.kind === "paid") await runStage(next.run || next.stage);
    else if (next.kind === "text") {
      if (next.episode) state.episode = next.episode;
      await runTextStage(next.run || next.stage, "", next.episode);
    } else toast(`панель не умеет запускать стадию ${next.stage}`, true);
    return;
  }
  if (e.target.closest("#estimate-btn")) { await showEstimate(); return; }
  if (e.target.closest("#refresh-balances")) { await loadBalances(); return; }
  if (e.target.closest("#reload")) { await loadProject(); return; }

  const keyBtn = e.target.closest("[data-key]");
  if (keyBtn) { askKey(keyBtn.dataset.key); return; }

  const zoom = e.target.closest("[data-zoom]");
  if (zoom) {
    openDialog(`<h3>${esc(zoom.dataset.zoom)}</h3>
      <div class="frame"><img src="${zoom.getAttribute("src")}" alt=""></div>`, true);
    return;
  }

  const review = e.target.closest("[data-review]");
  if (review) { await doReview(review.dataset.review, review.dataset.item); return; }

  const approve = e.target.closest("[data-approve]");
  if (approve) {
    try {
      await post("/api/approve", { project: state.project, path: approve.dataset.approve });
      toast("Одобрено");
      await loadProject();
    } catch (err) { toast(err.message, true); }
  }
});

/* Удаление проекта. Подтверждение — имя целиком, а не «да»: внутри лежат
   оплаченные генерации, и отменить это нечем. Проверяет имя СЕРВЕР; диалог
   только не даёт нажать кнопку случайно. */
function askDeleteProject() {
  const name = state.project;
  if (!name) return;
  openDialog(`<h3>Удалить проект «${esc(name)}»?</h3>
    <p class="lead">Удаляется всё дерево: бриф, библия, сценарии, манифест и
      скачанные кадры, отрезки и озвучка. Оплаченные генерации исчезнут вместе
      с ними, вернуть их нельзя.</p>
    <div class="fld"><span>Введи имя проекта целиком</span>
      <input id="dp-name" type="text" autocomplete="off" placeholder="${esc(name)}"></div>
    <div class="actions">
      <button class="btn ghost" data-close>Отмена</button><span class="spacer"></span>
      <button class="btn danger" id="dp-confirm">Удалить навсегда</button>
    </div>`);
  const field = $("#dp-name");
  if (field) field.focus();
}

async function deleteProject() {
  const name = state.project;
  const typed = ($("#dp-name") || {}).value || "";
  try {
    await post("/api/delete", { project: name, confirm: typed.trim() });
    closeDialog();
    state.project = null;
    state.episode = null;
    state.data = null;
    await loadProjects();
    if (state.project) await loadProject();
    toast(`Проект ${name} удалён`);
  } catch (e) { toast(e.message, true); }
}

/* Выбор движка текста пишется тем же маршрутом, что и модели медиа: вопрос
   один — «какой моделью это делается», — и разводить его по двум ручкам значит
   однажды получить два разных ответа. Проверяет выбор сервер. */
async function saveTextChoice(patch) {
  try {
    const current = state.textChoice || {};
    await post("/api/models", {
      project: state.project,
      models: { text: { ...current, ...patch } },
    });
    toast("Сохранено в project.json");
    await renderModels();
    await loadProject();
  } catch (e) { toast(e.message, true); }
}

async function saveSettings(changes) {
  try {
    const saved = await post("/api/settings", { project: state.project, ...changes });
    await loadProject();
    toast("Сохранено в project.json");
    // Смена режима флагом не переписывает уже написанный план съёмки, а
    // конвейер идёт по плану. Промолчать значит дать человеку решить, что
    // отрезки сниматься не будут, — и всё равно списать за них деньги.
    (saved.warnings || []).forEach((w) => toast(w, true));
  } catch (e) { toast(e.message, true); }
}

async function doReview(action, item) {
  // Отклонение без причины бесполезно: причина уходит в манифест и потом
  // объясняет, почему кадр переснимали.
  const reason = action === "reject" ? prompt("Причина отклонения:") : null;
  if (action === "reject" && !reason) return;
  try {
    await post("/api/review", { project: state.project, item, action, reason });
    await loadProject();
  } catch (e) { toast(e.message, true); }
}

async function showEstimate() {
  try {
    const est = await api(`/api/estimate?project=${encodeURIComponent(state.project)}` +
                          `&episode=${encodeURIComponent(state.episode)}`);
    const rows = est.rows.map((r) => `<tr><td>${esc(r.stage)}</td>
      <td class="mono">${r.count}</td>
      <td class="mono right">${money(r.cost)}</td></tr>`).join("");
    openDialog(`<h3>Смета остатка · ${esc(state.episode)}</h3>
      <p class="lead">Сколько ещё стоит доснять эпизод. Уже снятое и принятое не считается.</p>
      <div class="tbl-wrap"><table>
        <thead><tr><th>стадия</th><th>шт</th><th class="right">сумма</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="3" class="muted">платить не за что</td></tr>'}</tbody>
        <tfoot><tr><td>Итого</td><td></td>
          <td class="mono right">${money(est.total)}</td></tr></tfoot>
      </table></div>
      ${est.problems.length ? `<p class="note err">${est.problems.map(esc).join("<br>")}</p>` : ""}`);
  } catch (e) { toast(e.message, true); }
}

document.addEventListener("change", async (e) => {
  if (e.target.id === "language") await saveSettings({ language: e.target.value });
  if (e.target.id === "episode-seconds") {
    // Секунды и только секунды: бриф хранит их, прогноз считает по ним, и
    // перевод в минутах по дороге означал бы, что человек вводит одно число, а
    // в файле лежит другое.
    const seconds = Number.parseInt(e.target.value, 10);
    if (!Number.isFinite(seconds) || seconds < 1) {
      toast("Длительность серии — целое число секунд", true);
      return;
    }
    await saveSettings({ episode_duration_sec: seconds });
  }
  if (e.target.id === "budget-limit") {
    // Пустое поле — снять потолок; сервер откажет, если режим автономный.
    const raw = e.target.value.trim();
    await saveSettings({ budget_usd: raw === "" ? null : Number(raw) });
  }
  if (e.target.id === "segment-seconds") {
    // Число уходит числом: сервер проверит его сеткой видеомодели — той же,
    // которой отказывает платная стадия.
    const seconds = Number.parseInt(e.target.value, 10);
    if (!Number.isFinite(seconds)) { toast("Длительность — целое число секунд", true); return; }
    await saveSettings({ segment_seconds: seconds });
  }
  if (e.target.id === "text-model") state.model = e.target.value;
  if (e.target.id === "voice-lang") { voiceLang = e.target.value; await renderVoices(); }
  if (e.target.id === "text-model-choice") {
    await saveTextChoice({ model: e.target.value });
  }
  if (e.target.id === "text-effort") {
    await saveTextChoice({ effort: e.target.value });
  }
  const roleSelect = e.target.closest("[data-role]");
  if (roleSelect) await chooseModel(roleSelect.dataset.role, roleSelect.value);
  const slider = e.target.closest("[data-mix]");
  if (slider) await commitMix(slider);
  // Выключенный мастеринг нельзя было включить обратно: ползунок был
  // заблокирован, а другого способа поменять null в брифе панель не давала.
  if (e.target.id === "lufs-on") {
    await saveMix({ target_lufs: e.target.checked
      ? Number($('[data-mix="target_lufs"]').value) : null });
    return;
  }
  const mute = e.target.closest("[data-mute]");
  if (mute) {
    const muted = $$("[data-mute]").filter((b) => b.checked)
      .map((b) => b.dataset.mute);
    await saveMix({ muted });
  }
});

// Поля мастера пишутся в черновик на каждый ввод: смена жанра или формата
// перерисовывает тело диалога, и без этого набранное пропадало бы.
document.addEventListener("input", (e) => {
  const slider = e.target.closest("[data-mix]");
  if (slider) { previewMix(slider); return; }
  const field = e.target.closest("[data-np]");
  if (!field) return;
  const key = field.dataset.np;
  draft[key] = field.type === "number" ? Number(field.value) : field.value;
  // Жанр и формат меняют состав полей — только они перерисовывают форму.
  if (key === "genre" || key === "format") {
    if (key === "genre") draft.visual_mode = "";
    renderNewProject();
  }
});

$("#theme").addEventListener("click", () => {
  const now = document.documentElement.getAttribute("data-theme");
  const dark = now === "dark"
    || (!now && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.setAttribute("data-theme", dark ? "light" : "dark");
});

/* Композер растёт и сжимается сам: кнопки стадий переносятся по ширине окна,
   а строка контекста — по числу движков. Поэтому высоту меряем не один раз, а
   при каждом изменении: иначе нижний край страницы снова уедет под него. */
if (typeof ResizeObserver === "function") {
  const inner = $(".composer .inner");
  if (inner) new ResizeObserver(fitComposer).observe(inner);
}
window.addEventListener("resize", fitComposer);

/* ── Старт ─────────────────────────────────────────── */
(async () => {
  fitComposer();
  await loadProjects();
  await loadEnvironment();
  await loadProject();
  await loadBalances();
  await pollTask();          // вдруг задача уже идёт: сервер её пережил
})();
