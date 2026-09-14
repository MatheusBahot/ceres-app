"""
Busca cada empresa no Amazon Location Service (geo-places SearchText),
incluindo o recurso "Contact" pra trazer telefone.

GRATIS: 20.000 buscas de texto gratis por mes, nos primeiros 3 meses de
uma conta AWS nova (cobre a base toda de sobra, numa tacada so).

Pre-requisito:
1. Crie uma conta AWS (ou use uma existente) em aws.amazon.com
2. Va em "Amazon Location Service" no console, aba "API keys"
3. Crie uma API key com a acao "geo-places:SearchText" liberada
4. Anote a regiao que voce escolheu (ex: us-east-1) e a key gerada

IMPORTANTE: nao encontrei um exemplo publico 100% oficial do formato
exato do campo de telefone nesta API (a AWS documenta o recurso mas nao
publicou um JSON de resposta completo). O script imprime a resposta crua
da PRIMEIRA empresa encontrada com telefone, pra voce conferir se o campo
bateu certo. Se o campo vier vazio mas a resposta impressa mostrar um
telefone em outro lugar, me manda esse trecho que eu ajusto o script.

Le/escreve em data/bd_enriquecido.json (arquivo compartilhado).

Uso:
    export AWS_LOCATION_API_KEY="sua_chave_aqui"
    export AWS_LOCATION_REGION="us-east-1"   # a regiao que voce escolheu
    python3 data/aws_enrich.py
"""
import json, os, sys, time, random
import requests

sys.path.insert(0, os.path.dirname(__file__))
from _enrich_common import ENRIQUECIDO_PATH, ORIGINAL_PATH, similaridade, normaliza_e164, LIMIAR_CONFIANCA

API_KEY = os.environ.get("AWS_LOCATION_API_KEY")
REGION  = os.environ.get("AWS_LOCATION_REGION", "us-east-1")
URL     = f"https://places.geo.{REGION}.amazonaws.com/v2/search-text"
LOG_BAIXA_CONFIANCA = "data/log_aws_baixa_confianca.txt"
LOG_NAO_ENCONTRADO  = "data/log_aws_nao_encontrado.txt"
CHECKPOINT_EVERY = 25
DELAY_BASE = 0.2

_mostrou_exemplo = False


def extrair_telefone(item):
    """Tenta varios formatos possiveis - a AWS nao publicou um exemplo oficial completo."""
    contatos = item.get("Contacts") or {}
    for chave in ("Phones", "PhoneNumbers", "Phone"):
        lista = contatos.get(chave)
        if isinstance(lista, list) and lista:
            primeiro = lista[0]
            if isinstance(primeiro, dict):
                return primeiro.get("Value") or primeiro.get("value") or ""
            if isinstance(primeiro, str):
                return primeiro
    return ""


def buscar_na_aws(query, tentativas=3):
    global _mostrou_exemplo
    params = {"key": API_KEY}
    body = {
        "QueryText": query,
        "Filter": {"IncludeCountries": ["BRA"]},
        "AdditionalFeatures": ["Contact"],
        "MaxResults": 3,
    }
    for tentativa in range(tentativas):
        try:
            r = requests.post(URL, params=params, json=body, timeout=15)
            if r.status_code == 200:
                dados = r.json()
                itens = dados.get("ResultItems", [])
                if itens and not _mostrou_exemplo and any(extrair_telefone(it) for it in itens):
                    print("  [EXEMPLO - primeira resposta com telefone, confira o campo:]")
                    print(" ", json.dumps(itens[0], ensure_ascii=False)[:500])
                    _mostrou_exemplo = True
                return itens
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
        sys.exit("Defina AWS_LOCATION_API_KEY antes de rodar.")

    empresas = carregar_base()
    total = len(empresas)
    ja_feitas = sum(1 for e in empresas if e.get("_aws_checado"))
    if ja_feitas:
        print(f"Retomando: {ja_feitas} ja tinham sido consultadas antes.")

    falhas_seguidas = 0

    for i, e in enumerate(empresas, 1):
        if e.get("_aws_checado"):
            continue

        nome  = e.get("Nome_Fantasia") or e.get("Razao_Social") or ""
        query = f"{nome}, {e.get('Municipio','')}, Bahia, Brasil"
        resultados = buscar_na_aws(query)

        if resultados is None:
            falhas_seguidas += 1
            if falhas_seguidas >= 5:
                print()
                print("PARANDO: 5 falhas seguidas da API AWS.")
                print("Confira o [ERRO API] acima - geralmente e chave invalida,")
                print("regiao errada, ou a acao geo-places:SearchText nao liberada na key.")
                salvar(empresas)
                sys.exit(1)
            continue
        falhas_seguidas = 0

        melhor, melhor_score, melhor_tel = None, 0.0, ""
        for item in resultados:
            titulo = item.get("Title", "")
            score = similaridade(nome, titulo)
            if score > melhor_score:
                melhor, melhor_score = item, score
                melhor_tel = extrair_telefone(item)

        if melhor and melhor_score >= LIMIAR_CONFIANCA:
            e["aws_tel"]             = normaliza_e164(melhor_tel) or ""
            e["aws_nome_encontrado"] = melhor.get("Title", "")
            e["aws_confianca"]       = round(melhor_score, 2)
        elif melhor:
            e["aws_tel"] = ""
            e["aws_nome_encontrado"] = melhor.get("Title", "")
            e["aws_confianca"] = round(melhor_score, 2)
        else:
            e["aws_tel"] = e["aws_nome_encontrado"] = ""
            e["aws_confianca"] = 0.0

        e["_aws_checado"] = True
        time.sleep(DELAY_BASE + random.uniform(0, 0.1))

        if i % CHECKPOINT_EVERY == 0 or i == total:
            salvar(empresas)
            print(f"[{i}/{total}] processadas — checkpoint salvo.")

    salvar(empresas)

    baixa_confianca = [e for e in empresas if e.get("_aws_checado") and not e.get("aws_tel") and e.get("aws_nome_encontrado")]
    nao_encontradas = [e for e in empresas if e.get("_aws_checado") and not e.get("aws_tel") and not e.get("aws_nome_encontrado")]

    with open(LOG_BAIXA_CONFIANCA, "w", encoding="utf-8") as f:
        for e in baixa_confianca:
            f.write(f"{e.get('Nome_Fantasia','?')} | achou: {e.get('aws_nome_encontrado')} | confianca: {e.get('aws_confianca')} | CNPJ: {e.get('CNPJ','')}\n")

    with open(LOG_NAO_ENCONTRADO, "w", encoding="utf-8") as f:
        for e in nao_encontradas:
            f.write(f"{e.get('Nome_Fantasia','?')} | {e.get('Municipio','')} | CNPJ: {e.get('CNPJ','')}\n")

    com_tel = sum(1 for e in empresas if e.get("aws_tel"))
    print()
    print(f"Total de empresas:                    {total}")
    print(f"Achadas com confianca e com telefone:  {com_tel}")
    print(f"Achadas mas com confianca baixa:       {len(baixa_confianca)} (log: {LOG_BAIXA_CONFIANCA})")
    print(f"Nao encontradas na AWS:                {len(nao_encontradas)} (log: {LOG_NAO_ENCONTRADO})")
    print(f"Resultado salvo em {ENRIQUECIDO_PATH}")


if __name__ == "__main__":
    main()
