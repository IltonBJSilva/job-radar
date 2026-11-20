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


def carregar_candidato(caminho: Path | str | None = None) -> Candidato:
    caminho = Path(caminho) if caminho else config.PERFIL_PATH
    if not caminho.exists():
        raise PerfilNaoEncontrado(
            f"Perfil não encontrado em {caminho}. Copie "
            f"{config.PERFIL_EXEMPLO_PATH.name} para {config.PERFIL_PATH.name} "
            "e preencha com seus dados (ou rode: python candidatar.py iniciar)."
        )
    with open(caminho, encoding="utf-8") as f:
        dados = yaml.safe_load(f) or {}
    return candidato_de_dict(dados)


def candidato_de_dict(d: dict) -> Candidato:
    pessoal = d.get("pessoal", {})
    return Candidato(
        nome=pessoal.get("nome", ""),
        titulo=pessoal.get("titulo", ""),
        email=pessoal.get("email", ""),
        telefone=str(pessoal.get("telefone", "") or ""),
        cidade=pessoal.get("cidade", ""),
        links={k: v for k, v in (d.get("links") or {}).items() if v},
        resumo=(d.get("resumo") or "").strip(),
        habilidades={k: list(v or []) for k, v in (d.get("habilidades") or {}).items()},
        experiencias=[
            Experiencia(
                cargo=e.get("cargo", ""),
                empresa=e.get("empresa", ""),
                periodo=e.get("periodo", ""),
                local=e.get("local", ""),
                conquistas=list(e.get("conquistas") or []),
                tecnologias=list(e.get("tecnologias") or []),
            )
            for e in d.get("experiencias") or []
        ],
        projetos=[
            Projeto(
                nome=p.get("nome", ""),
                descricao=p.get("descricao", ""),
                link=p.get("link", ""),
                tecnologias=list(p.get("tecnologias") or []),
            )
            for p in d.get("projetos") or []
        ],
        formacao=[
            Formacao(curso=f.get("curso", ""), instituicao=f.get("instituicao", ""), periodo=f.get("periodo", ""))
            for f in d.get("formacao") or []
        ],
        certificacoes=list(d.get("certificacoes") or []),
        idiomas=list(d.get("idiomas") or []),
        preferencias=d.get("preferencias") or {},
        assinatura_email=(d.get("assinatura_email") or "").strip(),
    )
