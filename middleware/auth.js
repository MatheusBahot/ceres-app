const jwt = require('jsonwebtoken');
require('dotenv').config();
 
function authMiddleware(req, res, next) {
  const header = req.headers['authorization'];
  if (!header) return res.status(401).json({ error: 'Token nao fornecido.' });
 
  const token = header.split(' ')[1];
  if (!token) return res.status(401).json({ error: 'Token invalido.' });
 
  try {
    const payload = jwt.verify(token, process.env.JWT_SECRET);
    req.user = payload;
    next();
  } catch (e) {
    return res.status(401).json({ error: 'Sessao expirada. Faca login novamente.' });
  }
}
 
function adminOnly(req, res, next) {
  if (req.user?.role !== 'admin') {
    return res.status(403).json({ error: 'Acesso restrito ao administrador.' });
  }
  next();
}
 
module.exports = { authMiddleware, adminOnly };
