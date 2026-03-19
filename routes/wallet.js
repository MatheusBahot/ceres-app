const express  = require('express');
const Database = require('better-sqlite3');
const path     = require('path');
const { authMiddleware, adminOnly } = require('../middleware/auth');
 
const router = express.Router();
const db = new Database(path.join(__dirname, '../database/ceres.db'));
db.pragma('foreign_keys = ON');
 
router.get('/', authMiddleware, (req, res) => {
  const userId = (req.user.role === 'admin' && req.query.user_id)
    ? req.query.user_id : req.user.id;
  const rows = db.prepare(`
    SELECT w.id, w.status, w.notes, w.added_at,
           c.id as company_id, c.grupo, c.segmento, c.nome_fantasia,
           c.razao_social, c.cnpj, c.municipio, c.tel1, c.tel2, c.tel3, c.email
    FROM wallets w JOIN companies c ON c.id = w.company_id
    WHERE w.user_id = ? ORDER BY w.added_at DESC
  `).all(userId);
  const summary = {
    total:      rows.length,
    prospectar: rows.filter(r => r.status === 'prospectar').length,
    contatado:  rows.filter(r => r.status === 'contatado').length,
    cliente:    rows.filter(r => r.status === 'cliente').length,
    perdido:    rows.filter(r => r.status === 'perdido').length,
  };
  res.json({ wallet: rows, summary });
});
 
router.post('/add/:companyId', authMiddleware, (req, res) => {
  const cid = req.params.companyId;
  if (db.prepare('SELECT id FROM wallets WHERE company_id = ? AND user_id != ?')
        .get(cid, req.user.id))
    return res.status(409).json({ error: 'Empresa na carteira de outro vendedor.' });
  if (db.prepare('SELECT id FROM wallets WHERE company_id = ? AND user_id = ?')
        .get(cid, req.user.id))
    return res.status(409).json({ error: 'Empresa ja na sua carteira.' });
  db.prepare('INSERT INTO wallets (user_id, company_id, notes) VALUES (?, ?, ?)')
    .run(req.user.id, cid, req.body.notes || '');
  res.json({ message: 'Adicionada a carteira.' });
});
 
router.delete('/remove/:companyId', authMiddleware, (req, res) => {
  const r = db.prepare('DELETE FROM wallets WHERE company_id = ? AND user_id = ?')
    .run(req.params.companyId, req.user.id);
  if (r.changes === 0)
    return res.status(404).json({ error: 'Nao encontrada na carteira.' });
  res.json({ message: 'Removida da carteira.' });
});
 
router.patch('/update/:companyId', authMiddleware, (req, res) => {
  const { status, notes } = req.body;
  const valid = ['prospectar', 'contatado', 'cliente', 'perdido'];
  if (status && !valid.includes(status))
    return res.status(400).json({ error: 'Status invalido.' });
  if (!db.prepare('SELECT id FROM wallets WHERE company_id = ? AND user_id = ?')
        .get(req.params.companyId, req.user.id))
    return res.status(404).json({ error: 'Nao encontrada na carteira.' });
  db.prepare(`
    UPDATE wallets SET
      status = COALESCE(?, status),
      notes  = COALESCE(?, notes)
    WHERE company_id = ? AND user_id = ?
  `).run(status, notes, req.params.companyId, req.user.id);
  res.json({ message: 'Carteira atualizada.' });
});
 
router.get('/admin/overview', authMiddleware, adminOnly, (req, res) => {
  res.json(db.prepare(`
    SELECT u.id, u.name, u.email,
           COUNT(w.id) as total,
           SUM(CASE WHEN w.status='prospectar' THEN 1 ELSE 0 END) as prospectar,
           SUM(CASE WHEN w.status='contatado'  THEN 1 ELSE 0 END) as contatado,
           SUM(CASE WHEN w.status='cliente'    THEN 1 ELSE 0 END) as cliente,
           SUM(CASE WHEN w.status='perdido'    THEN 1 ELSE 0 END) as perdido
    FROM users u LEFT JOIN wallets w ON w.user_id = u.id
    WHERE u.role = 'vendedor'
    GROUP BY u.id ORDER BY total DESC
  `).all());
});
 
module.exports = router;
