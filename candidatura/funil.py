"""Funil por fonte: de onde vêm as respostas e as entrevistas.

Para cada fonte (LinkedIn, Gupy, sites das empresas, posts...): quantas você
curtiu, quantas enviou (e-mail ou pelo site), quantas responderam e quantas
viraram entrevista. "Entrevista" você marca na página da vaga (etapa).
"""

from __future__ import annotations

from candidatura import repositorio

ETAPAS = {"entrevista": "Entrevista", "teste": "Teste técnico", "proposta": "Proposta",
          "contratado": "Contratado 🎉", "recusado": "Recusado"}
ETAPAS_DE_ENTREVISTA = {"entrevista", "teste", "proposta", "contratado"}
_NOMES_ORIGEM = {"empresa": "Sites das empresas", "post": "Posts de recrutadores", "manual": "Colado à mão",
                 "espontanea": "Candidatura espontânea", "github": "GitHub (comunidade)", "remotar": "Remotar",
                 "gupy": "Gupy"}


def fonte_da_vaga(v: dict) -> str:
    origem = v.get("origem") or ""
    if origem in _NOMES_ORIGEM:
        return _NOMES_ORIGEM[origem]
    site = (v.get("site") or "").strip()
    if site.lower().startswith("linkedin"):
        return "LinkedIn"
    return site or "Outras"


def calcular() -> list[dict]:
    linhas: dict[str, dict] = {}
    for v in repositorio.listar(["pronta", "manual", "enviando", "enviada", "aplicada", "respondida", "encerrada",
                                 "erro", "curtida"], limite=100000):
        f = linhas.setdefault(fonte_da_vaga(v), {"fonte": fonte_da_vaga(v), "curtidas": 0, "enviadas": 0,
                                                 "respostas": 0, "entrevistas": 0})
        f["curtidas"] += 1
        enviada = (v["status"] in ("enviada", "respondida") and not v.get("simulado")) or v["status"] == "aplicada"
        if enviada:
            f["enviadas"] += 1
        if v["status"] == "respondida" or v.get("resposta_em"):
            f["respostas"] += 1
        if (v.get("etapa") or "") in ETAPAS_DE_ENTREVISTA:
            f["entrevistas"] += 1
    for f in linhas.values():
        f["taxa_resposta"] = round(100 * f["respostas"] / f["enviadas"]) if f["enviadas"] else 0
        f["taxa_entrevista"] = round(100 * f["entrevistas"] / f["enviadas"]) if f["enviadas"] else 0
    return sorted(linhas.values(), key=lambda f: (-f["entrevistas"], -f["respostas"], -f["enviadas"], f["fonte"]))
