"""Engine do Jogo do Auditor.

Divisão de responsabilidades:
  caso.py      carrega o YAML e controla o que cada papel enxerga
  estado.py    barras, rodadas, objeções, histórico (única fonte de verdade)
  llm.py       cliente Groq
  gestor.py    persona (chamada de texto livre)
  juiz.py      avaliador (chamada que retorna JSON)
  conduta.py   filtro local de grosseria, antes de gastar chamada
  relatorio.py exportação CSV da partida
"""

from .caso import Caso
from .estado import DIMENSOES, ROTULO_DIMENSAO, EstadoPartida, Turno

__all__ = ["Caso", "EstadoPartida", "Turno", "DIMENSOES", "ROTULO_DIMENSAO"]
