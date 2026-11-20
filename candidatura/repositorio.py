"""Persistência da fila de candidaturas (tabela `candidaturas` no jobs.db).

Status de uma candidatura:
    nova        -> ainda não avaliada (aparece no swipe)
    descartada  -> você recusou
    curtida     -> você aprovou; falta preparar
    pronta      -> CV/carta/e-mail gerados, tem e-mail de destino
    manual      -> preparada, mas sem e-mail: candidate-se pelo link com o PDF gerado
    enviada     -> e-mail enviado (ou simulado, ver campo `simulado`)
    erro        -> falha no preparo/envio (ver campo `erro`)
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

from candidatura import config
from core.config import DB_PATH as RADAR_DB_PATH

STATUS = ("nova", "descartada", "curtida", "pronta", "manual", "enviada", "erro")

_COLUNAS = """
    id TEXT PRIMARY KEY,
    titulo TEXT NOT NULL,
    empresa TEXT,
    local TEXT,
    modalidade TEXT,
    link TEXT,
    site TEXT,
    origem TEXT,
    publicado_em TEXT,
    descricao TEXT,
    email_destino TEXT,
    emails_encontrados TEXT,
    score INTEGER,
    em_comum TEXT,
    faltando TEXT,
    status TEXT NOT NULL DEFAULT 'nova',
    assunto TEXT,
    corpo TEXT,
    carta TEXT,
    cv_path TEXT,
    carta_path TEXT,
    erro TEXT,
    simulado INTEGER DEFAULT 0,
    criada_em TEXT DEFAULT CURRENT_TIMESTAMP,
    atualizada_em TEXT DEFAULT CURRENT_TIMESTAMP,
    enviada_em TEXT
"""

_JSON = ("emails_encontrados", "em_comum", "faltando")


@contextmanager
def conectar():
    """Banco PRÓPRIO (data/candidaturas.db, fora do Git): guarda seus e-mails,
    cartas e histórico de envio. O jobs.db do radar é versionado no GitHub,
    então nada pessoal pode morar nele."""
    config.CANDIDATURAS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.CANDIDATURAS_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def iniciar():
    with conectar() as conn:
        conn.execute(f"CREATE TABLE IF NOT EXISTS candidaturas ({_COLUNAS})")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cand_status ON candidaturas (status, score)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cand_email ON candidaturas (email_destino)")


def gerar_id(link: str, titulo: str = "", empresa: str = "") -> str:
    base = link or f"{empresa}|{titulo}"
    return hashlib.md5(base.encode("utf-8")).hexdigest()


def _linha_para_dict(linha: sqlite3.Row | None) -> dict | None:
    if linha is None:
        return None
    d = dict(linha)
    for campo in _JSON:
        try:
            d[campo] = json.loads(d.get(campo) or "[]")
        except (TypeError, ValueError):
            d[campo] = []
    return d


def inserir(vaga: dict) -> bool:
    """Insere se ainda não existe (por id). Devolve True se inseriu."""
    vaga = dict(vaga)
    vaga.setdefault("id", gerar_id(vaga.get("link", ""), vaga.get("titulo", ""), vaga.get("empresa", "")))
    for campo in _JSON:
        if campo in vaga and not isinstance(vaga[campo], str):
            vaga[campo] = json.dumps(vaga[campo], ensure_ascii=False)
    campos = [c for c in vaga if c in _nomes_colunas()]
    with conectar() as conn:
        cur = conn.execute(
            f"INSERT OR IGNORE INTO candidaturas ({', '.join(campos)}) VALUES ({', '.join('?' for _ in campos)})",
            [vaga[c] for c in campos],
        )
        return cur.rowcount > 0


def _nomes_colunas() -> set[str]:
    return {linha.strip().split()[0] for linha in _COLUNAS.strip().splitlines() if linha.strip()}


def atualizar(id_: str, **campos):
    if not campos:
        return
    for campo in _JSON:
        if campo in campos and not isinstance(campos[campo], str):
            campos[campo] = json.dumps(campos[campo], ensure_ascii=False)
    campos["atualizada_em"] = datetime.now().isoformat(timespec="seconds")
    if "status" in campos and campos["status"] not in STATUS:
        raise ValueError(f"status inválido: {campos['status']}")
    with conectar() as conn:
        conn.execute(
            f"UPDATE candidaturas SET {', '.join(f'{c} = ?' for c in campos)} WHERE id = ?",
            [*campos.values(), id_],
        )


def obter(id_: str) -> dict | None:
    with conectar() as conn:
        return _linha_para_dict(conn.execute("SELECT * FROM candidaturas WHERE id = ?", (id_,)).fetchone())


def listar(status: str | list[str] | None = None, limite: int = 500, ordem: str = "score DESC, criada_em DESC") -> list[dict]:
    sql, args = "SELECT * FROM candidaturas", []
    if status:
        lista = [status] if isinstance(status, str) else list(status)
        sql += f" WHERE status IN ({', '.join('?' for _ in lista)})"
        args += lista
    sql += f" ORDER BY {ordem} LIMIT ?"
    args.append(limite)
    with conectar() as conn:
        return [_linha_para_dict(l) for l in conn.execute(sql, args).fetchall()]


def contagem_por_status() -> dict[str, int]:
    with conectar() as conn:
        linhas = conn.execute("SELECT status, COUNT(*) FROM candidaturas GROUP BY status").fetchall()
    base = {s: 0 for s in STATUS}
    base.update({s: n for s, n in linhas})
    return base


def enviadas_hoje(incluir_simuladas: bool = False) -> int:
    hoje = datetime.now().date().isoformat()
    sql = "SELECT COUNT(*) FROM candidaturas WHERE status = 'enviada' AND substr(enviada_em, 1, 10) = ?"
    if not incluir_simuladas:
        sql += " AND simulado = 0"
    with conectar() as conn:
        return conn.execute(sql, (hoje,)).fetchone()[0]


def ja_contatado(email: str, empresa: str, dias: int, ignorar_id: str = "") -> bool:
    """True se já enviamos (de verdade) para este e-mail ou empresa na janela."""
    limite = (datetime.now() - timedelta(days=dias)).isoformat(timespec="seconds")
    with conectar() as conn:
        linha = conn.execute(
            """
            SELECT 1 FROM candidaturas
            WHERE status = 'enviada' AND simulado = 0 AND id != ? AND enviada_em >= ?
              AND (lower(email_destino) = lower(?) OR (? != '' AND lower(empresa) = lower(?)))
            LIMIT 1
            """,
            (ignorar_id, limite, email or "", empresa or "", empresa or ""),
        ).fetchone()
    return linha is not None


def importar_do_radar(limite: int = 2000, radar_db: str | None = None) -> int:
    """Copia para a fila as vagas aprovadas pelo radar que ainda não estão nela."""
    import os

    radar_db = radar_db or RADAR_DB_PATH
    if not os.path.exists(radar_db):
        return 0
    with conectar() as conn:
        conn.execute("ATTACH DATABASE ? AS radar", (str(radar_db),))
        try:
            colunas = {l[1] for l in conn.execute("PRAGMA radar.table_info(vagas_vistas)")}
            if not colunas:
                return 0
            desc = "v.descricao" if "descricao" in colunas else "''"
            cur = conn.execute(
                f"""
                INSERT OR IGNORE INTO candidaturas
                    (id, titulo, empresa, local, modalidade, link, site, origem, publicado_em, descricao)
                SELECT v.id, v.titulo, v.empresa, v.local, v.modalidade, v.link, v.site,
                       'radar', v.publicado_em, COALESCE({desc}, '')
                FROM radar.vagas_vistas v
                WHERE NOT EXISTS (SELECT 1 FROM candidaturas c WHERE c.id = v.id)
                ORDER BY v.encontrada_em DESC
                LIMIT ?
                """,
                (limite,),
            )
            n = cur.rowcount
            conn.commit()
        finally:
            conn.execute("DETACH DATABASE radar")
    return n


def metricas() -> dict:
    with conectar() as conn:
        total_env = conn.execute("SELECT COUNT(*) FROM candidaturas WHERE status='enviada' AND simulado=0").fetchone()[0]
        simuladas = conn.execute("SELECT COUNT(*) FROM candidaturas WHERE status='enviada' AND simulado=1").fetchone()[0]
        media = conn.execute("SELECT AVG(score) FROM candidaturas WHERE status IN ('pronta','enviada','manual')").fetchone()[0]
    return {
        "por_status": contagem_por_status(),
        "enviadas_reais": total_env,
        "simuladas": simuladas,
        "enviadas_hoje": enviadas_hoje(),
        "score_medio": round(media or 0),
    }
