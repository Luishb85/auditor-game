"""Carregamento dos prompts versionados em prompts/."""

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


@lru_cache(maxsize=None)
def carregar(nome: str) -> str:
    """Lê prompts/<nome>.txt. Em cache: o arquivo não muda durante a partida."""
    return (PROMPTS_DIR / f"{nome}.txt").read_text(encoding="utf-8")
