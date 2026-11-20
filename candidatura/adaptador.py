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
from candidatura.compatibilidade import Analise, canonizar, contar_ocorrencias, termos_declarados
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
    # A ordem dos GRUPOS é a sua (Linguagens antes de Práticas etc.).
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


_POUCO_DISTINTIVAS = {"Inglês", "Espanhol", "Scrum", "Git"}


def _declaradas(candidato: Candidato, analise: Analise) -> list[str]:
    """Tecnologias em comum, escritas EXATAMENTE como no seu perfil.

    O score compara por nome canônico (MariaDB conta como MySQL), mas o texto
    do currículo/carta nunca troca o seu termo pelo da vaga."""
    mapa = termos_declarados(candidato.todas_habilidades)
    saida = []
    for t in analise.em_comum:
        if t in _POUCO_DISTINTIVAS or t not in mapa:
            continue
        if mapa[t] not in saida:
            saida.append(mapa[t])
    return saida


def _titulo_adaptado(candidato: Candidato, declaradas: list[str]) -> str:
    """Mantém seu título e acrescenta até 3 tecnologias centrais da vaga que
    você DE FATO tem — é o que um recrutador lê nos primeiros 6 segundos."""
    base = candidato.titulo.split("|")[0].strip() or candidato.titulo
    chaves = declaradas[:3]
    return f"{base} | {' • '.join(chaves)}" if chaves else candidato.titulo


def _resumo_padrao(candidato: Candidato, declaradas: list[str], score: int) -> str:
    """Seu resumo + as tecnologias em comum, só quando a vaga é aderente."""
    resumo = candidato.resumo
    if declaradas and score >= 60:
        resumo = (resumo.rstrip(". ") + ". " if resumo else "") + f"Principais tecnologias: {_lista_humana(declaradas[:5])}."
    return resumo


def _lista_humana(itens: list[str]) -> str:
    if not itens:
        return ""
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]


def _minuscula_inicial(texto: str) -> str:
    texto = (texto or "").strip().rstrip(".")
    if len(texto) > 1 and texto[1].isupper():  # sigla: "API REST", "AWS"
        return texto
    return texto[:1].lower() + texto[1:] if texto else ""


_EMPRESAS_SEM_NOME = {"", "não informado", "nao informado", "confidencial", "empresa confidencial", "sigilosa"}


def nome_empresa(empresa: str) -> str:
    """'LOJAS TRÊS PASSOS' -> 'Lojas Três Passos'; vazio/confidencial -> ''."""
    empresa = (empresa or "").strip()
    if empresa.lower() in _EMPRESAS_SEM_NOME:
        return ""
    return empresa.title() if empresa.isupper() and len(empresa) > 4 else empresa


def titulo_curto(titulo: str, maximo: int = 60) -> str:
    """Tira '(Venda Direta)', '[Remoto]', '- Remote Work | REF#...' do título."""
    import re

    t = re.sub(r"\s*[\(\[].*?[\)\]]", "", titulo or "")
    t = re.split(r"\s+[-|/]\s+(?=(home office|remot|hybrid|h[ií]brido|ref|presencial))", t, flags=re.I)[0]
    t = " ".join(t.split()).strip(" -|/")
    if not t:  # título era só "[Remoto]" ou "(PJ)": melhor o original que vazio
        t = " ".join((titulo or "vaga").split())
    if len(t) > maximo:
        t = t[:maximo].rsplit(" ", 1)[0]
    return t.rstrip(" -|/&,+:;")


def _recentes(candidato: Candidato) -> set[str]:
    """Tecnologias da experiência mais recente (a primeira do perfil), ou
    todas as habilidades se você não listou tecnologias por experiência."""
    techs = candidato.experiencias[0].tecnologias if candidato.experiencias else []
    return {t.lower() for t in techs} if techs else {h.lower() for h in candidato.todas_habilidades}


def _emprego_atual(candidato: Candidato) -> bool:
    """Só dizemos "trabalho atualmente" se o período da 1ª experiência indica isso."""
    import re

    periodo = (candidato.experiencias[0].periodo if candidato.experiencias else "").lower()
    return bool(re.search(r"atual|presente|hoje|current|now|\batual\b", periodo))


def _verbo_tecnologias(candidato: Candidato) -> str:
    return "trabalho atualmente com" if _emprego_atual(candidato) else "tenho experiência recente com"


def _carta_padrao(candidato: Candidato, analise: Analise, declaradas: list[str], titulo: str, empresa: str) -> str:
    """Sem artigo antes da empresa ("na Itaú"/"no Nubank" erram com facilidade)
    e sem afirmar uso atual de tecnologia que você só usou no passado."""
    empresa_txt = nome_empresa(empresa)
    titulo_txt = titulo_curto(titulo)
    atuais = [t for t in declaradas if t.lower() in _recentes(candidato)][:4]
    papel = candidato.titulo.split("|")[0].strip()

    p1 = f"Gostaria de me candidatar à vaga de {titulo_txt}" + (f" ({empresa_txt})" if empresa_txt else "") + "."
    if papel:
        p1 += f" Sou {papel[0].lower() + papel[1:]}" + (f" e {_verbo_tecnologias(candidato)} {_lista_humana(atuais)}." if atuais else ".")

    evidencias = []
    for e in candidato.experiencias[:2]:
        melhor = sorted((c for c in e.conquistas if c and c.strip()), key=lambda c: -_relevancia(c, analise.pedidas))
        if melhor and e.empresa:
            evidencias.append(f"{e.empresa}: {_minuscula_inicial(melhor[0])}")
    if not evidencias and candidato.projetos:
        p = _ordenar_projetos(candidato, analise, 1)[0]
        if p.descricao and p.descricao.strip():
            evidencias.append(f"projeto {p.nome}: {_minuscula_inicial(p.descricao)}")
    p2 = ("Alguns resultados recentes — " + "; ".join(evidencias) + ".") if evidencias else ""

    disp = (candidato.preferencias or {}).get("disponibilidade")
    p3 = ("Seguem em anexo meu currículo e esta carta. Terei prazer em conversar sobre como posso contribuir com o time"
          + (f"; minha disponibilidade para início é {disp}" if disp else "") + ".")
    return "\n\n".join(p for p in (p1, p2, p3) if p)


_ROTULOS_LINKS = {"linkedin": "LinkedIn", "github": "GitHub", "portfolio": "Portfólio", "site": "Site",
                  "gitlab": "GitLab", "behance": "Behance"}


def _primeiro_ultimo(nome: str) -> str:
    partes = nome.split()
    return " ".join([partes[0], partes[-1]]) if len(partes) > 2 else nome


def _corpo_email(candidato: Candidato, titulo: str, empresa: str, declaradas: list[str], analise: Analise) -> str:
    """E-mail curto: a carta completa vai em anexo (não repetir o mesmo texto)."""
    empresa_txt = nome_empresa(empresa)
    atuais = [t for t in declaradas if t.lower() in _recentes(candidato)][:3]
    papel = candidato.titulo.split("|")[0].strip()
    destaque = ""
    for e in candidato.experiencias[:1]:
        melhor = sorted((c for c in e.conquistas if c and c.strip()), key=lambda c: -_relevancia(c, analise.pedidas))
        if melhor:
            destaque = f" Recentemente, {_minuscula_inicial(melhor[0])}."
    linhas = [
        "Olá,",
        "",
        f"Gostaria de me candidatar à vaga de {titulo_curto(titulo)}" + (f" ({empresa_txt})" if empresa_txt else "") + ". "
        + (f"Sou {papel[0].lower() + papel[1:]}" if papel else "Tenho experiência em desenvolvimento")
        + (f" e {_verbo_tecnologias(candidato)} {_lista_humana(atuais)}." if atuais else ".")
        + destaque,
        "",
        "Envio em anexo meu currículo e uma carta de apresentação. Fico à disposição para conversar.",
        "",
        "Atenciosamente,",
    ]
    assinatura = candidato.assinatura_email or "\n".join(
        x for x in [candidato.nome, candidato.telefone,
                    *[f"{_ROTULOS_LINKS.get(k.lower(), k.capitalize())}: {v}" for k, v in candidato.links.items()]] if x
    )
    return "\n".join(linhas) + "\n" + assinatura.strip() + "\n"


def _abertura_espontanea(candidato: Candidato, cargo: str, empresa: str) -> str:
    # "na empresa X" é sempre correto (evita "na Google"/"no Stefanini").
    empresa_txt = nome_empresa(empresa)
    atuais = [h for h in candidato.todas_habilidades if h.lower() in _recentes(candidato)][:4]
    texto = (f"Gostaria de me colocar à disposição para oportunidades de {titulo_curto(cargo)}"
             + (f" na empresa {empresa_txt}" if empresa_txt else "") + ", mesmo que não haja uma vaga aberta agora.")
    papel = candidato.titulo.split("|")[0].strip()
    if papel:
        texto += f" Sou {papel[0].lower() + papel[1:]}" + (
            f" e {_verbo_tecnologias(candidato)} {_lista_humana(atuais)}." if atuais else ".")
    return texto


def _pacote_espontaneo(candidato: Candidato, vaga: dict, analise: Analise) -> Pacote:
    """Sem vaga anunciada: nada de "gostaria de me candidatar à vaga de..."."""
    cargo = vaga.get("titulo", "").strip() or candidato.titulo
    empresa = (vaga.get("empresa") or "").strip()
    abertura = _abertura_espontanea(candidato, cargo, empresa)

    evidencias = []
    for e in candidato.experiencias[:2]:
        conquista = next((c for c in e.conquistas if c and c.strip()), "")
        if conquista and e.empresa:
            evidencias.append(f"{e.empresa}: {_minuscula_inicial(conquista)}")
    if not evidencias:
        for p in candidato.projetos[:2]:
            if p.descricao and p.descricao.strip():
                evidencias.append(f"projeto {p.nome}: {_minuscula_inicial(p.descricao)}")
    p2 = ("Alguns resultados recentes — " + "; ".join(evidencias) + ".") if evidencias else ""
    disp = (candidato.preferencias or {}).get("disponibilidade")
    p3 = ("Seguem em anexo meu currículo e esta carta. Caso surja uma posição compatível, terei prazer em conversar"
          + (f"; minha disponibilidade para início é {disp}" if disp else "") + ".")
    carta = "\n\n".join(p for p in (abertura, p2, p3) if p)

    linhas = ["Olá,", "", abertura, "",
              "Envio em anexo meu currículo e uma carta de apresentação. Se fizer sentido, peço que considerem "
              "meu perfil para processos atuais ou futuros.", "", "Atenciosamente,"]
    assinatura = candidato.assinatura_email or "\n".join(
        x for x in [candidato.nome, candidato.telefone,
                    *[f"{_ROTULOS_LINKS.get(k.lower(), k.capitalize())}: {v}" for k, v in candidato.links.items()]] if x
    )
    curriculo = CurriculoAdaptado(
        candidato=candidato, titulo=candidato.titulo, resumo=candidato.resumo,
        grupos=_ordenar_habilidades(candidato, analise), experiencias=_ordenar_experiencias(candidato, analise),
        projetos=_ordenar_projetos(candidato, analise), destaques=[],
    )
    assunto = f"Candidatura espontânea: {titulo_curto(cargo)} — {_primeiro_ultimo(candidato.nome)}"
    return Pacote(curriculo=curriculo, carta=carta, assunto=assunto,
                  corpo_email="\n".join(linhas) + "\n" + assinatura.strip() + "\n")


def montar_pacote(candidato: Candidato, vaga: dict, analise: Analise, usar_ia: bool = True) -> Pacote:
    if vaga.get("origem") == "espontanea":
        return _pacote_espontaneo(candidato, vaga, analise)
    titulo_vaga = vaga.get("titulo", "").strip()
    empresa = (vaga.get("empresa") or "").strip()
    descricao = vaga.get("descricao") or ""

    declaradas = _declaradas(candidato, analise)
    usou_ia = False
    resumo = None
    carta = None
    if usar_ia and ia.disponivel():
        resumo = ia.saida_segura(ia.resumo_adaptado(candidato, titulo_vaga, empresa, descricao, declaradas), candidato)
        carta = ia.saida_segura(ia.carta_adaptada(candidato, titulo_vaga, empresa, descricao, declaradas), candidato)
        usou_ia = bool(resumo or carta)

    curriculo = CurriculoAdaptado(
        candidato=candidato,
        titulo=_titulo_adaptado(candidato, [t for t in declaradas if t.lower() in _recentes(candidato)] or declaradas),
        resumo=resumo or _resumo_padrao(candidato, declaradas, analise.score),
        grupos=_ordenar_habilidades(candidato, analise),
        experiencias=_ordenar_experiencias(candidato, analise),
        projetos=_ordenar_projetos(candidato, analise),
        destaques=analise.em_comum,
    )
    carta = carta or _carta_padrao(candidato, analise, declaradas, titulo_vaga, empresa)

    assunto = f"Candidatura: {titulo_curto(titulo_vaga)} — {_primeiro_ultimo(candidato.nome)}"
    corpo = _corpo_email(candidato, titulo_vaga, empresa, declaradas, analise)
    return Pacote(curriculo=curriculo, carta=carta, assunto=assunto, corpo_email=corpo, usou_ia=usou_ia)
