"""Estado da partida: barras, rodadas, objeções e histórico.

Esta é a única fonte de verdade do jogo. O LLM nunca decide placar:
ele avalia (juiz) ou interpreta (gestor); quem move as barras é este módulo.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from .caso import Caso

Classificacao = Literal["resolvida", "parcial", "ignorada"]

DIMENSOES = [
    "evidencia",
    "criterio",
    "causa_efeito",
    "diagnostico",
    "comunicacao",
    "foco_no_fato",
]

# Teto de perda de credibilidade numa única rodada. Sem ele, classificação
# ruim + nota baixa + comunicação baixa se somam e punem três vezes a mesma falha.
PENALIDADE_MAXIMA_RODADA = 6

# Tentativas na mesma OBJEÇÃO (somando as duas camadas) antes de o gestor
# seguir adiante. Era por camada, o que dava seis tentativas por objeção e
# prendia a partida no mesmo assunto quase a partida inteira.
TENTATIVAS_POR_OBJECAO = 3

# Advertências de tom acumuladas que levam à convocação do RH. Na prática,
# "atenção ao tom" sem consequência nenhuma deixa a agressividade impune.
# Defina como 0 no YAML (conduta.advertencias_para_game_over) para desligar.
ADVERTENCIAS_PADRAO = 3

ROTULO_DIMENSAO = {
    "evidencia": "Evidência",
    "criterio": "Critério",
    "causa_efeito": "Causa-efeito",
    "diagnostico": "Diagnóstico da objeção",
    "comunicacao": "Comunicação (CNV)",
    "foco_no_fato": "Foco no fato",
}


@dataclass
class Turno:
    """Um par pergunta/resposta já avaliado."""

    numero: int
    fala_gestor: str
    resposta_auditor: str
    objecao_id: str
    camada: int
    classificacao: Classificacao | None
    notas: dict[str, Any]
    nota_geral: float | None
    comentario: str
    delta_credibilidade: int
    delta_resistencia: int
    delta_hostilidade: int
    conduta: str
    # Preenchido quando esta jogada ENCERROU uma objeção. A interface usa isso
    # para revelar a resposta esperada na hora, sem esperar o debriefing —
    # a objeção já passou, então não há spoiler.
    objecao_encerrada: str | None = None
    # Preenchido quando as tentativas acabaram sem o auditor resolver.
    objecao_esgotada: str | None = None


@dataclass
class EstadoPartida:
    caso: Caso
    credibilidade: int = 50
    resistencia: int = 70
    hostilidade: int = 3
    rodada: int = 1
    rodadas_max: int = 8

    objecao_atual: str = ""
    camada_atual: int = 1
    # Ordem sorteada no início da partida: abertura verossímil + resto embaralhado.
    ordem_objecoes: list[str] = field(default_factory=list)
    # id -> {1: classificacao|None, 2: classificacao|None}
    status_objecoes: dict[str, dict[int, Classificacao | None]] = field(default_factory=dict)

    historico: list[Turno] = field(default_factory=list)
    fala_pendente: str = ""          # fala do gestor aguardando resposta
    game_over: bool = False
    motivo_fim: str = ""
    advertencias: int = 0
    tentativas_por_objecao: int = TENTATIVAS_POR_OBJECAO
    advertencias_limite: int = ADVERTENCIAS_PADRAO
    frase_game_over: str = ""
    reescrita_cnv: str = ""
    inicio: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ------------------------------------------------------------------
    # Construção
    # ------------------------------------------------------------------
    @classmethod
    def nova(cls, caso: Caso, semente: int | None = None) -> "EstadoPartida":
        dif = caso.dificuldade
        barras = dif["barras_iniciais"]
        est = cls(
            caso=caso,
            credibilidade=barras["credibilidade_auditor"],
            resistencia=barras["resistencia_gestor"],
            hostilidade=dif["hostilidade_inicial"],
            rodadas_max=dif["rodadas"],
            tentativas_por_objecao=dif.get("tentativas_por_objecao", TENTATIVAS_POR_OBJECAO),
            advertencias_limite=caso.conduta.get(
                "advertencias_para_game_over", ADVERTENCIAS_PADRAO
            ),
        )
        est.status_objecoes = {o["id"]: {1: None, 2: None} for o in caso.objecoes_ativas()}
        est.ordem_objecoes = _sortear_ordem(caso, semente)
        est.objecao_atual = est._proxima_objecao() or est.ordem_objecoes[0]
        est.camada_atual = 1
        return est

    # ------------------------------------------------------------------
    # Seleção de objeções
    # ------------------------------------------------------------------
    def _encerrada(self, oid: str) -> bool:
        """Encerrada = a camada 2 já tem desfecho, resolvido ou não.

        Uma objeção esgotada (o auditor tentou e não resolveu) também sai de
        cena: senão ela é reescolhida indefinidamente e a partida trava.
        """
        return self.status_objecoes[oid][2] is not None

    def _abertas(self) -> list[str]:
        return [oid for oid in self.ordem_objecoes if not self._encerrada(oid)]

    def _proxima_objecao(self) -> str | None:
        """Primeira objeção aberta, na ordem sorteada, cuja hostilidade permite."""
        abertas = self._abertas()
        for oid in abertas:
            if self.caso.objecao(oid).get("hostilidade_minima", 0) <= self.hostilidade:
                return oid
        # nenhuma liberada no nível atual de hostilidade: mantém a ordem
        return abertas[0] if abertas else None

    def _tentativas_na_objecao(self) -> int:
        """Tentativas FRUSTRADAS nesta objeção, somando as duas camadas.

        Uma rodada que resolveu a camada não consome orçamento: quem acerta
        rápido não pode acabar com menos chances do que quem erra devagar.
        """
        return sum(
            1 for t in self.historico
            if t.objecao_id == self.objecao_atual and t.classificacao != "resolvida"
        )

    def objecao_corrente(self) -> dict:
        return self.caso.objecao(self.objecao_atual)

    def camada_corrente(self) -> dict:
        o = self.objecao_corrente()
        chave = f"camada_{self.camada_atual}"
        return o.get(chave, o.get("camada_1", {}))

    # ------------------------------------------------------------------
    # Aplicação do resultado de um turno
    # ------------------------------------------------------------------
    def aplicar_avaliacao(
        self,
        fala_gestor: str,
        resposta_auditor: str,
        avaliacao: dict[str, Any],
    ) -> Turno:
        """Converte a saída do juiz em movimento de barras e avança o jogo."""
        obj = self.objecao_corrente()
        classificacao: Classificacao = avaliacao.get("classificacao", "parcial")
        if classificacao not in ("resolvida", "parcial", "ignorada"):
            classificacao = "parcial"

        # Falha do juiz não pode punir nem premiar o jogador: placar parado.
        falhou = bool(avaliacao.get("erro"))

        efeito = {} if falhou else obj.get("efeito", {}).get(classificacao, {})
        d_cred = int(efeito.get("credibilidade", 0))
        d_resi = int(efeito.get("resistencia", 0))
        d_host = int(efeito.get("hostilidade", 0))

        # Bônus/ônus por qualidade da argumentação (independe da objeção).
        # Antes: erro custava -8 e acerto rendia +3. Dois acertos não pagavam
        # um erro, e uma partida bem jogada terminava com credibilidade baixa.
        nota = None if falhou else avaliacao.get("nota_geral")
        if isinstance(nota, (int, float)):
            if nota >= 4.5:
                d_cred += 6
            elif nota >= 3.5:
                d_cred += 4
            elif nota >= 3.0:
                d_cred += 1
            elif nota < 2.0:
                d_cred -= 4
                d_host += 1
            elif nota < 2.5:
                d_cred -= 2

            # Argumento forte também convence: liga as duas barras, que antes
            # contavam histórias diferentes (credibilidade 100, resistência 33).
            if nota >= 4.0:
                d_resi -= 3
            elif nota >= 3.0:
                d_resi -= 1

        # Retorno decrescente perto do teto: sem isto a credibilidade batia 100
        # na sexta rodada e a barra parava de informar.
        if d_cred > 0 and self.credibilidade >= 80:
            d_cred = max(1, d_cred // 2)

        # Comunicação muito baixa esquenta o gestor mesmo sem grosseria.
        notas = avaliacao.get("notas", {}) or {}
        com = notas.get("comunicacao")
        if isinstance(com, (int, float)) and com <= 1:
            d_host += 1
        # Reconhecer o esforço da área desarma.
        if isinstance(com, (int, float)) and com >= 4 and self.hostilidade > 0:
            d_host -= 1

        # Tetos por rodada: as penalidades se somavam (classificação + nota baixa
        # + comunicação) e uma resposta curta levava punição de resposta errada.
        d_cred = max(d_cred, -PENALIDADE_MAXIMA_RODADA)
        d_host = max(-1, min(1, d_host))

        # Tom acusatório repetido tem consequência: sem isso, "atenção ao tom"
        # é um tapinha que o jogador pode ignorar a partida inteira.
        if not falhou and avaliacao.get("conduta") == "atencao":
            self.advertencias += 1
            if self.advertencias >= 2:
                d_host += 1
                d_cred -= 2

        antes = (self.credibilidade, self.resistencia, self.hostilidade)
        self.credibilidade = _limita(self.credibilidade + d_cred, 0, 100)
        self.resistencia = _limita(self.resistencia + d_resi, 0, 100)
        self.hostilidade = _limita(self.hostilidade + d_host, 0, 5)

        turno = Turno(
            numero=self.rodada,
            fala_gestor=fala_gestor,
            resposta_auditor=resposta_auditor,
            objecao_id=self.objecao_atual,
            camada=self.camada_atual,
            classificacao=None if falhou else classificacao,
            notas=notas,
            nota_geral=nota if isinstance(nota, (int, float)) else None,
            comentario=avaliacao.get("comentario_curto", ""),
            delta_credibilidade=self.credibilidade - antes[0],
            delta_resistencia=self.resistencia - antes[1],
            delta_hostilidade=self.hostilidade - antes[2],
            conduta=avaliacao.get("conduta", "ok"),
        )
        self.historico.append(turno)

        # Avanço da objeção / camada. Se o juiz falhou, o gestor insiste.
        if falhou:
            self.rodada += 1
            self._checar_fim()
            return turno

        self.status_objecoes[self.objecao_atual][self.camada_atual] = classificacao

        # Parcial ou ignorada faz o gestor insistir — mas só até certo ponto.
        esgotou = (
            classificacao != "resolvida"
            and self._tentativas_na_objecao() >= self.tentativas_por_objecao
        )

        if esgotou:
            # Acabaram as tentativas: registra o desempenho e o gestor segue
            # adiante, em vez de insistir no mesmo assunto até o fim da partida.
            self.status_objecoes[self.objecao_atual][2] = (
                self.status_objecoes[self.objecao_atual][2] or classificacao
            )
            turno.objecao_esgotada = self.objecao_atual
            prox = self._proxima_objecao()
            if prox and prox != self.objecao_atual:
                self.objecao_atual = prox
                self.camada_atual = 1
        elif classificacao == "resolvida":
            if self.camada_atual == 1 and "camada_2" in obj:
                self.camada_atual = 2          # gestor volta por outro ângulo
            else:
                self.status_objecoes[self.objecao_atual][2] = "resolvida"
                turno.objecao_encerrada = self.objecao_atual
                prox = self._proxima_objecao()
                if prox and prox != self.objecao_atual:
                    self.objecao_atual = prox
                    self.camada_atual = 1

        self.rodada += 1
        self._checar_fim()
        return turno

    def todas_objecoes_encerradas(self) -> bool:
        return all(self._encerrada(oid) for oid in self.status_objecoes)

    def _checar_fim(self) -> None:
        if self.credibilidade <= 0:
            # Sem fundo, a partida virava oito rodadas de punição sem saída.
            self.game_over = True
            self.motivo_fim = "credibilidade"
        elif self.resistencia <= 0:
            self.game_over = True
            self.motivo_fim = "aceite"
        elif self.todas_objecoes_encerradas():
            # O gestor ficou sem argumentos: não faz sentido arrastar rodadas.
            self.game_over = True
            self.motivo_fim = "sem_objecoes"
        elif self.rodada > self.rodadas_max:
            self.game_over = True
            self.motivo_fim = "rodadas"

    def encerrar_por_conduta(self, frase: str, reescrita: str = "") -> None:
        self.game_over = True
        self.motivo_fim = "conduta"
        self.frase_game_over = frase
        self.reescrita_cnv = reescrita

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------
    def desfecho(self) -> str:
        if self.motivo_fim == "conduta":
            return "Convocação do RH"
        if self.motivo_fim == "credibilidade":
            return "Reunião suspensa pelo gestor"
        if self.motivo_fim == "sem_objecoes" and self.resistencia > 20:
            return "Aceite com ressalvas"
        if self.resistencia <= 20:
            return "Aceite pleno"
        if self.resistencia <= 45:
            return "Aceite com ressalvas"
        return "Achado não aceito (vai para instância superior)"

    def medias_dimensoes(self) -> dict[str, float | None]:
        """Média de cada dimensão ao longo da partida, ignorando 'na'."""
        out: dict[str, float | None] = {}
        for dim in DIMENSOES:
            vals = [
                t.notas[dim]
                for t in self.historico
                if isinstance(t.notas.get(dim), (int, float))
            ]
            out[dim] = round(sum(vals) / len(vals), 1) if vals else None
        return out

    def nota_media_geral(self) -> float | None:
        vals = [t.nota_geral for t in self.historico if t.nota_geral is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    def duracao_segundos(self) -> int:
        return int((datetime.now(timezone.utc) - self.inicio).total_seconds())

    def resumo_estado_para_prompt(self) -> str:
        """Resumo curto do estado, enviado ao LLM no lugar do histórico inteiro."""
        tratadas = [
            f"{oid} camada {cam} = {cls}"
            for oid, st in self.status_objecoes.items()
            for cam, cls in st.items()
            if cls
        ]
        return (
            f"Rodada {self.rodada} de {self.rodadas_max}. "
            f"Sua resistência está em {self.resistencia}/100 "
            f"(quanto menor, mais perto de aceitar). "
            f"Sua hostilidade está em {self.hostilidade}/5. "
            f"Objeções já tratadas: {'; '.join(tratadas) if tratadas else 'nenhuma'}."
        )


def _limita(v: int, menor: int, maior: int) -> int:
    return max(menor, min(maior, v))


def _sortear_ordem(caso: Caso, semente: int | None = None) -> list[str]:
    """Sorteia a ordem das objeções da partida.

    A primeira sai do grupo marcado com `pode_abrir: true` no YAML, porque uma
    reunião real não começa com o gestor negociando a criticidade. As demais
    vêm embaralhadas. Assim a partida varia sem perder verossimilhança.
    """
    rnd = random.Random(semente)
    ativas = [o["id"] for o in caso.objecoes_ativas()]
    if not caso.dificuldade.get("ordem_sorteada", False) or len(ativas) < 2:
        return ativas

    aberturas = [i for i in ativas if caso.objecao(i).get("pode_abrir", False)]
    if not aberturas:                       # nenhuma marcada: embaralha tudo
        resto = ativas[:]
        rnd.shuffle(resto)
        return resto

    primeira = rnd.choice(aberturas)
    resto = [i for i in ativas if i != primeira]
    rnd.shuffle(resto)
    return [primeira, *resto]
