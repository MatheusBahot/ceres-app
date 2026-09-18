"""
ULTIMA CAMADA - busca de texto livre via 'ddgs' (biblioteca open source
que faz busca no DuckDuckGo/Google/Bing/Brave etc, com parametro
'backend' documentado oficialmente pelos proprios autores da biblioteca -
nao e raspagem por fora dela), tentando extrair telefone, link de
WhatsApp e redes sociais que a propria empresa publicou na web.

CORRIGIDO (3a vez):
1. Agora consulta DOIS motores por empresa (duckduckgo + google, via o
   parametro backend da propria ddgs) e junta os resultados, aumentando
   o total de material bruto pra filtrar - mais chance de achar o
   resultado certo sem afrouxar a exigencia de precisao.
2. Para TELEFONE, o filtro de local ficou mais inteligente: aceita se o
   nome da empresa aparece no resultado E (a cidade/Bahia e mencionada
   OU o DDD do numero encontrado ja e um DDD real da Bahia - o proprio
   DDD e uma prova independente de localizacao, entao nao precisa
   exigir as duas coisas ao mesmo tempo).
3. Para INSTAGRAM/FACEBOOK, mantido o exigente (nome + cidade/Bahia no
   mesmo resultado), porque nao existe um equivalente ao DDD pra
   confirmar local de forma independente - aqui o volume maior de
   resultados (item 1) e o que deve ajudar a achar mais casos legitimos.

SEJA HONESTO CONSIGO MESMO SOBRE OS LIMITES DISSO: mesmo corrigido, isso e
busca de texto livre, nao uma API estruturada. NAO visita a pagina do
Instagram/Facebook em si.

Le/escreve em data/bd_enriquecido.json (arquivo compartilhado).

Pre-requisito:
    pip3 install ddgs --break-system-packages

Uso:
    python3 data/livre_enrich.py
"""
import json, os, sys, time, random, re

sys.path.insert(0, os.path.dirname(__file__))
from _enrich_common import ENRIQUECIDO_PATH, ORIGINAL_PATH, normaliza_e164, normaliza_nome

try:
    from ddgs import DDGS
    from ddgs.exceptions import DDGSException, RatelimitException, TimeoutException
except ImportError:
    sys.exit("Falta instalar a biblioteca: pip3 install ddgs --break-system-packages")

CHECKPOINT_EVERY = 15
DELAY_BASE = 2.0
BACKENDS = ("duckduckgo", "google")  # pode adicionar "brave" se quiser ainda mais cobertura

RE_WAME  = re.compile(r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=)(\d{10,13})")
RE_TEL   = re.compile(r"(?:\+?55\s?)?\(?\d{2}\)?[\s.-]?9?\d{4}[\s.-]?\d{4}")
RE_INSTA = re.compile(r"instagram\.com/([A-Za-z0-9_.]{2,30})")
RE_FB    = re.compile(r"facebook\.com/([A-Za-z0-9_.]{2,50})")

DDD_BAHIA = {"71", "73", "74", "75", "77"}


def ddd_da_bahia(numero):
    d = re.sub(r"\D", "", numero or "")
    if d.startswith("55"):
        d = d[2:]
    return len(d) >= 10 and d[:2] in DDD_BAHIA


def buscar_livre(query, tentativas=2):
    """Consulta multiplos backends e junta os resultados (deduplicados por URL)."""
    todos, vistos = [], set()
    algum_sucesso = False

    for backend in BACKENDS:
        for tentativa in range(tentativas):
            try:
                with DDGS(timeout=15) as ddgs:
                    resultados = ddgs.text(query, max_results=5, region="br-pt", backend=backend)
                for item in resultados:
                    href = item.get("href", "")
                    if href and href not in vistos:
                        vistos.add(href)
                        todos.append(item)
                algum_sucesso = True
                break
            except RatelimitException:
                time.sleep(6 + tentativa * 4)
            except TimeoutException:
                time.sleep(2)
                break
            except DDGSException as ex:
                print(f"  [ERRO ddgs/{backend}] {ex}")
                break

    return todos if algum_sucesso else None


def extrair_sinais(resultados, nome_empresa, municipio):
    nome_norm = normaliza_nome(nome_empresa)
    municipio_norm = normaliza_nome(municipio)

    wa_links, tels, instas, fbs = [], [], [], []
    algum_resultado_valido = False

    for r in resultados:
        texto_item = f"{r.get('title','')} {r.get('body','')} {r.get('href','')}"
        texto_norm = normaliza_nome(texto_item)

        tem_nome  = bool(nome_norm) and nome_norm in texto_norm
        tem_local = (bool(municipio_norm) and municipio_norm in texto_norm) or "BAHIA" in texto_norm

        if not tem_nome:
            continue

        for w in RE_WAME.findall(texto_item):
            if tem_local or ddd_da_bahia(w):
                wa_links.append(w)
        for t in RE_TEL.findall(texto_item):
            if tem_local or ddd_da_bahia(t):
                tels.append(t)

        if tem_local:
            algum_resultado_valido = True
            instas += RE_INSTA.findall(texto_item)
            fbs    += RE_FB.findall(texto_item)

    achou_algo = bool(wa_links or tels or algum_resultado_valido)

    return {
        "achou_algo": achou_algo,
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
    print(f"Consultando {len(BACKENDS)} motores por empresa ({', '.join(BACKENDS)}) - mais lento, mais cobertura.")

    falhas_seguidas = 0
    achou_algo_total = 0

    for i, e in enumerate(empresas, 1):
        if e.get("_livre_checado"):
            continue

        nome = e.get("Nome_Fantasia") or e.get("Razao_Social") or ""
        municipio = e.get("Municipio", "")
        query = f'{nome} {municipio} Bahia whatsapp telefone contato'
        resultados = buscar_livre(query)

        if resultados is None:
            falhas_seguidas += 1
            if falhas_seguidas >= 5:
                print()
                print("PARANDO: 5 falhas seguidas. Espere alguns minutos e rode de novo -")
                print("o checkpoint garante que retoma sem perder o que ja foi feito.")
                salvar(empresas)
                sys.exit(1)
            continue
        falhas_seguidas = 0

        sinais = extrair_sinais(resultados, nome, municipio)

        if sinais["achou_algo"]:
            wa_tel = normaliza_e164(sinais["wa_links"][0]) if sinais["wa_links"] else ""
            tel    = normaliza_e164(sinais["tels"][0]) if sinais["tels"] else ""
            e["livre_whatsapp_tel"] = wa_tel or ""
            e["livre_tel"]          = tel or ""
            e["livre_instagram"]    = sinais["instagram"]
            e["livre_facebook"]     = sinais["facebook"]
            e["livre_confianca"]    = 1.0
            if wa_tel or tel or sinais["instagram"] or sinais["facebook"]:
                achou_algo_total += 1
        else:
            e["livre_whatsapp_tel"] = e["livre_tel"] = ""
            e["livre_instagram"] = e["livre_facebook"] = ""
            e["livre_confianca"] = 0.0

        e["_livre_checado"] = True
        time.sleep(DELAY_BASE + random.uniform(0, 1.0))

        if i % CHECKPOINT_EVERY == 0 or i == total:
            salvar(empresas)
            print(f"[{i}/{total}] processadas — {achou_algo_total} com algum sinal ate agora — checkpoint salvo.")

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


if __name__ == "__main__":
    main()
