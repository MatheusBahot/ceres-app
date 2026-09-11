"""
Busca cada empresa no Google Maps (Places API New - Text Search) usando
nome + municipio, e extrai o telefone publicado no Google Business daquela
empresa — o contato que o proprio dono mantem atualizado pra clientes,
que costuma ser bem melhor que o telefone registrado na Receita (que na
Bahia, na pratica, e frequentemente o do escritorio de contabilidade).

IMPORTANTE - verificacao de confianca: a busca por nome pode retornar um
concorrente proximo em vez da empresa certa (isso foi medido e confirmado
numa amostra real). Por isso cada resultado so e aceito se o nome
encontrado bater com o nome da nossa base acima de um limiar de
similaridade (0.72, calibrado com casos reais). Abaixo disso, fica de
fora e vai pro log de baixa confianca pra revisao manual.

Custo: Google cobra na SKU "Enterprise" (US$35 a cada 1000 buscas) por
incluir o campo de telefone. As primeiras 1000 buscas/mes sao gratis.
Para ~1692 empresas, o custo estimado e de uns US$24.

Pre-requisito: criar um projeto no Google Cloud, ativar a "Places API
(New)" e gerar uma API key.

Tem checkpoint: se parar no meio, rode de novo que ele retoma sozinho.

Uso:
    export GOOGLE_PLACES_API_KEY="sua_chave_aqui"
    python3 data/maps_enrich.py
"""
import json, re, os, sys, time, random, difflib, unicodedata
import requests

API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY")
URL     = "https://places.googleapis.com/v1/places:searchText"

IN_PATH_RECEITA  = "data/bd_definitivo_com_receita.json"
IN_PATH_ORIGINAL = "data/bd_definitivo.json"
OUT_PATH = "data/bd_definitivo_com_maps.json"
LOG_BAIXA_CONFIANCA = "data/log_maps_baixa_confianca.txt"
LOG_NAO_ENCONTRADO  = "data/log_maps_nao_encontrado.txt"

LIMIAR_CONFIANCA = 0.72   # calibrado com casos reais, ver conversa
CHECKPOINT_EVERY = 25
DELAY_BASE = 0.15

STOPWORDS = r"\b(LTDA|ME|EIRELI|EPP|SA|S A|COMERCIO|COM|DE|DA|DO|DOS|DAS)\b"


def normaliza_nome(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^A-Za-z0-9 ]", "", s).upper().strip()
    s = re.sub(STOPWORDS, "", s)
    return re.sub(r"\s+", " ", s).strip()


def similaridade(a, b):
    return difflib.SequenceMatcher(None, normaliza_nome(a), normaliza_nome(b)).ratio()


def normaliza_e164(t):
    d = re.sub(r"\D", "", t or "")
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]
    if len(d) in (10, 11):
        return "+55" + d
    return None


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
            return []
        except requests.RequestException:
            time.sleep(1 + tentativa)
    return []


def carregar_progresso_anterior():
    if not os.path.exists(OUT_PATH):
        return {}
    with open(OUT_PATH, encoding="utf-8") as f:
        anteriores = json.load(f)
    return {e.get("CNPJ"): e for e in anteriores if e.get("_maps_checado")}


def main():
    if not API_KEY:
        sys.exit("Defina GOOGLE_PLACES_API_KEY antes de rodar "
                  "(export GOOGLE_PLACES_API_KEY=\"sua_chave\").")

    entrada = IN_PATH_RECEITA if os.path.exists(IN_PATH_RECEITA) else IN_PATH_ORIGINAL
    print(f"Carregando base de {entrada}...")
    with open(entrada, encoding="utf-8") as f:
        empresas = json.load(f)

    ja_processadas = carregar_progresso_anterior()
    if ja_processadas:
        print(f"Retomando: {len(ja_processadas)} ja tinham sido consultadas antes.")

    baixa_confianca, nao_encontradas = [], []
    total = len(empresas)

    for i, e in enumerate(empresas, 1):
        cnpj = e.get("CNPJ", "")

        if cnpj in ja_processadas:
            e.update(ja_processadas[cnpj])
        else:
            nome  = e.get("Nome_Fantasia") or e.get("Razao_Social") or ""
            cidade = e.get("Municipio", "")
            query = f"{nome} {cidade} Bahia Brasil"

            resultados = buscar_no_maps(query)
            melhor, melhor_score = None, 0.0
            for p in resultados:
                nome_encontrado = p.get("displayName", {}).get("text", "")
                score = similaridade(nome, nome_encontrado)
                if score > melhor_score:
                    melhor, melhor_score = p, score

            if melhor and melhor_score >= LIMIAR_CONFIANCA:
                tel = normaliza_e164(melhor.get("internationalPhoneNumber", ""))
                e["maps_tel"]            = tel or ""
                e["maps_nome_encontrado"] = melhor.get("displayName", {}).get("text", "")
                e["maps_confianca"]      = round(melhor_score, 2)
            elif melhor:
                e["maps_tel"] = ""
                e["maps_nome_encontrado"] = melhor.get("displayName", {}).get("text", "")
                e["maps_confianca"] = round(melhor_score, 2)
                baixa_confianca.append(e)
            else:
                e["maps_tel"] = ""
                e["maps_nome_encontrado"] = ""
                e["maps_confianca"] = 0.0
                nao_encontradas.append(e)

            e["_maps_checado"] = True
            time.sleep(DELAY_BASE + random.uniform(0, 0.1))

        if i % CHECKPOINT_EVERY == 0 or i == total:
            with open(OUT_PATH, "w", encoding="utf-8") as f:
                json.dump(empresas, f, ensure_ascii=False, indent=2)
            print(f"[{i}/{total}] processadas — checkpoint salvo.")

    with open(LOG_BAIXA_CONFIANCA, "w", encoding="utf-8") as f:
        for e in baixa_confianca:
            nome = e.get("Nome_Fantasia") or e.get("Razao_Social") or "?"
            f.write(f"{nome} | achou: {e.get('maps_nome_encontrado')} "
                    f"| confianca: {e.get('maps_confianca')} | CNPJ: {e.get('CNPJ','')}\n")

    with open(LOG_NAO_ENCONTRADO, "w", encoding="utf-8") as f:
        for e in nao_encontradas:
            nome = e.get("Nome_Fantasia") or e.get("Razao_Social") or "?"
            f.write(f"{nome} | {e.get('Municipio','')} | CNPJ: {e.get('CNPJ','')}\n")

    com_tel = sum(1 for e in empresas if e.get("maps_tel"))
    print()
    print(f"Total de empresas:                    {total}")
    print(f"Achadas com confianca e com telefone:  {com_tel}")
    print(f"Achadas mas com confianca baixa:       {len(baixa_confianca)} (log: {LOG_BAIXA_CONFIANCA})")
    print(f"Nao encontradas no Maps:               {len(nao_encontradas)} (log: {LOG_NAO_ENCONTRADO})")
    print(f"Resultado completo em {OUT_PATH}")
    print()
    print("Proximo passo: rode data/wa_pipeline.py — ele ja vai usar tambem")
    print("os telefones vindos do Maps na checagem de WhatsApp.")


if __name__ == "__main__":
    main()
