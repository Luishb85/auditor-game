"""Relatório CSV da partida.

As colunas foram desenhadas como as futuras tabelas do banco (partidas,
turnos). Quando o Supabase entrar, troca-se "gerar linha" por "gravar linha"
sem mudar o modelo de dados.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone

from .estado import DIMENSOES, EstadoPartida

COLUNAS = [
    # identificação da partida (futura tabela 'partidas')
    "partida_id", "data_hora_utc", "jogador", "caso_id", "nivel",
    "duracao_segundos", "desfecho", "motivo_fim",
    "credibilidade_final", "resistencia_final", "nota_media_geral",
    # detalhe do turno (futura tabela 'turnos')
    "rodada", "objecao_id", "camada", "classificacao", "conduta",
    "nota_geral_turno", *[f"nota_{d}" for d in DIMENSOES],
    "delta_credibilidade", "delta_resistencia", "delta_hostilidade",
    "resposta_auditor", "comentario_gerente",
]


def gerar_csv(estado: EstadoPartida, jogador: str = "anonimo") -> str:
    partida_id = str(uuid.uuid4())[:8]
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUNAS, delimiter=";")
    w.writeheader()

    base = {
        "partida_id": partida_id,
        "data_hora_utc": agora,
        "jogador": jogador or "anonimo",
        "caso_id": estado.caso.id,
        "nivel": estado.caso.nivel,
        "duracao_segundos": estado.duracao_segundos(),
        "desfecho": estado.desfecho(),
        "motivo_fim": estado.motivo_fim,
        "credibilidade_final": estado.credibilidade,
        "resistencia_final": estado.resistencia,
        "nota_media_geral": estado.nota_media_geral(),
    }

    for t in estado.historico:
        linha = dict(base)
        linha.update(
            {
                "rodada": t.numero,
                "objecao_id": t.objecao_id,
                "camada": t.camada,
                "classificacao": t.classificacao,
                "conduta": t.conduta,
                "nota_geral_turno": t.nota_geral,
                "delta_credibilidade": t.delta_credibilidade,
                "delta_resistencia": t.delta_resistencia,
                "delta_hostilidade": t.delta_hostilidade,
                "resposta_auditor": _limpa(t.resposta_auditor),
                "comentario_gerente": _limpa(t.comentario),
            }
        )
        for d in DIMENSOES:
            linha[f"nota_{d}"] = t.notas.get(d)
        w.writerow(linha)

    return buf.getvalue()


def nome_arquivo(estado: EstadoPartida, jogador: str = "anonimo") -> str:
    carimbo = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    seguro = "".join(c for c in (jogador or "anonimo") if c.isalnum() or c in "-_")
    return f"partida_{estado.caso.id}_{seguro or 'anonimo'}_{carimbo}.csv"


def _limpa(texto: str) -> str:
    """Tira quebras de linha para não estourar a célula do CSV."""
    return " ".join((texto or "").split())
