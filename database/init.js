const Database = require('better-sqlite3');
const bcrypt   = require('bcryptjs');
const path     = require('path');
const fs       = require('fs');
 
const DB_PATH   = path.join(__dirname, 'ceres.db');
const JSON_PATH = path.join(__dirname, '../data/bd_definitivo.json');
 
console.log('[init] Verificando banco de dados...');
 
const db = new Database(DB_PATH);
db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');
 
db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    email         TEXT    UNIQUE NOT NULL,
    password      TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'vendedor',
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    reset_token   TEXT,
    reset_expires TEXT
  );
 
  CREATE TABLE IF NOT EXISTS companies (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    grupo         TEXT,
    segmento      TEXT,
    nome_fantasia TEXT,
    razao_social  TEXT,
    cnpj          TEXT UNIQUE,
    municipio     TEXT,
    tel1          TEXT,
    tel2          TEXT,
    tel3          TEXT,
    email         TEXT,
    whatsapp      TEXT,
    whatsapp_business INTEGER DEFAULT 0,
    instagram     TEXT,
    facebook      TEXT,
    site          TEXT,
    prio          INTEGER DEFAULT 20
  );
 
  CREATE TABLE IF NOT EXISTS wallets (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    company_id INTEGER NOT NULL,
    status     TEXT    NOT NULL DEFAULT 'prospectar',
    notes      TEXT    DEFAULT '',
    added_at   TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (user_id)    REFERENCES users(id)     ON DELETE CASCADE,
    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
    UNIQUE(user_id, company_id)
  );
 
  CREATE TABLE IF NOT EXISTS reports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    type        TEXT    NOT NULL,
    company_id  INTEGER,
    title       TEXT    NOT NULL,
    description TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'aberto',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
  );
 
  CREATE INDEX IF NOT EXISTS idx_comp_municipio ON companies(municipio);
  CREATE INDEX IF NOT EXISTS idx_comp_grupo     ON companies(grupo);
  CREATE INDEX IF NOT EXISTS idx_comp_cnpj      ON companies(cnpj);
  CREATE INDEX IF NOT EXISTS idx_wallet_user    ON wallets(user_id);
  CREATE INDEX IF NOT EXISTS idx_wallet_company ON wallets(company_id);
`);
 
const { importarEmpresas } = require('./importCompanies');

const countExisting = db.prepare('SELECT COUNT(*) as c FROM companies').get().c;

if (countExisting === 0) {
  console.log('[init] Importando empresas...');
  const resultado = importarEmpresas(db, JSON_PATH);
  if (resultado.erro) {
    console.warn('[init] AVISO: ' + resultado.erro);
    console.warn('[init] Adicione o arquivo em data/ e reinicie o servidor.');
  } else {
    console.log('[init] ' + resultado.ok + ' empresas | ' + resultado.municipios + ' municipios.');
  }
} else {
  const mun = db.prepare('SELECT COUNT(DISTINCT municipio) as c FROM companies').get().c;
  console.log('[init] Banco existente: ' + countExisting + ' empresas | ' + mun + ' municipios.');
}
 
if (!db.prepare("SELECT id FROM users WHERE role='admin' LIMIT 1").get()) {
  const adminEmail = process.env.ADMIN_EMAIL || 'admin@ceresrefrigeracao.com.br';
  const adminPass  = process.env.ADMIN_PASSWORD || require('crypto').randomBytes(9).toString('base64');
  db.prepare("INSERT INTO users (name, email, password, role) VALUES (?,?,?,?)")
    .run('Administrador', adminEmail, bcrypt.hashSync(adminPass, 10), 'admin');
  if (process.env.ADMIN_PASSWORD) {
    console.log('[init] Admin criado: ' + adminEmail + ' (senha definida via ADMIN_PASSWORD)');
  } else {
    console.log('[init] Admin criado: ' + adminEmail + ' / senha gerada automaticamente: ' + adminPass);
    console.log('[init] Copie essa senha AGORA — ela so aparece uma vez nos logs.');
  }
}
 
db.close();
console.log('[init] OK.');
