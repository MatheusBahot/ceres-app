require('dotenv').config();
const express = require('express');
const path    = require('path');
const cors    = require('cors');
 
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
 
app.use('/api/auth',      authRoutes);
app.use('/api/companies', companiesRoutes);
app.use('/api/wallet',    walletRoutes);
app.use('/api/reports',   reportsRoutes);
 
const pages = ['/', '/home', '/search', '/wallet', '/reports', '/admin'];
pages.forEach(p => {
  app.get(p, (req, res) => {
    const file = p === '/' ? 'login.html' : p.slice(1) + '.html';
    res.sendFile(path.join(__dirname, 'public', file));
  });
});
 
app.get('/recover', (req, res) =>
  res.sendFile(path.join(__dirname, 'public', 'recover.html')));
 
app.listen(PORT, () => {
  console.log('\n Ceres rodando em http://localhost:' + PORT);
  console.log('    Admin: admin@ceresrefrigeracao.com.br / Ceres@2024!\n');
});
