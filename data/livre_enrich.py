"""
ULTIMA CAMADA - busca de texto livre via DuckDuckGo (sem chave de API,
sem cadastro), tentando extrair telefone, link de WhatsApp e redes
sociais que a propria empresa publicou na web.

SEJA HONESTO CONSIGO MESMO SOBRE OS LIMITES DISSO: isso e busca de texto
livre, nao uma API estruturada. E mais fragil (o DuckDuckGo pode mudar o
HTML a qualquer momento, ou limitar o ritmo se usarmos rapido demais), e
menos preciso (o "match" de confianca aqui e so "o nome da empresa
aparece na pagina de resultado", nao uma comparacao estruturada). Trate
isso como uma rede extra de baixo custo, nao como substituto das APIs
estruturadas (Receita, Maps, AWS, HERE).

NAO faz scraping de Facebook/Instagram diretamente (teria bloqueio
anti-bot e viola os termos deles) - so extrai o LINK do perfil quando ele
aparece nos resultados de busca, como um canal a mais pra voce contatar
manualmente.

Le/escreve em data/bd_enriquecido.json (arquivo compartilhado).

Uso:
    python3 data/livre_enrich.py
"""
import json, os, sys, time, random, re
import requests

sys.path.insert(0, os.path.dirname(__file__))
from _enrich_common import ENRIQUECIDO_PATH, ORIGINAL_PATH, normaliza_e164, normaliza_nome

URL = "https://html.duckduckgo.com/html/"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; pesquisa-b2b-pontual/1.0; +uso-unico-local)"}
CHECKPOINT_EVERY = 20
DELAY_BASE = 1.6   # respeitoso - sem chave, sem contrato, o unico limite e nao abusar

RE_TAG   = re.compile(r"<[^<]+?>")
RE_TEL   = re.compile(r"(?:\+?55\s?)?\(?\d{2}\)?[\s.-]?9?\d{4}[\s.-]?\d{4}")
RE_WAME  = re.compile(r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=)(\d{10,13})")
RE_INSTA = re.compile(r"instagram\.com/([A-Za-z0-9_.]{2,30})")
RE_FB    = re.compile(r"facebook\.com/([A-Za-z0-9_.]{2,50})")


def buscar_livre(query, tentativas=3):
    for tentativa in range(tentativas):
        try:
            r = requests.post(URL, data={"q": query}, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                return r.text
            if r.status_code == 429:
                time.sleep(6 + tentativa * 4)
                continue
            print(f"  [ERRO] status={r.status_code} - pode ser bloqueio temporario do DuckDuckGo")
            return None
        except requests.RequestException as ex:
            print(f"  [ERRO DE REDE] tentativa {tentativa+1}: {ex}")
            time.sleep(2 + tentativa)
    return None


def extrair_sinais(html, nome_empresa):
    texto = RE_TAG.sub(" ", html)
    nome_norm = normaliza_nome(nome_empresa)
    aparece_nome = bool(nome_norm) and nome_norm in normaliza_nome(texto)

    wa_links = RE_WAME.findall(texto)
    tels     = RE_TEL.findall(texto)
    instas   = RE_INSTA.findall(texto)
    fbs      = RE_FB.findall(texto)

    return {
        "aparece_nome": aparece_nome,
        "wa_links": wa_links,
        "tels": tels,
        "instagram": instas[0] if instas else "",
        "facebook": fbs[0] if fbs else "",
    }


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
    ja_feitas = sum(1 for e in empresas if e.get("_livre_checado"))
    if ja_feitas:
        print(f"Retomando: {ja_feitas} ja tinham sido consultadas antes.")

    falhas_seguidas = 0
    achou_algo = 0

    for i, e in enumerate(empresas, 1):
        if e.get("_livre_checado"):
            continue

        nome  = e.get("Nome_Fantasia") or e.get("Razao_Social") or ""
        query = f'"{nome}" {e.get("Municipio","")} Bahia whatsapp telefone contato'
        html = buscar_livre(query)

        if html is None:
            falhas_seguidas += 1
            if falhas_seguidas >= 5:
                print()
                print("PARANDO: 5 falhas seguidas. O DuckDuckGo pode ter limitado")
                print("temporariamente este IP - espere um tempo e rode de novo.")
                salvar(empresas)
                sys.exit(1)
            continue
        falhas_seguidas = 0

        sinais = extrair_sinais(html, nome)

        if sinais["aparece_nome"]:
            wa_tel = normaliza_e164(sinais["wa_links"][0]) if sinais["wa_links"] else ""
            tel    = normaliza_e164(sinais["tels"][0]) if sinais["tels"] else ""
            e["livre_whatsapp_tel"] = wa_tel or ""
            e["livre_tel"]          = tel or ""
            e["livre_instagram"]    = sinais["instagram"]
            e["livre_facebook"]     = sinais["facebook"]
            e["livre_confianca"]    = 1.0
            if wa_tel or tel or sinais["instagram"] or sinais["facebook"]:
                achou_algo += 1
        else:
            e["livre_whatsapp_tel"] = e["livre_tel"] = ""
            e["livre_instagram"] = e["livre_facebook"] = ""
            e["livre_confianca"] = 0.0

        e["_livre_checado"] = True
        time.sleep(DELAY_BASE + random.uniform(0, 0.5))

        if i % CHECKPOINT_EVERY == 0 or i == total:
            salvar(empresas)
            print(f"[{i}/{total}] processadas — {achou_algo} com algum sinal ate agora — checkpoint salvo.")

    salvar(empresas)

    com_wa_link  = sum(1 for e in empresas if e.get("livre_whatsapp_tel"))
    com_tel      = sum(1 for e in empresas if e.get("livre_tel"))
    com_insta    = sum(1 for e in empresas if e.get("livre_instagram"))
    com_fb       = sum(1 for e in empresas if e.get("livre_facebook"))
    print()
    print(f"Total de empresas:                       {total}")
    print(f"Com link wa.me/whatsapp encontrado:       {com_wa_link}")
    print(f"Com telefone generico encontrado:         {com_tel}")
    print(f"Com perfil de Instagram encontrado:       {com_insta}")
    print(f"Com perfil de Facebook encontrado:        {com_fb}")
    print(f"Resultado salvo em {ENRIQUECIDO_PATH}")
    print()
    print("Lembrete: essa camada e busca de texto livre, mais fragil que as")
    print("APIs estruturadas. Os telefones encontrados ainda passam pela")
    print("checagem real de WhatsApp no wa_pipeline.py antes de valerem algo.")


if __name__ == "__main__":
    main()
