"""
Busca ADICIONAL e direcionada, especifica para Instagram e Facebook,
usando o operador site: pra forcar o motor a devolver resultado daquela
plataforma. NAO substitui nada que ja foi encontrado - so preenche o que
ainda esta em branco (roda quantas vezes quiser, sempre olhando so pro
que falta).

Continua sendo busca de texto (via ddgs, sem chave de API) - NAO visita
a pagina do Instagram/Facebook em si.

Le/escreve em data/bd_enriquecido.json (arquivo compartilhado).

Pre-requisito:
    pip3 install ddgs --break-system-packages

Uso:
    python3 data/busca_social_direcionada.py
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
BACKENDS = ("duckduckgo", "google")

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


def buscar(query, tentativas=2):
    for backend in BACKENDS:
        for tentativa in range(tentativas):
            try:
                with DDGS(timeout=15) as ddgs:
                    return ddgs.text(query, max_results=5, region="br-pt", backend=backend)
            except RatelimitException:
                time.sleep(6 + tentativa * 4)
            except (TimeoutException, DDGSException):
                time.sleep(2)
                break
    return None


def extrai_sinais(resultados, nome_norm, municipio_norm):
    wa, tel, insta, fb = [], [], [], []
    for r in resultados:
        texto = f"{r.get('title','')} {r.get('body','')} {r.get('href','')}"
        texto_norm = normaliza_nome(texto)
        if not (bool(nome_norm) and nome_norm in texto_norm):
            continue
        tem_local = (bool(municipio_norm) and municipio_norm in texto_norm) or "BAHIA" in texto_norm

        wa  += [w for w in RE_WAME.findall(texto) if tem_local or ddd_da_bahia(w)]
        tel += [t for t in RE_TEL.findall(texto) if tem_local or ddd_da_bahia(t)]
        if tem_local:
            insta += RE_INSTA.findall(texto)
            fb    += RE_FB.findall(texto)
    return wa, tel, insta, fb


def carregar():
    path = ENRIQUECIDO_PATH if os.path.exists(ENRIQUECIDO_PATH) else ORIGINAL_PATH
    print(f"Carregando base de {path}...")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def salvar(empresas):
    with open(ENRIQUECIDO_PATH, "w", encoding="utf-8") as f:
        json.dump(empresas, f, ensure_ascii=False, indent=2)


def main():
    empresas = carregar()
    pendentes = [e for e in empresas
                 if not e.get("_busca_social_feita")
                 and (not e.get("livre_instagram") or not e.get("livre_facebook"))]
    total = len(pendentes)
    ja_feitas = sum(1 for e in empresas if e.get("_busca_social_feita"))
    print(f"{ja_feitas} ja verificadas antes. {total} ainda tem Instagram e/ou Facebook em branco.")

    falhas_seguidas = 0
    cooldowns_usados = 0
    MAX_COOLDOWNS = 4
    achados_novos = 0

    for i, e in enumerate(pendentes, 1):
        nome = e.get("Nome_Fantasia") or e.get("Razao_Social") or ""
        municipio = e.get("Municipio", "")
        nome_norm = normaliza_nome(nome)
        municipio_norm = normaliza_nome(municipio)

        consultas = []
        if not e.get("livre_instagram"):
            consultas.append(f'site:instagram.com "{nome}" {municipio} Bahia')
        if not e.get("livre_facebook"):
            consultas.append(f'site:facebook.com "{nome}" {municipio} Bahia')

        pelo_menos_um_sucesso = False
        achou_algo_aqui = False

        for query in consultas:
            resultados = buscar(query)
            if resultados is None:
                falhas_seguidas += 1
                continue
            falhas_seguidas = 0
            pelo_menos_um_sucesso = True

            wa, tel, insta, fb = extrai_sinais(resultados, nome_norm, municipio_norm)
            if wa and not e.get("livre_whatsapp_tel"):
                e["livre_whatsapp_tel"] = normaliza_e164(wa[0]) or ""
                achou_algo_aqui = True
            if tel and not e.get("livre_tel"):
                e["livre_tel"] = normaliza_e164(tel[0]) or ""
                achou_algo_aqui = True
            if insta and not e.get("livre_instagram"):
                e["livre_instagram"] = insta[0]
                achou_algo_aqui = True
            if fb and not e.get("livre_facebook"):
                e["livre_facebook"] = fb[0]
                achou_algo_aqui = True

            time.sleep(DELAY_BASE + random.uniform(0, 1.0))

        if falhas_seguidas >= 6:
            cooldowns_usados += 1
            if cooldowns_usados > MAX_COOLDOWNS:
                print()
                print("PARANDO: bloqueio persistente mesmo apos pausas de recuperacao.")
                print("Espere 1-2 horas antes de rodar de novo.")
                salvar(empresas)
                sys.exit(1)
            espera = 60 * cooldowns_usados
            print(f"Varias falhas seguidas - pausa de recuperacao #{cooldowns_usados} ({espera}s)...")
            salvar(empresas)
            time.sleep(espera)
            falhas_seguidas = 0
        elif pelo_menos_um_sucesso:
            cooldowns_usados = 0

        if pelo_menos_um_sucesso or not consultas:
            e["_busca_social_feita"] = True
        if achou_algo_aqui:
            achados_novos += 1

        if i % CHECKPOINT_EVERY == 0 or i == total:
            salvar(empresas)
            print(f"[{i}/{total}] processadas — {achados_novos} com dado novo ate agora — checkpoint salvo.")

    salvar(empresas)

    com_wa    = sum(1 for e in empresas if e.get("livre_whatsapp_tel"))
    com_tel   = sum(1 for e in empresas if e.get("livre_tel"))
    com_insta = sum(1 for e in empresas if e.get("livre_instagram"))
    com_fb    = sum(1 for e in empresas if e.get("livre_facebook"))
    print()
    print(f"Total de empresas na base:            {len(empresas)}")
    print(f"Com WhatsApp encontrado (total):      {com_wa}")
    print(f"Com telefone generico (total):        {com_tel}")
    print(f"Com Instagram (total):                {com_insta}")
    print(f"Com Facebook (total):                 {com_fb}")
    print(f"Resultado salvo em {ENRIQUECIDO_PATH}")


if __name__ == "__main__":
    main()
