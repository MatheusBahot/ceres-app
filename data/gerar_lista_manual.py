"""
Gera uma pagina HTML autonoma (zero API, zero servidor) pra voce confirmar
WhatsApp manualmente e buscar Maps/redes sociais com UM CLIQUE por empresa.

Separa numeros que JA SAO formato de celular (candidato real a WhatsApp)
dos que sao fixo (baixa chance, fica numa secao separada, sem gastar seu
clique). Adiciona 3 botoes de busca por empresa que abrem o Google Maps,
e o Google filtrado por Instagram e por Facebook - SEM raspar nada, voce
quem ve e decide o que copiar.

Tambem tem um campo pra voce colar um numero achado manualmente, que vira
botao de WhatsApp na hora.

Uso:
    python3 data/gerar_lista_manual.py
    (depois abra data/lista_whatsapp_manual.html no navegador)
"""
import json, os, re
from urllib.parse import quote

ENRIQUECIDO_PATH = "data/bd_enriquecido.json"
ORIGINAL_PATH    = "data/bd_definitivo.json"
OUT_HTML         = "data/lista_whatsapp_manual.html"

CAMPOS_TELEFONE = [
    "Tel1", "Tel2", "Tel3",
    "receita_tel1", "receita_tel2",
    "maps_tel", "aws_tel", "here_tel", "osm_tel",
    "livre_whatsapp_tel", "livre_tel",
]


def eh_celular(digitos):
    return len(digitos) == 11 and digitos[2] == "9"


def normaliza_e164(t):
    d = re.sub(r"\D", "", t or "")
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]
    if len(d) in (10, 11):
        return ("+55" + d, eh_celular(d))
    return None


def coletar_numeros(e):
    vistos, moveis, fixos = set(), [], []
    for campo in CAMPOS_TELEFONE:
        r = normaliza_e164(e.get(campo, ""))
        if r and r[0] not in vistos:
            vistos.add(r[0])
            (moveis if r[1] else fixos).append((campo, r[0]))
    return moveis, fixos


def main():
    path = ENRIQUECIDO_PATH if os.path.exists(ENRIQUECIDO_PATH) else ORIGINAL_PATH
    print(f"Carregando base de {path}...")
    with open(path, encoding="utf-8") as f:
        empresas = json.load(f)

    linhas = []
    for idx, e in enumerate(empresas):
        moveis, fixos = coletar_numeros(e)
        nome = e.get("Nome_Fantasia") or e.get("Razao_Social") or "?"
        municipio = e.get("Municipio", "")
        query_busca = quote(f"{nome} {municipio} Bahia")
        linhas.append({
            "id": idx,
            "nome": nome,
            "municipio": municipio,
            "cnpj": e.get("CNPJ", ""),
            "moveis": moveis,
            "fixos": fixos,
            "instagram": e.get("livre_instagram", ""),
            "facebook": e.get("livre_facebook", ""),
            "busca_maps": f"https://www.google.com/maps/search/{query_busca}",
            "busca_insta": f"https://www.google.com/search?q={quote('site:instagram.com')}+{query_busca}",
            "busca_fb": f"https://www.google.com/search?q={quote('site:facebook.com')}+{query_busca}",
        })

    com_movel = sum(1 for l in linhas if l["moveis"])
    print(f"{com_movel} de {len(linhas)} empresas ja tem celular real (prioridade alta).")
    print(f"As demais entram na fila de busca manual assistida (Maps/Instagram/Facebook).")

    dados_js = json.dumps(linhas, ensure_ascii=False)

    html = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Verificacao manual de WhatsApp - Ceres</title>
<style>
  body { font-family: -apple-system, Arial, sans-serif; max-width: 950px; margin: 20px auto; padding: 0 16px; background: #f5f6f8; }
  h1 { font-size: 1.3rem; }
  .barra { display: flex; gap: 10px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
  input[type=text] { flex: 1; padding: 8px; border-radius: 8px; border: 1px solid #ccc; min-width: 200px; }
  select { padding: 8px; border-radius: 8px; border: 1px solid #ccc; }
  button { padding: 8px 14px; border-radius: 8px; border: none; cursor: pointer; font-weight: 600; }
  .btn-export { background: #333; color: #fff; }
  .stats { color: #555; font-size: 0.85rem; margin-bottom: 14px; }
  .card { background: #fff; border-radius: 10px; padding: 12px 16px; margin-bottom: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
  .card.confirmado { border-left: 4px solid #25D366; }
  .card.recusado { border-left: 4px solid #d9534f; opacity: 0.55; }
  .card.prioridade { border-left: 4px solid #f0ad4e; }
  .nome { font-weight: 700; }
  .muni { color: #777; font-size: 0.85rem; }
  .secao-label { font-size: 0.7rem; text-transform: uppercase; color: #999; margin-top: 8px; }
  .nums { margin-top: 4px; display: flex; gap: 8px; flex-wrap: wrap; }
  .wa-btn { background: #25D366; color: #fff; text-decoration: none; padding: 6px 12px; border-radius: 20px; font-size: 0.85rem; }
  .wa-btn.fixo { background: #999; }
  .fonte { font-size: 0.7rem; opacity: 0.8; margin-left: 4px; }
  .busca-btn { background: #eee; color: #333; text-decoration: none; padding: 6px 12px; border-radius: 20px; font-size: 0.85rem; border: 1px solid #ddd; }
  .social-btn { background: #405DE6; color: #fff; text-decoration: none; padding: 6px 12px; border-radius: 20px; font-size: 0.85rem; }
  .acoes { margin-top: 10px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .btn-sim { background: #25D366; color: #fff; }
  .btn-nao { background: #d9534f; color: #fff; }
  .input-manual { padding: 6px 10px; border-radius: 20px; border: 1px solid #ccc; font-size: 0.85rem; width: 160px; }
  .btn-add { background: #333; color: #fff; border-radius: 20px; padding: 6px 12px; font-size: 0.85rem; }
  #vazio { text-align: center; color: #888; padding: 40px; }
</style>
</head>
<body>

<h1>Verificacao manual de WhatsApp + busca assistida</h1>
<p class="stats" id="stats"></p>

<div class="barra">
  <input type="text" id="filtro" placeholder="Filtrar por nome ou municipio...">
  <select id="ordem">
    <option value="prioridade">Celular real primeiro</option>
    <option value="todas">Todas na ordem original</option>
    <option value="pendentes">So nao verificadas</option>
  </select>
  <button class="btn-export" onclick="exportarCSV()">Baixar resultado (CSV)</button>
</div>

<div id="lista"></div>
<div id="vazio" style="display:none">Nenhuma empresa encontrada com esse filtro.</div>

<script>
const EMPRESAS = __DADOS__;
const CHAVE = 'ceres_wa_manual_v2';

function carregarProgresso() {
  try { return JSON.parse(localStorage.getItem(CHAVE)) || {}; }
  catch(e) { return {}; }
}
function salvarProgresso(p) { localStorage.setItem(CHAVE, JSON.stringify(p)); }
let progresso = carregarProgresso();  // { id: {status, manual} }

function marcar(id, status) {
  progresso[id] = progresso[id] || {};
  progresso[id].status = status;
  salvarProgresso(progresso);
  render();
}

function addManual(id) {
  const input = document.getElementById('manual-' + id);
  const valor = input.value.replace(/\\D/g, '');
  if (valor.length < 10) { alert('Digite um numero valido (com DDD).'); return; }
  progresso[id] = progresso[id] || {};
  progresso[id].manual = valor.startsWith('55') ? '+' + valor : '+55' + valor;
  salvarProgresso(progresso);
  render();
}

function atualizarStats() {
  const total = EMPRESAS.length;
  const comCelular = EMPRESAS.filter(e => e.moveis.length > 0).length;
  const sim = Object.values(progresso).filter(v => v.status === 'sim').length;
  const nao = Object.values(progresso).filter(v => v.status === 'nao').length;
  document.getElementById('stats').textContent =
    `${total} empresas no total | ${comCelular} ja tem celular real | ${sim} confirmadas com WhatsApp | ${nao} sem WhatsApp | ${total - sim - nao} pendentes`;
}

function render() {
  const filtro = document.getElementById('filtro').value.toLowerCase();
  const ordem = document.getElementById('ordem').value;
  const lista = document.getElementById('lista');
  lista.innerHTML = '';
  let visiveis = 0;

  let itens = [...EMPRESAS];
  if (ordem === 'prioridade') {
    itens.sort((a, b) => (b.moveis.length > 0) - (a.moveis.length > 0));
  }
  if (ordem === 'pendentes') {
    itens = itens.filter(e => !progresso[e.id] || !progresso[e.id].status);
  }

  for (const e of itens) {
    if (filtro && !(e.nome.toLowerCase().includes(filtro) || e.municipio.toLowerCase().includes(filtro))) continue;
    visiveis++;

    const st = progresso[e.id] || {};
    const div = document.createElement('div');
    div.className = 'card' + (st.status === 'sim' ? ' confirmado' : st.status === 'nao' ? ' recusado' : e.moveis.length ? ' prioridade' : '');

    let movelHtml = '';
    for (const [fonte, numero] of e.moveis) {
      const dig = numero.replace(/\\D/g, '');
      movelHtml += `<a class="wa-btn" href="https://wa.me/${dig}" target="_blank">💬 ${numero}<span class="fonte">(${fonte})</span></a>`;
    }
    if (st.manual) {
      const dig = st.manual.replace(/\\D/g, '');
      movelHtml += `<a class="wa-btn" href="https://wa.me/${dig}" target="_blank">💬 ${st.manual}<span class="fonte">(manual)</span></a>`;
    }

    let fixoHtml = '';
    for (const [fonte, numero] of e.fixos) {
      const dig = numero.replace(/\\D/g, '');
      fixoHtml += `<a class="wa-btn fixo" href="https://wa.me/${dig}" target="_blank">${numero}<span class="fonte">(${fonte}, provavel fixo)</span></a>`;
    }

    let socialHtml = '';
    if (e.instagram) socialHtml += `<a class="social-btn" href="https://instagram.com/${e.instagram}" target="_blank">📷 Instagram achado</a>`;
    if (e.facebook) socialHtml += `<a class="social-btn" href="https://facebook.com/${e.facebook}" target="_blank">👍 Facebook achado</a>`;

    div.innerHTML = `
      <div class="nome">${e.nome} ${e.moveis.length ? '⭐' : ''}</div>
      <div class="muni">${e.municipio} ${e.cnpj ? '| ' + e.cnpj : ''}</div>

      ${movelHtml ? `<div class="secao-label">Celular (candidato a WhatsApp)</div><div class="nums">${movelHtml}</div>` : ''}
      ${fixoHtml ? `<div class="secao-label">Outros numeros (provavel fixo)</div><div class="nums">${fixoHtml}</div>` : ''}

      <div class="secao-label">Buscar voce mesmo (abre em nova aba, sem raspagem)</div>
      <div class="nums">
        <a class="busca-btn" href="${e.busca_maps}" target="_blank">🗺️ Google Maps</a>
        <a class="busca-btn" href="${e.busca_insta}" target="_blank">📷 Buscar Instagram</a>
        <a class="busca-btn" href="${e.busca_fb}" target="_blank">👍 Buscar Facebook</a>
        ${socialHtml}
      </div>

      <div class="acoes">
        <input class="input-manual" id="manual-${e.id}" placeholder="Colar numero achado (DDD+numero)">
        <button class="btn-add" onclick="addManual(${e.id})">+ Adicionar</button>
        <button class="btn-sim" onclick="marcar(${e.id}, 'sim')">✓ Tem WhatsApp</button>
        <button class="btn-nao" onclick="marcar(${e.id}, 'nao')">✗ Nao tem</button>
      </div>
    `;
    lista.appendChild(div);
  }

  document.getElementById('vazio').style.display = visiveis === 0 ? 'block' : 'none';
  atualizarStats();
}

function exportarCSV() {
  let csv = 'nome,municipio,cnpj,status,celulares,fixos,numero_manual,instagram,facebook\\n';
  for (const e of EMPRESAS) {
    const st = progresso[e.id] || {};
    const celulares = e.moveis.map(n => n[1]).join(';');
    const fixos = e.fixos.map(n => n[1]).join(';');
    csv += `"${e.nome}","${e.municipio}","${e.cnpj}","${st.status || 'nao_verificado'}","${celulares}","${fixos}","${st.manual || ''}","${e.instagram}","${e.facebook}"\\n`;
  }
  const blob = new Blob([csv], {type: 'text/csv'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'resultado_whatsapp_manual.csv';
  a.click();
}

document.getElementById('filtro').addEventListener('input', render);
document.getElementById('ordem').addEventListener('change', render);
render();
</script>
</body>
</html>
"""
    html = html.replace("__DADOS__", dados_js)

    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Pagina gerada em {OUT_HTML}")


if __name__ == "__main__":
    main()
