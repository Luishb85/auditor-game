# 🛡️ Jogo do Auditor

Treino de defesa de achados de auditoria contra um gestor hostil simulado por IA.
O jogador é o auditor; o gestor é interpretado por um LLM (Groq); um segundo LLM,
independente, avalia cada jogada.

Baseado na metodologia **Achado Blindado**.

---

## Estrutura de pastas

```
auditor-game/
├── app.py                      # interface Streamlit (só UI e estado da sessão)
├── verificar.py                # diagnóstico de ambiente e lista de modelos
├── requirements.txt
├── README.md
├── .gitignore
├── .env.example                # modelo — copie para .env (chave da Groq)
├── .streamlit/
│   ├── config.toml             # tema
│   └── secrets.toml.example    # modelo — copie para secrets.toml
├── engine/
│   ├── __init__.py
│   ├── caso.py                 # carrega o YAML e controla o que cada papel vê
│   ├── estado.py               # barras, rodadas, objeções (fonte da verdade)
│   ├── llm.py                  # cliente Groq
│   ├── gestor.py               # persona (texto livre)
│   ├── juiz.py                 # avaliador (JSON)
│   ├── conduta.py              # filtro local de grosseria
│   ├── prompts.py              # carrega os prompts
│   └── relatorio.py            # exportação CSV
├── prompts/
│   ├── gestor.txt
│   ├── juiz.txt
│   └── reescrita_cnv.txt
└── cases/
    └── caso_01_parametro_bloqueio.yaml
```

A regra de ouro: **o LLM nunca mexe no placar.** O juiz avalia, o gestor interpreta,
e quem move as barras é o `estado.py`. Isso mantém o jogo previsível e auditável.

---

## Como rodar localmente

1. **Crie o ambiente e instale as dependências**

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

2. **Configure a chave da Groq**

Pegue uma chave gratuita em <https://console.groq.com>. Há duas formas; a
primeira é a mais prática para desenvolver.

**Opção A — `.env` (recomendada para rodar localmente)**

```bash
cp .env.example .env
```

Edite o `.env` e coloque a sua chave:

```
GROQ_API_KEY=gsk_sua_chave_aqui
```

**Opção B — `secrets.toml` (mesma que o Streamlit Cloud usa)**

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

A ordem de busca é: variável de ambiente (inclui o que vem do `.env`) e depois
`st.secrets`. Os dois arquivos estão no `.gitignore` e **nunca** devem ir para o
GitHub.

3. **Rode**

```bash
streamlit run app.py
```

Abre em <http://localhost:8501>.

---

## Publicar no Streamlit Community Cloud

1. Suba o projeto para um repositório no GitHub (sem o `secrets.toml`).
2. Em <https://share.streamlit.io>, conecte o repositório e aponte para `app.py`.
3. Em **Settings → Secrets**, cole:

```toml
GROQ_API_KEY = "gsk_sua_chave"
```

O app é público para quem tiver o link. Se precisar restringir, o caminho mais
simples é uma senha única em `st.secrets` conferida na abertura.

---

## Modelos da Groq

Os IDs de modelo mudam com o tempo. Os padrões estão em `engine/llm.py`:

| Papel | Padrão | Por quê |
|---|---|---|
| Gestor | `openai/gpt-oss-120b` | precisa de nuance e tom |
| Juiz | `openai/gpt-oss-20b` | tarefa estruturada, mais barata e rápida |

Os IDs mudam com frequência: os Llama 3.x foram desligados na Groq em
**16/08/2026**. Se aparecer `model_not_found`, veja o que a sua chave pode usar:

```bash
python verificar.py --modelos
```

e ajuste pelo `.env`, sem mexer no código:

```
MODELO_GESTOR=outro-modelo
MODELO_JUIZ=outro-modelo
```

**Atenção ao plano gratuito:** são **2 chamadas por turno** (gestor + juiz).
Confira os limites de requisições por minuto e por dia no console antes de
convidar várias pessoas a jogar ao mesmo tempo.

---

## Como criar um caso novo

Copie `cases/caso_01_parametro_bloqueio.yaml`, mude o `id` e preencha. As seções
obrigatórias são:

| Seção | O que é |
|---|---|
| `matriz` | o achado (critério, condição, causa, efeito, recomendação) |
| `numeros_chave` | o que aparece no painel lateral durante a partida |
| `dificuldade` | hostilidade inicial, objeções ativas, rodadas, barras iniciais |
| `gestor` | persona, bordão, gatilhos que sobem e descem a hostilidade |
| `objecoes` | banco de objeções, cada uma com camada 1 e camada 2 |
| `camada_defesa` | **gabarito** — só o juiz vê; aparece no debriefing |
| `rubrica` | as 6 dimensões de avaliação |
| `conduta` | o que encerra a partida |

O arquivo aparece sozinho em `Caso.listar()`. Para trocar o caso ativo, mude
`CASO_PADRAO` no topo do `app.py`.

**Dificuldade é configuração, não conteúdo.** Para gerar um nível fácil ou difícil
do mesmo caso, basta mudar `dificuldade` e a lista `objecoes_ativas`.

---

## Mecânica

**Barras.** Credibilidade do auditor (0-100), resistência do gestor (0-100) e
hostilidade (0-5). A partida termina quando a resistência zera, quando as objeções
se esgotam ou ao fim das rodadas.

**Objeções em duas camadas.** Resolvida a camada 1, o gestor volta pelo mesmo tema
com um ângulo novo antes de ceder. Se a resposta foi parcial ou ignorada, ele
insiste na mesma camada.

**Portão de conduta.** Duas camadas: filtro local de palavras (`conduta.py`,
sem custo de API) e o juiz, para o que é sutil. Violação encerra a partida com a
tela "Convocação do RH", que mostra a frase e uma reescrita em CNV. Tom acusatório
leve não encerra: custa nota em Comunicação.

**Rubrica.** Seis dimensões: evidência, critério, causa-efeito, diagnóstico da
objeção, comunicação (CNV) e foco no fato. Por jogada o jogador vê a nota geral
(1 a 5) e a variação das barras; as dimensões aparecem como desempenho global no fim.

---

## Relatório

Ao final da partida, um CSV com uma linha por turno. As colunas já seguem o
desenho das futuras tabelas do banco (`partidas`, `turnos`), então a migração
para Supabase é trocar "gerar linha" por "gravar linha".

Separador `;` e encoding UTF-8 com BOM, para abrir direto no Excel em português
e ingerir no Power BI.

---

## Roadmap

| Fase | Situação |
|---|---|
| 0. Desenho (caso, rubrica, objeções, partida de teste) | concluída |
| 1. Loop mínimo (Streamlit + Groq, gestor + juiz, placar) | **esta versão** |
| 2. Jogo completo (abas, painel, game over, debriefing, CSV) | **esta versão** |
| 3. Publicação no Streamlit Community Cloud | próxima |
| 4. Banco de dados (Supabase), telemetria e ranking | futura |

Evolução prevista: níveis fácil e difícil sobre o mesmo caso, casos 2 e 3
(Exemplos 1 e 3 do Achado Blindado), memória do LLM entre partidas, trilha de
auditoria de sistemas, RAG vetorial se surgir biblioteca grande de normas, e
migração para Flask.

---

Todos os casos usam dados fictícios.
