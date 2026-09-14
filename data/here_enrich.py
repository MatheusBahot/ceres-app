"""
Busca cada empresa na HERE Geocoding & Search API (endpoint /discover),
extraindo o telefone do campo "contacts".

Pre-requisito: crie uma conta em developer.here.com (freemium, sem
cartao pra comecar) e gere uma API key no painel de projetos.

Le/escreve em data/bd_enriquecido.json (arquivo compartilhado).

Uso:
    export HERE_API_KEY="sua_chave_aqui"
    python3 data/here_enrich.py
"""
import json, os, sys, time, random
import requests

sys.path.insert(0, os.path.dirname(__file__))
from _enrich_common import ENRIQUECIDO_PATH, ORIGINAL_PATH, similaridade, normaliza_e164, LIMIAR_CONFIANCA

API_KEY = os.environ.get("HERE_API_KEY")
URL     = "https://discover.search.hereapi.com/v1/discover"
LOG_BAIXA_CONFIANCA = "data/log_here_baixa_confianca.txt"
LOG_NAO_ENCONTRADO  = "data/log_here_nao_encontrado.txt"
CHECKPOINT_EVERY = 25
DELAY_BASE = 0.2

# Bahia fica aproximadamente nesse centro - usado so como "preferencia de proximidade" (at=)
BAHIA_LAT, BAHIA_LON = -12.97, -38.5


def extrair_telefone(item):
    contatos = item.get("contacts") or []
    for c in contatos:
        fones = c.get("phone") or []
        if fones:
            return fones[0].get("value", "")
    return ""


def buscar_no_here(query, tentativas=3):
    params = {
        "q": query,
        "at": f"{BAHIA_LAT},{BAHIA_LON}",
        "in": "countryCode:BRA",
        "limit": 3,
        "apiKey": API_KEY,
    }
    for tentativa in range(tentativas):
        try:
            r = requests.get(URL, params=params, timeout=15)
            if r.status_code == 200:
                return r.json().get("items", [])
            if r.status_code == 429:
                time.sleep(2 + tentativa * 2)
                continue
            print(f"  [ERRO API] status={r.status_code} resposta={r.text[:300]}")
            return None
        except requests.RequestException as ex:
            print(f"  [ERRO DE REDE] tentativa {tentativa+1}: {ex}")
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
    if not API_KEY:
        sys.exit("Defina HERE_API_KEY antes de rodar.")

    empresas = carregar_base()
    total = len(empresas)
    ja_feitas = sum(1 for e in empresas if e.get("_here_checado"))
    if ja_feitas:
        print(f"Retomando: {ja_feitas} ja tinham sido consultadas antes.")

    falhas_seguidas = 0

    for i, e in enumerate(empresas, 1):
        if e.get("_here_checado"):
            continue

        nome  = e.get("Nome_Fantasia") or e.get("Razao_Social") or ""
        query = f"{nome} {e.get('Municipio','')} Bahia"
        resultados = buscar_no_here(query)

        if resultados is None:
            falhas_seguidas += 1
            if falhas_seguidas >= 5:
                print()
                print("PARANDO: 5 falhas seguidas da API HERE.")
                print("Confira o [ERRO API] acima - geralmente e chave invalida ou expirada.")
                salvar(empresas)
                sys.exit(1)
            continue
        falhas_seguidas = 0

        melhor, melhor_score, melhor_tel = None, 0.0, ""
        for item in resultados:
            score = similaridade(nome, item.get("title", ""))
            if score > melhor_score:
                melhor, melhor_score = item, score
                melhor_tel = extrair_telefone(item)

        if melhor and melhor_score >= LIMIAR_CONFIANCA:
            e["here_tel"]             = normaliza_e164(melhor_tel) or ""
            e["here_nome_encontrado"] = melhor.get("title", "")
            e["here_confianca"]       = round(melhor_score, 2)
        elif melhor:
            e["here_tel"] = ""
            e["here_nome_encontrado"] = melhor.get("title", "")
            e["here_confianca"] = round(melhor_score, 2)
        else:
            e["here_tel"] = e["here_nome_encontrado"] = ""
            e["here_confianca"] = 0.0

        e["_here_checado"] = True
        time.sleep(DELAY_BASE + random.uniform(0, 0.1))

        if i % CHECKPOINT_EVERY == 0 or i == total:
            salvar(empresas)
            print(f"[{i}/{total}] processadas — checkpoint salvo.")

    salvar(empresas)

    baixa_confianca = [e for e in empresas if e.get("_here_checado") and not e.get("here_tel") and e.get("here_nome_encontrado")]
    nao_encontradas = [e for e in empresas if e.get("_here_checado") and not e.get("here_tel") and not e.get("here_nome_encontrado")]

    with open(LOG_BAIXA_CONFIANCA, "w", encoding="utf-8") as f:
        for e in baixa_confianca:
            f.write(f"{e.get('Nome_Fantasia','?')} | achou: {e.get('here_nome_encontrado')} | confianca: {e.get('here_confianca')} | CNPJ: {e.get('CNPJ','')}\n")

    with open(LOG_NAO_ENCONTRADO, "w", encoding="utf-8") as f:
        for e in nao_encontradas:
            f.write(f"{e.get('Nome_Fantasia','?')} | {e.get('Municipio','')} | CNPJ: {e.get('CNPJ','')}\n")

    com_tel = sum(1 for e in empresas if e.get("here_tel"))
    print()
    print(f"Total de empresas:                    {total}")
    print(f"Achadas com confianca e com telefone:  {com_tel}")
    print(f"Achadas mas com confianca baixa:       {len(baixa_confianca)} (log: {LOG_BAIXA_CONFIANCA})")
    print(f"Nao encontradas na HERE:               {len(nao_encontradas)} (log: {LOG_NAO_ENCONTRADO})")
    print(f"Resultado salvo em {ENRIQUECIDO_PATH}")


if __name__ == "__main__":
    main()
