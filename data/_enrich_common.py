"""
Funcoes compartilhadas pelos scripts de enriquecimento (cnpj_enrich,
maps_enrich, aws_enrich, here_enrich, osm_enrich). Nao roda sozinho.
"""
import re
import difflib
import unicodedata

ENRIQUECIDO_PATH = "data/bd_enriquecido.json"
ORIGINAL_PATH    = "data/bd_definitivo.json"

STOPWORDS = r"\b(LTDA|ME|EIRELI|EPP|SA|S A|COMERCIO|COM|DE|DA|DO|DOS|DAS)\b"
LIMIAR_CONFIANCA = 0.72  # calibrado com casos reais (ver conversa)


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
