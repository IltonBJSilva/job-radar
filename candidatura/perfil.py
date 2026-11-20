"""Perfil do candidato: a ÚNICA fonte de verdade do currículo.

A adaptação por vaga só reordena e destaca o que está aqui — nunca inventa
experiência, empresa, número ou tecnologia que você não declarou.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from candidatura import config


@dataclass
class Experiencia:
    cargo: str
    empresa: str
    periodo: str
    local: str = ""
    conquistas: list[str] = field(default_factory=list)
    tecnologias: list[str] = field(default_factory=list)


@dataclass
class Projeto:
    nome: str
    descricao: str
    link: str = ""
    tecnologias: list[str] = field(default_factory=list)


@dataclass
class Formacao:
    curso: str
    instituicao: str
    periodo: str = ""


@dataclass
class Candidato:
    nome: str
    titulo: str
    email: str
    telefone: str = ""
    cidade: str = ""
    links: dict[str, str] = field(default_factory=dict)
    resumo: str = ""
    habilidades: dict[str, list[str]] = field(default_factory=dict)
    experiencias: list[Experiencia] = field(default_factory=list)
    projetos: list[Projeto] = field(default_factory=list)
    formacao: list[Formacao] = field(default_factory=list)
    certificacoes: list[str] = field(default_factory=list)
    idiomas: list[str] = field(default_factory=list)
    preferencias: dict = field(default_factory=dict)
    assinatura_email: str = ""

    @property
    def todas_habilidades(self) -> list[str]:
        vistas, saida = set(), []
        for grupo in self.habilidades.values():
            for h in grupo:
                if h.lower() not in vistas:
                    vistas.add(h.lower())
                    saida.append(h)
        for exp in self.experiencias:
            for h in exp.tecnologias:
                if h.lower() not in vistas:
                    vistas.add(h.lower())
                    saida.append(h)
        for proj in self.projetos:
            for h in proj.tecnologias:
                if h.lower() not in vistas:
                    vistas.add(h.lower())
                    saida.append(h)
        return saida

    @property
    def primeiro_nome(self) -> str:
        return self.nome.split()[0] if self.nome else ""


class PerfilNaoEncontrado(FileNotFoundError):
    pass


class PerfilInvalido(ValueError):
    pass


def _texto(v) -> str:
    return "" if v is None else str(v).strip()


def _lista(v, separar_virgula: bool = False) -> list[str]:
    """Aceita lista, string ou nada. "Python, Django" vira ["Python", "Django"]
    (sem isso o CV mostraria "P, y, t, h, o, n")."""
    if v is None:
        return []
    if isinstance(v, (str, int, float)):
        partes = str(v).split(",") if separar_virgula else [str(v)]
        return [p.strip() for p in partes if p.strip()]
    if isinstance(v, (list, tuple)):
        return [_texto(x) for x in v if x is not None and _texto(x)]
    return []


def _dicts(v) -> list[dict]:
    return [x for x in (v or []) if isinstance(x, dict)] if isinstance(v, list) else []


def carregar_candidato(caminho: Path | str | None = None) -> Candidato:
    caminho = Path(caminho) if caminho else config.PERFIL_PATH
    if not caminho.exists():
        raise PerfilNaoEncontrado(
            f"Perfil não encontrado em {caminho}. Copie "
            f"{config.PERFIL_EXEMPLO_PATH.name} para {config.PERFIL_PATH.name} "
            "e preencha com seus dados (ou rode: python candidatar.py iniciar)."
        )
    try:
        with open(caminho, encoding="utf-8") as f:
            dados = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise PerfilInvalido(f"Erro de sintaxe em {caminho.name}: {e}") from e
    if not isinstance(dados, dict):
        raise PerfilInvalido(f"{caminho.name} precisa ser um mapa (pessoal:, habilidades:, ...).")
    candidato = candidato_de_dict(dados)
    if not candidato.nome or not candidato.email:
        raise PerfilInvalido(f"Preencha pessoal.nome e pessoal.email em {caminho.name}.")
    return candidato


def candidato_de_dict(d: dict) -> Candidato:
    pessoal = d.get("pessoal") if isinstance(d.get("pessoal"), dict) else {}
    links = d.get("links") if isinstance(d.get("links"), dict) else {}
    habilidades = d.get("habilidades")
    if isinstance(habilidades, list):  # lista solta em vez de grupos
        habilidades = {"Competências": habilidades}
    habilidades = habilidades if isinstance(habilidades, dict) else {}
    return Candidato(
        nome=_texto(pessoal.get("nome")),
        titulo=_texto(pessoal.get("titulo")),
        email=_texto(pessoal.get("email")),
        telefone=_texto(pessoal.get("telefone")),
        cidade=_texto(pessoal.get("cidade")),
        links={_texto(k): _texto(v) for k, v in links.items() if _texto(v)},
        resumo=_texto(d.get("resumo")),
        habilidades={_texto(k): _lista(v, separar_virgula=True) for k, v in habilidades.items() if _lista(v, True)},
        experiencias=[
            Experiencia(
                cargo=_texto(e.get("cargo")),
                empresa=_texto(e.get("empresa")),
                periodo=_texto(e.get("periodo")),
                local=_texto(e.get("local")),
                conquistas=_lista(e.get("conquistas")),
                tecnologias=_lista(e.get("tecnologias"), separar_virgula=True),
            )
            for e in _dicts(d.get("experiencias"))
        ],
        projetos=[
            Projeto(
                nome=_texto(p.get("nome")),
                descricao=_texto(p.get("descricao")),
                link=_texto(p.get("link")),
                tecnologias=_lista(p.get("tecnologias"), separar_virgula=True),
            )
            for p in _dicts(d.get("projetos"))
        ],
        formacao=[
            Formacao(curso=_texto(f.get("curso")), instituicao=_texto(f.get("instituicao")), periodo=_texto(f.get("periodo")))
            for f in _dicts(d.get("formacao"))
        ],
        certificacoes=_lista(d.get("certificacoes")),
        idiomas=_lista(d.get("idiomas")),
        preferencias=d.get("preferencias") if isinstance(d.get("preferencias"), dict) else {},
        assinatura_email=_texto(d.get("assinatura_email")),
    )
