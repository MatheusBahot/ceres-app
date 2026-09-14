"""
Busca cada empresa no Google Maps (Places API New - Text Search) usando
nome + municipio, extraindo o telefone publicado no Google Business.

Custo: SKU Enterprise, US$35/1000 buscas, 1000 gratis/mes. Para nao gastar
nada, rode ~950 e pare (Ctrl+C) antes de virar o mes, e retome depois —
o checkpoint cuida disso sozinho.

Verificacao de confianca: so aceita o resultado se o nome bater (limiar
0.72, calibrado com casos reais - ver conversa). Abaixo disso vai pro log
de baixa confianca.

Le/escreve em data/bd_enriquecido.json (arquivo compartilhado).

Uso:
    export GOOGLE_PLACES_API_KEY="sua_chave_aqui"
    python3 data/maps_enrich.py
"""
import json, os, sys, time, random
import requests

sys.path.insert(0, os.path.dirname(__file__))
from _enrich_common import ENRIQUECIDO_PATH, ORIGINAL_PATH, similaridade, normaliza_e164, LIMIAR_CONFIANCA

API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY")
URL     = "https://places.googleapis.com/v1/places:searchText"
LOG_BAIXA_CONFIANCA = "data/log_maps_baixa_confianca.txt"
LOG_NAO_ENCONTRADO  = "data/log_maps_nao_encontrado.txt"
CHECKPOINT_EVERY = 25
DELAY_BASE = 0.15


def buscar_no_maps(query, tentativas=3):
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.internationalPhoneNumber",
    }
    body = {"textQuery": query, "maxResultCount": 3}
    for tentativa in range(tentativas):
        try:
            r = requests.post(URL, headers=headers, json=body, timeout=15)
            if r.status_code == 200:
                return r.json().get("places", [])
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
        sys.exit("Defina GOOGLE_PLACES_API_KEY antes de rodar.")

    empresas = carregar_base()
    total = len(empresas)
    ja_feitas = sum(1 for e in empresas if e.get("_maps_checado"))
    if ja_feitas:
        print(f"Retomando: {ja_feitas} ja tinham sido consultadas antes.")

    falhas_seguidas = 0

    for i, e in enumerate(empresas, 1):
        if e.get("_maps_checado"):
            continue

        nome  = e.get("Nome_Fantasia") or e.get("Razao_Social") or ""
        query = f"{nome} {e.get('Municipio','')} Bahia Brasil"
        resultados = buscar_no_maps(query)

        if resultados is None:
            falhas_seguidas += 1
            if falhas_seguidas >= 5:
                print()
                print("PARANDO: 5 falhas seguidas da API Google.")
                print("Confira o [ERRO API] acima - geralmente e chave invalida, faturamento")
                print("nao ativado, ou 'Places API (New)' nao habilitada no projeto.")
                salvar(empresas)
                sys.exit(1)
            continue
        falhas_seguidas = 0

        melhor, melhor_score = None, 0.0
        for p in resultados:
            score = similaridade(nome, p.get("displayName", {}).get("text", ""))
            if score > melhor_score:
                melhor, melhor_score = p, score

        if melhor and melhor_score >= LIMIAR_CONFIANCA:
            e["maps_tel"]             = normaliza_e164(melhor.get("internationalPhoneNumber", "")) or ""
            e["maps_nome_encontrado"] = melhor.get("displayName", {}).get("text", "")
            e["maps_confianca"]       = round(melhor_score, 2)
        elif melhor:
            e["maps_tel"] = ""
            e["maps_nome_encontrado"] = melhor.get("displayName", {}).get("text", "")
            e["maps_confianca"] = round(melhor_score, 2)
        else:
            e["maps_tel"] = e["maps_nome_encontrado"] = ""
            e["maps_confianca"] = 0.0

        e["_maps_checado"] = True
        time.sleep(DELAY_BASE + random.uniform(0, 0.1))

        if i % CHECKPOINT_EVERY == 0 or i == total:
            salvar(empresas)
            print(f"[{i}/{total}] processadas — checkpoint salvo.")

    salvar(empresas)

    baixa_confianca = [e for e in empresas if e.get("_maps_checado") and not e.get("maps_tel") and e.get("maps_nome_encontrado")]
    nao_encontradas = [e for e in empresas if e.get("_maps_checado") and not e.get("maps_tel") and not e.get("maps_nome_encontrado")]

    with open(LOG_BAIXA_CONFIANCA, "w", encoding="utf-8") as f:
        for e in baixa_confianca:
            nome = e.get("Nome_Fantasia") or e.get("Razao_Social") or "?"
            f.write(f"{nome} | achou: {e.get('maps_nome_encontrado')} | confianca: {e.get('maps_confianca')} | CNPJ: {e.get('CNPJ','')}\n")

    with open(LOG_NAO_ENCONTRADO, "w", encoding="utf-8") as f:
        for e in nao_encontradas:
            f.write(f"{e.get('Nome_Fantasia') or e.get('Razao_Social') or '?'} | {e.get('Municipio','')} | CNPJ: {e.get('CNPJ','')}\n")

    com_tel = sum(1 for e in empresas if e.get("maps_tel"))
    print()
    print(f"Total de empresas:                    {total}")
    print(f"Achadas com confianca e com telefone:  {com_tel}")
    print(f"Achadas mas com confianca baixa:       {len(baixa_confianca)} (log: {LOG_BAIXA_CONFIANCA})")
    print(f"Nao encontradas no Maps:               {len(nao_encontradas)} (log: {LOG_NAO_ENCONTRADO})")
    print(f"Resultado salvo em {ENRIQUECIDO_PATH}")


if __name__ == "__main__":
    main()
