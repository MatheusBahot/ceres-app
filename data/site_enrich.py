"""
NOVO METODO - acha o site oficial de cada empresa (via ddgs, sem API) e
visita SO AQUELA PAGINA pra extrair telefone/WhatsApp/redes sociais.

Diferenca do livre_enrich.py: aquele le o TRECHO da pagina de resultado de
busca (que pode misturar varias empresas de um diretorio). Este aqui acha
o dominio proprio da empresa (nao um agregador/diretorio/rede social) e
busca direto na pagina dela - sem risco de pegar contato de outra empresa,
porque so tem uma empresa naquela pagina: a dona do site.

Isso NAO e scraping de rede social - e simplesmente visitar o site publico
de uma pequena empresa, a mesma coisa que qualquer visitante ou motor de
busca faz. Sites de empresas nao tem bloqueio anti-robo como Google Maps
ou Facebook/Instagram tem.

Le/escreve em data/bd_enriquecido.json (arquivo compartilhado).

Pre-requisito:
    pip3 install ddgs --break-system-packages

Uso:
    python3 data/site_enrich.py
"""
import json, os, sys, time, random, re
from urllib.parse import urlparse

import requests

sys.path.insert(0, os.path.dirname(__file__))
from _enrich_common import ENRIQUECIDO_PATH, ORIGINAL_PATH, normaliza_e164, normaliza_nome, similaridade

try:
    from ddgs import DDGS
    from ddgs.exceptions import DDGSException, RatelimitException, TimeoutException
except ImportError:
    sys.exit("Falta instalar a biblioteca: pip3 install ddgs --break-system-packages")

CHECKPOINT_EVERY = 20
DELAY_BUSCA = 2.5
DELAY_FETCH = 1.0
LIMIAR_CONFIANCA = 0.5  # mais permissivo que o das APIs estruturadas, porque aqui
                         # a pagina inteira e da propria empresa, entao o risco de
                         # confundir com outra empresa e bem menor

RE_WAME  = re.compile(r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=)(\d{10,13})")
RE_TEL   = re.compile(r"(?:\+?55\s?)?\(?\d{2}\)?[\s.-]?9?\d{4}[\s.-]?\d{4}")
RE_INSTA = re.compile(r"instagram\.com/([A-Za-z0-9_.]{2,30})")
RE_FB    = re.compile(r"facebook\.com/([A-Za-z0-9_.]{2,50})")
RE_TAG   = re.compile(r"<[^<]+?>")

DDD_BAHIA = {"71", "73", "74", "75", "77"}

DOMINIOS_EXCLUIDOS = {
    "facebook.com", "instagram.com", "linkedin.com", "youtube.com", "twitter.com", "x.com",
    "google.com", "maps.google.com", "goo.gl",
    "econodata.com.br", "guiamais.com.br", "telelistas.net", "apontador.com.br",
    "cnpj.biz", "cnpj.info", "empresascnpj.com", "solutudo.com.br", "consultasocio.com",
    "cnpja.com", "receitaws.com.br", "brasilapi.com.br", "gov.br",
    "wikipedia.org", "mercadolivre.com.br", "olx.com.br", "ifood.com.br",
    "wa.me", "api.whatsapp.com",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; pesquisa-b2b-pontual/1.0)"}


def dominio_valido(url):
    try:
        host = urlparse(url).netloc.lower().replace("www.", "")
        if not host or any(host == d or host.endswith("." + d) for d in DOMINIOS_EXCLUIDOS):
            return None
        return host
    except Exception:
        return None


def ddd_valido_bahia(numero):
    d = re.sub(r"\D", "", numero or "")
    if d.startswith("55"):
        d = d[2:]
    return len(d) >= 10 and d[:2] in DDD_BAHIA


def filtra_bahia(lista):
    return [n for n in lista if ddd_valido_bahia(n)]


def buscar_site(query, tentativas=3):
    for tentativa in range(tentativas):
        try:
            with DDGS(timeout=15) as ddgs:
                return ddgs.text(query, max_results=5, region="br-pt")
        except RatelimitException:
            espera = 8 + tentativa * 8
            print(f"  [RATE LIMIT] esperando {espera}s...")
            time.sleep(espera)
        except (TimeoutException, DDGSException) as ex:
            print(f"  [ERRO ddgs] {ex}")
            time.sleep(3 + tentativa)
    return None


def achar_site_oficial(nome, municipio):
    resultados = buscar_site(f"{nome} {municipio} Bahia site oficial")
    if not resultados:
        return None

    melhor, melhor_score = None, 0.0
    for r in resultados:
        host = dominio_valido(r.get("href", ""))
        if not host:
            continue
        score_titulo = similaridade(nome, r.get("title", ""))
        score_host   = similaridade(nome, host.split(".")[0])
        score = max(score_titulo, score_host)
        if score > melhor_score:
            melhor, melhor_score = {"url": r["href"], "host": host}, score

    if melhor and melhor_score >= LIMIAR_CONFIANCA:
        return melhor
    return None


def visitar_site(url, tentativas=2):
    for tentativa in range(tentativas):
        try:
            r = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
            if r.status_code == 200:
                return RE_TAG.sub(" ", r.text)
            return None
        except requests.RequestException:
            time.sleep(1 + tentativa)
    return None


def carregar_base():
    path = ENRIQUECIDO_PATH if os.path.exists(ENRIQUECIDO_PATH) else ORIGINAL_PATH
    print(f"Carregando base de {path}...")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def salvar(empresas):
    with open(ENRIQUECIDO_PATH, "w", encoding="utf-8") as f:
        json.dump(empresas, f, ensure_ascii=False, indent=2)


def main():
    empresas = carregar_base()
    total = len(empresas)
    ja_feitas = sum(1 for e in empresas if e.get("_site_checado"))
    if ja_feitas:
        print(f"Retomando: {ja_feitas} ja tinham sido consultadas antes.")

    falhas_seguidas = 0
    achou_site = 0

    for i, e in enumerate(empresas, 1):
        if e.get("_site_checado"):
            continue

        nome = e.get("Nome_Fantasia") or e.get("Razao_Social") or ""
        municipio = e.get("Municipio", "")

        site = achar_site_oficial(nome, municipio)
        time.sleep(DELAY_BUSCA + random.uniform(0, 0.8))

        if site is None:
            e["site_url"] = e["site_tel"] = e["site_whatsapp_tel"] = ""
            e["site_instagram"] = e["site_facebook"] = ""
            e["_site_checado"] = True
        else:
            conteudo = visitar_site(site["url"])
            time.sleep(DELAY_FETCH)

            if conteudo is None:
                e["site_url"] = site["url"]
                e["site_tel"] = e["site_whatsapp_tel"] = ""
                e["site_instagram"] = e["site_facebook"] = ""
            else:
                wa_links = filtra_bahia(RE_WAME.findall(conteudo))
                tels     = filtra_bahia(RE_TEL.findall(conteudo))
                instas   = RE_INSTA.findall(conteudo)
                fbs      = RE_FB.findall(conteudo)

                e["site_url"]          = site["url"]
                e["site_whatsapp_tel"] = normaliza_e164(wa_links[0]) if wa_links else ""
                e["site_tel"]          = normaliza_e164(tels[0]) if tels else ""
                e["site_instagram"]    = instas[0] if instas else ""
                e["site_facebook"]     = fbs[0] if fbs else ""
                achou_site += 1

            e["_site_checado"] = True

        if i % CHECKPOINT_EVERY == 0 or i == total:
            salvar(empresas)
            print(f"[{i}/{total}] processadas — {achou_site} sites visitados com sucesso — checkpoint salvo.")

    salvar(empresas)

    com_site = sum(1 for e in empresas if e.get("site_url"))
    com_wa   = sum(1 for e in empresas if e.get("site_whatsapp_tel"))
    com_tel  = sum(1 for e in empresas if e.get("site_tel"))
    com_insta = sum(1 for e in empresas if e.get("site_instagram"))
    com_fb    = sum(1 for e in empresas if e.get("site_facebook"))
    print()
    print(f"Total de empresas:                  {total}")
    print(f"Site oficial encontrado:             {com_site}")
    print(f"Com WhatsApp no site:                {com_wa}")
    print(f"Com telefone no site:                {com_tel}")
    print(f"Com Instagram linkado no site:       {com_insta}")
    print(f"Com Facebook linkado no site:        {com_fb}")
    print(f"Resultado salvo em {ENRIQUECIDO_PATH}")


if __name__ == "__main__":
    main()
