const express  = require('express');
const Database = require('better-sqlite3');
const path     = require('path');
const { authMiddleware, adminOnly } = require('../middleware/auth');
 
const router = express.Router();
const db = new Database(path.join(__dirname, '../database/ceres.db'));
db.pragma('foreign_keys = ON');
 
// ── ATENÇÃO: /stats/summary DEVE vir antes de /:id ────────────────────────────
router.get('/stats/summary', authMiddleware, (req, res) => {
  const total    = db.prepare('SELECT COUNT(*) as c FROM companies').get().c;
  const cidades  = db.prepare('SELECT COUNT(DISTINCT municipio) as c FROM companies').get().c;
  const grupos   = db.prepare('SELECT COUNT(DISTINCT grupo) as c FROM companies').get().c;
  const porGrupo = db.prepare(
    'SELECT grupo, COUNT(*) as total FROM companies GROUP BY grupo ORDER BY total DESC'
  ).all();
  res.json({ total, cidades, grupos, porGrupo });
});
 
// ── MUNICÍPIOS — retorna [{municipio, total}] ordenado A-Z ────────────────────
router.get('/cities', authMiddleware, (req, res) => {
  let rows;
  if (req.user.role === 'admin') {
    rows = db.prepare(`
      SELECT municipio, COUNT(*) as total
      FROM companies
      GROUP BY municipio
      ORDER BY municipio COLLATE NOCASE
    `).all();
  } else {
    rows = db.prepare(`
      SELECT c.municipio, COUNT(*) as total
      FROM companies c
      WHERE c.id NOT IN (
        SELECT w.company_id FROM wallets w WHERE w.user_id != ?
      )
      GROUP BY c.municipio
      ORDER BY c.municipio COLLATE NOCASE
    `).all(req.user.id);
  }
  res.json(rows);
});
 
// ── GRUPOS POR MUNICÍPIO — retorna [{grupo, total}] ───────────────────────────
router.get('/groups/:city', authMiddleware, (req, res) => {
  const city = decodeURIComponent(req.params.city);
  let rows;
  if (req.user.role === 'admin') {
    rows = db.prepare(`
      SELECT grupo, COUNT(*) as total
      FROM companies
      WHERE municipio = ?
      GROUP BY grupo
      ORDER BY grupo COLLATE NOCASE
    `).all(city);
  } else {
    rows = db.prepare(`
      SELECT c.grupo, COUNT(*) as total
      FROM companies c
      WHERE c.municipio = ?
        AND c.id NOT IN (
          SELECT w.company_id FROM wallets w WHERE w.user_id != ?
        )
      GROUP BY c.grupo
      ORDER BY c.grupo COLLATE NOCASE
    `).all(city, req.user.id);
  }
  res.json(rows);
});
 
// ── LISTAR EMPRESAS — retorna array de empresas ───────────────────────────────
router.get('/list', authMiddleware, (req, res) => {
  const { city, group, q } = req.query;
 
  let query = `
    SELECT c.id, c.grupo, c.segmento, c.nome_fantasia, c.razao_social,
           c.cnpj, c.municipio, c.tel1, c.tel2, c.tel3, c.email,
           c.whatsapp, c.whatsapp_business, c.instagram, c.facebook, c.site,
           CASE WHEN w.id IS NOT NULL THEN 1 ELSE 0 END as in_my_wallet,
           w.status as wallet_status
    FROM companies c
    LEFT JOIN wallets w ON w.company_id = c.id AND w.user_id = ?
    WHERE 1=1
  `;
  const params = [req.user.id];
 
  if (city)  { query += ' AND c.municipio = ?';  params.push(decodeURIComponent(city));  }
  if (group) { query += ' AND c.grupo = ?';       params.push(decodeURIComponent(group)); }
  if (q) {
    const t = '%' + q + '%';
    query += ' AND (c.nome_fantasia LIKE ? OR c.razao_social LIKE ? OR c.cnpj LIKE ?)';
    params.push(t, t, t);
  }
 
  if (req.user.role !== 'admin') {
    query += ' AND c.id NOT IN (SELECT w2.company_id FROM wallets w2 WHERE w2.user_id != ?)';
    params.push(req.user.id);
  }
 
  query += ' ORDER BY c.nome_fantasia COLLATE NOCASE LIMIT 500';
 
  const rows = db.prepare(query).all(...params);
  res.json(rows);
});
 
// ── DETALHES DE UMA EMPRESA — DEVE vir depois das rotas específicas ───────────
router.get('/:id', authMiddleware, (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (isNaN(id)) return res.status(400).json({ error: 'ID inválido.' });
 
  const c = db.prepare('SELECT * FROM companies WHERE id = ?').get(id);
  if (!c) return res.status(404).json({ error: 'Empresa não encontrada.' });
 
  if (req.user.role !== 'admin') {
    const blocked = db.prepare(
      'SELECT id FROM wallets WHERE company_id = ? AND user_id != ?'
    ).get(id, req.user.id);
    if (blocked)
      return res.status(403).json({ error: 'Esta empresa está na carteira de outro vendedor.' });
  }
  res.json(c);
});
 
// ── ATUALIZAR EMPRESA (admin) ─────────────────────────────────────────────────
router.patch('/:id', authMiddleware, adminOnly, (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (isNaN(id)) return res.status(400).json({ error: 'ID inválido.' });
  const { grupo, segmento, nome_fantasia, razao_social, municipio, tel1, tel2, tel3, email } = req.body;
  db.prepare(`
    UPDATE companies SET
      grupo=COALESCE(?,grupo), segmento=COALESCE(?,segmento),
      nome_fantasia=COALESCE(?,nome_fantasia), razao_social=COALESCE(?,razao_social),
      municipio=COALESCE(?,municipio), tel1=COALESCE(?,tel1),
      tel2=COALESCE(?,tel2), tel3=COALESCE(?,tel3), email=COALESCE(?,email)
    WHERE id = ?
  `).run(grupo, segmento, nome_fantasia, razao_social, municipio, tel1, tel2, tel3, email, id);
  res.json({ message: 'Empresa atualizada.' });
});
 
module.exports = router;
