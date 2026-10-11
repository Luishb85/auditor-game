"""O gestor: persona interpretada pelo LLM.

A engine decide QUAL objeção entra e COMO a fala abre; o LLM só veste isso com
tom e personalidade. Instrução de frequência ("use o bordão de vez em quando")
é justamente o que um LLM ignora, então essa decisão sai do prompt e vem para cá.
"""

from __future__ import annotations

import random
import re

from . import llm, prompts
from .estado import EstadoPartida

# Quantos turnos do diálogo são reenviados ao modelo. O resto vira resumo.
JANELA_HISTORICO = 4

# Em quantas falas, proporcionalmente, o bordão pode aparecer.
CHANCE_BORDAO = 0.25

# Acima disso, a fala do gestor é considerada eco da resposta do auditor.
LIMITE_ECO = 0.45


def _usa_bordao(estado: EstadoPartida) -> bool:
    """Sorteia, nunca em duas falas seguidas."""
    ultima = estado.historico[-1].fala_gestor if estado.historico else ""
    bordao = estado.caso.gestor.get("bordao", "")
    if bordao and ultima and _normaliza(bordao)[:25] in _normaliza(ultima):
        return False
    return random.random() < CHANCE_BORDAO


def _system(estado: EstadoPartida, usa_bordao: bool, reforcar: bool = False) -> str:
    caso = estado.caso
    obj = estado.objecao_corrente()
    camada = estado.camada_corrente()
    bordao = caso.gestor.get("bordao", "")

    if usa_bordao and bordao:
        instr = f'Nesta fala você PODE usar o seu bordão ("{bordao}"), uma vez só.'
    else:
        instr = (
            f'NESTA FALA NÃO use o seu bordão ("{bordao}") nem nada parecido. '
            "Comece de outro jeito."
        )
    if reforcar:
        instr += (
            "\nATENÇÃO: a sua fala anterior repetiu os argumentos do auditor. "
            "Reaja contra o achado, a partir dos interesses da sua área."
        )

    return prompts.carregar("gestor").format(
        nome=caso.gestor["nome_ficticio"],
        cargo=caso.gestor["cargo"],
        contexto_gestor=caso.contexto_gestor(),
        hostilidade=estado.hostilidade,
        objecao_nome=obj["nome"],
        objecao_tipo=obj["tipo"],
        frases_modelo=" | ".join(camada.get("frases_modelo", [])),
        observacao=(f"Contexto: {camada['observacao']}" if camada.get("observacao") else ""),
        resumo_estado=estado.resumo_estado_para_prompt(),
        instrucao_bordao=instr,
    )


def _mensagens(estado: EstadoPartida) -> list[dict[str, str]]:
    """Últimos turnos como diálogo, mais um lembrete final de papel.

    O lembrete vai no fim de propósito: depois de ler um argumento bem
    construído do auditor, o modelo tende a concordar com ele. A instrução
    mais recente é a que mais pesa.
    """
    msgs: list[dict[str, str]] = []
    for t in estado.historico[-JANELA_HISTORICO:]:
        if t.fala_gestor:
            msgs.append({"role": "assistant", "content": t.fala_gestor})
        msgs.append({"role": "user", "content": t.resposta_auditor})

    if not msgs:
        msgs.append(
            {
                "role": "user",
                "content": (
                    "Bom dia. Vou apresentar o achado da auditoria sobre o processo "
                    "de validação de renda. Pode abrir a reunião com a sua reação."
                ),
            }
        )

    obj = estado.objecao_corrente()
    msgs.append(
        {
            "role": "system",
            "content": (
                f"Lembrete: você é {estado.caso.gestor['nome_ficticio']}, o gestor "
                f"auditado, e está RESISTINDO ao achado. Responda à fala do auditor "
                f"levantando ou sustentando a objeção \"{obj['nome']}\". "
                "Não repita os argumentos dele como se fossem seus. "
                "Só a sua fala, 2 a 5 frases."
            ),
        }
    )
    return msgs


def _normaliza(t: str) -> str:
    return re.sub(r"[^a-zà-ú0-9 ]", " ", (t or "").lower())


def _palavras(t: str) -> set[str]:
    return {p for p in _normaliza(t).split() if len(p) > 4}


# Frases que só um AUDITOR diria. Quando aparecem na boca do gestor, ele trocou
# de lado — o defeito que mais estraga o jogo. A lista é curta de propósito:
# o conserto principal é o prompt; isto é uma rede de segurança.
MARCAS_DE_AUDITOR = [
    r"\bpermanece v[áa]lida\b",
    r"\bn[ãa]o cabe (a n[óo]s )?(simplesmente )?rebaixar\b",
    r"\b(a )?alta classifica[çc][ãa]o\b.{0,40}\b(mant|permanec|v[áa]lid)",
    r"\bseguindo a metodologia de auditoria\b",
    r"\bo achado procede\b",
    r"\bconcordo com o achado\b",
    r"\bdevemos manter\b.{0,40}\b(criticidade|classifica[çc][ãa]o|foco)\b",
    r"\bque a auditoria recomenda\b",
    r"\bsem (um )?fundamento t[ée]cnico\b",
    r"\breconhe[çc]o que o controle (est[áa] )?(falh|desalinhad)",
    # concessões que só o auditor faz: admitir o alcance sistêmico da falha
    r"\b(afeta|atinge|compromete)\b.{0,30}\btodo o fluxo\b",
    r"\bn[ãa]o s[óo] (as |nas )?\d+ opera[çc]",
    r"\bn[ãa]o apenas (as |nas )?\d+ opera[çc]",
]


def _trocou_de_lado(fala: str, resposta_auditor: str) -> bool:
    """Detecta o gestor argumentando pelo lado da auditoria.

    Duas vias: parafrasear a posição do auditor (marcas de linguagem) ou
    repetir literalmente o vocabulário da resposta anterior.
    """
    norm = _normaliza(fala)
    if any(re.search(p, norm) for p in MARCAS_DE_AUDITOR):
        return True

    g, a = _palavras(fala), _palavras(resposta_auditor)
    if len(g) < 8 or not a:
        return False
    return len(g & a) / len(g) >= LIMITE_ECO


def falar(estado: EstadoPartida) -> str:
    """Gera a próxima fala do gestor, com uma retentativa se ela virar eco."""
    usa_bordao = _usa_bordao(estado)
    fala = llm.conversa(
        system=_system(estado, usa_bordao),
        mensagens=_mensagens(estado),
        modelo=llm.MODELO_GESTOR,
        temperatura=0.85,
        max_tokens=1200,
    )

    ultima_resposta = estado.historico[-1].resposta_auditor if estado.historico else ""
    if _trocou_de_lado(fala, ultima_resposta):
        fala = llm.conversa(
            system=_system(estado, usa_bordao, reforcar=True),
            mensagens=_mensagens(estado),
            modelo=llm.MODELO_GESTOR,
            temperatura=0.95,
            max_tokens=1200,
        )
    return fala
