"""Cliente Groq compartilhado pelo gestor e pelo juiz.

Os IDs de modelo da Groq mudam com o tempo. Se uma chamada falhar com
"model not found", confira os modelos disponíveis no console da Groq
(https://console.groq.com) e ajuste as constantes abaixo.
"""

from __future__ import annotations

import json
import os
import re

from groq import Groq

# Carrega o .env da raiz do projeto, se existir. Opcional: se o python-dotenv
# não estiver instalado, o app continua funcionando com secrets.toml ou com a
# variável de ambiente exportada manualmente.
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_ENV = RAIZ / ".env"
DOTENV_DISPONIVEL = True

try:
    from dotenv import load_dotenv

    load_dotenv(CAMINHO_ENV)
except ImportError:
    DOTENV_DISPONIVEL = False

# Modelo maior para a persona (precisa de nuance e tom).
MODELO_GESTOR = os.getenv("MODELO_GESTOR", "openai/gpt-oss-120b")
# Modelo menor e mais barato para o juiz (tarefa estruturada).
MODELO_JUIZ = os.getenv("MODELO_JUIZ", "openai/gpt-oss-20b")
# Os Llama 3.x saíram da Groq em 16/08/2026. Para ver o que a SUA conta tem:
#   python verificar.py --modelos

_cliente: Groq | None = None


def cliente() -> Groq:
    """Cria o cliente uma vez.

    Ordem de busca da chave:
      1. variável de ambiente GROQ_API_KEY (inclui o que veio do .env)
      2. .streamlit/secrets.toml  -> usado no Streamlit Community Cloud
    """
    global _cliente
    if _cliente is None:
        chave = os.getenv("GROQ_API_KEY")
        if not chave:
            try:  # só importa streamlit se estiver rodando dentro dele
                import streamlit as st

                chave = st.secrets.get("GROQ_API_KEY")
            except Exception:
                chave = None
        if not chave:
            raise RuntimeError(diagnostico())
        _cliente = Groq(api_key=chave)
    return _cliente


def diagnostico() -> str:
    """Mensagem de erro que diz ONDE o app procurou e o que encontrou."""
    linhas = ["GROQ_API_KEY não encontrada. Verifique:", ""]

    if not DOTENV_DISPONIVEL:
        linhas.append(
            "  ❌ A biblioteca python-dotenv NÃO está instalada, então o arquivo "
            ".env é ignorado. Rode: pip install -r requirements.txt"
        )
    else:
        linhas.append("  ✅ python-dotenv instalado.")

    if CAMINHO_ENV.exists():
        texto = CAMINHO_ENV.read_text(encoding="utf-8", errors="ignore")
        tem_chave = any(
            ln.strip().startswith("GROQ_API_KEY") and not ln.strip().startswith("#")
            for ln in texto.splitlines()
        )
        if tem_chave:
            linhas.append(
                f"  ⚠️ {CAMINHO_ENV} existe e tem a linha GROQ_API_KEY, mas o valor "
                "não foi lido. Confira se não há aspas, espaços antes do '=' ou se "
                "a linha ainda está comentada com '#'."
            )
        else:
            linhas.append(
                f"  ❌ {CAMINHO_ENV} existe, mas não tem uma linha GROQ_API_KEY ativa."
            )
    else:
        vizinhos = sorted(p.name for p in RAIZ.glob(".env*"))
        linhas.append(f"  ❌ O arquivo {CAMINHO_ENV} NÃO existe.")
        if vizinhos:
            linhas.append(
                f"     Arquivos parecidos encontrados: {', '.join(vizinhos)}. "
                "No Windows, o Bloco de Notas costuma salvar como '.env.txt' — "
                "o nome tem de ser exatamente '.env'."
            )

    linhas += [
        "",
        "  Alternativa: .streamlit/secrets.toml com  GROQ_API_KEY = \"gsk_...\"",
        "  Depois de criar ou corrigir o arquivo, PARE e reinicie o streamlit.",
    ]
    return "\n".join(linhas)


def conversa(
    system: str,
    mensagens: list[dict[str, str]],
    modelo: str = MODELO_GESTOR,
    temperatura: float = 0.8,
    max_tokens: int = 1200,
) -> str:
    """Chamada de texto livre (usada pelo gestor).

    max_tokens é generoso de propósito: nos modelos de raciocínio (gpt-oss),
    o raciocínio consome do mesmo orçamento, e um limite apertado corta a
    resposta no meio. O tamanho real da fala é controlado pelo prompt.
    """
    resp = cliente().chat.completions.create(
        **_com_raciocinio_baixo(
            dict(
                model=modelo,
                messages=[{"role": "system", "content": system}, *mensagens],
                temperature=temperatura,
                max_tokens=max_tokens,
            )
        )
    )
    return _limpa_raciocinio((resp.choices[0].message.content or "").strip())


def _com_raciocinio_baixo(kwargs: dict) -> dict:
    """Reduz o raciocínio nos modelos que suportam, para sobrar token e tempo.

    Só é aplicado quando o ID do modelo indica suporte; nos demais, a Groq
    rejeitaria o parâmetro.
    """
    if "gpt-oss" in kwargs.get("model", ""):
        kwargs["reasoning_effort"] = "low"
    return kwargs


def _limpa_raciocinio(texto: str) -> str:
    """Remove blocos de raciocínio que alguns modelos deixam na resposta.

    Os gpt-oss normalmente devolvem o raciocínio num campo separado, mas em
    algumas respostas ele vaza como <think>...</think>. O gestor não pode
    mostrar isso ao jogador.
    """
    texto = re.sub(r"<think>.*?</think>", "", texto, flags=re.DOTALL | re.IGNORECASE)
    texto = re.sub(r"<\|?channel\|?>.*?<\|?message\|?>", "", texto, flags=re.DOTALL)
    return texto.strip()


def modelos_disponiveis() -> list[str]:
    """IDs de modelo que esta chave consegue usar. Útil quando um ID some."""
    return sorted(m.id for m in cliente().models.list().data)


def json_estruturado(
    system: str,
    usuario: str,
    modelo: str = MODELO_JUIZ,
    temperatura: float = 0.2,
    max_tokens: int = 2000,
) -> dict:
    """Chamada que precisa voltar JSON (usada pelo juiz).

    max_tokens alto porque o raciocínio dos gpt-oss sai do mesmo orçamento:
    com pouco espaço, o JSON vem cortado no meio.
    """
    kwargs = _com_raciocinio_baixo(
        dict(
            model=modelo,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": usuario},
            ],
            temperature=temperatura,
            max_tokens=max_tokens,
        )
    )
    try:
        resp = cliente().chat.completions.create(
            **kwargs, response_format={"type": "json_object"}
        )
    except Exception:
        resp = cliente().chat.completions.create(**kwargs)

    escolha = resp.choices[0]
    bruto = (escolha.message.content or "").strip()
    truncado = getattr(escolha, "finish_reason", "") == "length"
    return _extrai_json(bruto, truncado)


def _extrai_json(texto: str, truncado: bool = False) -> dict:
    texto = _limpa_raciocinio(texto)
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass

    m = re.search(r"\{.*\}", texto, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    reparado = _repara_json(texto)
    if reparado is not None:
        return reparado

    motivo = "a resposta foi cortada por limite de tokens" if truncado else "formato inesperado"
    raise ValueError(f"JSON inválido do juiz ({motivo}): {texto[:200]}")


def _repara_json(texto: str) -> dict | None:
    """Tenta fechar um JSON truncado: string aberta, chaves e colchetes.

    Serve para aproveitar uma avaliação quase completa em vez de descartá-la.
    """
    inicio = texto.find("{")
    if inicio == -1:
        return None
    s = texto[inicio:]

    # 1ª tentativa: fechar o que ficou aberto no fim.
    tentativa = _fechar(s)
    if tentativa is not None:
        return tentativa

    # 2ª tentativa: descartar o par chave/valor incompleto do fim, recuando
    # vírgula a vírgula até achar um ponto onde o JSON feche válido.
    for corte in reversed(_virgulas_fora_de_string(s)):
        tentativa = _fechar(s[:corte])
        if tentativa is not None:
            return tentativa
    return None


def _estado_sintatico(s: str) -> tuple[bool, list[str]]:
    """Devolve (está dentro de string?, pilha de { e [ abertos)."""
    em_string = False
    escapado = False
    pilha: list[str] = []
    for ch in s:
        if escapado:
            escapado = False
        elif ch == "\\":
            escapado = True
        elif ch == '"':
            em_string = not em_string
        elif not em_string:
            if ch in "{[":
                pilha.append(ch)
            elif ch in "}]" and pilha:
                pilha.pop()
    return em_string, pilha


def _fechar(s: str) -> dict | None:
    em_string, pilha = _estado_sintatico(s)
    candidato = s + ('"' if em_string else "")
    candidato += "".join("}" if a == "{" else "]" for a in reversed(pilha))
    try:
        valor = json.loads(candidato)
        return valor if isinstance(valor, dict) else None
    except json.JSONDecodeError:
        return None


def _virgulas_fora_de_string(s: str) -> list[int]:
    posicoes, em_string, escapado = [], False, False
    for i, ch in enumerate(s):
        if escapado:
            escapado = False
        elif ch == "\\":
            escapado = True
        elif ch == '"':
            em_string = not em_string
        elif ch == "," and not em_string:
            posicoes.append(i)
    return posicoes
