"""
Consulta a Receita Federal (via BrasilAPI, gratuita e sem necessidade de
cadastro) para cada CNPJ da base, buscando o telefone OFICIALMENTE
registrado da empresa — que costuma ser mais atual do que o telefone
avulso que estava no arquivo original. Também traz e-mail oficial e a
situação cadastral (permite detectar empresas já fechadas/baixadas).

Fonte: dados abertos da Receita Federal, expostos publicamente pela
BrasilAPI (https://brasilapi.com.br/api/cnpj/v1/{cnpj}). Dado de pessoa
juridica, publico por lei — nao e dado pessoal de individuo.

Tem checkpoint: se cair a conexao ou voce cancelar (Ctrl+C), rode de novo
que ele retoma de onde parou, sem perder o que ja foi consultado.

Uso:
    python3 data/cnpj_enrich.py
"""
import json, re, os, sys, time, random
import requests

DATA_PATH = "data/bd_definitivo.json"
OUT_PATH  = "data/bd_definitivo_com_receita.json"
LOG_PATH  = "data/log_receita_nao_encontrado.txt"
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
                return None  # CNPJ nao encontrado na base da Receita
            if r.status_code == 429:
                time.sleep(2 + tentativa * 2)  # respeita rate-limit, tenta de novo mais devagar
                continue
            return None
        except requests.RequestException:
            time.sleep(1 + tentativa)
    return None


def carregar_progresso_anterior():
    """Se ja existe um resultado parcial, usa pra nao reconsultar quem ja foi checado."""
    if not os.path.exists(OUT_PATH):
        return {}
    with open(OUT_PATH, encoding="utf-8") as f:
        anteriores = json.load(f)
    return {e.get("CNPJ"): e for e in anteriores if e.get("_receita_checado")}


def main():
    with open(DATA_PATH, encoding="utf-8") as f:
        empresas = json.load(f)

    ja_processadas = carregar_progresso_anterior()
    if ja_processadas:
        print(f"Retomando: {len(ja_processadas)} CNPJs ja tinham sido consultados antes.")

    nao_encontradas = []
    total = len(empresas)

    for i, e in enumerate(empresas, 1):
        cnpj_original = e.get("CNPJ", "")

        if cnpj_original in ja_processadas:
            e.update(ja_processadas[cnpj_original])
        else:
            cnpj = limpa_cnpj(cnpj_original)
            dados = consultar_receita(cnpj)
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
            with open(OUT_PATH, "w", encoding="utf-8") as f:
                json.dump(empresas, f, ensure_ascii=False, indent=2)
            print(f"[{i}/{total}] processadas — checkpoint salvo em {OUT_PATH}")

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        for e in nao_encontradas:
            f.write(f"{e.get('Nome_Fantasia') or e.get('Razao_Social') or '?'} | {e.get('CNPJ','')}\n")

    achados = total - len(nao_encontradas)
    print()
    print(f"Concluido. {achados}/{total} CNPJs encontrados na Receita Federal.")
    print(f"{len(nao_encontradas)} nao encontrados (log em {LOG_PATH}).")
    print(f"Resultado completo em {OUT_PATH}")
    print()
    print("Proximo passo: rodar data/wa_pipeline.py (ele agora tambem usa")
    print("os telefones novos da Receita, alem dos que ja estavam na base).")


if __name__ == "__main__":
    main()
