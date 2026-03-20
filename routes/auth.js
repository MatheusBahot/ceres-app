const express  = require('express');
const bcrypt   = require('bcryptjs');
const jwt      = require('jsonwebtoken');
const { v4: uuidv4 } = require('uuid');
const Database = require('better-sqlite3');
const path     = require('path');
const { authMiddleware, adminOnly } = require('../middleware/auth');
 
require('dotenv').config();
const router = express.Router();
const db = new Database(path.join(__dirname, '../database/ceres.db'));
db.pragma('foreign_keys = ON');
 
// ── LOGIN ─────────────────────────────────────────────────────────────────────
router.post('/login', (req, res) => {
  const { email, password } = req.body;
  if (!email || !password) return res.status(400).json({ error: 'Preencha todos os campos.' });
 
  const user = db.prepare('SELECT * FROM users WHERE email = ? AND active = 1').get(email.toLowerCase().trim());
  if (!user) return res.status(401).json({ error: 'E-mail ou senha incorretos.' });
 
  const match = bcrypt.compareSync(password, user.password);
  if (!match) return res.status(401).json({ error: 'E-mail ou senha incorretos.' });
 
  const token = jwt.sign(
    { id: user.id, name: user.name, email: user.email, role: user.role },
    process.env.JWT_SECRET,
    { expiresIn: '8h' }
  );
 
  res.json({
    token,
    user: { id: user.id, name: user.name, email: user.email, role: user.role }
  });
});
 
 
// ── AUTO-CADASTRO PÚBLICO ─────────────────────────────────────────────────────
router.post('/signup', (req, res) => {
  const { name, email, password } = req.body;
  if (!name || !email || !password)
    return res.status(400).json({ error: 'Preencha todos os campos.' });
  if (password.length < 8)
    return res.status(400).json({ error: 'Senha mínima de 8 caracteres.' });
 
  const exists = db.prepare('SELECT id FROM users WHERE email = ?')
    .get(email.toLowerCase().trim());
  if (exists)
    return res.status(409).json({ error: 'E-mail já cadastrado.' });
 
  const hash = bcrypt.hashSync(password, 10);
  db.prepare('INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)')
    .run(name.trim(), email.toLowerCase().trim(), hash, 'vendedor');
 
  // Já faz login automático após cadastro
  const user = db.prepare('SELECT * FROM users WHERE email = ?')
    .get(email.toLowerCase().trim());
  const token = jwt.sign(
    { id: user.id, name: user.name, email: user.email, role: user.role },
    process.env.JWT_SECRET,
    { expiresIn: '8h' }
  );
  res.json({
    message: 'Conta criada com sucesso.',
    token,
    user: { id: user.id, name: user.name, email: user.email, role: user.role }
  });
});
 
// ── CRIAR VENDEDOR (apenas admin) ─────────────────────────────────────────────
router.post('/register', authMiddleware, adminOnly, (req, res) => {
  const { name, email, password } = req.body;
  if (!name || !email || !password) return res.status(400).json({ error: 'Preencha todos os campos.' });
  if (password.length < 8) return res.status(400).json({ error: 'Senha mínima de 8 caracteres.' });
 
  const exists = db.prepare('SELECT id FROM users WHERE email = ?').get(email.toLowerCase().trim());
  if (exists) return res.status(409).json({ error: 'E-mail já cadastrado.' });
 
  const hash = bcrypt.hashSync(password, 10);
  db.prepare('INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)').run(
    name.trim(), email.toLowerCase().trim(), hash, 'vendedor'
  );
 
  res.json({ message: `Vendedor "${name}" criado com sucesso.` });
});
 
// ── LISTAR VENDEDORES (admin) ──────────────────────────────────────────────────
router.get('/users', authMiddleware, adminOnly, (req, res) => {
  const users = db.prepare(
    "SELECT id, name, email, role, active, created_at FROM users ORDER BY created_at DESC"
  ).all();
  res.json(users);
});
 
// ── ATIVAR / DESATIVAR VENDEDOR (admin) ────────────────────────────────────────
router.patch('/users/:id/toggle', authMiddleware, adminOnly, (req, res) => {
  const user = db.prepare('SELECT * FROM users WHERE id = ?').get(req.params.id);
  if (!user) return res.status(404).json({ error: 'Usuário não encontrado.' });
  if (user.role === 'admin') return res.status(400).json({ error: 'Não é possível desativar o admin.' });
 
  const newStatus = user.active === 1 ? 0 : 1;
  db.prepare('UPDATE users SET active = ? WHERE id = ?').run(newStatus, user.id);
  res.json({ message: newStatus === 1 ? 'Usuário ativado.' : 'Usuário desativado.' });
});
 
// ── ALTERAR PRÓPRIA SENHA ─────────────────────────────────────────────────────
router.post('/change-password', authMiddleware, (req, res) => {
  const { current_password, new_password } = req.body;
  if (!current_password || !new_password) return res.status(400).json({ error: 'Preencha todos os campos.' });
  if (new_password.length < 8) return res.status(400).json({ error: 'Nova senha mínima de 8 caracteres.' });
 
  const user = db.prepare('SELECT * FROM users WHERE id = ?').get(req.user.id);
  if (!bcrypt.compareSync(current_password, user.password))
    return res.status(401).json({ error: 'Senha atual incorreta.' });
 
  const hash = bcrypt.hashSync(new_password, 10);
  db.prepare('UPDATE users SET password = ? WHERE id = ?').run(hash, user.id);
  res.json({ message: 'Senha alterada com sucesso.' });
});
 
// ── SOLICITAR RESET DE SENHA ──────────────────────────────────────────────────
router.post('/forgot-password', (req, res) => {
  const { email } = req.body;
  if (!email) return res.status(400).json({ error: 'Informe o e-mail.' });
 
  const user = db.prepare('SELECT * FROM users WHERE email = ? AND active = 1').get(email.toLowerCase().trim());
  // Sempre retorna sucesso (segurança — não revela se email existe)
  if (!user) return res.json({ message: 'Se o e-mail existir, você receberá as instruções.' });
 
  const token  = uuidv4();
  const expiry = new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString(); // 2h
 
  db.prepare('UPDATE users SET reset_token = ?, reset_expires = ? WHERE id = ?').run(token, expiry, user.id);
 
  // Em produção, enviaria e-mail via nodemailer.
  // Em dev, apenas retorna o token no response (admin pode ver no painel).
  console.log(`\n🔑 Token de reset para ${email}: ${token}\n`);
 
  if (process.env.NODE_ENV === 'development') {
    return res.json({
      message: 'Token de redefinição gerado (modo dev).',
      dev_token: token   // Só visível em desenvolvimento
    });
  }
  res.json({ message: 'Se o e-mail existir, você receberá as instruções.' });
});
 
// ── REDEFINIR SENHA COM TOKEN ─────────────────────────────────────────────────
router.post('/reset-password', (req, res) => {
  const { token, new_password } = req.body;
  if (!token || !new_password) return res.status(400).json({ error: 'Dados incompletos.' });
  if (new_password.length < 8) return res.status(400).json({ error: 'Senha mínima de 8 caracteres.' });
 
  const user = db.prepare('SELECT * FROM users WHERE reset_token = ?').get(token);
  if (!user) return res.status(400).json({ error: 'Token inválido ou expirado.' });
 
  const now = new Date().toISOString();
  if (user.reset_expires < now) return res.status(400).json({ error: 'Token expirado. Solicite novamente.' });
 
  const hash = bcrypt.hashSync(new_password, 10);
  db.prepare('UPDATE users SET password = ?, reset_token = NULL, reset_expires = NULL WHERE id = ?')
    .run(hash, user.id);
 
  res.json({ message: 'Senha redefinida com sucesso.' });
});
 
// ── PERFIL DO USUÁRIO LOGADO ──────────────────────────────────────────────────
router.get('/me', authMiddleware, (req, res) => {
  const user = db.prepare('SELECT id, name, email, role, created_at FROM users WHERE id = ?').get(req.user.id);
  if (!user) return res.status(404).json({ error: 'Usuário não encontrado.' });
  res.json(user);
});
 
module.exports = router;
