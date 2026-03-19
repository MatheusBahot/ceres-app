// ═══════════════════════════════════════════════════════════
//  CERES — Core JS  |  Auth helpers, Toast, Router guard
// ═══════════════════════════════════════════════════════════
 
const API = '/api';
 
// ── AUTH ──────────────────────────────────────────────────
const Auth = {
  getToken:   () => localStorage.getItem('ceres_token'),
  getUser:    () => { try { return JSON.parse(localStorage.getItem('ceres_user')); } catch { return null; } },
  isLoggedIn: () => !!Auth.getToken(),
  isAdmin:    () => Auth.getUser()?.role === 'admin',
  save(token, user) {
    localStorage.setItem('ceres_token', token);
    localStorage.setItem('ceres_user', JSON.stringify(user));
  },
  logout() {
    localStorage.removeItem('ceres_token');
    localStorage.removeItem('ceres_user');
    window.location.href = '/';
  }
};
 
// ── ROUTE GUARD ────────────────────────────────────────────
function requireAuth() {
  if (!Auth.isLoggedIn()) { window.location.href = '/'; }
}
function requireAdmin() {
  requireAuth();
  if (!Auth.isAdmin()) { window.location.href = '/home'; }
}
 
// ── FETCH WRAPPER ──────────────────────────────────────────
async function api(path, options = {}) {
  const token = Auth.getToken();
  const res = await fetch(API + path, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      ...options.headers,
    },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) { Auth.logout(); return; }
  if (!res.ok) throw new Error(data.error || 'Erro na requisição.');
  return data;
}
 
// ── TOAST ──────────────────────────────────────────────────
function toast(msg, type = 'info', duration = 4000) {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  const icons = { success: '✓', error: '✕', info: 'ℹ' };
  el.innerHTML = `<span style="font-size:1rem">${icons[type]||'ℹ'}</span> ${msg}`;
  container.appendChild(el);
  setTimeout(() => { el.style.opacity='0'; el.style.transform='translateY(10px)';
    el.style.transition='all 0.3s'; setTimeout(() => el.remove(), 320); }, duration);
}
 
// ── NAVBAR BOOTSTRAP ───────────────────────────────────────
function bootstrapNavbar() {
  const user = Auth.getUser();
  if (!user) return;
 
  // Avatar initials
  const av = document.querySelector('.avatar');
  if (av) {
    av.textContent = user.name.split(' ').map(w=>w[0]).join('').slice(0,2).toUpperCase();
    av.title = user.name;
  }
 
  // Active link
  const currentPath = window.location.pathname;
  document.querySelectorAll('.navbar-nav a').forEach(a => {
    if (a.getAttribute('href') === currentPath) a.classList.add('active');
  });
 
  // Hide admin-only links for vendedor
  if (user.role !== 'admin') {
    document.querySelectorAll('[data-admin-only]').forEach(el => el.style.display = 'none');
  }
 
  // Dropdown toggle
  const dropBtn = document.getElementById('user-dropdown-btn');
  const dropMenu = document.getElementById('user-dropdown');
  if (dropBtn && dropMenu) {
    dropBtn.addEventListener('click', e => {
      e.stopPropagation();
      const open = dropMenu.style.display === 'block';
      dropMenu.style.display = open ? 'none' : 'block';
    });
    document.addEventListener('click', () => { if (dropMenu) dropMenu.style.display = 'none'; });
  }
 
  // Logout
  document.querySelectorAll('[data-logout]').forEach(el => {
    el.addEventListener('click', e => { e.preventDefault(); Auth.logout(); });
  });
}
 
// ── UTILS ──────────────────────────────────────────────────
function fmt_cnpj(v) {
  const d = (v||'').replace(/\D/g,'').padStart(14,'0');
  return `${d.slice(0,2)}.${d.slice(2,5)}.${d.slice(5,8)}/${d.slice(8,12)}-${d.slice(12)}`;
}
function escHtml(s) {
  return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function groupColor(grupo) {
  const m = {
    'FRIGORÍFICOS E CARNES':        '#7F0000',
    'SUPERMERCADOS E MERCEARIAS':   '#1A4D00',
    'PADARIAS E FOOD SERVICE':      '#7A3B00',
    'FARMÁCIAS E DROGARIAS':        '#003580',
    'LABORATÓRIOS E CLÍNICAS':      '#004D4D',
    'HOTÉIS E POUSADAS':            '#4A2000',
    'EVENTOS E BUFFET':             '#2D4A00',
    'CONSTRUTORAS E OBRAS':         '#00356B',
    'ARQUITETURA E ENGENHARIA':     '#1A0060',
    'INSTALAÇÕES REFRIGERAÇÃO/HVAC':'#8B0000',
    'INDÚSTRIA E ATACADO ALIMENTOS':'#4A0E00',
    'FLORICULTURAS':                '#005A3C',
  };
  return m[grupo] || '#444';
}
function statusBadge(s) {
  const map = {
    prospectar: ['badge-blue','Prospectar'],
    contatado:  ['badge-orange','Contatado'],
    cliente:    ['badge-green','Cliente'],
    perdido:    ['badge-red','Perdido'],
  };
  const [cls, label] = map[s] || ['badge-gray', s];
  return `<span class="badge ${cls}">${label}</span>`;
}
 
document.addEventListener('DOMContentLoaded', bootstrapNavbar);
