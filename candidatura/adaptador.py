"""Adapta currículo, carta e e-mail para uma vaga específica.

Princípio: TUDO que aparece no currículo vem do seu perfil. A adaptação:
  - coloca primeiro as habilidades que a vaga pede (e destaca em negrito);
  - ordena experiências/conquistas/projetos pela aderência à vaga;
  - ajusta o título profissional e o resumo (com IA, se configurada);
  - nunca adiciona tecnologia que você não declarou.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from candidatura import ia
from candidatura.compatibilidade import Analise, canonizar, contar_ocorrencias
from candidatura.perfil import Candidato, Experiencia, Projeto


@dataclass
class GrupoHabilidades:
    nome: str
    itens: list[tuple[str, bool]]  # (habilidade, destacada?)


@dataclass
class CurriculoAdaptado:
    candidato: Candidato
    titulo: str
    resumo: str
    grupos: list[GrupoHabilidades]
    experiencias: list[Experiencia]
    projetos: list[Projeto]
    destaques: list[str] = field(default_factory=list)


@dataclass
class Pacote:
    curriculo: CurriculoAdaptado
    carta: str
    assunto: str
    corpo_email: str
    usou_ia: bool = False


def _relevancia(texto: str, tecnologias_vaga: list[str]) -> int:
    return contar_ocorrencias(texto, tecnologias_vaga)


def _ordenar_habilidades(candidato: Candidato, analise: Analise) -> list[GrupoHabilidades]:
    pedidas = set(analise.em_comum)
    grupos = []
    for nome, itens in candidato.habilidades.items():
        marcados = [(h, canonizar(h) in pedidas) for h in itens]
        # Estável: destacadas primeiro, mantendo a sua ordem original dentro de cada bloco.
        marcados.sort(key=lambda x: not x[1])
        grupos.append(GrupoHabilidades(nome, marcados))
    # Grupo com mais destaques sobe.
    grupos.sort(key=lambda g: -sum(1 for _, d in g.itens if d))
    return grupos


def _ordenar_experiencias(candidato: Candidato, analise: Analise) -> list[Experiencia]:
    """Mantém a ordem cronológica das experiências (recrutador espera isso),
    mas reordena as conquistas DENTRO de cada uma pela aderência à vaga."""
    saida = []
    for e in candidato.experiencias:
        conquistas = sorted(
            e.conquistas,
            key=lambda c: -_relevancia(c + " " + " ".join(e.tecnologias), analise.pedidas),
        )
        saida.append(Experiencia(e.cargo, e.empresa, e.periodo, e.local, conquistas, e.tecnologias))
    return saida


def _ordenar_projetos(candidato: Candidato, analise: Analise, maximo: int = 4) -> list[Projeto]:
    pontuados = [
        (_relevancia(f"{p.nome} {p.descricao} {' '.join(p.tecnologias)}", analise.pedidas), i, p)
        for i, p in enumerate(candidato.projetos)
    ]
    pontuados.sort(key=lambda x: (-x[0], x[1]))
    return [p for _, _, p in pontuados[:maximo]]


def _titulo_adaptado(candidato: Candidato, analise: Analise) -> str:
    """Mantém seu título e acrescenta até 3 tecnologias centrais da vaga que
    você DE FATO tem — é o que um recrutador lê nos primeiros 6 segundos."""
    base = candidato.titulo.split("|")[0].strip() or candidato.titulo
    chaves = [t for t in analise.em_comum if t not in {"Inglês", "Espanhol", "Scrum", "Git"}][:3]
    return f"{base} | {' • '.join(chaves)}" if chaves else candidato.titulo


def _resumo_padrao(candidato: Candidato, analise: Analise, titulo_vaga: str) -> str:
    resumo = candidato.resumo
    chaves = [t for t in analise.em_comum if t not in {"Inglês", "Espanhol"}][:5]
    if chaves:
        resumo = (resumo.rstrip(". ") + ". " if resumo else "") + (
            f"Experiência prática com {', '.join(chaves[:-1]) + ' e ' + chaves[-1] if len(chaves) > 1 else chaves[0]}, "
            f"alinhada ao que a posição de {titulo_vaga} exige."
        )
    return resumo


def _lista_humana(itens: list[str]) -> str:
    if not itens:
        return ""
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]


def _carta_padrao(candidato: Candidato, analise: Analise, titulo: str, empresa: str) -> str:
    empresa_txt = empresa if empresa and empresa.lower() not in {"não informado", "confidencial"} else "sua empresa"
    chaves = [t for t in analise.em_comum if t not in {"Inglês", "Espanhol"}][:4]

    p1 = (
        f"Tenho interesse na vaga de {titulo} na {empresa_txt}. "
        f"Atuo como {candidato.titulo.split('|')[0].strip().lower() or 'desenvolvedor'}"
        + (f" e trabalho no dia a dia com {_lista_humana(chaves)}, tecnologias citadas na descrição da vaga." if chaves else ".")
    )

    evidencias = []
    for e in candidato.experiencias[:2]:
        melhor = sorted(e.conquistas, key=lambda c: -_relevancia(c, analise.pedidas))
        if melhor:
            evidencias.append(f"na {e.empresa}, {melhor[0][0].lower() + melhor[0][1:].rstrip('.')}")
    if not evidencias and candidato.projetos:
        p = _ordenar_projetos(candidato, analise, 1)[0]
        evidencias.append(f"no projeto {p.nome}, {p.descricao[0].lower() + p.descricao[1:].rstrip('.')}")
    p2 = ("Alguns exemplos do que já entreguei: " + "; ".join(evidencias) + ".") if evidencias else ""

    prefs = candidato.preferencias or {}
    disp = prefs.get("disponibilidade")
    p3 = (
        "Envio em anexo meu currículo"
        + (" e deixo abaixo os links do meu portfólio" if candidato.links else "")
        + ". Ficarei feliz em conversar sobre como posso contribuir com o time"
        + (f" — tenho disponibilidade {disp}" if disp else "")
        + "."
    )
    return "\n\n".join(p for p in (p1, p2, p3) if p)


def montar_pacote(candidato: Candidato, vaga: dict, analise: Analise, usar_ia: bool = True) -> Pacote:
    titulo_vaga = vaga.get("titulo", "").strip()
    empresa = (vaga.get("empresa") or "").strip()
    descricao = vaga.get("descricao") or ""

    usou_ia = False
    resumo = None
    carta = None
    if usar_ia and ia.disponivel():
        resumo = ia.resumo_adaptado(candidato, titulo_vaga, empresa, descricao, analise.em_comum)
        carta = ia.carta_adaptada(candidato, titulo_vaga, empresa, descricao, analise.em_comum)
        usou_ia = bool(resumo or carta)

    curriculo = CurriculoAdaptado(
        candidato=candidato,
        titulo=_titulo_adaptado(candidato, analise),
        resumo=resumo or _resumo_padrao(candidato, analise, titulo_vaga),
        grupos=_ordenar_habilidades(candidato, analise),
        experiencias=_ordenar_experiencias(candidato, analise),
        projetos=_ordenar_projetos(candidato, analise),
        destaques=analise.em_comum,
    )
    carta = carta or _carta_padrao(candidato, analise, titulo_vaga, empresa)

    assunto = f"Candidatura: {titulo_vaga} — {candidato.nome}"
    links = "\n".join(f"{k.capitalize()}: {v}" for k, v in candidato.links.items())
    corpo = (
        "Olá, tudo bem?\n\n"
        f"{carta}\n\n"
        + (f"{links}\n\n" if links else "")
        + "Atenciosamente,\n"
        + (candidato.assinatura_email or f"{candidato.nome}\n{candidato.telefone}\n{candidato.email}")
    )
    return Pacote(curriculo=curriculo, carta=carta, assunto=assunto, corpo_email=corpo.strip() + "\n", usou_ia=usou_ia)
