"""
Consulta a Receita Federal (via BrasilAPI, gratuita e sem cadastro) para
cada CNPJ da base, buscando o telefone OFICIALMENTE registrado da empresa.

Fonte: dados abertos da Receita Federal, expostos pela BrasilAPI
(https://brasilapi.com.br/api/cnpj/v1/{cnpj}). Dado de pessoa juridica,
publico por lei.

Le/escreve em data/bd_enriquecido.json (arquivo unico compartilhado por
todos os scripts de enriquecimento). Se ainda nao existir, cria a partir
de data/bd_definitivo.json.

Tem checkpoint: se parar no meio, rode de novo que ele retoma sozinho.

Uso:
    python3 data/cnpj_enrich.py
"""
import json, re, os, sys, time, random
import requests

sys.path.insert(0, os.path.dirname(__file__))
from _enrich_common import ENRIQUECIDO_PATH, ORIGINAL_PATH

LOG_PATH = "data/log_receita_nao_encontrado.txt"
CHECKPOINT_EVERY = 50
DELAY_BASE = 0.35   # ~3 consultas/seg, ritmo respeitoso (BrasilAPI bloqueia abuso)


def limpa_cnpj(c):
    return re.sub(r"\D", "", c or "").zfill(14)


def consultar_receita(cnpj, tentativas=3):
    url = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}"
    for tentativa in range(tentativas):
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return {}  # CNPJ nao encontrado - resultado vazio, nao e falha de rede
            if r.status_code == 429:
                time.sleep(2 + tentativa * 2)
                continue
            print(f"  [ERRO API] status={r.status_code} resposta={r.text[:200]}")
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
    empresas = carregar_base()
    total = len(empresas)
    ja_feitas = sum(1 for e in empresas if e.get("_receita_checado"))
    if ja_feitas:
        print(f"Retomando: {ja_feitas} ja tinham sido consultadas antes.")

    nao_encontradas = []
    falhas_seguidas = 0

    for i, e in enumerate(empresas, 1):
        if e.get("_receita_checado"):
            continue

        cnpj = limpa_cnpj(e.get("CNPJ", ""))
        dados = consultar_receita(cnpj)

        if dados is None:
            falhas_seguidas += 1
            if falhas_seguidas >= 5:
                print()
                print("PARANDO: 5 falhas seguidas da API. Confira o [ERRO API] acima.")
                salvar(empresas)
                sys.exit(1)
            continue
        falhas_seguidas = 0

        if dados:
            e["receita_tel1"]     = dados.get("ddd_telefone_1") or ""
            e["receita_tel2"]     = dados.get("ddd_telefone_2") or ""
            e["receita_email"]    = dados.get("email") or ""
            e["receita_situacao"] = dados.get("descricao_situacao_cadastral") or ""
        else:
            e["receita_tel1"] = e["receita_tel2"] = e["receita_email"] = e["receita_situacao"] = ""
            nao_encontradas.append(e)

        e["_receita_checado"] = True
        time.sleep(DELAY_BASE + random.uniform(0, 0.15))

        if i % CHECKPOINT_EVERY == 0 or i == total:
            salvar(empresas)
            print(f"[{i}/{total}] processadas — checkpoint salvo.")

    salvar(empresas)

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        for e in nao_encontradas:
            f.write(f"{e.get('Nome_Fantasia') or e.get('Razao_Social') or '?'} | {e.get('CNPJ','')}\n")

    achados = sum(1 for e in empresas if e.get("receita_tel1") or e.get("receita_tel2"))
    print()
    print(f"Total de empresas:              {total}")
    print(f"Com telefone da Receita:        {achados}")
    print(f"Sem telefone da Receita:        {total - achados} (log: {LOG_PATH})")
    print(f"Resultado salvo em {ENRIQUECIDO_PATH}")


if __name__ == "__main__":
    main()
