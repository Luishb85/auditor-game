"""Jogo do Auditor — treino de defesa de achados contra um gestor hostil.

Rodar:  streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

from engine import DIMENSOES, ROTULO_DIMENSAO, Caso, EstadoPartida
from engine import conduta as mod_conduta
from engine import gestor as mod_gestor
from engine import juiz as mod_juiz
from engine import relatorio as mod_relatorio

CASO_PADRAO = "caso_01_parametro_bloqueio.yaml"

st.set_page_config(page_title="Jogo do Auditor", page_icon="🛡️", layout="wide")


# ======================================================================
# Estado da sessão
# ======================================================================
def iniciar_partida(nome_arquivo: str = CASO_PADRAO) -> None:
    caso = Caso.carregar(nome_arquivo)
    # Descarta os CSVs em cache da partida anterior.
    for k in [k for k in st.session_state if str(k).startswith("csv::")]:
        del st.session_state[k]
    st.session_state.estado = EstadoPartida.nova(caso)
    st.session_state.erro = None
    st.session_state.aguardando_abertura = True


if "estado" not in st.session_state:
    iniciar_partida()

estado: EstadoPartida = st.session_state.estado
caso = estado.caso


# ======================================================================
# Turno
# ======================================================================
def abrir_reuniao() -> None:
    """Primeira fala do gestor."""
    try:
        estado.fala_pendente = mod_gestor.falar(estado)
    except Exception as e:
        st.session_state.erro = str(e)
    st.session_state.aguardando_abertura = False


def jogar(resposta: str) -> None:
    """Um turno completo: conduta → juiz → placar → próxima fala do gestor."""
    fala = estado.fala_pendente

    # Camada 1 do portão de conduta: filtro local, sem gastar chamada.
    termo = mod_conduta.violacao_evidente(resposta)
    if termo:
        estado.historico.append(
            _turno_vazio(estado, fala, resposta, f"Termo inaceitável: “{termo}”.")
        )
        estado.encerrar_por_conduta(resposta, mod_juiz.reescrever_em_cnv(resposta, estado))
        return

    # Camada 2: o juiz avalia e também julga o tom.
    try:
        avaliacao = mod_juiz.avaliar(estado, fala, resposta)
    except Exception as e:
        st.session_state.erro = str(e)
        return

    if avaliacao["conduta"] == "violacao":
        estado.historico.append(
            _turno_vazio(estado, fala, resposta, avaliacao["comentario_curto"])
        )
        estado.encerrar_por_conduta(resposta, mod_juiz.reescrever_em_cnv(resposta, estado))
        return

    estado.aplicar_avaliacao(fala, resposta, avaliacao)

    # Advertências de tom acumuladas também encerram a reunião.
    if (
        not estado.game_over
        and estado.advertencias_limite
        and estado.advertencias >= estado.advertencias_limite
    ):
        estado.encerrar_por_conduta(resposta, mod_juiz.reescrever_em_cnv(resposta, estado))
        estado.motivo_fim = "advertencias"
        return

    if not estado.game_over:
        try:
            estado.fala_pendente = mod_gestor.falar(estado)
        except Exception as e:
            st.session_state.erro = str(e)


def _turno_vazio(est, fala, resposta, comentario):
    from engine.estado import Turno

    return Turno(
        numero=est.rodada, fala_gestor=fala, resposta_auditor=resposta,
        objecao_id=est.objecao_atual, camada=est.camada_atual,
        classificacao=None, notas={}, nota_geral=None, comentario=comentario,
        delta_credibilidade=0, delta_resistencia=0, delta_hostilidade=0,
        conduta="violacao",
    )


# ======================================================================
# Painel lateral
# ======================================================================
def barra(rotulo: str, valor: int, maximo: int = 100) -> None:
    st.caption(f"{rotulo} · **{valor}**")
    st.progress(valor / maximo)


with st.sidebar:
    b = caso.briefing_auditor()

    # O placar vem primeiro: é o que o jogador consulta a cada jogada.
    st.markdown("### 📊 Placar")
    barra("Credibilidade do auditor", estado.credibilidade)
    barra("Resistência do gestor", estado.resistencia)
    st.caption(f"Hostilidade · **{estado.hostilidade}/5**")
    st.progress(estado.hostilidade / 5)
    jogadas = len(estado.historico)
    if estado.game_over:
        st.caption(f"Partida encerrada · **{jogadas}** rodadas jogadas")
    else:
        st.caption(
            f"Rodada **{min(jogadas + 1, estado.rodadas_max)}** de {estado.rodadas_max}"
            f" · {jogadas} jogada{'s' if jogadas != 1 else ''} avaliada"
            f"{'s' if jogadas != 1 else ''}"
        )
    if estado.advertencias and estado.advertencias_limite:
        st.caption(f"⚠️ Advertências de tom: **{estado.advertencias}** de {estado.advertencias_limite}")

    st.divider()
    st.markdown("### 🔢 Números-chave")
    for n in b["numeros_chave"]:
        st.markdown(f"- {n}")

    with st.expander("📋 Resumo do achado"):
        st.markdown(f"**Condição.** {b['condicao']}")
        st.markdown(f"**Critério.** {b['criterio']}")
        st.markdown(f"**Causa.** {b['causa']}")
        st.markdown(f"**Recomendação.** {b['recomendacao']}")
        st.caption("Matriz completa e cartas de evidência na aba “O caso”.")

    st.divider()
    st.markdown("### 🎯 Objeções")
    marca = {"resolvida": "✅", "parcial": "🟡", "ignorada": "❌", None: "⬜"}
    for o in caso.objecoes_ativas():
        stt = estado.status_objecoes[o["id"]]
        atual = o["id"] == estado.objecao_atual and not estado.game_over
        c1 = marca[stt[1]]
        c2 = marca[stt[2]] if "camada_2" in o else "—"
        seta = "▸ " if atual else ""
        st.markdown(f"{seta}{c1}{c2} {o['nome']}")
    st.caption("Dois marcadores por objeção: camada 1 e camada 2.")

    st.divider()
    if st.button("🔄 Nova partida", use_container_width=True):
        iniciar_partida()
        st.rerun()


# ======================================================================
# Abas
# ======================================================================
st.title("🛡️ Jogo do Auditor")
st.caption(f"{caso.titulo} · nível {caso.nivel}")

if st.session_state.get("erro"):
    st.error(f"Erro ao falar com a Groq: {st.session_state.erro}")

aba_partida, aba_caso, aba_guia = st.tabs(["🎙️ Partida", "📑 O caso", "🧭 Guia do auditor"])


# ---------------------------------------------------------------- Partida
with aba_partida:
    if st.session_state.get("aguardando_abertura"):
        with st.spinner("O gestor está abrindo a reunião..."):
            abrir_reuniao()
        st.rerun()

    for t in estado.historico:
        if t.fala_gestor:
            with st.chat_message("assistant", avatar="😠"):
                st.write(t.fala_gestor)
        with st.chat_message("user", avatar="🕵️"):
            st.write(t.resposta_auditor)

        if t.conduta == "violacao":
            st.error(f"🚨 Violação de conduta. {t.comentario}")
            continue

        nota = f"{t.nota_geral:.1f}/5" if t.nota_geral is not None else "—"
        estrelas = "⭐" * int(round(t.nota_geral or 0))
        deltas = []
        if t.delta_credibilidade:
            deltas.append(f"Credibilidade {t.delta_credibilidade:+d}")
        if t.delta_resistencia:
            deltas.append(f"Resistência {t.delta_resistencia:+d}")
        if t.delta_hostilidade:
            deltas.append(f"Hostilidade {t.delta_hostilidade:+d}")
        rotulo_cls = {"resolvida": "✅ objeção resolvida",
                      "parcial": "🟡 objeção parcialmente tratada",
                      "ignorada": "❌ objeção ignorada"}.get(t.classificacao, "")
        with st.container(border=True):
            st.caption("🎧 Gerente de Auditoria")
            st.markdown(f"**{estrelas or '—'} {nota}** · {rotulo_cls}")
            if deltas:
                st.caption(" · ".join(deltas))
            if t.comentario:
                st.markdown(f"_{t.comentario}_")
            if t.conduta == "atencao":
                st.warning("⚠️ Atenção ao tom: a resposta soou acusatória.")

        # Objeção encerrada: revela a resposta esperada agora, enquanto o
        # raciocínio ainda está fresco. Não é spoiler — o tema já passou.
        if t.objecao_encerrada:
            o = caso.objecao(t.objecao_encerrada)
            with st.expander(f"📖 Objeção “{o['nome']}” encerrada — a resposta esperada"):
                st.markdown(o["resposta_forte"])
                st.caption(f"O que enfraquece: {o['resposta_fraca']}")

        if t.objecao_esgotada:
            o = caso.objecao(t.objecao_esgotada)
            with st.expander(
                f"⏭️ Tentativas esgotadas em “{o['nome']}” — o gestor seguiu adiante"
            ):
                st.markdown(
                    "O desempenho nesta objeção ficou registrado e a reunião "
                    "avançou. Era este o caminho:"
                )
                st.markdown(o["resposta_forte"])
                st.caption(f"O que enfraquece: {o['resposta_fraca']}")

    # ---- fim de jogo ----
    if estado.game_over:
        st.divider()
        if estado.motivo_fim == "credibilidade":
            st.warning("## 🚪 Reunião suspensa pelo gestor")
            st.markdown(
                "A sua credibilidade na mesa chegou a zero. O gestor pediu para "
                "suspender a reunião e retomar quando a auditoria apresentar os "
                "fatos de forma estruturada. O achado segue registrado, mas a "
                "defesa não se sustentou nesta conversa."
            )
            st.info(
                "Não é derrota definitiva: numa reunião real, isso significa "
                "voltar com o dossiê organizado. No jogo, vale rever o debriefing "
                "abaixo e começar outra partida."
            )
        elif estado.motivo_fim in ("conduta", "advertencias"):
            st.error("## 🚨 Convocação do RH")
            if estado.motivo_fim == "advertencias":
                st.markdown(
                    f"Foram **{estado.advertencias} advertências de tom** na mesma "
                    "reunião. O gestor registrou uma reclamação formal sobre a "
                    "conduta da auditoria."
                )
            else:
                st.markdown(
                    "A reunião foi encerrada. O gestor registrou uma reclamação "
                    "formal sobre a conduta da auditoria."
                )
            st.markdown("**A fala que causou isso:**")
            st.markdown(f"> {estado.frase_game_over}")
            if estado.reescrita_cnv:
                st.markdown("**Como poderia ter sido dito:**")
                st.info(estado.reescrita_cnv)
        else:
            st.success(f"## 🏁 Fim da partida — {estado.desfecho()}")
            c1, c2, c3 = st.columns(3)
            c1.metric("Credibilidade", estado.credibilidade)
            c2.metric("Resistência do gestor", estado.resistencia)
            c3.metric("Nota média", estado.nota_media_geral() or "—")

            st.markdown("### Desempenho por dimensão")
            medias = estado.medias_dimensoes()
            validas = {k: v for k, v in medias.items() if v is not None}
            for d in DIMENSOES:
                v = medias[d]
                st.caption(f"{ROTULO_DIMENSAO[d]} · **{v if v is not None else '—'}**")
                st.progress((v or 0) / 5)
            if validas:
                forte = max(validas, key=validas.get)
                fraca = min(validas, key=validas.get)
                st.markdown(
                    f"**Ponto mais forte:** {ROTULO_DIMENSAO[forte]} ({validas[forte]}) · "
                    f"**A treinar:** {ROTULO_DIMENSAO[fraca]} ({validas[fraca]})"
                )

            st.markdown("### Objeções")
            for o in caso.objecoes_ativas():
                stt = estado.status_objecoes[o["id"]]
                st.markdown(
                    f"- **{o['nome']}** — camada 1: {stt[1] or 'não tratada'}"
                    + (f" · camada 2: {stt[2] or 'não tratada'}" if "camada_2" in o else "")
                )

            with st.expander("📖 Debriefing — a resposta preparada pela metodologia"):
                cd = caso.camada_defesa
                st.markdown("**Postura de resposta esperada**")
                for x in cd["postura_resposta"]:
                    st.markdown(f"- {x}")
                st.markdown("**Erros comuns nesta defesa**")
                for x in cd["erros_comuns_do_auditor"]:
                    st.markdown(f"- {x}")
                st.markdown("**Respostas fortes por objeção**")
                for o in caso.objecoes_ativas():
                    st.markdown(f"- **{o['nome']}:** {o['resposta_forte']}")

        st.divider()
        jogador = st.text_input("Seu nome ou apelido (para o relatório)", value="anonimo")

        # O CSV é gerado UMA vez por apelido e guardado na sessão. Gerar a cada
        # rerun criava um partida_id e um nome de arquivo novos a cada tecla
        # digitada, e o arquivo do botão anterior deixava de existir no servidor
        # ("o ficheiro não estava disponível no site").
        chave = f"csv::{jogador}"
        if chave not in st.session_state:
            st.session_state[chave] = (
                mod_relatorio.gerar_csv(estado, jogador).encode("utf-8-sig"),
                mod_relatorio.nome_arquivo(estado, jogador),
            )
        dados, nome = st.session_state[chave]
        st.download_button(
            "⬇️ Baixar relatório da partida (CSV)",
            data=dados,
            file_name=nome,
            mime="text/csv",
        )

    # ---- turno em andamento ----
    else:
        if estado.fala_pendente:
            with st.chat_message("assistant", avatar="😠"):
                st.write(estado.fala_pendente)

        resposta = st.chat_input("Sua resposta como auditor...")
        if resposta:
            with st.spinner("O gestor está pensando..."):
                jogar(resposta)
            st.rerun()


# ---------------------------------------------------------------- O caso
with aba_caso:
    b = caso.briefing_auditor()
    st.markdown(f"## {b['titulo']}")
    st.info("Todos os dados deste caso são fictícios.")

    st.markdown("### Matriz do achado")
    for rotulo, chave in [
        ("Objeto", "objeto"), ("Objetivo", "objetivo"),
        ("Questão de auditoria", "questao_auditoria"), ("Critério", "criterio"),
        ("Condição", "condicao"), ("Causa", "causa"), ("Efeito", "efeito"),
        ("Boas práticas identificadas", "boas_praticas"),
        ("Recomendação", "recomendacao"),
    ]:
        st.markdown(f"**{rotulo}.** {b[chave]}")

    st.markdown("### Cartas de evidência")
    for e in b["evidencias"]:
        st.markdown(f"- {e}")

    st.markdown("### Com quem você vai falar")
    g = caso.gestor
    st.markdown(f"**{g['nome_ficticio']}** — {g['cargo']}. {g['tom_base']}")


# ---------------------------------------------------------------- Guia
with aba_guia:
    st.markdown("## Guia do auditor")
    st.caption("Boas práticas gerais de defesa de achado. Sem respostas deste caso.")

    st.markdown("""
### Antes de rebater, diagnostique
Nem toda objeção é igual. A **cognitiva** é dúvida real: o gestor não entendeu o
critério ou discorda da leitura do dado — responda com informação. A **defensiva**
protege a imagem da área — reconheça o esforço antes de apresentar a evidência,
ou o dado vira ataque. A **tática de poder** não discute o fato: negocia a nota,
o prazo ou a utilidade do trabalho — recuse o enquadramento sem recusar a pessoa.

### Reconheça antes de evidenciar
Uma frase de reconhecimento do contexto da área, dita antes do dado, derruba a
hostilidade mais do que qualquer argumento técnico. Deixar isso para o fim da
reunião é tarde: a essa altura o gestor já está defendendo território.

### Dado antes de adjetivo
"Isso é grave" não pontua. "O parâmetro está configurado em 25% e a política
determina 10%" pontua. Repetir o achado com mais ênfase não é argumento novo.

### Cuidado com o que o dado sustenta
Uma amostra mostra que o problema **existe**; ela não mede sozinha o tamanho dele
na carteira. Quando a extensão importa, sustente pela causa (o controle que falha
para todos os casos), não por extrapolação estatística que a amostra não suporta.

### Não compre a briga de culpa
Quando o gestor diz "o problema é de outra área", a armadilha é discutir de quem
é a responsabilidade. O achado registra um fato e uma ausência de controle; a
atribuição entre áreas é decisão de governança, para depois da reunião.

### Separe severidade de existência
Negociar o prazo de tratamento é legítimo. Negociar a criticidade sem fato novo
não é. Se a classificação cair sob pressão, o que caiu foi a independência.

### Aceite a ressalva legítima
Se o gestor pede para registrar algo verdadeiro e favorável à área, registre.
Isso não enfraquece o achado: fecha a reunião com a relação preservada.

### Firmeza não é agressão
Tom acusatório custa pontos. Ofensa encerra a partida — e, na vida real, a sua
credibilidade. A estrutura que funciona: **fato → impacto → controle → pedido**.
""")
