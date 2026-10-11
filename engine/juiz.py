"""O Gerente de Auditoria: avalia e orienta a jogada do auditor.

Para o jogador, é o gerente que o acompanha na reunião. No código o módulo
continua se chamando juiz.py.

Chamada separada da persona do gestor de propósito: um gestor que também dá a
nota tende a ser condescendente ou a ficar preso no personagem.
"""

from __future__ import annotations

import re

from . import llm, prompts
from .estado import DIMENSOES, EstadoPartida


def elementos_cobertos(estado: EstadoPartida, texto_extra: str = "") -> set[str]:
    """Quais elementos-chave do caso já apareceram nas falas do auditor.

    Detecção determinística por padrão de texto. Instrução textual de memória
    não resolve: diante de um gabarito concreto, o avaliador volta a cobrar o
    mesmo item. Uma lista explícita do que já foi dito, sim.
    """
    tudo = " ".join([t.resposta_auditor or "" for t in estado.historico] + [texto_extra])
    plano = _texto_plano(tudo)
    cobertos = set()
    for el in estado.caso.elementos_chave:
        if any(re.search(p, plano, re.IGNORECASE) for p in el.get("padroes", [])):
            cobertos.add(el["id"])
    return cobertos


def _progresso(estado: EstadoPartida, resposta_atual: str = "") -> str:
    """O que o auditor já estabeleceu, em lista explícita.

    Sem isso o avaliador julga cada rodada no vácuo e repete a mesma cobrança
    indefinidamente — o auditor cita um dado na rodada 1 e continua sendo
    penalizado por não citá-lo na rodada 3.
    """
    if not estado.historico and not resposta_atual:
        return "Nenhuma: esta é a primeira resposta do auditor na reunião."

    cobertos = elementos_cobertos(estado, resposta_atual)
    ja = [el["nome"] for el in estado.caso.elementos_chave if el["id"] in cobertos]

    partes = []
    if ja:
        partes.append(
            "Pontos que o auditor JÁ colocou na mesa (não cobre nenhum de novo):\n"
            + "\n".join(f"  ✓ {x}" for x in ja)
        )
    else:
        partes.append("O auditor ainda não estabeleceu nenhum ponto factual.")

    # Deliberadamente NÃO enviamos lista de "o que falta". Quando enviávamos,
    # o avaliador passava a pontuar cobertura de itens em vez de qualidade do
    # argumento — uma resposta certa que não marcasse as caixinhas tirava 1,0.
    if estado.historico:
        falas = "\n".join(
            f'  Rodada {t.numero}: "{_resumir(t.resposta_auditor)}"'
            for t in estado.historico if t.resposta_auditor
        )
        partes.append("Falas anteriores do auditor:\n" + falas)
    return "\n\n".join(partes)


def _resumir(texto: str, limite: int = 320) -> str:
    texto = " ".join((texto or "").split())
    return texto if len(texto) <= limite else texto[:limite].rstrip() + "..."


def _system(estado: EstadoPartida, resposta_atual: str = "") -> str:
    obj = estado.objecao_corrente()
    return prompts.carregar("juiz").format(
        contexto_juiz=estado.caso.contexto_juiz(),
        progresso_auditor=_progresso(estado, resposta_atual),
        objecao_nome=obj["nome"],
        objecao_tipo=obj["tipo"],
        camada=estado.camada_atual,
        resposta_forte=obj["resposta_forte"],
        resposta_fraca=obj["resposta_fraca"],
    )


def _copiou_o_comentario(estado: EstadoPartida, resposta: str) -> bool:
    """Detecta o auditor colando de volta o comentário do gerente.

    Aconteceu em teste: o gerente escreveu "inclua a diferença de 25% para 10%",
    o jogador colou a frase e tirou 5. O jogo vira cópia, não argumentação.
    """
    if not estado.historico:
        return False
    comentario = estado.historico[-1].comentario or ""
    if not comentario:
        return False

    # Cópia literal: a resposta é um trecho do comentário.
    if len(_texto_plano(resposta)) > 25 and _texto_plano(resposta) in _texto_plano(comentario):
        return True

    palavras_resp = _significativas(resposta)
    if not (3 <= len(palavras_resp) <= 40):   # só respostas curtas
        return False
    palavras_com = _significativas(comentario)
    if not palavras_com:
        return False
    return len(palavras_resp & palavras_com) / len(palavras_resp) >= 0.7


def _texto_plano(texto: str) -> str:
    """Minúsculas, espaços colapsados, preservando vírgula, ponto e %.

    A vírgula e o ponto ficam porque números como 13,75% e itens como 4.3
    são justamente o que precisamos reconhecer.
    """
    return " ".join(re.sub(r"[^a-zà-ú0-9%,. ]", " ", (texto or "").lower()).split())


def _significativas(texto: str) -> set[str]:
    limpo = re.sub(r"[^a-zà-úA-ZÀ-Ú0-9%\s]", " ", texto or "").lower()
    return {p for p in limpo.split() if len(p) > 3}


def avaliar(estado: EstadoPartida, fala_gestor: str, resposta: str) -> dict:
    """Devolve o dicionário de avaliação, sempre com as chaves esperadas."""
    usuario = (
        f"FALA DO GESTOR:\n{fala_gestor}\n\n"
        f"RESPOSTA DO AUDITOR:\n{resposta}\n\n"
        "Avalie a resposta do auditor conforme a rubrica."
    )
    try:
        bruto = llm.json_estruturado(
            system=_system(estado, resposta),
            usuario=usuario,
            modelo=llm.MODELO_JUIZ,
            temperatura=0.2,
        )
    except Exception as e:  # o jogo não pode parar por causa do juiz
        return {
            "classificacao": "parcial",
            "notas": {d: None for d in DIMENSOES},
            "nota_geral": None,
            "conduta": "ok",
            "comentario_curto": (
                "Esta rodada não pôde ser avaliada, então o placar não mudou. "
                "A conversa continua normalmente."
            ),
            "detalhe_erro": str(e),
            "erro": True,
        }

    aval = _normalizar(bruto)

    # Colar o comentário do gerente não pode valer nota alta.
    if _copiou_o_comentario(estado, resposta):
        aval["classificacao"] = "parcial" if aval["classificacao"] == "resolvida" else aval["classificacao"]
        if aval["nota_geral"] is not None:
            aval["nota_geral"] = min(aval["nota_geral"], 2.0)
        for d in aval["notas"]:
            if aval["notas"][d] is not None:
                aval["notas"][d] = min(aval["notas"][d], 2.0)
        aval["comentario_curto"] = (
            "Você repetiu o comentário da rodada anterior em vez de formular a "
            "sua própria resposta. O conteúdo está certo, mas numa reunião real "
            "você precisa construir o argumento com as suas palavras e ligá-lo "
            "ao que o gestor acabou de dizer. " + aval["comentario_curto"]
        )
    return aval


def _normalizar(d: dict) -> dict:
    """Protege a engine de variações do modelo (campos faltando, 'na', strings)."""
    notas_brutas = d.get("notas") or {}
    notas: dict[str, float | None] = {}
    for dim in DIMENSOES:
        v = notas_brutas.get(dim)
        if isinstance(v, str):
            v = None if v.strip().lower() in ("na", "n/a", "") else _num(v)
        elif isinstance(v, (int, float)):
            v = max(0.0, min(5.0, float(v)))
        else:
            v = None
        notas[dim] = v

    nota_geral = d.get("nota_geral")
    if isinstance(nota_geral, str):
        nota_geral = _num(nota_geral)
    if not isinstance(nota_geral, (int, float)):
        vals = [v for v in notas.values() if v is not None]
        nota_geral = round(sum(vals) / len(vals), 1) if vals else None
    if isinstance(nota_geral, (int, float)):
        nota_geral = round(max(0.0, min(5.0, float(nota_geral))), 1)

    conduta = str(d.get("conduta", "ok")).strip().lower()
    if conduta not in ("ok", "atencao", "violacao"):
        conduta = "ok"

    classificacao = str(d.get("classificacao", "parcial")).strip().lower()
    if classificacao not in ("resolvida", "parcial", "ignorada"):
        classificacao = "parcial"

    return {
        "classificacao": classificacao,
        "notas": notas,
        "nota_geral": nota_geral,
        "conduta": conduta,
        "comentario_curto": str(d.get("comentario_curto", "")).strip(),
    }


def _num(s: str) -> float | None:
    try:
        return max(0.0, min(5.0, float(str(s).replace(",", ".").strip())))
    except ValueError:
        return None


def reescrever_em_cnv(frase: str, estado: EstadoPartida | None = None) -> str:
    """Usada na tela do RH: mostra como a fala poderia ter sido dita.

    Recebe o contexto do caso porque, sem ele, o modelo inventava normas
    ("Manual de Controle Interno, seção 3.2") que não existem no achado.
    """
    if estado is not None:
        m = estado.caso.matriz
        contexto = (
            f"- Condição: {m['condicao']}\n"
            f"- Critério: {m['criterio']}\n"
            f"- Causa: {m['causa']}\n"
            f"- Efeito: {m['efeito']}\n"
            f"- Recomendação: {m['recomendacao']}"
        )
    else:
        contexto = "(contexto não disponível — não cite nenhuma norma específica)"

    try:
        return llm.conversa(
            system="Você treina auditores em comunicação não violenta.",
            mensagens=[
                {"role": "user", "content": prompts.carregar("reescrita_cnv").format(
                    frase=frase, contexto_achado=contexto)}
            ],
            modelo=llm.MODELO_GESTOR,
            temperatura=0.5,
            max_tokens=1000,
        )
    except Exception:
        return (
            "Não foi possível gerar a reescrita agora. A estrutura a praticar é: "
            "fato observado, impacto (risco), controle ou política que sustenta o "
            "ponto, e pedido concreto à área — sem adjetivo sobre as pessoas."
        )
