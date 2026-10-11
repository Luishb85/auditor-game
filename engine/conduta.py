"""Primeira camada do portão de conduta: filtro local, antes de gastar chamada.

A segunda camada é o juiz, que pega o que é sutil (ironia hostil, ataque velado).
Este filtro só pega o que é inequívoco, para não gerar game over injusto.
"""

from __future__ import annotations

import re
import unicodedata

# Palavrões e ofensas diretas. Lista curta e inequívoca de propósito:
# falso positivo aqui custa uma partida inteira do jogador.
PALAVRAS_PROIBIDAS = {
    "idiota", "imbecil", "burro", "burra", "incompetente", "estupido", "estupida",
    "ridiculo", "ridicula", "mentiroso", "mentirosa", "palhaco", "palhaca",
    "merda", "porra", "caralho", "foda", "fodase", "bosta", "cuzao", "otario",
    "otaria", "babaca", "escroto", "lixo", "retardado", "retardada", "imbecilidade",
}

# Ameaças explícitas e ataques à pessoa do gestor. Testes mostraram o
# avaliador tratando isto como mera "advertência de tom", então o filtro
# local passa a pegar os casos inequívocos.
PADROES_AMEACA = [
    r"\bvou te (demitir|ferrar|acabar|destruir)\b",
    r"\bvoc[eê] (vai|v[aá]) se ferrar\b",
    r"\bvou acabar com (a sua|sua) carreira\b",
    # ataque à competência
    r"\balgu[eé]m mais (preparado|competente|capacitado)\b",
    r"\bvoc[eê] n[aã]o (est[aá] )?(entende|entendendo|compreende)\b",
    r"\bvoc[eê] n[aã]o (sabe|entende) (do que|o que)\b",
    # responsabilização pessoal por prejuízo
    r"\b(sua|a sua) (plr|remunera[cç][aã]o|sal[aá]rio|b[oô]nus)\b.{0,40}\b(rombo|preju[ií]zo|perda|conta)\b",
    r"\bquem (vai |ir[aá] )?pagar?\b.{0,60}\b(sua equipe|voc[eê]s|seu setor)\b",
    r"\b(sua equipe|seu setor|voc[eê]s)\b.{0,40}\b(pag(ue|ar|a)|arq(ue|uem)|arcar)\b",
    r"\b(pag(ue|ar|a)|arq(ue|uem)|arcar)\b.{0,40}\b(sua equipe|seu setor)\b",
]


def _normaliza(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto.lower())
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return sem_acento


def violacao_evidente(texto: str) -> str | None:
    """Devolve o termo que disparou a violação, ou None."""
    norm = _normaliza(texto)
    for palavra in re.findall(r"\b[\w]+\b", norm):
        if palavra in PALAVRAS_PROIBIDAS:
            return palavra
    for padrao in PADROES_AMEACA:
        m = re.search(padrao, norm)
        if m:
            return m.group(0)
    return None
