const Database = require('better-sqlite3');
const bcrypt   = require('bcryptjs');
const path     = require('path');
const fs       = require('fs');
 
const DB_PATH   = path.join(__dirname, 'ceres.db');
const JSON_PATH = path.join(__dirname, '../data/bd_definitivo.json');
 
console.log('Iniciando banco de dados Ceres...');
 
const db = new Database(DB_PATH);
db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');
 
// ── TABELAS ───────────────────────────────────────────────────────────────────
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
 
// ── IMPORTAR EMPRESAS ─────────────────────────────────────────────────────────
const countExisting = db.prepare('SELECT COUNT(*) as c FROM companies').get().c;
 
if (countExisting === 0) {
  console.log('Importando empresas do banco de dados...');
 
  if (!fs.existsSync(JSON_PATH)) {
    console.error('ERRO: arquivo ' + JSON_PATH + ' nao encontrado.');
    console.error('Copie o bd_definitivo.json para a pasta data/ e execute novamente.');
    process.exit(1);
  }
 
  const raw      = fs.readFileSync(JSON_PATH, 'utf8');
  const empresas = JSON.parse(raw);
 
  // Normaliza chaves — suporta tanto o formato novo quanto o original do Excel
  function normaliza(e) {
    return {
      grupo:         e.grupo         || e['Grupo']          || e['grupo']          || 'OUTROS',
      segmento:      e.Segmento      || e['Segmento']        || e['segmento']       || '',
      nome_fantasia: e.Nome_Fantasia || e['Nome Fantasia']   || e['nome_fantasia']  || '',
      razao_social:  e.Razao_Social  || e['Razão Social']    || e['razao_social']   || '',
      cnpj:          e.CNPJ          || e['cnpj']            || '',
      municipio:     e.Municipio     || e['Município']       || e['municipio']      || '',
      tel1:          e.Tel1          || e['Telefone 1']      || e['tel1']           || '',
      tel2:          e.Tel2          || e['Telefone 2']      || e['tel2']           || '',
      tel3:          e.Tel3          || e['Telefone 3']      || e['tel3']           || '',
      email:         e.Email         || e['E-mail']          || e['email']          || '',
      prio:          e.prio          || 20,
    };
  }
 
  const insert = db.prepare(`
    INSERT OR IGNORE INTO companies
      (grupo, segmento, nome_fantasia, razao_social, cnpj,
       municipio, tel1, tel2, tel3, email, prio)
    VALUES
      (@grupo, @segmento, @nome_fantasia, @razao_social, @cnpj,
       @municipio, @tel1, @tel2, @tel3, @email, @prio)
  `);
 
  const run = db.transaction(list => {
    let ok = 0, skip = 0;
    for (const e of list) {
      try {
        const n = normaliza(e);
        if (!n.cnpj && !n.nome_fantasia) { skip++; continue; }
        insert.run(n);
        ok++;
      } catch(err) { skip++; }
    }
    return { ok, skip };
  });
 
  const { ok, skip } = run(empresas);
  console.log(ok + ' empresas importadas. ' + (skip ? skip + ' ignoradas.' : ''));
 
  // Validar
  const mun = db.prepare('SELECT COUNT(DISTINCT municipio) as c FROM companies').get().c;
  console.log(mun + ' municipios distintos no banco.');
 
} else {
  const mun = db.prepare('SELECT COUNT(DISTINCT municipio) as c FROM companies').get().c;
  console.log('Banco ja carregado: ' + countExisting + ' empresas, ' + mun + ' municipios.');
}
 
// ── ADMIN PADRÃO ──────────────────────────────────────────────────────────────
const adminExists = db.prepare("SELECT id FROM users WHERE role='admin' LIMIT 1").get();
if (!adminExists) {
  const hash = bcrypt.hashSync('Ceres@2024!', 10);
  db.prepare("INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)")
    .run('Administrador', 'admin@ceresrefrigeracao.com.br', hash, 'admin');
  console.log('Admin criado: admin@ceresrefrigeracao.com.br / Ceres@2024!');
}
 
db.close();
console.log('Banco de dados pronto!');
