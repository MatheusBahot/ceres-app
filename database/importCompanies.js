const fs = require('fs');

function normaliza(e) {
  return {
    grupo:         e.grupo         || e['Grupo']        || 'OUTROS',
    segmento:      e.Segmento      || e['Segmento']     || '',
    nome_fantasia: e.Nome_Fantasia || e['Nome Fantasia']|| '',
    razao_social:  e.Razao_Social  || e['Razão Social'] || '',
    cnpj:          e.CNPJ          || e['cnpj']         || '',
    municipio:     e.Municipio     || e['Município']    || '',
    tel1:          e.Tel1          || e['Telefone 1']   || '',
    tel2:          e.Tel2          || e['Telefone 2']   || '',
    tel3:          e.Tel3          || e['Telefone 3']   || '',
    email:         e.Email         || e['E-mail']       || '',
    whatsapp:          e.whatsapp_number   || '',
    whatsapp_business: e.whatsapp_business ? 1 : 0,
    instagram:         (e.livre_instagram || e.site_instagram) ? ('https://instagram.com/' + (e.livre_instagram || e.site_instagram)) : '',
    facebook:          (e.livre_facebook  || e.site_facebook)  ? ('https://facebook.com/'  + (e.livre_facebook  || e.site_facebook))  : '',
    site:              e.site_url || '',
    prio:          e.prio          || 20,
  };
}

/**
 * Importa/atualiza empresas a partir de um JSON, preservando o "id" das
 * que ja existem (mesmo CNPJ) - isso mantem intactas as carteiras e
 * relatorios ja criados por vendedores, mesmo apos reimportar.
 * Remove do banco qualquer empresa cujo CNPJ nao esteja mais no arquivo.
 */
function importarEmpresas(db, jsonPath) {
  if (!fs.existsSync(jsonPath)) {
    return { erro: 'Arquivo nao encontrado: ' + jsonPath };
  }
  const empresas = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));

  const upsert = db.prepare(`
    INSERT INTO companies
      (grupo, segmento, nome_fantasia, razao_social, cnpj,
       municipio, tel1, tel2, tel3, email, whatsapp, whatsapp_business,
       instagram, facebook, site, prio)
    VALUES
      (@grupo, @segmento, @nome_fantasia, @razao_social, @cnpj,
       @municipio, @tel1, @tel2, @tel3, @email, @whatsapp, @whatsapp_business,
       @instagram, @facebook, @site, @prio)
    ON CONFLICT(cnpj) DO UPDATE SET
      grupo=excluded.grupo, segmento=excluded.segmento,
      nome_fantasia=excluded.nome_fantasia, razao_social=excluded.razao_social,
      municipio=excluded.municipio, tel1=excluded.tel1, tel2=excluded.tel2,
      tel3=excluded.tel3, email=excluded.email, whatsapp=excluded.whatsapp,
      whatsapp_business=excluded.whatsapp_business, instagram=excluded.instagram,
      facebook=excluded.facebook, site=excluded.site, prio=excluded.prio
  `);

  const selecionarTodos = db.prepare('SELECT id, cnpj FROM companies');
  const deletar = db.prepare('DELETE FROM companies WHERE id = ?');

  const rodar = db.transaction((lista) => {
    let ok = 0, ignorados = 0;
    const cnpjsValidos = new Set();

    for (const e of lista) {
      const dados = normaliza(e);
      if (!dados.cnpj) { ignorados++; continue; }
      cnpjsValidos.add(dados.cnpj);
      try {
        upsert.run(dados);
        ok++;
      } catch (_) {
        ignorados++;
      }
    }

    const existentes = selecionarTodos.all();
    let removidos = 0;
    for (const row of existentes) {
      if (!cnpjsValidos.has(row.cnpj)) {
        deletar.run(row.id);
        removidos++;
      }
    }

    return { ok, ignorados, removidos };
  });

  const resultado = rodar(empresas);
  const municipios = db.prepare('SELECT COUNT(DISTINCT municipio) as c FROM companies').get().c;
  return { ...resultado, total: empresas.length, municipios };
}

module.exports = { importarEmpresas, normaliza };
