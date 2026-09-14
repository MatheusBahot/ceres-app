"""
Busca cada empresa no OpenStreetMap (via Nominatim), extraindo telefone
das tags "phone" ou "contact:phone" quando existirem.

100% gratis, sem cadastro, sem chave de API. Mas a cobertura de telefone
pra comercio pequeno do interior da Bahia tende a ser bem mais fraca que
Google/HERE/AWS, porque o OSM depende de voluntarios mapeando cada lugar.
Vale rodar por ser gratis, mas nao espere o mesmo volume das outras.

Regra de uso do Nominatim (obrigatoria): no maximo 1 requisicao por
segundo, e informar um User-Agent identificando a aplicacao - o script
ja faz isso.

Le/escreve em data/bd_enriquecido.json (arquivo compartilhado).

Uso:
    python3 data/osm_enrich.py
"""
import json, os, sys, time
import requests

sys.path.insert(0, os.path.dirname(__file__))
from _enrich_common import ENRIQUECIDO_PATH, ORIGINAL_PATH, similaridade, normaliza_e164, LIMIAR_CONFIANCA

URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "ceres-app-enrichment/1.0 (uso pontual, ver https://github.com/MatheusBahot/ceres-app)"}
LOG_BAIXA_CONFIANCA = "data/log_osm_baixa_confianca.txt"
LOG_NAO_ENCONTRADO  = "data/log_osm_nao_encontrado.txt"
CHECKPOINT_EVERY = 25
DELAY_BASE = 1.05   # Nominatim exige no maximo 1 req/seg - respeitar a risca


def extrair_telefone(item):
    extra = item.get("extratags") or {}
    return extra.get("phone") or extra.get("contact:phone") or ""


def buscar_no_osm(query, tentativas=3):
    params = {
        "q": query,
        "format": "json",
        "countrycodes": "br",
        "extratags": 1,
        "addressdetails": 1,
        "limit": 3,
    }
    for tentativa in range(tentativas):
        try:
            r = requests.get(URL, params=params, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(3 + tentativa * 2)
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
    empresas = carregar_base()
    total = len(empresas)
    ja_feitas = sum(1 for e in empresas if e.get("_osm_checado"))
    if ja_feitas:
        print(f"Retomando: {ja_feitas} ja tinham sido consultadas antes.")
    print("Aviso: ritmo de 1 consulta/segundo (exigencia do Nominatim) - isso")
    print(f"vai levar uns {total // 60} minutos no total.")

    falhas_seguidas = 0

    for i, e in enumerate(empresas, 1):
        if e.get("_osm_checado"):
            continue

        nome  = e.get("Nome_Fantasia") or e.get("Razao_Social") or ""
        query = f"{nome}, {e.get('Municipio','')}, Bahia"
        resultados = buscar_no_osm(query)

        if resultados is None:
            falhas_seguidas += 1
            if falhas_seguidas >= 5:
                print()
                print("PARANDO: 5 falhas seguidas do Nominatim.")
                salvar(empresas)
                sys.exit(1)
            continue
        falhas_seguidas = 0

        melhor, melhor_score, melhor_tel = None, 0.0, ""
        for item in resultados:
            titulo = item.get("display_name", "").split(",")[0]
            score = similaridade(nome, titulo)
            if score > melhor_score:
                melhor, melhor_score = item, score
                melhor_tel = extrair_telefone(item)

        if melhor and melhor_score >= LIMIAR_CONFIANCA and melhor_tel:
            e["osm_tel"]             = normaliza_e164(melhor_tel) or ""
            e["osm_nome_encontrado"] = melhor.get("display_name", "").split(",")[0]
            e["osm_confianca"]       = round(melhor_score, 2)
        else:
            e["osm_tel"] = ""
            e["osm_nome_encontrado"] = melhor.get("display_name", "").split(",")[0] if melhor else ""
            e["osm_confianca"] = round(melhor_score, 2) if melhor else 0.0

        e["_osm_checado"] = True
        time.sleep(DELAY_BASE)

        if i % CHECKPOINT_EVERY == 0 or i == total:
            salvar(empresas)
            print(f"[{i}/{total}] processadas — checkpoint salvo.")

    salvar(empresas)

    com_tel = sum(1 for e in empresas if e.get("osm_tel"))
    print()
    print(f"Total de empresas:              {total}")
    print(f"Com telefone confirmado no OSM: {com_tel}")
    print(f"(cobertura baixa e esperada aqui - e normal)")
    print(f"Resultado salvo em {ENRIQUECIDO_PATH}")


if __name__ == "__main__":
    main()
