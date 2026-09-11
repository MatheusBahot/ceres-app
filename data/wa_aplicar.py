"""
Aplica de vez o resultado da verificacao de WhatsApp:
- faz backup da base atual
- mantem em bd_definitivo.json SOMENTE as empresas com whatsapp_number confirmado
- o campo "whatsapp_number" fica salvo em cada empresa, pronto pra ser
  importado pelo init.js no proximo deploy

So rode isso DEPOIS de revisar data/relatorio_sem_whatsapp.txt e ter
certeza de que quer remover essas empresas.

Uso:
    python3 data/wa_aplicar.py
"""
import json, shutil, datetime, sys, os

ENRIQUECIDO = "data/bd_definitivo_enriquecido.json"
ORIGINAL    = "data/bd_definitivo.json"

def main():
    if not os.path.exists(ENRIQUECIDO):
        sys.exit(f"Nao encontrei {ENRIQUECIDO}. Rode data/wa_pipeline.py primeiro.")

    with open(ENRIQUECIDO, encoding="utf-8") as f:
        empresas = json.load(f)

    mantidas = [e for e in empresas if e.get("whatsapp_number")]
    removidas = len(empresas) - len(mantidas)

    print(f"Total analisado: {len(empresas)}")
    print(f"Serao mantidas (com WhatsApp confirmado): {len(mantidas)}")
    print(f"Serao removidas (sem WhatsApp confirmado): {removidas}")
    resp = input("Confirma a aplicacao definitiva? Digite SIM para continuar: ").strip()
    if resp != "SIM":
        print("Cancelado. Nada foi alterado.")
        return

    carimbo = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    backup_path = f"data/bd_definitivo_BACKUP_pre_whatsapp_{carimbo}.json"
    shutil.copyfile(ORIGINAL, backup_path)
    print(f"Backup da base anterior salvo em {backup_path}")

    with open(ORIGINAL, "w", encoding="utf-8") as f:
        json.dump(mantidas, f, ensure_ascii=False, indent=2)

    print(f"{ORIGINAL} atualizado com {len(mantidas)} empresas (todas com WhatsApp confirmado).")
    print("Proximo passo: commitar e enviar para o GitHub (o Render vai reimportar no proximo deploy).")

if __name__ == "__main__":
    main()
