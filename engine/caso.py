"""Carregamento e acesso aos casos (arquivos YAML em cases/)."""

from pathlib import Path
from typing import Any

import yaml

CASES_DIR = Path(__file__).resolve().parent.parent / "cases"


class Caso:
    """Envolve o dicionário do YAML e expõe só o que cada papel pode ver.

    A separação de visibilidade é regra de jogo, não detalhe de implementação:
    o gestor NUNCA pode receber a camada de defesa (seria o gabarito do auditor).
    """

    def __init__(self, dados: dict[str, Any]):
        self.d = dados

    # ---------- carregamento ----------

    @classmethod
    def carregar(cls, nome_arquivo: str) -> "Caso":
        caminho = CASES_DIR / nome_arquivo
        with open(caminho, encoding="utf-8") as f:
            return cls(yaml.safe_load(f))

    @classmethod
    def listar(cls) -> list[str]:
        return sorted(p.name for p in CASES_DIR.glob("*.yaml"))

    # ---------- atalhos ----------

    @property
    def id(self) -> str:
        return self.d["id"]

    @property
    def titulo(self) -> str:
        return self.d["titulo"]

    @property
    def nivel(self) -> str:
        return self.d.get("nivel", "medio")

    @property
    def matriz(self) -> dict:
        return self.d["matriz"]

    @property
    def numeros_chave(self) -> list[str]:
        return self.d.get("numeros_chave", [])

    @property
    def dificuldade(self) -> dict:
        return self.d["dificuldade"]

    @property
    def gestor(self) -> dict:
        return self.d["gestor"]

    @property
    def rubrica(self) -> dict:
        return self.d["rubrica"]

    @property
    def conduta(self) -> dict:
        return self.d["conduta"]

    @property
    def desfecho(self) -> dict:
        return self.d["desfecho"]

    @property
    def camada_defesa(self) -> dict:
        """Gabarito. Só o juiz e o debriefing podem ver."""
        return self.d["camada_defesa"]

    @property
    def elementos_chave(self) -> list[dict]:
        """Elementos que o auditor pode apresentar ao longo da reunião.

        A engine detecta quais já apareceram e informa o avaliador, que fica
        proibido de cobrá-los de novo.
        """
        return self.d.get("elementos_chave", [])

    # ---------- objeções ----------

    def objecoes(self) -> list[dict]:
        return self.d["objecoes"]

    def objecao(self, obj_id: str) -> dict:
        for o in self.objecoes():
            if o["id"] == obj_id:
                return o
        raise KeyError(f"Objeção {obj_id} não existe no caso {self.id}")

    def objecoes_ativas(self) -> list[dict]:
        """Na ordem definida em dificuldade.objecoes_ativas."""
        ordem = self.dificuldade["objecoes_ativas"]
        return [self.objecao(i) for i in ordem]

    # ---------- visões por papel ----------

    def briefing_auditor(self) -> dict:
        """O que o jogador vê. Sem camada de defesa, sem respostas_fortes."""
        m = self.matriz
        return {
            "titulo": self.titulo,
            "objeto": m["objeto"],
            "objetivo": m["objetivo"],
            "questao_auditoria": m["questao_auditoria"],
            "criterio": m["criterio"],
            "condicao": m["condicao"],
            "evidencias": m["evidencias"],
            "causa": m["causa"],
            "efeito": m["efeito"],
            "boas_praticas": m["boas_praticas"],
            "recomendacao": m["recomendacao"],
            "criticidade": m.get("criticidade", "alta"),
            "numeros_chave": self.numeros_chave,
        }

    def contexto_gestor(self) -> str:
        """Fatia enviada ao LLM que faz a persona. Enxuta de propósito."""
        m = self.matriz
        g = self.gestor
        return (
            f"CARGO: {g['cargo']}\n"
            f"NOME: {g['nome_ficticio']}\n"
            f"BORDÃO: {g['bordao']}\n"
            f"TOM BASE: {g['tom_base']}\n"
            f"O QUE VOCÊ SABE: {g['gestor_sabe']}\n\n"
            f"ACHADO QUE A AUDITORIA TROUXE:\n"
            f"- Condição: {m['condicao']}\n"
            f"- Critério: {m['criterio']}\n"
            f"- Causa apontada: {m['causa']}\n"
            f"- Recomendação: {m['recomendacao']}\n"
            f"- Criticidade proposta: {m.get('criticidade', 'alta')}\n"
        )

    def contexto_juiz(self) -> str:
        """Fatia enviada ao LLM avaliador. Inclui o gabarito."""
        m = self.matriz
        cd = self.camada_defesa
        postura = "\n".join(f"  - {x}" for x in cd["postura_resposta"])
        erros = "\n".join(f"  - {x}" for x in cd["erros_comuns_do_auditor"])
        return (
            f"ACHADO:\n"
            f"- Condição: {m['condicao']}\n"
            f"- Critério: {m['criterio']}\n"
            f"- Causa: {m['causa']}\n"
            f"- Efeito: {m['efeito']}\n"
            f"- Boas práticas da área: {m['boas_praticas']}\n"
            f"- Recomendação: {m['recomendacao']}\n\n"
            f"GABARITO (postura de resposta esperada):\n{postura}\n\n"
            f"ERROS COMUNS A PENALIZAR:\n{erros}\n"
        )
