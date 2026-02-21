const STORAGE_KEY = "english-loop-state-v2";
const SITE_UPDATED_AT = "2026-02-21 12:42:54";
const LEVEL_JSON_PATH = "data/processed/level_recommendations.json";

const defaultLessons = [
  { id: "l1", title: "Airport Basics", tag: "travel", cards: ["Where is gate 12?", "Can I have a window seat?"] },
  { id: "l2", title: "Small Talk", tag: "daily", cards: ["How was your weekend?", "That sounds great."] },
  { id: "l3", title: "Work Email", tag: "business", cards: ["Please find attached.", "Could you review this by EOD?"] }
];

const defaultState = {
  profile: { level: "A1", score: 0 },
  lessons: defaultLessons,
  srs: {},
  stats: { learned: 0, reviewed: 0, streak: 0 },
  subscription: { plan: "free", converted: false },
  users: [],
  currentUserId: null,
  auditLogs: []
};

const diagQuestions = [
  { id: "q1", text: "영어로 자기소개가 가능한가요?", score: 1 },
  { id: "q2", text: "영어 이메일을 이해할 수 있나요?", score: 2 },
  { id: "q3", text: "회의에서 간단히 의견을 낼 수 있나요?", score: 2 },
  { id: "q4", text: "원어민 발화를 70% 이상 이해하나요?", score: 3 },
  { id: "q5", text: "업무 협상 영어가 가능한가요?", score: 4 }
];

function loadState() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return structuredClone(defaultState);

  const parsed = JSON.parse(raw);
  const merged = { ...structuredClone(defaultState), ...parsed };

  if (!Array.isArray(merged.users)) merged.users = [];
  if (!Array.isArray(merged.auditLogs)) merged.auditLogs = [];
  if (!Array.isArray(merged.lessons) || merged.lessons.length === 0) merged.lessons = defaultLessons;
  if (!merged.stats) merged.stats = { learned: 0, reviewed: 0, streak: 0 };
  if (!merged.subscription) merged.subscription = { plan: "free", converted: false };

  return merged;
}

const state = loadState();
let currentCard = null;

function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function hashPassword(input) {
  return btoa(unescape(encodeURIComponent(input)));
}

function currentUser() {
  if (!state.currentUserId) return null;
  return state.users.find((u) => u.id === state.currentUserId) || null;
}

function isAdmin() {
  return currentUser()?.role === "admin";
}

function addAuditLog(action, detail = "") {
  const user = currentUser();
  const actor = user ? `${user.email}(${user.role})` : "guest";
  state.auditLogs.unshift({
    ts: new Date().toISOString(),
    actor,
    action,
    detail
  });
  state.auditLogs = state.auditLogs.slice(0, 200);
}

function ensureSeedAdmin() {
  const hasAdmin = state.users.some((u) => u.role === "admin");
  if (hasAdmin) return;
  state.users.push({
    id: `u${Date.now()}`,
    email: "admin@english-loop.local",
    passwordHash: hashPassword("Admin1234"),
    role: "admin",
    createdAt: new Date().toISOString()
  });
  saveState();
}

function validateEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function validatePassword(password) {
  return typeof password === "string" && password.length >= 6;
}

function allCards() {
  return state.lessons.flatMap((lesson) => lesson.cards.map((text, idx) => ({
    key: `${lesson.id}:${idx}`,
    lesson: lesson.title,
    tag: lesson.tag,
    text
  })));
}

function dueCards() {
  const now = Date.now();
  return allCards().filter((c) => {
    const item = state.srs[c.key];
    return !item || item.nextDue <= now;
  });
}

function toLessonFromReco(item, idx) {
  const meaning = item.meaning_1_ko || item.meaning_1 || "";
  const example = (item.examples_by_meaning || []).flatMap((b) => b.examples || [])[0] || "";
  const title = `${item.lemma}${item.pos ? ` (${item.pos})` : ""}`;
  const card = [
    `${item.lemma} — ${meaning}`.trim(),
    example
  ].filter(Boolean).join("\n");

  return {
    id: `reco-${idx + 1}`,
    title,
    tag: "db-recommendation",
    cards: [card || item.lemma]
  };
}

async function loadRecommendationsIntoLessons() {
  try {
    const res = await fetch(LEVEL_JSON_PATH);
    if (!res.ok) return;
    const data = await res.json();
    const level = state.profile?.level || "A1";
    const levelItems = data?.levels?.[level] || data?.levels?.A1 || [];
    if (!Array.isArray(levelItems) || levelItems.length === 0) return;

    const mapped = levelItems.slice(0, 120).map(toLessonFromReco);
    if (mapped.length > 0) {
      state.lessons = mapped;
      saveState();
    }
  } catch {
    // fallback to default lessons silently
  }
}

function pickLearningCard() {
  const cards = dueCards();
  currentCard = cards[0] || allCards()[0];
  const el = document.getElementById("learning-card");
  if (!currentCard) {
    el.textContent = "학습 카드가 없습니다.";
    return;
  }
  el.innerHTML = `<strong>[${currentCard.lesson}]</strong><p>${currentCard.text}</p>`;
}

function applySrs(key, quality) {
  const prev = state.srs[key] || { intervalDays: 0, ease: 2.5 };
  const interval = quality === "good" ? Math.max(1, Math.round((prev.intervalDays || 1) * prev.ease)) : 1;
  const ease = quality === "good" ? Math.min(2.8, prev.ease + 0.1) : Math.max(1.3, prev.ease - 0.2);
  const nextDue = Date.now() + interval * 24 * 60 * 60 * 1000;
  state.srs[key] = { intervalDays: interval, ease, nextDue };
  state.stats.reviewed += 1;
  saveState();
}

function renderDiag() {
  const form = document.getElementById("diag-form");
  form.innerHTML = diagQuestions.map((q) => `
    <label><input type="checkbox" value="${q.score}"/> ${q.text}</label><br/>
  `).join("");
}

function submitDiag() {
  const checks = [...document.querySelectorAll("#diag-form input:checked")];
  const score = checks.reduce((a, c) => a + Number(c.value), 0);
  const level = score < 4 ? "A1" : score < 7 ? "A2" : score < 10 ? "B1" : "B2+";
  state.profile = { level, score };
  saveState();
  document.getElementById("diag-result").textContent = `진단 완료: ${level} (점수 ${score})`;
  renderProgress();
}

function renderReview() {
  const due = dueCards();
  document.getElementById("review-summary").textContent = `오늘 복습 대기: ${due.length}개`;
  document.getElementById("review-list").innerHTML = due.slice(0, 10).map((d) => `<li>${d.text} <small>#${d.tag}</small></li>`).join("");
}

function renderProgress() {
  const totalCards = allCards().length;
  const reviewed = state.stats.reviewed;
  const mastery = Object.keys(state.srs).length;
  document.getElementById("progress-board").innerHTML = `
    <p>레벨: <strong>${state.profile.level}</strong></p>
    <p>총 카드: ${totalCards}</p>
    <p>복습 누적: ${reviewed}</p>
    <p>SRS 등록 카드: ${mastery}</p>
    <p>구독 플랜: ${state.subscription.plan}</p>
  `;
}

function searchLessons() {
  const q = document.getElementById("search-input").value.trim().toLowerCase();
  const matches = state.lessons
    .filter((l) => l.title.toLowerCase().includes(q) || l.tag.toLowerCase().includes(q))
    .slice(0, 6);
  const results = matches.length ? matches : state.lessons.slice(0, 3);
  document.getElementById("search-results").innerHTML = results
    .map((r) => `<li>${r.title} <small>#${r.tag}</small></li>`)
    .join("");
}

function selectPlan(plan) {
  const before = state.subscription.plan;
  state.subscription.plan = plan;
  state.subscription.converted = plan !== "trial" && plan !== "free";
  addAuditLog("subscription_change", `${before} -> ${plan}`);
  saveState();
  document.getElementById("subscribe-state").textContent = `현재 선택: ${plan}`;
  renderProgress();
  renderAuditLog();
}

function addLessonByAdmin() {
  if (!isAdmin()) {
    alert("관리자만 레슨을 추가할 수 있습니다.");
    return;
  }

  const title = document.getElementById("admin-title").value.trim();
  const tag = document.getElementById("admin-tag").value.trim() || "custom";
  const content = document.getElementById("admin-content").value.trim();
  if (!title || !content) return;
  const lesson = { id: `l${Date.now()}`, title, tag, cards: content.split(/\n+/).filter(Boolean) };
  state.lessons.push(lesson);
  addAuditLog("lesson_add", title);
  saveState();

  document.getElementById("admin-title").value = "";
  document.getElementById("admin-tag").value = "";
  document.getElementById("admin-content").value = "";

  renderAuditLog();
  renderReview();
  renderProgress();
  searchLessons();
}

function setAuthMessage(msg, isError = false) {
  const el = document.getElementById("auth-message");
  el.textContent = msg;
  el.className = isError ? "msg error" : "msg success";
}

function register() {
  const email = document.getElementById("signup-email").value.trim().toLowerCase();
  const password = document.getElementById("signup-password").value;
  const role = document.getElementById("signup-role").value;

  if (!validateEmail(email)) return setAuthMessage("올바른 이메일 형식이 아닙니다.", true);
  if (!validatePassword(password)) return setAuthMessage("비밀번호는 6자 이상이어야 합니다.", true);
  if (!["learner", "admin"].includes(role)) return setAuthMessage("권한(role) 값이 유효하지 않습니다.", true);
  if (state.users.some((u) => u.email === email)) return setAuthMessage("이미 가입된 이메일입니다.", true);

  const user = {
    id: `u${Date.now()}`,
    email,
    passwordHash: hashPassword(password),
    role,
    createdAt: new Date().toISOString()
  };

  state.users.push(user);
  state.currentUserId = user.id;
  addAuditLog("signup", `${email} (${role})`);
  addAuditLog("login", "after signup");
  saveState();

  document.getElementById("signup-password").value = "";
  document.getElementById("login-password").value = "";
  setAuthMessage(`가입 완료 및 로그인됨: ${email}`);
  renderUserPanel();
  renderAdminAccess();
  renderAuditLog();
}

function login() {
  const email = document.getElementById("login-email").value.trim().toLowerCase();
  const password = document.getElementById("login-password").value;

  if (!validateEmail(email)) return setAuthMessage("올바른 이메일 형식이 아닙니다.", true);
  if (!validatePassword(password)) return setAuthMessage("비밀번호는 6자 이상이어야 합니다.", true);

  const user = state.users.find((u) => u.email === email);
  if (!user || user.passwordHash !== hashPassword(password)) {
    return setAuthMessage("이메일 또는 비밀번호가 일치하지 않습니다.", true);
  }

  state.currentUserId = user.id;
  addAuditLog("login", email);
  saveState();

  document.getElementById("login-password").value = "";
  setAuthMessage(`로그인 성공: ${email}`);
  renderUserPanel();
  renderAdminAccess();
  renderAuditLog();
}

function logout() {
  const user = currentUser();
  if (!user) return;
  addAuditLog("logout", user.email);
  state.currentUserId = null;
  saveState();

  setAuthMessage("로그아웃 되었습니다.");
  renderUserPanel();
  renderAdminAccess();
  renderAuditLog();
}

function renderUserPanel() {
  const user = currentUser();
  const badge = document.getElementById("current-user");
  const logoutBtn = document.getElementById("logout-btn");

  if (!user) {
    badge.textContent = "현재 사용자: guest (role: none)";
    logoutBtn.disabled = true;
    return;
  }

  badge.textContent = `현재 사용자: ${user.email} (role: ${user.role})`;
  logoutBtn.disabled = false;
}

function renderAdminAccess() {
  const guard = document.getElementById("admin-guard");
  const controls = document.getElementById("admin-controls");
  if (isAdmin()) {
    guard.textContent = "관리자 권한 확인됨";
    guard.className = "msg success";
    controls.style.display = "block";
  } else {
    guard.textContent = "관리자 전용 영역입니다. admin 계정으로 로그인하세요.";
    guard.className = "msg error";
    controls.style.display = "none";
  }
}

function renderAuditLog() {
  const container = document.getElementById("audit-log");
  container.innerHTML = state.auditLogs.slice(0, 10).map((log) => {
    const ts = new Date(log.ts).toLocaleString();
    return `<li><strong>${log.action}</strong> - ${log.actor} <small>${log.detail || ""}</small> <br/><small>${ts}</small></li>`;
  }).join("");
}

function bindEvents() {
  document.getElementById("diag-submit").addEventListener("click", submitDiag);
  document.getElementById("btn-good").addEventListener("click", () => {
    if (!currentCard) return;
    applySrs(currentCard.key, "good");
    pickLearningCard();
    renderReview();
    renderProgress();
  });
  document.getElementById("btn-again").addEventListener("click", () => {
    if (!currentCard) return;
    applySrs(currentCard.key, "again");
    pickLearningCard();
    renderReview();
  });
  document.getElementById("btn-next").addEventListener("click", pickLearningCard);
  document.getElementById("search-btn").addEventListener("click", searchLessons);
  document.querySelectorAll(".plan-btn").forEach((btn) => btn.addEventListener("click", () => selectPlan(btn.dataset.plan)));
  document.getElementById("admin-add").addEventListener("click", addLessonByAdmin);

  document.getElementById("signup-btn").addEventListener("click", register);
  document.getElementById("login-btn").addEventListener("click", login);
  document.getElementById("logout-btn").addEventListener("click", logout);
}

function renderUpdateTimestamp() {
  const el = document.getElementById("update-timestamp");
  if (!el) return;
  el.textContent = `업데이트: ${SITE_UPDATED_AT}`;
}

async function init() {
  renderUpdateTimestamp();
  ensureSeedAdmin();
  await loadRecommendationsIntoLessons();
  renderDiag();
  bindEvents();
  pickLearningCard();
  renderReview();
  renderProgress();
  searchLessons();
  renderUserPanel();
  renderAdminAccess();
  renderAuditLog();
  document.getElementById("subscribe-state").textContent = `현재 선택: ${state.subscription.plan}`;
}

init();
