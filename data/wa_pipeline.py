"""
Verifica quais empresas têm WhatsApp de verdade, usando a API oficial da
CheckNumber.AI (nao precisa logar com seu proprio WhatsApp, sem risco de
banimento). Documentacao: https://docs.checknumber.ai/whatsapp-activity-checker/

Le data/bd_enriquecido.json (produzido por cnpj_enrich.py, maps_enrich.py,
aws_enrich.py, here_enrich.py e/ou osm_enrich.py - rode quantos quiser
antes deste, cada um adiciona seus proprios campos) e cruza TODOS os
telefones de TODAS as fontes numa unica checagem de WhatsApp.

Uso:
    export CHECKNUMBER_API_KEY="sua_chave_aqui"
    python3 data/wa_pipeline.py
"""
import json, os, sys, time, zipfile, io, csv
import requests

sys.path.insert(0, os.path.dirname(__file__))
from _enrich_common import ENRIQUECIDO_PATH, ORIGINAL_PATH, normaliza_e164

API_KEY   = os.environ.get("CHECKNUMBER_API_KEY")
BASE      = "https://api.checknumber.ai"
TASK_TYPE = "ws_active"   # retorna whatsapp_days + whatsapp_business (conta comercial)
CAMPOS_TELEFONE = (
    "Tel1", "Tel2", "Tel3",
    "maps_tel", "aws_tel", "here_tel", "osm_tel",
    "livre_whatsapp_tel", "livre_tel",
    "site_whatsapp_tel", "site_tel",
)


def carregar_empresas():
    path = ENRIQUECIDO_PATH if os.path.exists(ENRIQUECIDO_PATH) else ORIGINAL_PATH
    print(f"Usando base: {path}")
    if path == ORIGINAL_PATH:
        print("Aviso: nenhum enriquecimento rodado ainda (cnpj_enrich/maps_enrich/")
        print("aws_enrich/here_enrich/osm_enrich) - usando so os telefones originais.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def extrair_numeros(empresas):
    numeros = set()
    for e in empresas:
        for campo in CAMPOS_TELEFONE:
            n = normaliza_e164(e.get(campo, ""))
            if n:
                numeros.add(n)
    return sorted(numeros)


def enviar_tarefa(numeros):
    arquivo = ("\n".join(numeros)).encode("utf-8")
    resp = requests.post(
        f"{BASE}/v1/tasks",
        headers={"X-API-Key": API_KEY},
        files={"file": ("numeros.txt", arquivo, "text/plain")},
        data={"task_type": TASK_TYPE},
        timeout=60,
    )
    if resp.status_code != 200:
        sys.exit(f"Erro ao criar tarefa na CheckNumber.AI (status {resp.status_code}): {resp.text[:500]}")
    dados = resp.json()
    if "task_id" not in dados:
        sys.exit(f"Resposta inesperada da CheckNumber.AI (sem task_id): {dados}")
    return dados


def consultar_status(task_id):
    resp = requests.post(
        f"{BASE}/v1/gettasks",
        headers={"X-API-Key": API_KEY},
        data={"task_id": task_id},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def baixar_resultado(url):
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    return resp.content


def parse_resultado(conteudo_zip):
    resultados = {}
    with zipfile.ZipFile(io.BytesIO(conteudo_zip)) as z:
        for nome in z.namelist():
            if not nome.lower().endswith((".csv", ".txt")):
                continue
            with z.open(nome) as f:
                texto = f.read().decode("utf-8", errors="ignore")
            linhas = list(csv.reader(io.StringIO(texto)))
            if not linhas:
                continue
            header = [h.strip().lower() for h in linhas[0]]
            idx_num  = header.index("number") if "number" in header else 0
            idx_days = header.index("whatsapp_days")     if "whatsapp_days"     in header else None
            idx_biz  = header.index("whatsapp_business") if "whatsapp_business" in header else None
            for linha in linhas[1:]:
                if not linha or len(linha) <= idx_num:
                    continue
                numero = linha[idx_num].strip()
                dias = linha[idx_days].strip() if idx_days is not None and idx_days < len(linha) else "N/A"
                biz  = linha[idx_biz].strip().lower() if idx_biz is not None and idx_biz < len(linha) else "no"
                resultados[numero] = {"whatsapp_days": dias, "whatsapp_business": biz == "yes"}
    return resultados


def mesclar(empresas, resultados):
    sem_whatsapp = []
    for e in empresas:
        candidatos = []
        for campo in CAMPOS_TELEFONE:
            n = normaliza_e164(e.get(campo, ""))
            if n and n in resultados:
                r = resultados[n]
                if r["whatsapp_days"] not in ("N/A", "", None):
                    candidatos.append((n, r, campo))
        if candidatos:
            candidatos.sort(key=lambda x: (not x[1]["whatsapp_business"]))
            melhor_num, melhor, campo_origem = candidatos[0]
            e["whatsapp_number"]   = melhor_num
            e["whatsapp_business"] = melhor["whatsapp_business"]
            e["whatsapp_days"]     = melhor["whatsapp_days"]
            e["whatsapp_fonte"]    = campo_origem
        else:
            e["whatsapp_number"]   = None
            e["whatsapp_business"] = False
            e["whatsapp_days"]     = None
            e["whatsapp_fonte"]    = None
            sem_whatsapp.append(e)
    return empresas, sem_whatsapp


def main():
    if not API_KEY:
        sys.exit("Defina a variavel de ambiente CHECKNUMBER_API_KEY antes de rodar.")

    print("Carregando base...")
    empresas = carregar_empresas()
    numeros = extrair_numeros(empresas)
    print(f"{len(numeros)} numeros unicos serao verificados na CheckNumber.AI.")

    with open("data/numeros_para_checar.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(numeros))

    print("Enviando tarefa...")
    tarefa = enviar_tarefa(numeros)
    task_id = tarefa["task_id"]
    print(f"Tarefa criada: {task_id} (total={tarefa.get('total')})")

    print("Aguardando processamento (pode levar alguns minutos)...")
    while True:
        time.sleep(10)
        status = consultar_status(task_id)
        print(f"  status={status['status']}  {status.get('success', 0)}/{status.get('total', '?')}")
        if status["status"] == "exported":
            resultado_url = status["result_url"]
            break
        if status["status"] not in ("pending", "processing"):
            sys.exit(f"Status inesperado retornado pela API: {status}")

    print("Baixando resultados...")
    resultados = parse_resultado(baixar_resultado(resultado_url))
    print(f"{len(resultados)} numeros retornaram resultado.")

    print("Mesclando com a base de empresas...")
    empresas, sem_whatsapp = mesclar(empresas, resultados)

    with open("data/bd_definitivo_enriquecido.json", "w", encoding="utf-8") as f:
        json.dump(empresas, f, ensure_ascii=False, indent=2)

    with open("data/relatorio_sem_whatsapp.txt", "w", encoding="utf-8") as f:
        for e in sem_whatsapp:
            f.write(f"{e.get('Nome_Fantasia') or e.get('Razao_Social') or '?'} | {e.get('Municipio','')} | {e.get('CNPJ','')}\n")

    por_fonte = {}
    for e in empresas:
        f_ = e.get("whatsapp_fonte")
        if f_:
            por_fonte[f_] = por_fonte.get(f_, 0) + 1

    com_wa = len(empresas) - len(sem_whatsapp)
    print()
    print(f"Total de empresas:        {len(empresas)}")
    print(f"Com WhatsApp confirmado:  {com_wa}")
    print(f"Sem WhatsApp confirmado:  {len(sem_whatsapp)}")
    print()
    print("WhatsApp confirmado veio de cada fonte:")
    for campo, qtd in sorted(por_fonte.items(), key=lambda x: -x[1]):
        print(f"  {campo:20s}: {qtd}")
    print()
    print("A base original (data/bd_definitivo.json) NAO foi alterada ainda.")
    print("Resultado completo em data/bd_definitivo_enriquecido.json")
    print("Lista das sem WhatsApp em data/relatorio_sem_whatsapp.txt")
    print()
    print("Revise o relatorio. Quando estiver pronto para aplicar de vez, rode:")
    print("    python3 data/wa_aplicar.py")


if __name__ == "__main__":
    main()
