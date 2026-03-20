require('dotenv').config();
const express = require('express');
const path    = require('path');
const cors    = require('cors');
 
// ── INICIALIZAR BANCO NA SUBIDA DO SERVIDOR ───────────────────────────────────
// Roda o init antes de qualquer rota, garante que o banco existe
require('./database/init');
 
const authRoutes      = require('./routes/auth');
const companiesRoutes = require('./routes/companies');
const walletRoutes    = require('./routes/wallet');
const reportsRoutes   = require('./routes/reports');
 
const app  = express();
const PORT = process.env.PORT || 3000;
 
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(express.static(path.join(__dirname, 'public')));
 
// ── HEALTH CHECK (UptimeRobot / Render) ──────────────────────────────────────
app.get('/health', (req, res) => {
  res.json({ status: 'ok', app: 'ceres', ts: new Date().toISOString() });
});
 
// ── API ───────────────────────────────────────────────────────────────────────
app.use('/api/auth',      authRoutes);
app.use('/api/companies', companiesRoutes);
app.use('/api/wallet',    walletRoutes);
app.use('/api/reports',   reportsRoutes);
 
// ── PÁGINAS HTML ──────────────────────────────────────────────────────────────
const pages = ['/', '/home', '/search', '/wallet', '/cursos', '/reports', '/admin', '/termos', '/privacidade'];
pages.forEach(pg => {
  app.get(pg, (req, res) => {
    const file = pg === '/' ? 'login.html' : `${pg.slice(1)}.html`;
    res.sendFile(path.join(__dirname, 'public', file));
  });
});
app.get('/register', (req, res) =>
  res.sendFile(path.join(__dirname, 'public', 'register.html')));
app.get('/recover', (req, res) =>
  res.sendFile(path.join(__dirname, 'public', 'recover.html')));
 
app.listen(PORT, '0.0.0.0', () => {
  console.log('Ceres rodando na porta ' + PORT);
});
