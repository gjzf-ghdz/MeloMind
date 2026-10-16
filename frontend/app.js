// ============================================================
// MeloMind - Frontend Music Recommender (Standalone / Offline)
// All backend logic ported to JavaScript
// ============================================================

let currentSongs = [];
let lastAnalysis = null;

// 直接打开 index.html (file://) 时，API 请求指向本地服务器
const API_BASE = (location.protocol === 'file:') ? 'http://localhost:8000' : '';

// ============================================================
// 0. AUTH (登录 / 注册 / 会话)
// ============================================================
let authToken = null;
let currentUser = null;

const TOKEN_KEY = 'melomind_token';

function loadStoredToken() {
  try {
    authToken = localStorage.getItem(TOKEN_KEY) || null;
  } catch (e) {
    authToken = null;
  }
}

function saveToken(token) {
  authToken = token;
  try { localStorage.setItem(TOKEN_KEY, token); } catch (e) {}
}

function clearToken() {
  authToken = null;
  try { localStorage.removeItem(TOKEN_KEY); } catch (e) {}
}

async function apiRequest(path, options = {}) {
  const headers = Object.assign({ 'Content-Type': 'application/json' }, options.headers || {});
  if (authToken) headers['Authorization'] = 'Bearer ' + authToken;
  try {
    const resp = await fetch(API_BASE + path, {
      method: options.method || 'GET',
      headers,
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
    let data = null;
    try { data = await resp.json(); } catch (e) { data = null; }
    return { ok: resp.ok, status: resp.status, data };
  } catch (e) {
    const hint = '请确认后端服务已启动，并通过 http://localhost:8000 访问。';
    return { ok: false, status: 0, data: { ok: false, error: '网络请求失败：' + (e && e.message ? e.message : '无法连接服务器') + '。' + hint } };
  }
}

function openAuthModal(tab) {
  const modal = document.getElementById('authModal');
  if (!modal) return;
  modal.style.display = 'flex';
  switchAuthTab(tab || 'login');
  clearAuthError();
}

function closeAuthModal() {
  const modal = document.getElementById('authModal');
  if (modal) modal.style.display = 'none';
  clearAuthError();
}

function switchAuthTab(mode) {
  const loginForm = document.getElementById('loginForm');
  const registerForm = document.getElementById('registerForm');
  const tabLogin = document.getElementById('tabLogin');
  const tabRegister = document.getElementById('tabRegister');
  if (!loginForm || !registerForm) return;
  if (mode === 'register') {
    loginForm.style.display = 'none';
    registerForm.style.display = '';
    if (tabLogin) tabLogin.classList.remove('active');
    if (tabRegister) tabRegister.classList.add('active');
  } else {
    loginForm.style.display = '';
    registerForm.style.display = 'none';
    if (tabRegister) tabRegister.classList.remove('active');
    if (tabLogin) tabLogin.classList.add('active');
  }
  clearAuthError();
}

function showAuthError(msg) {
  const el = document.getElementById('authError');
  if (!el) return;
  el.textContent = msg || '';
  el.style.display = msg ? 'block' : 'none';
}

function clearAuthError() {
  showAuthError('');
}

function validateUsernameLocal(v) {
  if (!v) return '用户名不能为空';
  if (!/^[A-Za-z0-9_]{3,20}$/.test(v)) return '用户名需为 3-20 位字母、数字或下划线';
  return '';
}

function validatePasswordLocal(v) {
  if (!v) return '密码不能为空';
  if (v.length < 6 || v.length > 32) return '密码长度需为 6-32 位';
  return '';
}

async function doLogin() {
  clearAuthError();
  const btn = document.querySelector('#loginForm .auth-btn');
  const origText = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = '登录中...'; }
  try {
    const username = (document.getElementById('loginUsername').value || '').trim();
    const password = document.getElementById('loginPassword').value || '';
    let err = validateUsernameLocal(username) || validatePasswordLocal(password);
    if (err) { showAuthError(err); return; }

    const r = await apiRequest('/api/login', { method: 'POST', body: { username, password } });
    if (!r.ok || !r.data || !r.data.ok) {
      showAuthError((r.data && r.data.error) || '登录失败，请稍后重试');
      return;
    }
    saveToken(r.data.token);
    currentUser = r.data.user;
    await loadFavorites();
    await loadHistory();
    applyUserState();
    closeAuthModal();
    addMsg('登录成功，欢迎回来，' + (currentUser.username || '') + '！', 'sys');
  } catch (e) {
    console.error('登录异常:', e);
    showAuthError('登录失败：' + (e && e.message ? e.message : '未知错误，请重试'));
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = origText || '登录'; }
  }
}

async function doRegister() {
  clearAuthError();
  const btn = document.querySelector('#registerForm .auth-btn');
  const origText = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = '注册中...'; }
  try {
    const username = (document.getElementById('regUsername').value || '').trim();
    const password = document.getElementById('regPassword').value || '';
    const password2 = document.getElementById('regPassword2').value || '';
    let err = validateUsernameLocal(username) || validatePasswordLocal(password);
    if (err) { showAuthError(err); return; }
    if (password !== password2) { showAuthError('两次输入的密码不一致'); return; }

    const r = await apiRequest('/api/register', {
      method: 'POST',
      body: { username, password },
    });
    if (!r.ok || !r.data || !r.data.ok) {
      showAuthError((r.data && r.data.error) || '注册失败，请稍后重试');
      return;
    }
    saveToken(r.data.token);
    currentUser = r.data.user;
    await loadFavorites();
    await loadHistory();
    applyUserState();
    closeAuthModal();
    addMsg('注册成功，已自动登录，欢迎 ' + (currentUser.username || '') + '！', 'sys');
    // 新用户先做偏好调查，再功能导览
    setTimeout(openPrefSurvey, 600);
  } catch (e) {
    console.error('注册异常:', e);
    showAuthError('注册失败：' + (e && e.message ? e.message : '未知错误，请重试'));
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = origText || '注册'; }
  }
}

async function doLogout() {
  await apiRequest('/api/logout', { method: 'POST' });
  clearToken();
  currentUser = null;
  clearFavorites();
  clearHistoryState();
  applyUserState();
  addMsg('已登出。', 'sys');
}

async function loadMe() {
  if (!authToken) { applyUserState(); return; }
  const r = await apiRequest('/api/me');
  if (r.ok && r.data && r.data.ok) {
    currentUser = r.data.user;
    await loadFavorites();
    await loadHistory();
  } else {
    clearToken();
    currentUser = null;
    clearFavorites();
    clearHistoryState();
  }
  applyUserState();
}

function applyUserState() {
  const guest = document.querySelector('#userInfo .user-info-guest');
  const logged = document.querySelector('#userInfo .user-info-logged');
  const nameEl = document.getElementById('userInfoName');
  if (currentUser) {
    if (guest) guest.style.display = 'none';
    if (logged) logged.style.display = 'flex';
    if (nameEl) {
      nameEl.textContent = '👤 ' + (currentUser.username || '');
      nameEl.title = '点击进入个人中心';
    }
  } else {
    if (guest) guest.style.display = 'flex';
    if (logged) logged.style.display = 'none';
  }
}

function requireAuth() {
  if (currentUser) return true;
  openAuthModal('login');
  showAuthError('请先登录后再发送对话');
  return false;
}

// ============================================================
// 0b. FAVORITES (收藏夹)
// ============================================================
let currentFavorites = [];
let favKeys = new Set();

function favKeyFor(song) {
  if (!song) return '';
  const id = (song.id || '').toString().trim();
  if (id) return 'id:' + id;
  const sm = (song.songmid || '').toString().trim();
  if (sm) return 'sm:' + sm;
  const title = (song.title || '').toString().trim();
  const artist = (song.artist || '').toString().trim();
  return 'ta:' + title + '|' + artist;
}

function isFavorited(song) {
  return favKeys.has(favKeyFor(song));
}

function clearFavorites() {
  currentFavorites = [];
  favKeys = new Set();
  updateFavEntryCount();
}

function clearHistoryState() {
  currentHistory = [];
  updateHistoryEntryCount();
}

function updateFavEntryCount() {
  const el = document.getElementById('profileFavCount');
  if (el) el.textContent = String(currentFavorites.length);
}

async function loadFavorites() {
  const r = await apiRequest('/api/favorites', { method: 'GET' });
  if (r.ok && r.data && r.data.ok) {
    currentFavorites = Array.isArray(r.data.favorites) ? r.data.favorites : [];
  } else {
    currentFavorites = [];
  }
  favKeys = new Set(currentFavorites.map(favKeyFor));
  updateFavEntryCount();
}

async function toggleFavorite(index) {
  const song = currentSongs[index];
  if (!song) return;
  if (!requireAuth()) return;
  const key = favKeyFor(song);
  const favorited = favKeys.has(key);
  if (favorited) {
    const r = await apiRequest('/api/favorites/remove', { method: 'POST', body: { fav_key: key } });
    if (r.ok && r.data && r.data.ok) {
      favKeys.delete(key);
      currentFavorites = currentFavorites.filter(s => favKeyFor(s) !== key);
    } else {
      addMsg('取消收藏失败：' + ((r.data && r.data.error) || '未知错误'), 'sys');
      return;
    }
  } else {
    const r = await apiRequest('/api/favorites/add', { method: 'POST', body: { song } });
    if (r.ok && r.data && r.data.ok) {
      favKeys.add(key);
      currentFavorites.push(song);
    } else {
      addMsg('收藏失败：' + ((r.data && r.data.error) || '未知错误'), 'sys');
      return;
    }
  }
  updateFavEntryCount();
  refreshFavoriteButtons();
  const profileModal = document.getElementById('profileModal');
  const favPane = document.getElementById('profilePaneFav');
  if (profileModal && profileModal.style.display !== 'none' &&
      favPane && favPane.style.display !== 'none') {
    renderFavorites();
  }
}

function refreshFavoriteButtons() {
  document.querySelectorAll('.fav-btn[data-fav-index]').forEach(btn => {
    const i = parseInt(btn.getAttribute('data-fav-index'), 10);
    const song = currentSongs[i];
    if (!song) return;
    const favorited = favKeys.has(favKeyFor(song));
    btn.classList.toggle('favorited', favorited);
    btn.innerHTML = favorited ? '\u{2764} 已收藏' : '\u{2661} 收藏';
  });
}

async function removeFavorite(index) {
  const song = currentFavorites[index];
  if (!song) return;
  const key = favKeyFor(song);
  const r = await apiRequest('/api/favorites/remove', { method: 'POST', body: { fav_key: key } });
  if (r.ok && r.data && r.data.ok) {
    favKeys.delete(key);
    currentFavorites = currentFavorites.filter(s => favKeyFor(s) !== key);
    updateFavEntryCount();
    renderFavorites();
    refreshFavoriteButtons();
  } else {
    addMsg('取消收藏失败：' + ((r.data && r.data.error) || '未知错误'), 'sys');
  }
}

function renderFavorites() {
  const list = document.getElementById('profilePaneFav');
  if (!list) return;
  updateFavEntryCount();
  if (!currentFavorites.length) {
    list.innerHTML = '<div class="fav-empty"><div class="fav-empty-icon">\u{266B}</div><p>还没有收藏的歌曲<br>在推荐结果中点击 \u{2764} 收藏喜欢的音乐</p></div>';
    return;
  }
  const genreEmoji = {
    ambient:'\u{1F30A}',classical:'\u{1F3B9}',electronic:'\u{1F3A7}',
    rock:'\u{1F3B8}',pop:'\u{1F3B5}',folk:'\u{1F3BB}',hiphop:'\u{1F3A4}',
    indie:'\u{1F3B6}',jazz:'\u{1F3BA}','r&b':'\u{1F3B9}',
    'neo-classical':'\u{1F3B9}',minimalist:'\u{1F30A}',
  };
  list.innerHTML = currentFavorites.map((s, i) => {
    const emoji = genreEmoji[s.genre] || '\u{1F3B5}';
    const dots = Array.from({length:10}, (_,j) =>
      '<div class="edot'+(j < s.energy ? ' on':'')+'"></div>').join('');
    return '<div class="card" onclick="openFavSongQQMusic('+i+')">' +
      '<div class="card-top">' +
        '<div class="card-cover">' +
          (s.cover_url ? '<img src="'+s.cover_url+'" alt="" onerror="this.parentElement.innerHTML=\''+emoji+'\'">' : emoji) +
        '</div>' +
        '<div class="card-info">' +
          '<div class="card-title">'+s.title+'</div>' +
          '<div class="card-artist">'+s.artist+' \u00B7 '+s.album+'</div>' +
          '<div class="card-meta">' +
            '<span class="meta-tag accent">'+(s.source==='qqmusic'?'QQ音乐':(s.source||''))+'</span>' +
            '<span class="meta-tag">'+s.genre+'</span>' +
            '<span class="meta-tag">'+s.tempo_bpm+' BPM</span>' +
            (s.instrumental ? '<span class="meta-tag">纯音乐</span>' : '') +
          '</div>' +
        '</div>' +
        '<div class="card-energy"><div class="edots">'+dots+'</div></div>' +
      '</div>' +
      (s.reason ? '<div class="card-reason">\u{1F4A1} '+s.reason+'</div>' : '') +
      '<div class="card-footer">' +
        '<button class="mini-btn primary" onclick="event.stopPropagation(); openFavSongQQMusic('+i+')">\u{1F517} QQ音乐</button>' +
        '<button class="mini-btn fav-btn favorited" onclick="event.stopPropagation(); removeFavorite('+i+')">\u{2764} 取消收藏</button>' +
      '</div>' +
    '</div>';
  }).join('');
}

function openFavSongQQMusic(index) {
  const song = currentFavorites[index];
  if (!song) return;
  if (song.external_url) window.open(song.external_url, '_blank');
}

// ============================================================
// 0c. HISTORY (搜索历史)
// ============================================================
let currentHistory = [];

function updateHistoryEntryCount() {
  const el = document.getElementById('profileHistCount');
  if (el) el.textContent = String(currentHistory.length);
}

async function saveHistory(query, taskType, songs, reply) {
  if (!currentUser || !query) return;
  try {
    await apiRequest('/api/history', {
      method: 'POST',
      body: { query, task_type: taskType, songs: songs || [], reply: reply || '' },
    });
  } catch (e) { /* 静默失败，不影响推荐体验 */ }
}

async function loadHistory() {
  const r = await apiRequest('/api/history', { method: 'GET' });
  if (r.ok && r.data && r.data.ok) {
    currentHistory = Array.isArray(r.data.history) ? r.data.history : [];
  } else {
    currentHistory = [];
  }
  updateHistoryEntryCount();
}

function renderHistory() {
  const container = document.getElementById('profilePaneHist');
  if (!container) return;
  updateHistoryEntryCount();

  if (!currentHistory.length) {
    container.innerHTML = '<div class="fav-empty"><div class="fav-empty-icon">\u{1F552}</div><p>还没有搜索记录<br>发送消息后这里会显示你的搜索历史</p></div>';
    return;
  }

  let html = '';
  for (let i = 0; i < currentHistory.length; i++) {
    const rec = currentHistory[i];
    const time = rec.timestamp || '';
    const taskLabel = rec.task_type ? `<span class="hist-task">${escapeHtml(rec.task_type)}</span>` : '';
    let songsHtml = '';
    for (const s of (rec.songs || []).slice(0, 4)) {
      const title = escapeHtml(s.title || '');
      const artist = escapeHtml(s.artist || '');
      const url = s.qqmusic_url || s.external_url || '';
      const link = url ? `<a href="${escapeHtml(url)}" target="_blank" class="hist-song-link">${title}</a>` : `<span class="hist-song-title">${title}</span>`;
      songsHtml += `<span class="hist-song">${link}<span class="hist-artist">${artist}</span></span>`;
    }
    const moreCount = (rec.songs || []).length > 4 ? ` <span class="hist-more">+${rec.songs.length - 4}</span>` : '';
    html += `<div class="hist-item" onclick="replayHistory(${i})">
      <div class="hist-time">${escapeHtml(time)}</div>
      <div class="hist-query">${escapeHtml(rec.query || '')}</div>
      <div class="hist-meta">${taskLabel}</div>
      <div class="hist-songs">${songsHtml}${moreCount}</div>
      <div class="hist-replay">点击回放 &rarr;</div>
    </div>`;
  }
  container.innerHTML = html;
}

function replayHistory(index) {
  const rec = currentHistory[index];
  if (!rec) return;
  closeProfileModal();
  addMsg(rec.query || '', 'user');
  if (rec.reply) {
    addMsg(rec.reply, 'sys');
  } else {
    addMsg('回放历史记录：' + (rec.timestamp || '') + ' 的搜索结果', 'sys');
  }
  const replaySongs = (rec.songs || []).map(s => ({
    title: s.title || '',
    artist: s.artist || '',
    album: '历史记录',
    source: 'qqmusic',
    genre: 'pop',
    energy: 5,
    tempo_bpm: 0,
    instrumental: false,
    reason: '来自历史记录的推荐',
    cover_url: '',
    external_url: s.qqmusic_url || '',
    search_keyword: s.search_keyword || '',
    id: '',
    songmid: '',
  }));
  renderSongs(replaySongs);
  const chat = document.getElementById('chatMsgs');
  if (chat) chat.scrollTop = chat.scrollHeight;
  const recs = document.querySelector('.recs-scroll');
  if (recs) recs.scrollTop = 0;
}

// ============================================================
// 0d. PROFILE (个人中心)
// ============================================================
function openProfileModal(tab) {
  if (!requireAuth()) return;
  const modal = document.getElementById('profileModal');
  if (!modal) return;
  modal.style.display = 'flex';
  fillProfileInfo();
  switchProfileTab(tab || 'account');
  refreshMe();
}

function closeProfileModal() {
  const modal = document.getElementById('profileModal');
  if (modal) modal.style.display = 'none';
  clearProfileMsg();
}

function switchProfileTab(mode) {
  const panes = {
    account: document.getElementById('profilePaneAccount'),
    favorites: document.getElementById('profilePaneFav'),
    history: document.getElementById('profilePaneHist'),
  };
  const tabs = {
    account: document.getElementById('ptabAccount'),
    favorites: document.getElementById('ptabFav'),
    history: document.getElementById('ptabHist'),
  };
  Object.keys(panes).forEach(k => {
    if (panes[k]) panes[k].style.display = (k === mode) ? '' : 'none';
    if (tabs[k]) tabs[k].classList.toggle('active', k === mode);
  });
  if (mode === 'favorites') {
    loadFavorites().then(renderFavorites);
  } else if (mode === 'history') {
    loadHistory().then(renderHistory);
  }
  clearProfileMsg();
}

function fillProfileInfo() {
  if (!currentUser) return;
  const uname = currentUser.username || '';
  const uEl = document.getElementById('profileUsername');
  const pEl = document.getElementById('profilePhone');
  const cEl = document.getElementById('profileCreatedAt');
  const labelEl = document.getElementById('profileUserLabel');
  if (uEl) uEl.textContent = uname;
  if (pEl) pEl.textContent = currentUser.phone || '--';
  if (cEl) cEl.textContent = (currentUser.created_at || '').replace('T', ' ') || '--';
  if (labelEl) labelEl.textContent = '@' + uname;
}

async function refreshMe() {
  const r = await apiRequest('/api/me');
  if (r.ok && r.data && r.data.ok) {
    currentUser = r.data.user;
    applyUserState();
  }
  fillProfileInfo();
}

function showProfileMsg(msg, isError) {
  const el = document.getElementById('profileMsg');
  if (!el) return;
  el.textContent = msg || '';
  el.style.display = msg ? 'block' : 'none';
  el.classList.toggle('err', !!isError);
  el.classList.toggle('ok', !isError);
}

function clearProfileMsg() {
  showProfileMsg('', false);
}

async function doChangeUsername() {
  clearProfileMsg();
  const newUsername = (document.getElementById('pfNewUsername').value || '').trim();
  const password = document.getElementById('pfUsernamePassword').value || '';
  const err = validateUsernameLocal(newUsername);
  if (err) { showProfileMsg(err, true); return; }
  if (!password) { showProfileMsg('请输入当前密码以确认身份', true); return; }
  const btn = document.getElementById('pfUsernameBtn');
  if (btn) { btn.disabled = true; btn.textContent = '保存中...'; }
  try {
    const r = await apiRequest('/api/user/update_username', {
      method: 'POST',
      body: { username: newUsername, password },
    });
    if (!r.ok || !r.data || !r.data.ok) {
      showProfileMsg((r.data && r.data.error) || '修改失败，请稍后重试', true);
      return;
    }
    currentUser = Object.assign({}, currentUser, r.data.user);
    applyUserState();
    fillProfileInfo();
    const in1 = document.getElementById('pfNewUsername');
    const in2 = document.getElementById('pfUsernamePassword');
    if (in1) in1.value = '';
    if (in2) in2.value = '';
    showProfileMsg('用户名已修改为 ' + r.data.user.username + '，收藏夹与历史记录已一并迁移');
  } catch (e) {
    console.error('修改用户名异常:', e);
    showProfileMsg('修改失败：' + (e && e.message ? e.message : '未知错误'), true);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '保存新用户名'; }
  }
}

async function doChangePassword() {
  clearProfileMsg();
  const oldPw = document.getElementById('pfOldPassword').value || '';
  const newPw = document.getElementById('pfNewPassword').value || '';
  const newPw2 = document.getElementById('pfNewPassword2').value || '';
  if (!oldPw) { showProfileMsg('请输入原密码', true); return; }
  const err = validatePasswordLocal(newPw);
  if (err) { showProfileMsg(err, true); return; }
  if (newPw !== newPw2) { showProfileMsg('两次输入的新密码不一致', true); return; }
  const btn = document.getElementById('pfPasswordBtn');
  if (btn) { btn.disabled = true; btn.textContent = '保存中...'; }
  try {
    const r = await apiRequest('/api/user/change_password', {
      method: 'POST',
      body: { old_password: oldPw, new_password: newPw },
    });
    if (!r.ok || !r.data || !r.data.ok) {
      showProfileMsg((r.data && r.data.error) || '修改失败，请稍后重试', true);
      return;
    }
    ['pfOldPassword', 'pfNewPassword', 'pfNewPassword2'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });
    showProfileMsg('密码修改成功，下次登录请使用新密码');
  } catch (e) {
    console.error('修改密码异常:', e);
    showProfileMsg('修改失败：' + (e && e.message ? e.message : '未知错误'), true);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '保存新密码'; }
  }
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text || '';
  return div.innerHTML;
}

async function checkServerConnectivity() {
  const r = await apiRequest('/api/me', { method: 'GET' });
  if (r.status === 0) {
    const banner = document.createElement('div');
    banner.className = 'conn-banner';
    banner.innerHTML = '\u26A0\uFE0F 无法连接服务器。请先启动后端服务（运行 backend/server.py），并在浏览器访问 <a href="http://localhost:8000">http://localhost:8000</a>';
    const main = document.querySelector('.main') || document.body;
    main.insertBefore(banner, main.firstChild);
  }
}

// Clicking the auth modal background closes it
document.addEventListener('DOMContentLoaded', function () {
  const modal = document.getElementById('authModal');
  if (modal) {
    modal.addEventListener('click', function (e) {
      if (e.target === modal) closeAuthModal();
    });
  }
  const profileModal = document.getElementById('profileModal');
  if (profileModal) {
    profileModal.addEventListener('click', function (e) {
      if (e.target === profileModal) closeProfileModal();
    });
  }
  loadStoredToken();
  loadMe();
  checkServerConnectivity();
  // 不再预加载 30MB 本地数据库，推荐由后端 /api/chat 完成
});


// ============================================================
// 1. UI INTERACTION
// ============================================================
function send(text) {
  const inp = document.getElementById("chatInput");
  const msg = text || inp.value.trim();
  if (!msg) { inp.focus(); return; }
  if (!requireAuth()) { return; }
  if (!text) inp.value = "";
  const btn = document.getElementById("sendBtn");
  btn.disabled = true;

  addMsg(msg, "user");
  const typing = addTyping();
  setStatus("thinking", "分析中...");

  // 调用后端 API 完成分析与推荐（后端在本地内存中处理，1 秒内返回，无需加载 30MB 数据库）
  const ctrl = new AbortController();
  const timeout = setTimeout(() => ctrl.abort(), 30000);
  fetch(API_BASE + '/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(authToken ? { 'Authorization': 'Bearer ' + authToken } : {}) },
    body: JSON.stringify({ message: msg }),
    signal: ctrl.signal,
  }).then(r => r.json()).then(data => {
    clearTimeout(timeout);
    typing.remove();
    if (data && data.reply) {
      const analysis = data.analysis || {};
      const strategy = data.strategy || {};
      const songs = data.songs || [];
      const reply = data.reply;

      lastAnalysis = { ...analysis, strategy, userMessage: msg };

      addMsg(reply, "sys");
      updateState(analysis);
      updateBanner(strategy);
      updateParamCard(strategy);
      renderSongs(songs);
      saveHistory(msg, analysis.task_type, songs, reply);
      setStatus("ready", "就绪");
    } else {
      addMsg("出了点问题：" + ((data && data.error) || "未收到推荐结果，请稍后重试"), "sys");
      setStatus("ready", "就绪");
    }
    btn.disabled = false;
  }).catch(err => {
    clearTimeout(timeout);
    typing.remove();
    const errMsg = err.name === 'AbortError'
      ? "请求超时（30 秒），可能是网络较慢，请重试"
      : (err.message || "").indexOf("JSON") >= 0
        ? "服务器响应异常，请稍后重试；若连续出现请联系管理员"
        : "网络错误：" + (err.message || "无法连接服务器，请检查网络后重试");
    addMsg(errMsg, "sys");
    setStatus("ready", "就绪");
    btn.disabled = false;
  });
}

function addMsg(text, cls) {
  const c = document.getElementById("chatMsgs");
  const d = document.createElement("div");
  d.className = "msg " + cls;
  d.innerHTML = text.replace(/\n/g, "<br>");
  c.appendChild(d);
  c.scrollTop = c.scrollHeight;
}

function addTyping() {
  const c = document.getElementById("chatMsgs");
  const d = document.createElement("div");
  d.className = "typing";
  d.innerHTML = '<span></span><span></span><span></span>';
  c.appendChild(d);
  c.scrollTop = c.scrollHeight;
  return d;
}

function setStatus(s, t) {
  const dot = document.querySelector('#statusBar .dot');
  dot.className = 'dot' + (s === 'thinking' ? ' thinking' : '');
  document.querySelector('#statusBar').childNodes[1].textContent = ' ' + t;
}

/* 情绪编码 → 单一情绪词（与后端 models.emotion_word 同一套口径）
   复合编码如 calm-focused：优先取细分词（focused→专注）；细分词不是情绪词时
   （如 anxious-deadline 的 deadline）回退到大类（anxious→焦虑）。 */
const EMOTION_WORDS = {
  happy:'愉悦', joyful:'愉悦', delighted:'愉悦', excited:'激动',
  festive:'亢奋', celebratory:'狂喜', social:'轻快', romantic:'浪漫',
  confident:'自信', hopeful:'期待', uplifting:'振奋', energetic:'活力',
  energized:'提神', powerful:'力量', inspired:'灵感',
  calm:'平静', relaxed:'松弛', serene:'宁静', peaceful:'安宁',
  soothing:'舒缓', warm:'温暖', dreamy:'梦幻', nostalgic:'怀旧',
  reflective:'沉思', mysterious:'神秘', balanced:'平稳',
  neutral:'平稳', ordinary:'平稳', bored:'无聊',
  focused:'专注', alert:'清醒',
  anxious:'焦虑', tension:'紧绷', overwhelmed:'紧绷',
  pressured:'紧张', stressed:'紧张', worried:'担忧',
  tired:'疲惫', sleepy:'困倦', exhausted:'疲惫', fatigued:'疲惫',
  sad:'低落', depressed:'低落', lonely:'孤单', melancholic:'惆怅',
  frustrated:'受挫', angry:'烦躁', annoyed:'烦躁',
};

function emotionWord(code) {
  const parts = String(code || '').trim().split('-').filter(Boolean);
  if (!parts.length) return '平稳';
  for (let i = parts.length - 1; i >= 0; i--) {
    if (EMOTION_WORDS[parts[i]]) return EMOTION_WORDS[parts[i]];
  }
  return EMOTION_WORDS[parts[0]] || '平稳';
}

function updateState(a) {
  const tn = {coding:'编程',writing:'写作',study:'学习',workout:'运动',
               commute:'通勤',relax:'放松',creative:'创意',general:'通用',entertainment:'娱乐'};
  const taskBase = tn[(a.task_type || '').split('-')[0]] || a.task_type || '--';
  const taskShow = a.task_detail && a.task_detail !== taskBase
    ? taskBase + '·' + a.task_detail : taskBase;
  // 情绪栏只显示一个情绪词：情绪本身已由任务状态/场景推断得出，
  // 这里不再展示推断过程（原来会拼成"情绪·细分说明"并挂一个"推断"徽标）
  document.getElementById('stTask').textContent = taskShow;
  document.getElementById('stEmotion').textContent = emotionWord(a.emotion);
  document.getElementById('stPriority').textContent =
    a.need_regulation ? '需要调节' : '保持状态';
}

function updateBanner(s) {
  const b = document.getElementById('banner');
  b.style.display = 'block';
  b.innerHTML =
    '<div class="banner-row">' + '\u{1F3AF} ' + escapeHtml(s.notes || '') + '</div>' +
    '<div class="banner-row">' + '\u{1F4CB} ' + escapeHtml(s.priority || '') + '</div>' +
    '<div class="banner-row">' + '\u{1F4A1} ' + escapeHtml(s.session_advice || '') + '</div>';
}

function updateParamCard(strategy) {
  const card = document.getElementById('paramCard');
  if (!strategy) { card.style.display = 'none'; return; }
  card.style.display = 'block';
  document.getElementById('paramGenres').textContent =
    (strategy.genres || []).join(' / ') || '--';
  document.getElementById('paramMood').textContent =
    strategy.mood_target || '--';
  const energy = strategy.energy_level || 5;
  const energyDiv = document.getElementById('paramEnergy');
  const bars = Array.from({length: 10}, (_, i) =>
    '<div class="dbar' + (i < energy ? ' fill' : '') + '"></div>').join('');
  energyDiv.innerHTML =
    '<span class="elabel">低</span>' +
    '<div class="ebar">' + bars + '</div>' +
    '<span class="elabel">高</span>' +
    '<span class="enum">' + energy + '/10</span>';
  document.getElementById('paramTempo').textContent =
    strategy.tempo_range || '--';
  document.getElementById('paramInstrumental').textContent =
    strategy.instrumental_preferred ? '纯音乐（无歌词）' : '歌曲 / 可有歌词';
  document.getElementById('paramExplain').textContent =
    strategy.explanation || '--';
}

/* ===== 歌曲板块标签（语言 / 纯音乐）与站内 30 秒试听 ===== */

// 板块口径与后端 models.song_language 保持一致：纯音乐优先于语言
const SONG_LANG_LABELS = { instrumental:'纯音乐', chinese:'中文歌', english:'英文歌', other:'其它语言' };

function songLang(s) {
  if (!s) return 'other';
  if (s.language) return s.language;
  // 历史记录 / 收藏里的旧数据没有 language 字段，按同一口径兜底
  if (s.instrumental) return 'instrumental';
  const t = (s.title || '') + (s.artist || '');
  if (/[\u3040-\u30ff\uac00-\ud7af]/.test(t)) return 'other';
  return /[\u4e00-\u9fff]/.test(t) ? 'chinese' : 'english';
}

function showToast(msg) {
  let el = document.getElementById('mmToast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'mmToast';
    el.className = 'mm-toast';
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(function () { el.classList.remove('show'); }, 2800);
}

const PREVIEW_SECONDS = 30;
let previewAudio = null;
let previewIndex = -1;
// 缓存值：{ url, expire, kind:'original'|'cover', artist, title }
const previewUrlCache = new Map();

function songMidOf(song) {
  // 本地曲库 id 即 QQ 音乐 songmid（仅作 QQ 音源的检索键）
  const id = ((song && (song.songmid || song.id)) || '').toString().trim();
  return /^[0-9A-Za-z]{8,20}$/.test(id) ? id : '';
}

// 站内试听以「标题 + 歌手」为主检索键（Apple 官方 30 秒片段），songmid 仅作回退
function songPreviewKey(song) {
  if (!song) return '';
  const mid = songMidOf(song);
  if (mid) return mid;
  const t = (song.title || '').trim();
  return t ? ((song.artist || '').trim() + '|' + t).toLowerCase() : '';
}

function canPreview(song) {
  if (!song) return false;
  return !!songMidOf(song) || !!(song.title && song.artist);
}

// 已取到过的试听版本信息（未过期才算）：kind='cover' 说明是他人翻唱/其它版本
function previewVersionOf(song) {
  const k = songPreviewKey(song);
  if (!k) return null;
  const c = previewUrlCache.get(k);
  return (c && c.expire > Date.now()) ? c : null;
}

// 翻唱版提示文案：明确告诉用户实际听到的是谁唱的
// 用词判定：双方都有中文名且中文名不同 → 确定不是同一位歌手，说「翻唱版」；
// 一方中文一方外文（如「李克勤」/「Hacken Lee」）无法断定是不是同一人的艺名，
// 只说「其他版本」，避免把原唱的现场版/重录版误说成翻唱。
function cjkPart(s) {
  const m = (s || '').match(/[\u2e80-\u9fff\u3040-\u30ff\uac00-\ud7af]+/g);
  return m ? m.join('') : '';
}

function previewKindWord(song, info) {
  const a = (song && song.artist) || '';
  const b = (info && info.artist) || '';
  const inst = !!(song && song.instrumental);
  if (a && b) {
    const ca = cjkPart(a), cb = cjkPart(b);
    const bothCjk = ca && cb;
    const neitherCjk = !ca && !cb;
    if (bothCjk && (ca.indexOf(cb) >= 0 || cb.indexOf(ca) >= 0)) {
      return '其他版本';                    // 同一位歌手的不同录音
    }
    if (bothCjk || neitherCjk) {
      return inst ? '其他演奏版' : '翻唱版';  // 确定是别人唱的
    }
  }
  return '其他版本';                        // 名字写法对不上，无法断定
}

function coverLabelFor(song, info) {
  if (!info || info.kind !== 'cover') return '';
  return previewKindWord(song, info) + ' · ' + (info.artist || '他人');
}

function setCardState(i, state, tip, isCover) {
  const card = document.getElementById('songCard' + i);
  if (!card) return;
  card.classList.remove('playing', 'loading');
  if (state === 'playing') card.classList.add('playing');
  if (state === 'loading') card.classList.add('loading');
  const badge = document.getElementById('coverPlay' + i);
  if (badge) badge.textContent = state === 'playing' ? '\u25A0' : (state === 'loading' ? '\u22EF' : '\u25B6');
  const tipEl = document.getElementById('previewTip' + i);
  if (tipEl) {
    if (tip) tipEl.textContent = tip;
    tipEl.classList.toggle('is-cover', !!isCover);
  }
  if (state === 'idle') {
    const bar = document.getElementById('cardBar' + i);
    if (bar) bar.style.width = '0%';
  }
}

// 未播放时的提示：若不是原唱，标注要一直留着（停播后也不消失）
function previewIdleLabel(i) {
  const s = currentSongs[i];
  return coverLabelFor(s, previewVersionOf(s));
}

function stopPreview() {
  if (previewAudio) {
    try { previewAudio.pause(); } catch (e) { /* 忽略：元素可能尚未加载 */ }
    previewAudio.onended = null;
    previewAudio.ontimeupdate = null;
    previewAudio.onerror = null;
    previewAudio.removeAttribute('src');
  }
  if (previewIndex >= 0) {
    const lbl = previewIdleLabel(previewIndex);
    setCardState(previewIndex, 'idle', lbl || '点击卡片试听 30 秒', !!lbl);
    previewIndex = -1;
  }
}

async function previewSong(index) {
  const song = currentSongs[index];
  if (!song) return;
  if (previewIndex === index) { stopPreview(); return; }   // 再点一次 = 停止
  stopPreview();

  const key = songPreviewKey(song);
  if (!key) { showToast('这首歌没有站内试听，可点「QQ音乐」查看'); return; }

  setCardState(index, 'loading', '正在获取试听…');
  previewIndex = index;

  let url = '';
  let info = null;
  let retryable = false;               // 音源接口繁忙（限流），与「这首歌没资源」区分
  const cached = previewUrlCache.get(key);
  if (cached && cached.expire > Date.now()) { url = cached.url; info = cached; }
  if (!url) {
    const qs = new URLSearchParams();
    const mid = songMidOf(song);
    if (mid) qs.set('mid', mid);
    if (song.title) qs.set('title', song.title);
    if (song.artist) qs.set('artist', song.artist);
    if (song.duration_sec) qs.set('duration', String(song.duration_sec));
    if (song.genre) qs.set('genre', song.genre);   // 用于排除「同名不同歌」
    const res = await apiRequest('/api/preview?' + qs.toString());
    if (res.ok && res.data && res.data.url) {
      url = res.data.url;
      const ttl = Math.max(60, (res.data.expires_in || 21600) - 60);
      info = {
        url: url,
        expire: Date.now() + ttl * 1000,
        kind: res.data.match || 'original',
        artist: res.data.preview_artist || '',
        title: res.data.preview_title || '',
        storeUrl: res.data.store_url || ''      // 音源方曲目页（商店入口）
      };
      previewUrlCache.set(key, info);
    } else if (res.status === 503 || (res.data && res.data.retry)) {
      retryable = true;
    }
  }
  if (previewIndex !== index) return;   // 等待期间用户点了别的歌

  if (!url) {
    if (retryable) {
      setCardState(index, 'idle', '音源繁忙，请稍后再试');
      previewIndex = -1;
      showToast('音源接口繁忙，请等几秒再点一次');
    } else {
      setCardState(index, 'idle', '这首暂时无法试听');
      previewIndex = -1;
      showToast('这首暂时无法站内试听，可点「QQ音乐」打开');
    }
    return;
  }

  // 试听到的不是原唱时，必须明确告知用户实际演唱者
  const coverLabel = coverLabelFor(song, info);
  if (coverLabel && !(song.__coverNotified)) {
    song.__coverNotified = true;
    showToast('未找到原唱录音，正在播放 ' + (info.artist || '他人') + ' 的版本');
  }

  if (!previewAudio) { previewAudio = new Audio(); previewAudio.preload = 'none'; }
  previewAudio.src = url;
  previewAudio.currentTime = 0;
  previewAudio.ontimeupdate = function () {
    const bar = document.getElementById('cardBar' + index);
    if (bar) {
      bar.style.width = Math.min(100, (previewAudio.currentTime / PREVIEW_SECONDS) * 100) + '%';
    }
    if (previewAudio.currentTime >= PREVIEW_SECONDS) stopPreview();   // 试听 30 秒自动停
  };
  previewAudio.onended = function () { stopPreview(); };
  previewAudio.onerror = function () {
    if (previewIndex !== index) return;
    setCardState(index, 'idle', '试听加载失败');
    previewIndex = -1;
    showToast('试听加载失败，可点「QQ音乐」打开');
  };
  try {
    await previewAudio.play();
  } catch (e) {
    if (previewIndex !== index) return;
    setCardState(index, 'idle', '点击卡片试听 30 秒');
    previewIndex = -1;
    showToast('浏览器拦截了播放，请再点一次卡片');
    return;
  }
  if (previewIndex !== index) return;
  setCardState(index, 'playing', coverLabel || '试听中 · 30 秒', !!coverLabel);
}

function renderSongs(songs) {
  const g = document.getElementById('songGrid');
  currentSongs = songs;

  stopPreview();

  const items = songs.map((s, i) => ({ s: s, i: i }));
  document.getElementById('songCount').textContent = songs.length + ' 首歌';

  if (!songs.length) {
    g.innerHTML = '<div class="empty"><div class="empty-icon">\u{1F3B5}</div><p>歌曲加载中，请稍后再试</p></div>';
    return;
  }
  const genreEmoji = {
    ambient:'\u{1F30A}',classical:'\u{1F3B9}',electronic:'\u{1F3A7}',
    rock:'\u{1F3B8}',pop:'\u{1F3B5}',folk:'\u{1F3BB}',hiphop:'\u{1F3A4}',
    indie:'\u{1F3B6}',jazz:'\u{1F3BA}','r&b':'\u{1F3B9}',
    'neo-classical':'\u{1F3B9}',minimalist:'\u{1F30A}',
  };
  g.innerHTML = items.map((item, order) => {
    const s = item.s, i = item.i;
    const emoji = genreEmoji[s.genre] || '\u{1F3B5}';
    const dots = Array.from({length:10}, (_,j) =>
      '<div class="edot'+(j < s.energy ? ' on':'')+'"></div>').join('');
    const lang = songLang(s);
    const coverTip = coverLabelFor(s, previewVersionOf(s));   // 已知是翻唱就常驻标注
    return '<div class="card" id="songCard'+i+'" data-lang="'+lang+'"' +
        ' style="animation-delay:'+Math.min(order * 40, 320)+'ms"' +
        ' onclick="previewSong('+i+')">' +
      '<div class="card-top">' +
        '<div class="card-cover">' +
          (s.cover_url ? '<img src="'+s.cover_url+'" alt="" onerror="this.parentElement.innerHTML=\''+emoji+'\'">' : emoji) +
          '<span class="cover-play" id="coverPlay'+i+'">\u25B6</span>' +
        '</div>' +
        '<div class="card-info">' +
          '<div class="card-title">'+s.title+'</div>' +
          '<div class="card-artist">'+s.artist+' \u00B7 '+s.album+'</div>' +
          '<div class="card-meta">' +
            '<span class="meta-tag cat-'+lang+'">'+SONG_LANG_LABELS[lang]+'</span>' +
            '<span class="meta-tag">'+s.genre+'</span>' +
            '<span class="meta-tag">'+s.tempo_bpm+' BPM</span>' +
          '</div>' +
        '</div>' +
        '<div class="card-energy"><div class="edots">'+dots+'</div></div>' +
      '</div>' +
      '<div class="card-reason">'+s.reason+'</div>' +
      '<div class="card-foot">' +
        '<span class="card-tip'+(coverTip ? ' is-cover' : '')+'" id="previewTip'+i+'">'+(coverTip || '点击卡片试听 30 秒')+'</span>' +
        '<div class="card-actions">' +
          '<button class="mini-btn" onclick="event.stopPropagation(); showDetail('+i+')">\u{2139} 详情</button>' +
          '<button class="mini-btn" onclick="event.stopPropagation(); openQQMusic('+i+')">\u{1F517} QQ音乐</button>' +
          '<button class="mini-btn fav-btn'+(isFavorited(s)?' favorited':'')+'" data-fav-index="'+i+'" onclick="event.stopPropagation(); toggleFavorite('+i+')">'+(isFavorited(s)?'\u{2764} 已收藏':'\u{2661} 收藏')+'</button>' +
        '</div>' +
      '</div>' +
      '<div class="card-progress"><i id="cardBar'+i+'"></i></div>' +
    '</div>';
  }).join('');
}

function openQQMusic(index) {
  const song = currentSongs[index];
  if (!song) return;
  if (song.external_url) {
    window.open(song.external_url, '_blank');
  }
}

function showDetail(index) {
  const song = currentSongs[index];
  if (!song) return;
  const old = document.getElementById('detailModal');
  if (old) old.remove();
  const energyBar = Array.from({length:10}, (_,i) =>
    '<span class="dbar'+(i < song.energy ? ' fill':'')+'"></span>').join('');
  const moodTagStr = (song.mood_tags || []).map(t =>
    '<span class="dtag">'+t+'</span>').join('');
  const extBtn = song.external_url
    ? '<a href="'+song.external_url+'" target="_blank" rel="noopener" class="dbtn dbtn-ext">\u{1F517} 在QQ音乐中打开</a>'
    : '';
  const knownVer = previewVersionOf(song);
  const knownCover = coverLabelFor(song, knownVer);
  const previewBtn = canPreview(song)
    ? '<button class="dbtn dbtn-preview" onclick="hideDetail(); previewSong('+index+')">\u25B6 ' +
      (knownCover ? '试听' + previewKindWord(song, knownVer) + ' 30 秒' : '试听 30 秒') + '</button>'
    : '';
  // 已知试听不是原唱：在弹窗里也如实标注，避免用户误以为在听原唱
  const coverNote = knownCover
    ? '<p class="preview-note">\u2139 站内试听未找到原唱录音，实际播放的是「' +
      (knownVer.artist || '其他歌手') + '」的版本（可能为翻唱 / 现场版 / 重录版）</p>'
    : '';
  // 音源方曲目页入口（商店跳转）：既方便用户听完整版，也满足音源方的推广条款
  const storeBtn = (knownVer && knownVer.storeUrl)
    ? '<a href="'+knownVer.storeUrl+'" target="_blank" rel="noopener" class="dbtn dbtn-ext">\u{1F3B5} 在 Apple Music 打开</a>'
    : '';
  // 试听片段的来源与使用方式（合规声明）
  const sourceNote = '<p class="preview-note preview-src">\u2139 试听为音源方官方提供的 30 秒片段' +
    '(Apple)，仅用于试听参考；音频由音源方 CDN 直接提供，本站不下载、不转存、不再分发。</p>';
  const coverContent = song.cover_url
    ? '<img src="'+song.cover_url+'" alt="" onerror="this.innerHTML=\'\u{1F3B5}\'">'
    : '\u{1F3B5}';
  const modal = document.createElement('div');
  modal.id = 'detailModal';
  modal.className = 'modal-overlay';
  modal.onclick = function(e) { if (e.target === this) hideDetail(); };
  modal.innerHTML = '<div class="modal">' +
    '<button class="modal-close" onclick="hideDetail()">&times;</button>' +
    '<div class="modal-hero">' +
      '<div class="modal-cover">'+coverContent+'</div>' +
      '<div class="modal-head">' +
        '<h2 class="modal-title">'+song.title+'</h2>' +
        '<p class="modal-artist">'+song.artist+'</p>' +
        '<p class="modal-album">'+song.album+'</p>' +
      '</div>' +
    '</div>' +
    '<div class="modal-body">' +
      '<div class="modal-section">' +
        '<h3>\u{1F3B9} 音乐属性</h3>' +
        '<div class="modal-grid">' +
          '<div class="modal-item"><span class="modal-label">风格</span><span class="modal-value">'+song.genre+'</span></div>' +
          '<div class="modal-item"><span class="modal-label">节奏 (BPM)</span><span class="modal-value">'+song.tempo_bpm+'</span></div>' +
          '<div class="modal-item"><span class="modal-label">时长</span><span class="modal-value">'+formatDuration(song.duration_sec)+'</span></div>' +
          '<div class="modal-item"><span class="modal-label">板块</span><span class="modal-value">'+SONG_LANG_LABELS[songLang(song)]+'</span></div>' +
          '<div class="modal-item"><span class="modal-label">主要乐器</span><span class="modal-value">'+(song.instrument_type || inferInstrumentType(song.genre))+'</span></div>' +
          '<div class="modal-item"><span class="modal-label">数据来源</span><span class="modal-value accent">'+song.source+'</span></div>' +
        '</div>' +
      '</div>' +
      '<div class="modal-section">' +
        '<h3>\u{26A1} 能量等级</h3>' +
        '<div class="modal-energy">' +
          '<span class="elabel low">低</span>' +
          '<div class="ebar">'+energyBar+'</div>' +
          '<span class="elabel high">高</span>' +
        '</div>' +
        '<p class="energy-desc">'+getEnergyDesc(song.energy)+'</p>' +
      '</div>' +
      (moodTagStr ? '<div class="modal-section"><h3>\u{1F3AD} 情绪标签</h3><div class="modal-tags">'+moodTagStr+'</div></div>' : '') +
      '<div class="modal-section"><h3>\u{1F4A1} 推荐理由</h3><p class="modal-reason">'+song.reason+'</p></div>' +
    '</div>' +
    coverNote + sourceNote +
    '<div class="modal-actions">'+previewBtn+storeBtn+extBtn+'<button class="dbtn dbtn-close" onclick="hideDetail()">关闭</button></div>' +
  '</div>';
  document.body.appendChild(modal);
}

function hideDetail() {
  const modal = document.getElementById('detailModal');
  if (modal) { modal.style.opacity = '0'; setTimeout(() => modal.remove(), 200); }
}

function formatDuration(sec) {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return m + ':' + s.toString().padStart(2, '0');
}

function getEnergyDesc(e) {
  if (e <= 2) return '极低能量，适合深度放松、冥想或入睡';
  if (e <= 4) return '低能量，适合专注工作、学习或阅读';
  if (e <= 6) return '中等能量，适合创意工作、通勤或日常放松';
  if (e <= 8) return '高能量，适合运动、提振心情或需要动力的时刻';
  return '极高能量，适合高强度运动、派对或需要极限激发';
}

function clearAll() {
  document.getElementById('chatMsgs').innerHTML =
    '<div class="msg sys"><p>\u{1F44B} 对话已清空。告诉我你的任务和心情吧~</p><p>我会推荐匹配的歌曲，点击歌曲可跳转QQ音乐。</p></div>';
  document.getElementById('songGrid').innerHTML =
    '<div class="empty"><div class="empty-icon">\u{1F3B5}</div><p>在左侧说说你的状态<br>我来为你推荐合适的音乐</p></div>';
  document.getElementById('songCount').textContent = '';
  document.getElementById('banner').style.display = 'none';
  document.getElementById('paramCard').style.display = 'none';
  currentSongs = [];
  lastAnalysis = null;
  document.getElementById('stTask').textContent = '--';
  document.getElementById('stEmotion').textContent = '--';
  document.getElementById('stPriority').textContent = '--';
}

// ============================================================
// Welcome Modal & Onboarding Tour
// ============================================================

function closeWelcomeModal(markSeen) {
  const m = document.getElementById('welcomeModal');
  if (m) m.style.display = 'none';
  if (markSeen) localStorage.setItem('melomind_welcomed', '1');
}

// --- Onboarding Tour ---
const TOUR_STEPS = [
  {
    target: '#chatInput',
    title: '对话输入框',
    body: '在这里输入你正在做什么、心情如何，比如「写代码焦虑」「复习考试想专注」。系统会理解你的状态并推荐匹配的音乐。按 Enter 发送。',
    placement: 'top',
  },
  {
    target: '.tips',
    title: '快捷场景按钮',
    body: '不知道怎么描述？点击这些预设场景按钮，一键发送常见任务描述，快速体验推荐效果。',
    placement: 'right',
  },
  {
    target: '#statePanel',
    title: '实时状态面板',
    body: '发送消息后，这里会显示 AI 识别出的任务类型、情绪状态和推荐策略，让你直观看到系统如何理解你。',
    placement: 'right',
  },
  {
    target: '#paramCard',
    title: '音乐参数卡片',
    body: '推荐歌曲前，这里会展示根据你的状态生成的音乐参数：推荐风格、目标情绪、能量等级、节奏范围等。第一次推荐后才会显示。',
    placement: 'left',
  },
  {
    target: '#songGrid',
    title: '推荐歌曲列表',
    body: '推荐的歌曲会显示在这里。点击歌曲卡片可查看详情并跳转 QQ音乐播放。卡片上的 ❤ 可以收藏喜欢的歌曲。',
    placement: 'left',
  },
  {
    target: '#userInfoName',
    title: '个人中心入口',
    body: '点击你的用户名进入个人中心，这里可以管理收藏夹、查看搜索历史、修改用户名和密码。',
    placement: 'right',
  },
  {
    target: '.ai-top-btn',
    title: '抖音 AI 生成专属音乐',
    body: '想拥有完全属于自己的原创音乐？点击这里，用抖音 AI 根据你的描述生成专属歌曲！',
    placement: 'bottom',
  },
];

let tourIndex = 0;

function startTour() {
  tourIndex = 0;
  const overlay = document.getElementById('tourOverlay');
  if (overlay) overlay.style.display = '';
  setTimeout(showTourStep, 100);
}

function showTourStep() {
  const step = TOUR_STEPS[tourIndex];
  if (!step) { endTour(); return; }

  const el = document.querySelector(step.target);
  if (!el) { tourIndex++; showTourStep(); return; }

  // Handle hidden elements (e.g. paramCard with display:none)
  let wasHidden = false;
  let origDisplay = '';
  if (el.offsetParent === null && el.id === 'paramCard') {
    wasHidden = true;
    origDisplay = el.style.display;
    el.style.display = 'block';
    el.style.visibility = 'hidden';
  }

  // Scroll element into view
  el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });

  const rect = el.getBoundingClientRect();
  const pad = 6;
  const spotlight = document.getElementById('tourSpotlight');

  // Position spotlight
  spotlight.style.left = (rect.left - pad) + 'px';
  spotlight.style.top = (rect.top - pad) + 'px';
  spotlight.style.width = (rect.width + pad * 2) + 'px';
  spotlight.style.height = (rect.height + pad * 2) + 'px';

  // Position tooltip
  const tooltip = document.getElementById('tourTooltip');
  const tw = 340;
  const th = 160; // estimated
  let tx, ty;
  const gap = 16;

  switch (step.placement) {
    case 'top':
      tx = rect.left + rect.width / 2 - tw / 2;
      ty = rect.top - th - gap;
      break;
    case 'bottom':
      tx = rect.left + rect.width / 2 - tw / 2;
      ty = rect.bottom + gap;
      break;
    case 'right':
      tx = rect.right + gap;
      ty = rect.top + rect.height / 2 - th / 2;
      break;
    case 'left':
      tx = rect.left - tw - gap;
      ty = rect.top + rect.height / 2 - th / 2;
      break;
    default:
      tx = rect.right + gap;
      ty = rect.top;
  }

  // Keep tooltip within viewport
  tx = Math.max(12, Math.min(tx, window.innerWidth - tw - 12));
  ty = Math.max(12, Math.min(ty, window.innerHeight - th - 12));

  tooltip.style.left = tx + 'px';
  tooltip.style.top = ty + 'px';

  // Update content
  document.getElementById('tourStepNum').textContent = (tourIndex + 1) + '/' + TOUR_STEPS.length;
  document.getElementById('tourStepTitle').textContent = step.title;
  document.getElementById('tourStepBody').textContent = step.body;
  document.getElementById('tourProgress').textContent = '第 ' + (tourIndex + 1) + ' 步，共 ' + TOUR_STEPS.length + ' 步';

  // Update buttons
  const btnPrev = document.getElementById('tourBtnPrev');
  btnPrev.disabled = tourIndex === 0;

  const btnNext = document.getElementById('tourBtnNext');
  if (tourIndex === TOUR_STEPS.length - 1) {
    btnNext.textContent = '完成';
    btnNext.classList.add('tour-btn-finish');
  } else {
    btnNext.textContent = '下一步';
    btnNext.classList.remove('tour-btn-finish');
  }

  // Restore hidden element state
  if (wasHidden) {
    el.style.visibility = '';
    el.style.display = origDisplay;
  }
}

function tourNext() {
  tourIndex++;
  if (tourIndex >= TOUR_STEPS.length) {
    endTour();
  } else {
    showTourStep();
  }
}

function tourPrev() {
  if (tourIndex > 0) {
    tourIndex--;
    showTourStep();
  }
}

function endTour() {
  const overlay = document.getElementById('tourOverlay');
  if (overlay) overlay.style.display = 'none';
  localStorage.setItem('melomind_toured', '1');
}

// ========== 音乐偏好调查（注册后触发） ==========
function openPrefSurvey() {
  const box = document.getElementById('prefSurvey');
  if (box) box.style.display = '';
}

function skipPrefSurvey() {
  const box = document.getElementById('prefSurvey');
  if (box) box.style.display = 'none';
  // 跳过也触发导览
  setTimeout(startTour, 300);
}

async function submitPrefSurvey() {
  // 收集答案
  const language = (document.querySelector('input[name="pref-language"]:checked') || {}).value || 'both';
  const instrumental = (document.querySelector('input[name="pref-instrumental"]:checked') || {}).value || 'both';
  const genres = Array.from(document.querySelectorAll('input[data-pref="genres"]:checked')).map(cb => cb.value);
  const energy = (document.querySelector('input[name="pref-energy"]:checked') || {}).value || 'both';

  const prefs = { language, instrumental, genres, energy };

  const box = document.getElementById('prefSurvey');
  const submitBtn = box.querySelector('.pref-submit-btn');
  const origText = submitBtn.textContent;
  submitBtn.disabled = true;
  submitBtn.textContent = '保存中...';

  try {
    const r = await apiRequest('/api/user/preferences', {
      method: 'POST',
      body: prefs,
    });
    if (r.ok && r.data && r.data.ok) {
      addMsg('偏好已保存，推荐会更懂你 🎵', 'sys');
    } else {
      addMsg('偏好保存失败，但不影响使用', 'sys');
    }
  } catch (e) {
    addMsg('偏好保存失败，但不影响使用', 'sys');
  }

  box.style.display = 'none';
  // 偏好调查后触发功能导览
  setTimeout(startTour, 400);
}

// Reposition on resize
window.addEventListener('resize', function () {
  const overlay = document.getElementById('tourOverlay');
  if (overlay && overlay.style.display !== 'none') {
    showTourStep();
  }
});

// Fallback: also trigger welcome modal on window.load (in case DOMContentLoaded timing issue)
window.addEventListener('load', function () {
  if (!localStorage.getItem('melomind_welcomed')) {
    const m = document.getElementById('welcomeModal');
    if (m && m.style.display === 'none') {
      m.style.animation = 'none';
      m.style.display = 'flex';
      m.style.opacity = '1';
    }
  }
});

function openDouyinAI() {
  const modal = document.getElementById('aiStudioModal');
  if (!modal) return;
  modal.style.display = 'flex';
  modal.style.opacity = '1';

  // 预填当前对话的场景描述
  const input = document.getElementById('aiStudioInput');
  const hasCtx = !!(lastAnalysis && lastAnalysis.userMessage);
  if (hasCtx) input.value = lastAnalysis.userMessage;
  document.getElementById('aiStudioQuick').style.display = hasCtx ? 'flex' : 'none';
  document.getElementById('aiStudioHint').style.display = hasCtx ? 'block' : 'none';
  document.getElementById('aiStudioHint').textContent =
    '已自动带入你当前对话的状态描述，可直接修改';
  aiStudioShowPane(1);
}

function aiStudioShowPane(n) {
  document.getElementById('aiStudioPane1').style.display = n === 1 ? 'block' : 'none';
  document.getElementById('aiStudioPane2').style.display = n === 2 ? 'block' : 'none';
  const d1 = document.getElementById('aiStepDot1');
  const d2 = document.getElementById('aiStepDot2');
  const line = document.getElementById('aiStepLine');
  d1.className = 'ai-studio-step' + (n >= 1 ? ' active' : '') + (n > 1 ? ' done' : '');
  d2.className = 'ai-studio-step' + (n >= 2 ? ' active' : '');
  line.className = 'ai-studio-step-line' + (n >= 2 ? ' active' : '');
}

function closeAiStudio() {
  const modal = document.getElementById('aiStudioModal');
  if (modal) modal.style.display = 'none';
}

function aiStudioUseContext() {
  if (lastAnalysis && lastAnalysis.userMessage) {
    document.getElementById('aiStudioInput').value = lastAnalysis.userMessage;
  }
}

function aiStudioBack() {
  aiStudioShowPane(1);
}

const AI_STUDIO_TASK_NAMES = {
  coding: '编程', writing: '写作', study: '学习', workout: '运动',
  commute: '通勤', relax: '放松', creative: '创意', entertainment: '娱乐', general: '日常',
};
const AI_STUDIO_EMO_NAMES = {
  happy: '愉悦', anxious: '焦虑', tired: '疲惫', sad: '低落',
  calm: '平静', neutral: '中性', festive: '兴奋',
};

const AI_STUDIO_STYLE_MAP = [
  { keys: ['电子', 'electronic', 'edm', '电音', 'synth'], lead: '合成器 Pad', solo: '合成器 Lead', color: '微光质感的合成器高音' },
  { keys: ['钢琴', 'piano', '古典', 'classical'], lead: '钢琴', solo: '小提琴', color: '弦乐群的暖意' },
  { keys: ['民谣', 'folk', '吉他', 'acoustic'], lead: '木吉他', solo: '口琴', color: '弦乐轻轻衬底' },
  { keys: ['摇滚', 'rock', '朋克'], lead: '电吉他', solo: '电吉他', color: '失真音墙的厚度' },
  { keys: ['爵士', 'jazz', '蓝调'], lead: '钢琴', solo: '萨克斯', color: '铜管的金属光泽' },
  { keys: ['lo-fi', 'lofi', '嘻哈', 'hip-hop', '说唱'], lead: '电钢琴', solo: '小号', color: '黑胶噪声的颗粒感' },
  { keys: ['治愈', '轻音乐', '纯音乐', '冥想', '睡眠', '轻音乐'], lead: '钢琴', solo: '长笛', color: '八音盒般的晶莹泛音' },
  { keys: ['古风', '国风', '民乐'], lead: '古筝', solo: '竹笛', color: '琵琶轮指的点缀' },
];
const AI_STUDIO_STYLE_DEFAULT = { lead: '钢琴与合成器 Pad', solo: '电吉他', color: '弦乐衬底的暖意' };
const AI_STUDIO_EMO_SENSE = {
  anxious: { a: '略带忐忑的倾诉中逐渐平复', b: '压抑后的释放与舒展', r: '沉淀后的安定' },
  tired: { a: '低回倦意中透出一丝松弛', b: '疲惫被托举起来的暖流', r: '卸下重负后的轻盈' },
  sad: { a: '低回婉转的淡淡忧伤', b: '伤感中生长出的释怀', r: '与自己和解的平静' },
  happy: { a: '明快上扬的愉悦叙事', b: '尽兴的欢乐绽放', r: '意犹未尽的甜蜜回味' },
  festive: { a: '雀跃欢腾的律动叙事', b: '全场共舞的燃点', r: '余温未散的欢畅' },
  calm: { a: '平缓安宁的呼吸感', b: '开阔舒展的平静高潮', r: '更深一层的安宁' },
};
const AI_STUDIO_EMO_SENSE_DEFAULT = { a: '娓娓道来的叙事感', b: '情绪的自然绽放', r: '温和的回归与回味' };

function buildStructuredPrompt(cfg) {
  const style = (function () {
    const g = cfg.genres.join(' ').toLowerCase();
    for (const s of AI_STUDIO_STYLE_MAP) {
      if (s.keys.some(k => g.includes(k))) return s;
    }
    return AI_STUDIO_STYLE_DEFAULT;
  })();
  const sense = AI_STUDIO_EMO_SENSE[cfg.emoKey] || AI_STUDIO_EMO_SENSE_DEFAULT;

  // 能量决定节奏表述
  const high = cfg.energy >= 7, low = cfg.energy <= 3;
  const rhyA = high ? '中快板，底鼓以四分音符稳步推进，军鼓落于 2/4 拍' : low ? '缓板，鼓点稀疏近乎留白，仅以低频脉冲轻托' : '行板律动，鼓刷与轻打击乐克制铺底';
  const rhyB = high ? '全奏强拍，底鼓双踩与镲片开合密集推进，第 4 小节以鼓乐填充（fill）蓄力' : low ? '律动轻缓抬起，密度略有增加但不破坏留白感' : '律动加密，军鼓回击与踩镲开合增强推动感';
  const colorIntro = low ? '温润柔和，混响轻敷营造空间纵深' : high ? '明亮而有冲劲，瞬态清晰' : '柔和适中，层次通透';
  const vocalA = '全曲无人声，器乐旋律即主题本身';
  const scenePhrase = cfg.scene ? `为${cfg.scene}场景而作` : '';

  const line = (seg, inst, mel, har, rhy, tim, emo, theme) =>
    `${seg}：${inst}；旋律${mel}；和声${har}；节奏${rhy}；音色${tim}；情感${emo}；主题${theme}。`;

  return [
    line('前奏', `${style.lead}独奏引入，低频声部暂缺`,
      '以级进为主的动机轻声呈现，主题片段初露轮廓',
      '停留于主和弦（I）持续铺陈，确立调中心',
      '自由节奏（rubato），无鼓点，以气口留白',
      colorIntro,
      `静谧的引入与期待感${cfg.emoDetail ? `，呼应「${cfg.emoDetail}」的起点状态` : ''}`,
      `围绕「${cfg.desc}」完成第一次点题${scenePhrase ? `，${scenePhrase}` : ''}`),

    line('A 段', `${style.lead}延续动机，贝斯与节奏组进入，织体由单声部扩为多层`,
      `主歌叙述句，音域适中、以级进为主，${vocalA}`,
      'I–vi–IV–V 的和声进行，四小节一循环',
      rhyA,
      '清晰靠前、声部层次分明',
      sense.a,
      `围绕「${cfg.desc}」缓缓展开叙事`),

    line('B 段', `弦乐与和声垫全面充盈，${style.lead}推至高声部，全频段铺满`,
      '跳进增多、音域上扬，副歌记忆点（hook）清晰可辨',
      '转向 IV–V–iii–vi 的张力循环，制造离调倾向',
      rhyB,
      low ? '依旧柔美但更显开阔' : '明亮开阔，高频光泽增强',
      sense.b,
      `将「${cfg.desc}」的情绪推向顶点并升华`),

    line('间奏', `${style.solo}器乐独奏承接，鼓组以填充（fill）过渡衔接`,
      '主题的对位变奏，与主旋律形成呼应式对话',
      '短暂离调后向下属方向过渡，为再现蓄力',
      '延续 B 段律动，末小节渐强过渡',
      `与 A 段形成音色对比，突出${style.solo}的独奏质感`,
      '一次深呼吸式的过渡与沉淀',
      '主题以器乐形式重述，给听众留出回味空间'),

    line("A'再现段", `${style.lead}回归主奏，伴奏织体较 A 段更为成熟，加入装饰性副旋律`,
      '主题再现并附加装饰变奏（ornamentation），尾句上行期待解决',
      '回归主调，重申 I 级调中心',
      '保持律动但力度渐收（dim.）',
      `在原有基调上增添${style.color}`,
      sense.r,
      '主题首尾呼应，情绪收拢'),

    line('尾奏', '各声部逐层退出，仅留' + style.lead + '收尾',
      '动机碎片化、渐弱重复，终止于主音',
      '以完全终止（K46–V–I）稳定收束',
      low ? '渐慢（rit.）至自由延长，自然消隐' : '渐慢（rit.），末拍自由延长（fermata）',
      '渐隐（fade out），余韵绵长',
      '释然而留有余韵',
      `在静谧中完成「${cfg.desc}」的收束点题`),
  ].join('\n')
    + `\n\n请根据以上结构提示词生成一首纯音乐歌曲（全曲无人声，以器乐演奏完整呈现前奏–A段–B段–间奏–再现段–尾奏的六段式结构）。`;
}

function generateMusicPrompt() {
  const desc = (document.getElementById('aiStudioInput').value || '').trim();
  if (!desc) {
    document.getElementById('aiStudioInput').focus();
    return;
  }

  // 生成按钮加载态
  const btn = document.getElementById('aiStudioGenBtn');
  btn.disabled = true;
  btn.textContent = '正在生成提示词...';

  setTimeout(() => {
    const a = lastAnalysis || {};
    const s = a.strategy || {};
    const taskKey = (a.task_type || '').split('-')[0];
    const emoKey = (a.emotion || '').split('-')[0];
    const scene = AI_STUDIO_TASK_NAMES[taskKey] || '';
    const emo = AI_STUDIO_EMO_NAMES[emoKey] || a.emotion_detail || '';
    const genres = (s.genres && s.genres.length ? s.genres : ['流行']);
    const energy = s.energy_level || 5;
    const tempo = s.tempo_range || (energy >= 7 ? 'BPM 120-140，明快有力' : energy <= 3 ? 'BPM 60-80，舒缓平缓' : 'BPM 90-110，适中流畅');
    const instrumental = '纯音乐（无人声）';
    const moodTarget = s.mood_target || (emo ? `从${emo}过渡到放松舒适` : '放松舒适');

    const energyLabel = energy >= 7 ? '高能量' : energy <= 3 ? '低能量' : '中等能量';
    const energyDesc = energy >= 7 ? '节奏鲜明、鼓点有力，充满推进感' : energy <= 3 ? '织体轻盈、音色柔和，无强烈起伏' : '律动适中，平缓中带有活力';

    const dims = [
      { icon: '🎨', label: '音乐风格', value: genres.join('、') },
      { icon: '💭', label: '情绪基调', value: moodTarget },
      { icon: '⚡', label: '能量等级', value: `${energyLabel}（${energy}/10），${energyDesc}` },
      { icon: '🥁', label: '节奏速度', value: tempo },
      { icon: '🎤', label: '人声设置', value: instrumental },
      { icon: '📖', label: '创作主题', value: desc },
    ];
    document.getElementById('aiPromptGrid').innerHTML = dims.map(d => `
      <div class="ai-prompt-item">
        <div class="ai-prompt-item-label">${d.icon} ${d.label}</div>
        <div class="ai-prompt-item-value">${d.value}</div>
      </div>`).join('');

    const full = buildStructuredPrompt({
      genres,
      energy,
      instrumental: !!s.instrumental_preferred,
      vocalDesc: s.instrumental_preferred ? '' : (s.mood_target ? `贴合「${s.mood_target}」的` : ''),
      moodTarget,
      tempo,
      desc,
      scene,
      emoKey,
      emoDetail: a.emotion_detail || '',
    });

    document.getElementById('aiPromptFull').value = full;
    aiStudioShowPane(2);

    btn.disabled = false;
    btn.innerHTML = '&#10024; 生成创作提示词';
  }, 600);
}

function copyMusicPrompt() {
  const text = document.getElementById('aiPromptFull').value || '';
  if (!text) return;
  const done = () => {
    const btn = document.querySelector('.ai-studio-actions .ai-studio-btn-ghost:nth-child(2)');
    if (btn) {
      const orig = btn.innerHTML;
      btn.innerHTML = '&#10003; 已复制';
      setTimeout(() => { btn.innerHTML = orig; }, 1500);
    }
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done).catch(() => {});
  } else {
    const ta = document.getElementById('aiPromptFull');
    ta.select();
    document.execCommand('copy');
    done();
  }
}

function goDouyinStudio() {
  const prompt = document.getElementById('aiPromptFull').value || '';
  const url = `https://music.douyin.com/studio?prompt=${encodeURIComponent(prompt)}&style=pop&bpm=120`;
  window.open(url, '_blank', 'noopener');
}

// Global exports for onclick handlers
window.send = send;
window.openQQMusic = openQQMusic;
window.showDetail = showDetail;
window.hideDetail = hideDetail;
window.clearAll = clearAll;
window.openDouyinAI = openDouyinAI;
window.closeAiStudio = closeAiStudio;
window.aiStudioUseContext = aiStudioUseContext;
window.aiStudioBack = aiStudioBack;
window.generateMusicPrompt = generateMusicPrompt;
window.copyMusicPrompt = copyMusicPrompt;
window.goDouyinStudio = goDouyinStudio;
window.openAuthModal = openAuthModal;
window.closeAuthModal = closeAuthModal;
window.switchAuthTab = switchAuthTab;
window.doLogin = doLogin;
window.doRegister = doRegister;
window.doLogout = doLogout;
window.toggleFavorite = toggleFavorite;
window.openProfileModal = openProfileModal;
window.closeProfileModal = closeProfileModal;
window.switchProfileTab = switchProfileTab;
window.doChangeUsername = doChangeUsername;
window.doChangePassword = doChangePassword;
window.removeFavorite = removeFavorite;
window.openFavSongQQMusic = openFavSongQQMusic;