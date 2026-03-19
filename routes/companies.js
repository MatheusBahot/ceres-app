const express  = require('express');
const Database = require('better-sqlite3');
const path     = require('path');
const { authMiddleware, adminOnly } = require('../middleware/auth');
 
const router = express.Router();
const db = new Database(path.join(__dirname, '../database/ceres.db'));
db.pragma('foreign_keys = ON');
 
router.get('/cities', authMiddleware, (req, res) => {
  let cities;
  if (req.user.role === 'admin') {
    cities = db.prepare(
      'SELECT DISTINCT municipio FROM companies ORDER BY municipio COLLATE NOCASE'
    ).all();
  } else {
    cities = db.prepare(`
      SELECT DISTINCT c.municipio FROM companies c
      WHERE c.id NOT IN (
        SELECT w.company_id FROM wallets w WHERE w.user_id != ?
      )
      ORDER BY c.municipio COLLATE NOCASE
    `).all(req.user.id);
  }
  res.json(cities.map(r => r.municipio));
});
 
router.get('/groups/:city', authMiddleware, (req, res) => {
  const city = decodeURIComponent(req.params.city);
  let rows;
  if (req.user.role === 'admin') {
    rows = db.prepare(`
      SELECT grupo, COUNT(*) as total FROM companies
      WHERE municipio = ? GROUP BY grupo ORDER BY total DESC
    `).all(city);
  } else {
    rows = db.prepare(`
      SELECT c.grupo, COUNT(*) as total FROM companies c
      WHERE c.municipio = ?
        AND c.id NOT IN (SELECT w.company_id FROM wallets w WHERE w.user_id != ?)
      GROUP BY c.grupo ORDER BY total DESC
    `).all(city, req.user.id);
  }
  res.json(rows);
});
 
router.get('/list', authMiddleware, (req, res) => {
  const { city, group, q } = req.query;
  let query = `
    SELECT c.id, c.grupo, c.segmento, c.nome_fantasia, c.razao_social,
           c.cnpj, c.municipio, c.tel1, c.tel2, c.tel3, c.email,
           w.id as in_my_wallet, w.status as wallet_status
    FROM companies c
    LEFT JOIN wallets w ON w.company_id = c.id AND w.user_id = ?
    WHERE 1=1
  `;
  const params = [req.user.id];
  if (city)  { query += ' AND c.municipio = ?';  params.push(decodeURIComponent(city)); }
  if (group) { query += ' AND c.grupo = ?';       params.push(decodeURIComponent(group)); }
  if (q) {
    query += ' AND (c.nome_fantasia LIKE ? OR c.razao_social LIKE ? OR c.cnpj LIKE ?)';
    const t = '%' + q + '%';
    params.push(t, t, t);
  }
  if (req.user.role !== 'admin') {
    query += ' AND c.id NOT IN (SELECT w2.company_id FROM wallets w2 WHERE w2.user_id != ?)';
    params.push(req.user.id);
  }
  query += ' ORDER BY c.municipio COLLATE NOCASE, c.nome_fantasia COLLATE NOCASE LIMIT 500';
  res.json(db.prepare(query).all(...params));
});
 
router.get('/stats/summary', authMiddleware, (req, res) => {
  res.json({
    total:    db.prepare('SELECT COUNT(*) as c FROM companies').get().c,
    cidades:  db.prepare('SELECT COUNT(DISTINCT municipio) as c FROM companies').get().c,
    grupos:   db.prepare('SELECT COUNT(DISTINCT grupo) as c FROM companies').get().c,
    porGrupo: db.prepare(
      'SELECT grupo, COUNT(*) as total FROM companies GROUP BY grupo ORDER BY total DESC LIMIT 12'
    ).all(),
  });
});
 
router.patch('/:id', authMiddleware, adminOnly, (req, res) => {
  const { grupo, segmento, nome_fantasia, razao_social, municipio,
          tel1, tel2, tel3, email } = req.body;
  db.prepare(`
    UPDATE companies SET
      grupo=COALESCE(?,grupo), segmento=COALESCE(?,segmento),
      nome_fantasia=COALESCE(?,nome_fantasia), razao_social=COALESCE(?,razao_social),
      municipio=COALESCE(?,municipio), tel1=COALESCE(?,tel1),
      tel2=COALESCE(?,tel2), tel3=COALESCE(?,tel3), email=COALESCE(?,email)
    WHERE id = ?
  `).run(grupo, segmento, nome_fantasia, razao_social,
          municipio, tel1, tel2, tel3, email, req.params.id);
  res.json({ message: 'Empresa atualizada.' });
});
 
module.exports = router;
