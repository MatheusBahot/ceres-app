const express  = require('express');
const Database = require('better-sqlite3');
const path     = require('path');
const { authMiddleware, adminOnly } = require('../middleware/auth');
 
const router = express.Router();
const db = new Database(path.join(__dirname, '../database/ceres.db'));
 
router.post('/', authMiddleware, (req, res) => {
  const { type, company_id, title, description } = req.body;
  if (!type || !title || !description)
    return res.status(400).json({ error: 'Preencha todos os campos.' });
  if (!['erro', 'sugestao', 'atualizacao'].includes(type))
    return res.status(400).json({ error: 'Tipo invalido.' });
  db.prepare(
    'INSERT INTO reports (user_id, type, company_id, title, description) VALUES (?,?,?,?,?)'
  ).run(req.user.id, type, company_id || null, title.trim(), description.trim());
  res.json({ message: 'Reportado com sucesso. Obrigado!' });
});
 
router.get('/', authMiddleware, adminOnly, (req, res) => {
  const { status } = req.query;
  const base = `
    SELECT r.*, u.name as user_name, c.nome_fantasia as company_name
    FROM reports r
    JOIN users u ON u.id = r.user_id
    LEFT JOIN companies c ON c.id = r.company_id
  `;
  const rows = status
    ? db.prepare(base + ' WHERE r.status = ? ORDER BY r.created_at DESC').all(status)
    : db.prepare(base + ' ORDER BY r.created_at DESC').all();
  res.json(rows);
});
 
router.patch('/:id/status', authMiddleware, adminOnly, (req, res) => {
  const { status } = req.body;
  if (!['aberto', 'em_analise', 'resolvido'].includes(status))
    return res.status(400).json({ error: 'Status invalido.' });
  db.prepare('UPDATE reports SET status = ? WHERE id = ?').run(status, req.params.id);
  res.json({ message: 'Status atualizado.' });
});
 
router.get('/my', authMiddleware, (req, res) => {
  res.json(db.prepare(`
    SELECT r.*, c.nome_fantasia as company_name FROM reports r
    LEFT JOIN companies c ON c.id = r.company_id
    WHERE r.user_id = ? ORDER BY r.created_at DESC
  `).all(req.user.id));
});
 
module.exports = router;
