"""
Traz Instagram, Facebook, site oficial e WhatsApp ja encontrado (via
site proprio da empresa ou busca livre) para dentro de
data/bd_definitivo.json - o arquivo que o site de verdade importa.

IMPORTANTE - nivel de confianca: o WhatsApp aqui NAO passou pela
checagem paga da CheckNumber.AI ainda (isso exige saldo). E o numero
que foi ENCONTRADO diretamente (de preferencia no site oficial da
propria empresa, que e a fonte mais confiavel que temos de graca).
Quando voce rodar wa_pipeline.py + wa_aplicar.py depois (com saldo na
CheckNumber.AI), aquele processo confirma de verdade e substitui isso
por um dado mais rigoroso, alem de remover quem nao tiver WhatsApp
confirmado. Este script aqui NAO remove ninguem - so adiciona contato.

Uso:
    python3 data/mesclar_redes_sociais.py
"""
import json, shutil, datetime

ENRIQUECIDO = "data/bd_enriquecido.json"
DEFINITIVO  = "data/bd_definitivo.json"


def main():
    with open(ENRIQUECIDO, encoding="utf-8") as f:
        enriquecido = json.load(f)
    with open(DEFINITIVO, encoding="utf-8") as f:
        original = json.load(f)

    por_cnpj = {e.get("CNPJ"): e for e in enriquecido}

    com_wa = com_insta = com_fb = com_site = 0
    for e in original:
        fonte = por_cnpj.get(e.get("CNPJ"))
        if not fonte:
            continue

        wa = fonte.get("site_whatsapp_tel") or fonte.get("livre_whatsapp_tel") or ""
        if wa:
            e["whatsapp_number"] = wa
            e.setdefault("whatsapp_business", False)
            com_wa += 1

        insta = fonte.get("livre_instagram") or fonte.get("site_instagram") or ""
        if insta:
            e["livre_instagram"] = insta
            com_insta += 1

        fb = fonte.get("livre_facebook") or fonte.get("site_facebook") or ""
        if fb:
            e["livre_facebook"] = fb
            com_fb += 1

        if fonte.get("site_url"):
            e["site_url"] = fonte["site_url"]
            com_site += 1

    carimbo = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    backup = f"data/bd_definitivo_BACKUP_pre_redes_sociais_{carimbo}.json"
    shutil.copyfile(DEFINITIVO, backup)
    print(f"Backup salvo em {backup}")

    with open(DEFINITIVO, "w", encoding="utf-8") as f:
        json.dump(original, f, ensure_ascii=False, indent=2)

    print()
    print(f"Total de empresas: {len(original)}")
    print(f"Com WhatsApp encontrado (ainda NAO confirmado via CheckNumber.AI): {com_wa}")
    print(f"Com Instagram: {com_insta}")
    print(f"Com Facebook: {com_fb}")
    print(f"Com site oficial: {com_site}")
    print()
    print("Nenhuma empresa foi removida. Proximo passo: commitar, dar push,")
    print("e chamar o endpoint /api/companies/admin/reimport pra atualizar o site.")


if __name__ == "__main__":
    main()
