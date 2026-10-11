"""Diagnóstico de ambiente.

    python verificar.py              confere dependências, .env, chave e conexão
    python verificar.py --modelos    lista os modelos que a SUA chave pode usar
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ok = True

if "--modelos" in sys.argv:
    sys.path.insert(0, str(RAIZ))
    from engine import llm

    print("\nModelos disponíveis para esta chave:\n")
    try:
        for m in llm.modelos_disponiveis():
            print("  " + m)
    except Exception as e:
        print(f"  Falha ao consultar: {e}")
        sys.exit(1)
    print(
        f"\nEm uso agora:\n  gestor = {llm.MODELO_GESTOR}\n  juiz   = {llm.MODELO_JUIZ}"
        "\n\nPara trocar, acrescente ao .env:"
        "\n  MODELO_GESTOR=<id da lista>\n  MODELO_JUIZ=<id da lista>\n"
    )
    sys.exit(0)


def item(certo: bool, texto: str) -> None:
    global ok
    print(f"  {'OK  ' if certo else 'ERRO'}  {texto}")
    if not certo:
        ok = False


print("\n=== 1. Dependências ===")
for pacote, modulo in [
    ("streamlit", "streamlit"),
    ("groq", "groq"),
    ("PyYAML", "yaml"),
    ("python-dotenv", "dotenv"),
]:
    try:
        __import__(modulo)
        item(True, pacote)
    except ImportError:
        item(False, f"{pacote} não instalado  ->  pip install -r requirements.txt")

print("\n=== 2. Arquivo .env ===")
env = RAIZ / ".env"
if env.exists():
    item(True, f"{env} existe")
    linhas = [
        ln for ln in env.read_text(encoding="utf-8", errors="ignore").splitlines()
        if ln.strip().startswith("GROQ_API_KEY")
    ]
    if not linhas:
        item(False, "nenhuma linha GROQ_API_KEY no arquivo")
    else:
        bruto = linhas[0]
        valor = bruto.split("=", 1)[1].strip() if "=" in bruto else ""
        limpo = valor.strip("\"'")          # compara sem as aspas
        item(not bruto.lstrip().startswith("#"), "a linha não está comentada com '#'")
        item(bool(limpo), "a linha tem um valor depois do '='")
        item(
            valor == limpo,
            "o valor está SEM aspas (no .env não se usa aspas)",
        )
        item(limpo != "gsk_sua_chave_aqui", "o valor foi trocado pela sua chave real")
        item(limpo.startswith("gsk_"), "a chave começa com 'gsk_'")
else:
    item(False, f"{env} NÃO existe  ->  copie o .env.example para .env")
    parecidos = sorted(p.name for p in RAIZ.glob(".env*"))
    if parecidos:
        print(f"        arquivos parecidos na pasta: {', '.join(parecidos)}")
        print("        atenção: o nome tem de ser exatamente '.env', sem '.txt'")

print("\n=== 3. Chave carregada pelo app ===")
sys.path.insert(0, str(RAIZ))
try:
    from engine import llm

    import os

    chave = os.getenv("GROQ_API_KEY")
    if chave:
        item(True, f"chave lida: {chave[:7]}...{chave[-4:]} ({len(chave)} caracteres)")
    else:
        secrets = RAIZ / ".streamlit" / "secrets.toml"
        item(False, "nenhuma chave no ambiente")
        print(f"        secrets.toml existe? {'sim' if secrets.exists() else 'não'}")
except Exception as e:
    item(False, f"falha ao importar a engine: {e}")

print("\n=== 4. Conexão com a Groq ===")
try:
    from engine import llm

    resp = llm.conversa(
        system="Responda apenas: ok",
        mensagens=[{"role": "user", "content": "teste"}],
        max_tokens=10,
    )
    item(True, f"modelo {llm.MODELO_GESTOR} respondeu: {resp[:40]!r}")
except Exception as e:
    msg = str(e)
    item(False, msg.splitlines()[0] if msg else "falha desconhecida")
    if "model" in msg.lower() and "not" in msg.lower():
        print("        o ID do modelo mudou. Veja os disponíveis em console.groq.com")
        print("        e ajuste MODELO_GESTOR / MODELO_JUIZ no .env")
    elif "401" in msg or "invalid" in msg.lower():
        print("        a chave foi lida, mas a Groq a recusou. Gere outra no console.")

print("\n" + ("Tudo certo. Rode: streamlit run app.py" if ok else "Corrija os itens marcados com ERRO acima."))
