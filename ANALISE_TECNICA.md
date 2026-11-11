# 🔥 FIRE FORCE — Análise Técnica Completa do Repositório

> **Escopo:** leitura integral de `fireforce_bot.py` (23.034 linhas / 1,08 MB), dos 3 workflows
> de `.github/`, do histórico de 25 PRs e **execução real** do código (import, banco, renderização
> e 81 asserções funcionais). Nenhuma linha do bot foi modificada para produzir este documento.
>
> **Data da análise:** 11/11/2026 • **Versão analisada:** `v13.7` • **Commit base:** `ff20efb`

---

## 1. O QUE É O PROJETO

Bot Discord **monolítico de arquivo único** para gerir uma *Liga Oficial de Diários de Free Fire*.
Não é um bot de moderação genérico: é um **sistema operacional de negócio** que orquestra, no mesmo
processo:

| Domínio | O que faz |
|---|---|
| 🎮 Competição | Painéis de inscrição, 4 modos (Solo 48 / Duo 24 / Trio 16 / Squad 12 = 48 jogadores), filas de espera, repetição diária automática, envio de ID+senha da sala 5 min antes |
| 🆔 Anti-fraude | Consulta de ID Free Fire multi-provedor, Blacklist por UID, nível mínimo, anti-UID duplicado, anti-inscrição de quem está em serviço |
| 💰 Financeiro | Carteira virtual, depósito PIX, saque com fila e reserva protegida, transferência atômica, cupons, comissão por ADM, caixa da org, livro-caixa |
| 🎧 Atendimento | Tickets em 2 filas (suporte/mediador), assumir/reassumir, avaliação com nota → salário, carteira de trabalho semanal, transcrição de canal |
| 🏆 Progressão | 12 patentes (Bronze → Hacker), auto-cargo no Discord, vitórias, winrate, sequência, rankings, eventos com bônus |
| 🖼️ Visual | 3 renderizadores HD em Pillow (Tabela Oficial, Card de Perfil, Card de Booyah) + QR Code PIX BRCode |
| 🤝 Comercial | Parcerias com vitrine e Divulgação paga, ambos como ticket |
| ☁️ Resiliência | Snapshot gzip+base64 no Supabase, tabelas estruturadas em tempo real, keep-alive, anti-wipe, auto-update, encerramento limpo de ciclo |

---

## 2. A ARQUITETURA DE EXECUÇÃO (a parte mais incomum — e mais bem resolvida)

O bot **não tem servidor**. Ele roda dentro de **runners Windows efêmeros do GitHub Actions**,
encadeados um no outro indefinidamente:

```
 ┌─ Run N (windows-latest, timeout 360 min) ────────────────────────────────┐
 │ 1. checkout                                                               │
 │ 2. liga RDP (runneradmin + secrets.RDP_SENHA) + Tailscale (fireforce-rdp)  │
 │ 3. setup-python 3.12 + pip install                                        │
 │ 4. GERA em runtime: vigia_bot.ps1, iniciar_bot.ps1, reiniciar_bot.ps1,     │
 │    status_bot.ps1 + 3 atalhos na área de trabalho do RDP                   │
 │ 5. monta .env a partir dos Segredos (nada aparece em log)                  │
 │ 6. sobe o bot ESCONDIDO sob o vigia                                        │
 │ 7. laço de 342 min (~5h42m): dorme ≤120s, confere se o python.exe vive,    │
 │    ressuscita se caiu                                                      │
 │ 8. ANTES de desligar: dispara o Run N+1 pela API do GitHub e SÓ encerra    │
 │    depois de CONFIRMAR que a sucessora está na fila                        │
 │ 9. grava _encerrar_ciclo.flag → bot salva 100% no Supabase → bot.close()   │
 └───────────────────────────────────────────────────────────────────────────┘
        ↓ concurrency: group=fireforce-bot, cancel-in-progress=false
        ↓ (UMA máquina por vez — nunca duas: o mesmo PIX contaria 2x)
 ┌─ Run N+1 assume no instante em que N libera ───────────────────────────────┐
```

**Por que isso é bem feito:**

- **Não depende de `cron` do GitHub** (que atrasa/descarta sob carga). A máquina atual *puxa* a
  próxima via `POST /actions/workflows/{id}/dispatches` e **confirma na fila** antes de morrer.
- **`FF_DURACAO_MIN=342`** deixa 18 min de folga sobre o teto duro de 6h do GitHub, e o
  `tetoDisparo` é 355 min — margem calculada, não chutada.
- **Fallback de `ref`**: se o dispatch com a ref atual der HTTP 422, tenta `ref=main`.
- **Trava anti-loop**: o passo de recuperação conta falhas nos últimos 20 min e **para** se houver
  3+ — não entra em loop infinito de runs.
- **Respeita cancelamento manual**: `if: failure() && !cancelled()`. Cancelar no Actions realmente
  desliga o sistema.
- **`SYNC_SEGUNDOS=30`** no runner (vs. 60 padrão) porque a máquina *morre de repente*.
- **`batimento.yml`** (dias 1 e 15) existe por um motivo preciso e documentado: o GitHub desativa
  workflows agendados após ~60 dias sem atividade. É um carimbo de 1 linha em `batimento.txt`.
- **`supabase_keepalive.yml`** (a cada 2 dias) impede a pausa do projeto Supabase por inatividade
  **e** atualiza `atualizado_em` — sem dependência externa (só `urllib` da stdlib).

---

## 3. ANATOMIA DO CÓDIGO (medido, não estimado)

```
Arquivo único            23.034 linhas   1,08 MB
  código                 20.349 linhas   (88,3%)
  comentário puro           331 linhas
  comentário inline          51
  em branco               2.407 linhas

Funções                     635   (215 com docstring = 33%)
Classes                     123   ( 55 com docstring = 44%)
  discord.ui.View            72
  discord.ui.Modal           28
  discord.ui.Select          18
  infra (_ConexaoSQLiteBlindada, _FiltroAvisoIntents, _FFNaoEncontradoGlobal, _GuildRef)  4

Comandos slash               45   (45/45 guild_only • 33/45 default_permissions)
Tabelas SQLite               36   + 12 índices
aiosqlite.connect            252 pontos de acesso
Loops de background          10
criar_embed()                622 chamadas
interaction.response/followup 687 pontos de resposta
registrar_log (Discord)        51
_log_arquivo (disco)           87
marcar_sujo()                 105
Emojis                      1.779

Type hints: 1.063/1.200 parâmetros = 88%   |   retorno anotado: 239/635 = 37%
Pyflakes: 8 apontamentos, ZERO nomes indefinidos
Compila: OK   |   Importa: OK em 0,32s   |   Segredos hardcoded: NENHUM
```

**Maior função:** `init_db` (549 linhas — schema + migrações). Depois: `renderizar_card_perfil_png`
(406), `renderizar_tabela_sala_png` (370), `_executar_reserva_slot` (351), `_rotear` (277).

---

## 4. OS 10 PILARES QUE SUSTENTAM A EXCELÊNCIA

Isto é o que o código faz e que **precisa ser preservado em qualquer mudança futura**:

### 4.1 Blindagem global do SQLite por monkey-patch (linha 403-445)
`aiosqlite.connect` é **substituído no módulo** por `_ConexaoSQLiteBlindada`, que injeta
`timeout=30`, `PRAGMA busy_timeout=30000` e `synchronous=NORMAL` em **todas as 252 conexões** —
inclusive as abertas por código de terceiros. Verificado em execução real:
`journal_mode=wal busy_timeout=30000 synchronous=1`. Uma única decisão cobre o arquivo inteiro;
não há como um dev novo "esquecer" o timeout.

### 4.2 Escudo global de erros de UI (linha 279-404)
`discord.ui.View.on_error` e `discord.ui.Modal.on_error` são **sobrescritos na classe base**.
Resultado: nenhuma das 72 Views / 28 Modais pode produzir "Esta interação falhou" sem log.
E o mais refinado — `_erro_interacao_expirada()` **filtra de propósito** os códigos `10062`
(Unknown interaction) e `40060` (already acknowledged): corrida normal do Discord não vira ruído
no log. `@bot.tree.error` faz o mesmo para slash, com ramificação por tipo
(cooldown / MissingPermissions / BotMissingPermissions / CheckFailure / genérico).

### 4.3 Roteador dinâmico de componentes persistentes (linha 21948-22003)
Rede de segurança pós-restart. Se alguém clica num seletor `ff_*_sel:<id>` que ainda não foi
hidratado em `persistent_views`, o listener **reconstrói a View na hora e executa o callback**.
Detalhe de altíssimo nível: antes de despachar, ele **inspeciona o `_view_store` interno do
discord.py** (por `message_id` e pelo bucket global `None`) para garantir que **nunca** executa o
mesmo clique duas vezes. Isso é conhecer a biblioteca por dentro.

### 4.4 Corrida (hedged requests) + disjuntor + 5 camadas de fallback na consulta FF (linha 2133-2712)
```
camada 1: cache negativo em RAM (5 min) — UID inexistente não bate na API de novo
camada 2: cache SQLite fresco (24h)
camada 3: CORRIDA entre 3 provedores com disparo escalonado (0,35s)
          → 1º que responder vence, os outros são cancelados no finally
          → se alguém diz "não existe", espera 2,0s para OUTRO provedor contestar
          → disjuntor: 3 falhas seguidas = 300s de descanso, ignorado na corrida
          → se TODOS estão em descanso, tenta o primeiro mesmo assim (nunca desiste)
camada 4: cache SQLite VENCIDO + aviso honesto ("servidores instáveis, último dado salvo")
camada 5: histórico local do próprio bot (slot_jogadores) + aviso de manutenção
```
Mais: `_ff_procurar()` percorre a resposta com **profundidade limitada a 6** e uma lista de
sub-objetos **prioritários e diferentes** para jogador vs. clã, e uma lista explícita de blocos
**ignorados** (`petinfo`, `captainbasicinfo`, `servicestatus`…). Motivo documentado: nunca
confundir o nick/level do **pet** ou do **capitão da guilda** com o do jogador. Isso é conhecer o
domínio dos dados de terceiros.

### 4.5 Dinheiro: transação única, `BEGIN IMMEDIATE`, estorno e dedupe
- `transferir_saldo_atomic` (12489): os **dois lados** e as **duas linhas de ledger** saem numa
  única transação (`executemany`), com `ref = f"transfer:{interaction.id}"` — idempotência pelo ID
  da interação do Discord.
- `movimentar_saldo` (12443): `BEGIN IMMEDIATE`, validação `math.isfinite`, arredondamento, e
  **nunca** deixa saldo negativo. Verificado: 150,75 − 50,25 = 100,50 ✅; estouro de −9.999 →
  `None` e saldo intacto ✅.
- `_executar_reserva_slot` (6384): **revalida TUDO dentro da transação** — horário ativo,
  duplicidade de comprador, duplicidade de UID, lotação, bloqueio de horário, e até se o membro
  voltou a ficar "em serviço" — e faz `rollback` + apaga o canal recém-criado se qualquer checagem
  falhar. A checagem "otimista" antes (6262) é só UX; a autoridade é a transação.
- `_lock_aprovacao` (7153) com o comentário exato do bug que impede: *"dois staffs clicando Aprovar
  no MESMO segundo não podem dar a MESMA vaga para dois jogadores diferentes"*.
- `estornar_moedas_reserva_se_necessario` roda na virada de ciclo, na recusa, na expiração e na
  limpeza — o dinheiro do jogador sempre volta.

### 4.6 PIX BRCode 100% conforme o manual do BACEN (linha 2777-2988)
CRC16-CCITT (`init 0xFFFF`, poli `0x1021`) **validado por mim contra o vetor `29B1`** para
`"123456789"` ✅. Campo `62/05` fixo em `***` com a **nota técnica citando a seção 2.1.1 do
manual** e explicando que Caixa/Santander/Bradesco/BB/Itaú rejeitam TXID personalizado fora do PSP.
Validação real de CPF e CNPJ por dígito verificador (não só tamanho), normalização `+55` de
celular, remoção de zero-width, e **desambiguação honesta**: 11 dígitos que podem ser CPF *ou*
celular → o bot **recusa e pede o tipo** em vez de chutar.

### 4.7 Supabase: fotografia compacta + anti-wipe + fatiamento
- Snapshot de **todas** as tabelas → `gzip(6)` + `base64` (medido: 2,2 KB para 4 linhas).
- `snapshot_aplicar` **intersecciona colunas** com `PRAGMA table_info` — nunca descarta uma tabela
  inteira porque uma coluna foi adicionada/removida entre versões. Migração de schema à prova de
  fotografia antiga.
- **Fatiamento automático** em blocos de 1,8 MB + manifesto + limpeza de blocos excedentes
  (evita o limite de POST do plano grátis).
- **Trava anti-wipe em duas camadas**: (a) `_SUPABASE_BLOQUEIO_BANCO_VAZIO` se a restauração inicial
  falhou numa máquina de banco vazio; (b) re-checagem no envio — se o banco local está vazio **e**
  a nuvem tem um pacote >280 chars, o envio é **retido** sem `forcar`. Uma máquina nova nunca
  sobrescreve o backup bom.
- `loop_sync` **tenta se auto-recuperar** a cada ciclo enquanto o bloqueio estiver ativo.
- `SYNC_LIMITE_TABELAS` limita as 8 tabelas que crescem (transacoes 4000, ff_cache 1500…).
- `limpar_lixo_banco` é o ponto mais delicado e está documentado como tal: **"NUNCA toca em
  carteiras, vitórias, patentes, lines_salvas, blacklist, chaves PIX ou horários ativos"**, e
  **compacta** slots arquivados há >35 dias em `estatisticas_jogador.partidas_base` com
  `ultimo_slot_migrado` monótono — o jogador **nunca perde partidas nem patente** quando o histórico
  é enxugado. Tudo dentro de um único `BEGIN IMMEDIATE`, com `rowcount` somado e logado.
- `sincronizar_estruturado` (15818) obedece a uma **ordem de segurança explícita**: o upsert vem
  **sempre antes** da limpeza de chaves obsoletas, e a limpeza só roda se o upsert teve `ok` — com
  comentário explicando que *"se algum cálculo falhou, `linhas_rankings` levanta erro e não chegamos
  aqui"*. Uma falha de rede nunca vira um ranking apagado.

### 4.8 Imagem HD sem travar o event loop
Os 3 renderizadores são **CPU-pesados** (SSAA 2× em 2760×1980). Medido em execução real:
tabela 0,38–0,47s • booyah 0,16–0,20s • perfil 0,52s. **Todos** passam por
`await asyncio.to_thread(...)` — inclusive `ast.parse` e os 4 `subprocess.run` de git.
Robustez testada por mim: booyah com **0 jogadores** ✅, nicks gigantes com unicode matemático e
`꧁꧂𓆉` ✅, patente máxima com `proxima_patente = None` ✅. Isso funciona porque
`_card_limpar_texto` compara a máscara de `\uffff` (glyph *notdef*) por fonte e substitui só o que
a fonte não desenha, e `_card_truncar_px` corta por **pixel**, não por caractere.
Fontes com cadeia de fallback Windows → Debian → `load_default(size=...)`.

### 4.9 Ciclos de vida e reconciliação honestos
- `FireForceBot.close()` salva o estado e fecha a sessão HTTP **no mesmo event loop** em que foram
  criados (comentário explica o bug antigo: `close()` abria um loop novo depois de `bot.run()`).
- `loop_pulso` é **também** o supervisor: chama `_iniciar_tarefas_background()` a cada 30s, que é
  idempotente por `done()` — revive qualquer loop morto e nunca duplica.
- `on_ready` usa `_ON_READY_LOCK` + `_BOT_INICIALIZADO` porque **o Gateway reconecta** e o evento
  dispara de novo; sem isso, views seriam republicadas e loops duplicados.
- `_reconciliar_ticket_estado` é a melhor função de resiliência do arquivo: distingue
  `discord.NotFound` (órfão **real**) de `discord.Forbidden/HTTPException` (problema de **acesso** —
  *não* marcar como órfão), e faz as chamadas ao Discord **fora** das transações SQLite
  (comentário: "para não travar o banco").
- `tempo_fora()` + `recuperar_apos_queda()`: se ficou fora ≥3 min, reconfere tudo **antes** de o
  loop de expiração apagar reservas antigas, e conta à equipe o que recuperou.
- `INICIADO_EM`, `ultimo_pulso` e `ultimo_ping_supabase` alimentam o `/saude`, que mostra loops
  vivos, último erro de sync, estado do disjuntor e pendências abertas.

### 4.10 Intents: zero privilegiadas, por decisão documentada
`members`, `presences`, `message_content` e `voice_states` **todos OFF** (verificado em execução),
com 15 linhas explicando o *porquê* (sem verificação do Discord, ~55 MB de RAM fixos
independentemente do tamanho do servidor) e como reverter se um dia precisar. Em vez do cache de
membros: `mencao()` gera `<@id>` puro (funciona sempre) e `membro_do_guild()` busca na API sob
demanda. `_GuildRef` (15654) permite sincronizar o Supabase **antes** de o cache de guilds existir.
Até o warning inofensivo do discord.py é filtrado cirurgicamente (`_FiltroAvisoIntents`) — *"sem
esconder nenhum outro alerta real"*.

---

## 5. VERIFICAÇÃO EMPÍRICA QUE EU EXECUTEI

Não é opinião — rodei o código:

| Verificação | Resultado |
|---|---|
| `py_compile` | ✅ sem erros de sintaxe |
| Import do módulo inteiro | ✅ **0,32s**, 45 comandos registrados |
| `pyflakes` | ✅ **8 apontamentos**, nenhum nome indefinido |
| `init_db()` real | ✅ 36 tabelas, 12 índices, `wal`, `busy_timeout=30000`, `synchronous=1` |
| `init_db()` 2ª vez | ✅ idempotente (0,01s) |
| CRC16 vs. vetor `29B1` | ✅ |
| 8 payloads PIX (estrutura EMV, CRC auto-consistente, txid `***`) | ✅ 8/8 |
| 7 validações de chave PIX (CPF/CNPJ/e-mail/EVP/celular/zero-width) | ✅ 7/7 |
| `parse_valor` (10 casos, incluindo `inf` e `1.234,56`) | ✅ 10/10 |
| 12 patentes + monotonicidade em 400 pontos | ✅ 8/8 |
| `pode_comprar_vaga` (6 cenários) | ✅ 6/6 |
| `mascarar_chave` (LGPD) | ✅ 3/3 |
| Carteira: crédito, débito, bloqueio de saldo negativo | ✅ |
| Snapshot Supabase: dump → gzip → base64 → round-trip idêntico | ✅ |
| Blacklist: banir / listar / consultar / remover | ✅ |
| `limpar_lixo_banco(forcar=True)` | ✅ |
| 4 Tabelas Oficiais HD (solo/duo/trio/squad) | ✅ 1380×990…1320×980, 166–215 KB |
| 4 Cards de Booyah HD | ✅ 1000×580, 132–141 KB |
| Card de Perfil HD | ✅ 1240×700, 275 KB |
| Casos-limite de renderização (0 jogadores, nicks gigantes, patente máxima) | ✅ 3/3 |
| **TOTAL** | **81/81 asserções + 15 verificações de integração** |

---

## 6. ONDE A EXCELÊNCIA AINDA NÃO CHEGOU — 22 achados, priorizados

### 🔴 CRÍTICO — risco de segurança ou de indisponibilidade total

**A1. Não existe `.gitignore`.** O repo rastreia só 6 arquivos, mas o runtime cria, **dentro do
checkout git** (`GITHUB_WORKSPACE`): `.env` (com `DISCORD_TOKEN` **e** `SUPABASE_SERVICE_ROLE_KEY`),
`ffv1.db` + `-wal` + `-shm`, `fireforce.log`, `fireforce.log.1`, `vigia.log`,
`_encerrar_ciclo.flag`, `ff_inicio_ciclo.txt`, 6 PNGs. Um único `git add -A && git push` — por um
humano no RDP **ou** por um agente de IA — publica o token, a chave service role e o banco inteiro
com saldos e chaves PIX de todos os jogadores. **É o maior risco do repositório hoje.**

**A2. O auto-update valida só sintaxe, e o vigia re-aplica o `main` quebrado para sempre.**
`_checar_e_aplicar_auto_update` (21544) valida UTF-8 + presença de `VERSAO_BOT` + `ast.parse`. Um
erro **semântico** (NameError na importação, assinatura errada de discord.py, indentação que muda
lógica) passa na validação, substitui o arquivo, o bot reinicia e cai. Aí o `vigia_bot.ps1` faz
`git fetch` + `git checkout -f origin/main -- fireforce_bot.py` **em toda iteração** e re-aplica o
mesmo código quebrado, a cada 5s, até 300 quedas. Não há `.bak` do arquivo anterior → **não existe
rollback automático**. E **nenhum workflow valida nada antes do merge na `main`** — o único gate é o
`ast.parse` de um bot já em produção.
*Correção de excelência:* (a) CI em `push`/`pull_request` que rode `py_compile` + import num
subprocesso com as dependências pinned; (b) no auto-update, validar com **import real em
subprocesso** (`python -c "import fireforce_bot_novo"`) antes do `os.replace`; (c) gravar
`fireforce_bot.py.bak` e, se o processo novo morrer em <120s duas vezes seguidas, restaurar o `.bak`
e pausar o auto-update com alerta no canal de logs.

**A3. Dependências sem pin e sem `requirements.txt`.**
`pip install discord.py aiohttp aiosqlite "qrcode[pil]" Pillow` — sem nenhuma versão. Como uma
máquina **nova** é criada a cada 5h42m, cada ciclo instala o *latest* do PyPI daquele momento. Um
release breaking de `discord.py` ou `Pillow` derruba **todas** as máquinas subsequentes de uma vez,
sem alteração nenhuma no repo e sem caminho de volta. Hoje: discord.py 2.7.1, aiohttp 3.14.5,
Pillow 13.0.0.

### 🟠 ALTO — custo, desempenho e concorrência

**A4. Zero cooldown nos 45 comandos.** `grep app_commands.cooldown` → **0 ocorrências**. Entre os
sem proteção estão justamente os caros: `/perfil` (0,52s de CPU), `/booyah` (0,2s + N consultas FF +
download de avatares), `/verificar` (até 3 provedores × 15 regiões), `/backup` (POST de MBs no
Supabase), `/restaurar` (sobrescreve o banco local), `/dados`, `/transferir` (**dinheiro**),
`/addsaldo`, `/admin`. Um único usuário segurando Enter em `/perfil` satura o pool de threads.

**A5. `rebuild_painel` não tem cache de assinatura — e roda a cada 15s.**
`atualizar_tabela` (5111) faz isso **certinho**: monta uma tupla de assinatura (id, msg_id, tipo,
categoria, horário, premiação, valor, ocupadas + assinatura de cada slot) e retorna sem tocar no
Discord se nada mudou (`_TABELA_ASSINATURA_CACHE`). `rebuild_painel` (5294) **não tem nada
parecido**: a cada 15s, por painel, faz N+1 `SELECT COUNT(*)` (um por horário) + `fetch_message` +
`edit` — mesmo sem nenhuma mudança. São 8 chamadas HTTP/min por painel, queimando budget de rate
limit e fazendo o seletor "piscar". **A solução já existe no próprio arquivo: é só aplicar o mesmo
padrão.**

**A6. `_obter_commit_curto_local()` bloqueia o event loop.** (21465)
Faz `subprocess.run(["git","rev-parse","--short","HEAD"], timeout=6)` **síncrono**, e é chamado
diretamente de contexto async em dois lugares: `/saude` (14677) e o auto-update (21591) — que roda
**a cada 60s** e cai nesse ramo toda vez que já está atualizado (o caso normal). Enquanto isso o
`vigia_bot.ps1` faz `git fetch` no mesmo `.git`, podendo segurar o lock do índice. Pior caso:
**6 segundos de event loop congelado a cada minuto**, com todas as interações do Discord dando
timeout. As outras 4 chamadas de `subprocess.run` do arquivo estão corretamente atrás de
`asyncio.to_thread` — esta escapou.

**A7. `processar_repeticao_diaria()` roda 3× a cada 30s.** Chamada por `loop_expirar` (a cada 30s)
**e** por `loop_tabelas` (a cada 15s). Cada execução pega `_lock_repeticao_diaria` e varre todos os
horários ativos com JOIN. É idempotente, então não corrompe — mas é trabalho triplicado no banco e
contenta de lock desnecessária. Basta um guard de "já rodei neste minuto BRT".

### 🟡 MÉDIO — dívida técnica e código morto (herança da era pré-v12.0 / LivePix)

O PR #5 (v12.0) anuncia *"PIX direto sem LivePix"*. A integração foi removida, mas **o cadáver
ficou**. Detectei por análise de grafo de referências (contando `Name`, `Attribute` **e** tokens
dentro de string literals, para não marcar como morto o que é invocado via `globals()`):

**A8. 178 linhas de código morto em 11 funções — zero referências:**

| Linha | Função | Linhas |
|---|---|---|
| 12767 | `aprovar_pagamento` — *"Usado pelo pagamento com saldo e pela confirmação automática da LivePix"* | **77** |
| 1292 | `checar_uid_duplicado_horario` (substituída pela query inline em 6414) | 20 |
| 12359 | `nomes_candidatos` | 12 |
| 12333 | `codigos_no_texto` + `RE_CODIGO_FF` | 11 |
| 12373 | `nome_do_pagamento_bate` | 11 |
| 14981 | `pagamento_depois_do_pedido` | 11 |
| 12412 | `_ja_visto` | 10 |
| 12401 | `valor_bate` | 9 |
| 19042 | `_resolver_nome_pix` | 8 |
| 15792 | `_apagar_rows` | 6 |
| 18840 | `avisar_eventos_nos_pagamentos` — corpo é literalmente `return True` | 3 |

Puxam junto: `normalizar_nome`, `nomes_parecidos` e `apelidos_do_usuario`-via-`nomes_candidatos`
ficam órfãos por tabela (as duas primeiras **só** são chamadas por funções mortas — testei-as mesmo
assim e estão corretas, o que reforça que eram boa engenharia de um recurso desligado).
O cabeçalho do bloco 13757 anuncia *"CASAMENTO AUTOMÁTICO (o coração da confirmação em 5 min)"* e
**não tem uma linha de código embaixo** — só o comentário seguinte. Documentação que mente.

**A9. Estruturas de banco vestigiais:**
- `checkouts` (763) — **16 colunas, ZERO referências** em todo o arquivo.
- `livepix_vistos` (665) — só é lida/escrita por `_ja_visto`, que é morto.
- `horarios.vagas_total` — **gravada sempre como o literal `48`** (linha 8212) mesmo para
  duo/trio/squad, e **nunca lida para nada**: toda a fiscalização de lotação usa o dict hardcoded
  `LOTES_POR_MODO` (16 pontos). Ou seja: a coluna guarda dado **errado** e **não usado**.
- `config.livepix_link` — migração em 802, serializada para o Supabase em 15640/15712, e **nunca
  exposta em nenhuma UI nem consumida por nenhuma lógica**.

**A10. Linha 5419 — lixo de refactor:**
```python
_PAINEL_PAGINA_ATUAL[int(painel_id), ] if False else None
```
Expressão morta com `if False`, constrói uma tupla e descarta. A linha seguinte faz o trabalho real.

**A11. `movimentar_saldo` não dá rollback explícito no caminho de falha** (12443).
Quando falta saldo, `return None` sai com o `BEGIN IMMEDIATE` **aberto**, confiando no rollback
implícito do `close()` do `async with`. Funciona, mas segura o lock de escrita até lá — e é
**inconsistente** com `transferir_saldo_atomic` (12507) e `_executar_reserva_slot` (6432), que fazem
`await db.rollback()` explicitamente. O padrão correto já existe no arquivo.

**A12. Contrato implícito frágil no card de perfil.** `renderizar_card_perfil_png` acessa
`dados["patente"]` e `dados["proxima_patente"]` por **índice direto** (11341). Confirmei em
execução: `dados={}` → `KeyError: 'patente'`. Hoje funciona porque
`obter_estatisticas_completas_jogador` (1661) achata essas chaves — mas o contrato entre as duas
funções, separadas por 400 linhas, não está em lugar nenhum. O `try/except` do chamador (11822)
degrada com elegância (sem imagem), então não é um bug de produção — é uma armadilha de manutenção.

**A13. Indexação direta em dicts de configuração — inconsistente.**
`LOTES_POR_MODO[...]` / `JOGADORES_POR_LOTE[...]` com `[]` em **11 pontos** (4021, 5321, 5323, 5547,
5592, 6150, 6284, 7176, 7929, 7934, 12780) → `KeyError` se um `tipo` sujo vier do banco. Nos outros
**6 pontos** usa `.get()` com fallback. Duas convenções para o mesmo dict.

**A14. Caches em RAM sem orçamento.**
- `_FF_NAO_ENCONTRADOS` (2179) — **cresce sem poda nenhuma**: todo UID inexistente consultado entra
  e nunca sai.
- `_CACHE_AVATAR_FF_BYTES` (3490) — FIFO de 64 entradas, mas aceita até **4 MB por imagem** →
  **até 256 MB** de teto, contra a meta documentada de *"~55 MB de RAM fixo"* (linha 193).
- `_TABELA_ASSINATURA_CACHE` (3028) — só é limpo quando `canal_tabela` vira NULL.
Na prática o ciclo de 5h42m zera tudo, o que **contém** o problema — mas é contenção acidental, não
projeto. Um orçamento em bytes + LRU resolveria de vez.

### 🟢 BAIXO — polimento e documentação

**A15. `/help` esconde 3 comandos do Dono.** Cruzando os 45 nomes registrados com os mencionados no
corpo do `/help`: faltam **`/info`**, **`/reparar_pendencias`** e **`/tickets_fechar`** — justamente
ferramentas de diagnóstico do Dono/Gerente. (Nenhum comando inexistente é anunciado ✅.)

**A16. Nome de arquivo errado na mensagem de auto-ajuda** (linha 22998):
`print("   5️⃣  Rode de novo:  python fireforce_bot_v11.py\n")` — o arquivo é `fireforce_bot.py`.
É a mensagem que aparece quando o token está mal configurado, ou seja, exatamente quando o usuário
está perdido.

**A17. Os 8 apontamentos do pyflakes:** `typing.List` importado sem uso (36); variáveis locais
mortas `card_h` (3781), `agora` (18781), `cargo` (22093); 4 f-strings sem placeholder (9108, 13201,
14550, 18177). Nenhum é bug — são ruído.

**A18. `supabase_setup.sql` não existe — e o onboarding de um Supabase novo é impossível só pelo
repo.** A linha 15629 promete: *"O SQL que cria essas tabelas está no arquivo
`supabase_setup.sql`"*. Esse arquivo **não está no repositório** (`git ls-files` → 6 arquivos, nenhum
deles). Verifiquei que isto **não é só documentação desatualizada**: `sincronizar_estruturado`
(15818) apenas faz `_upsert_supabase` (POST com `on_conflict`) em `ff_config`, `ff_cargos`,
`ff_staff_online` e `ff_rankings` — **ele não cria tabela nenhuma**. Ou seja: num projeto Supabase
novo, todo o sync estruturado falha com `42P01 relation does not exist` e o único DDL que existe
está na cabeça de quem configurou o projeto atual. As chaves de upsert (`guild_id`,
`guild_id,tipo`, `guild_id,user_id`, `guild_id,categoria,user_id`) e as 5 colunas de
`fireforce_estado` (`id`, `dado`, `atualizado_em`, `versao` + conflito em `id`) estão todas
deduzíveis do código — reconstruir o `.sql` é direto e remove um ponto único de falha operacional.

> **RESOLVIDO DE OUTRO JEITO (decisão do dono, 11/11/2026).** Um `supabase_setup.sql` chegou a
> ser reconstruído e validado contra o código (62 conferências: colunas, chaves de conflito,
> tipos e o caminho fatiado do `fireforce_estado`). Ele foi **apagado por pedido do dono**, que
> já possui o DDL original do seu projeto. A validação, porém, deixou um achado que **vale mais
> que o arquivo**: a ordem de escolha de chave é
> `SUPABASE_SERVICE_ROLE_KEY → SUPABASE_KEY → SUPABASE_ANON_KEY`, e o projeto em produção tem
> **somente a anon** (print dos segredos do repositório em 11/11/2026: `DISCORD_TOKEN`,
> `RDP_SENHA`, `SUPABASE_ANON_KEY`, `SUPABASE_ID`, `SUPABASE_URL`, `TAILSCALE_AUTHKEY`).
> Consequência prática: um `.sql` que "endurecesse" o RLS (sem política para anon) **derrubaria a
> sincronização em produção** — a chave que o bot realmente usa seria barrada. Portanto o
> esquema corre para este projeto é **manter o RLS como está**; o comentário do bot na seção
> "🧱 ESTRUTURAS NO SUPABASE" foi reescrito para dizer exatamente isso e para deixar claro que
> o bot nunca cria tabela. O contrato vivo com o esquema são as tuplas `COLUNAS_FF_CONFIG`,
> `CARGOS_DO_BOT` e `CATEGORIAS_SQL` — quem renomear coluna no Supabase renomeia ali.
> Registro também, para não repetir o erro: `SUPABASE_ID` e `SUPABASE_TABELA` **não são
> obrigatórios** (têm padrão `"principal"` e `"fireforce_estado"`); o README antigo os listava
> como se fossem, e foi corrigido.

**A19. `README.md` tem 1 linha** (`# Fireforcebot`, 14 bytes). Um sistema com 23 mil linhas, 3
workflows, segredos cuja obrigatoriedade real ninguém havia mapeado (só `DISCORD_TOKEN` é
indispensável; o Supabase pede `SUPABASE_URL` + **uma** chave entre service role, key ou anon),
um esquema de encadeamento de runners e 36 tabelas não tem
**nenhuma** documentação de entrada: quais segredos criar, o que é `SUPABASE_ID` (o comentário diz
que "vira o cofre: use algo difícil de adivinhar" — e ele está **só** lá, na linha 15217), como parar
o ciclo, como fazer rollback, o que significa o código de saída 42.

**A20. Zero testes automatizados.** As 81 asserções + 15 verificações de integração desta análise
**não vivem no repo**. Não há `tests/`, e nenhum workflow roda nada além de `batimento.txt`. Para um
bot que lida com dinheiro real e se auto-atualiza a cada 60s a partir da `main`, isso é o que separa
"excelente" de "excelente e seguro".

**A21. `on_guild_join` (22005) chama `canal.send` sem `try/except`.** Se o primeiro canal com
`send_messages` estiver em slowmode/NSFW/bloqueado, a exceção sobe para o handler de eventos do
discord.py. Todo o resto do arquivo trata isso; aqui não.

**A22. `salvar_config` (1052) monta SQL por f-string a partir de `**kwargs`.**
Hoje é **seguro**: verifiquei que todas as chaves vêm de mapas fixos no código
(`CANAIS_PUBLICOS`, chamadas nomeadas) — nunca de entrada do usuário. Mas não há whitelist de
colunas, e a função ainda abre uma **segunda** conexão aninhada (`obter_config` dentro de
`salvar_config`) e tem corrida de INSERT duplicado se dois comandos configurarem a mesma guild nova
ao mesmo tempo.

---

## 7. LEITURA DO HISTÓRICO — o que ele revela sobre o padrão

25 PRs, todos de branches `arena/*`, todos mergeados, num ritmo de ~5/dia entre 04 e 11/11/2026:

```
v11.3 → v11.4 → v11.5 → v11.6 → v12.0 → v12.1 → v12.2 → v12.3
      → v13.0 → v13.1 → v13.2 → v13.3 → v13.4 → v13.5 → v13.6 → v13.7
      → v13.7.1 (Influenciadores)  → PR#19 REVERT para v13.7
      → v13.7.2 (auditoria)        → PR#21/22 v13.8.0/13.8.1 (Influenciadores de novo)
      → PR#24 "Restaurar bot para v13.7 ANTES do sistema de influenciadores"
      → PR#25 (ciclo contínuo sem depender de cron)
```

Três conclusões operacionais importantes:

1. **O sistema de Influenciadores foi construído e desfeito DUAS vezes.** O estado atual é
   deliberadamente **v13.7 sem influenciadores**. Isso define o apetite de risco do projeto:
   **estabilidade > feature nova**. Qualquer proposta futura precisa respeitar isso.
2. **Os títulos dos PRs mostram que "auditoria completa" e "blindagem" são rotina** (PR #10, #15,
   #20), não exceção. O padrão de excelência é mantido por **passadas de auditoria recorrentes** —
   esta análise é a continuação natural desse processo.
3. **A numeração de versão no código (`VERSAO_BOT = "13.7"`) é a fonte de verdade**, e o
   auto-update a usa para logar `vX ➜ vY`. Bumpar a versão **não é cosmético**: é o que aparece no
   canal de logs de todos os servidores a cada deploy.

---

## 8. AS REGRAS QUE EU VOU SEGUIR AQUI

Para manter e elevar o padrão, sem quebrar o que já é excelente:

**Sempre:**
1. **Nunca** remover as blindagens globais (monkey-patch do SQLite, `on_error` global, roteador
   dinâmico, `_FiltroAvisoIntents`). Elas são a fundação.
2. **Nunca** tocar em `limpar_lixo_banco` sem preservar o contrato "NUNCA apaga carteira, vitória,
   patente, line, blacklist, chave PIX ou horário ativo" e a compactação monótona de `partidas_base`.
3. Toda operação com dinheiro continua dentro de `BEGIN IMMEDIATE`, com estorno nos caminhos de
   falha e `ref` idempotente.
4. Todo trabalho de CPU (Pillow) ou de processo (git) continua atrás de `asyncio.to_thread`.
5. **Reutilizar os padrões que já existem no arquivo** em vez de inventar novos: precisa de cache de
   mudança? copie `_TABELA_ASSINATURA_CACHE`. Precisa de retry? copie `_sb_req`. Precisa de
   reconciliação? copie `_reconciliar_ticket_estado`.
6. Bumpar `VERSAO_BOT` a cada mudança funcional (é o contrato com o canal de logs e com o
   auto-update).
7. Manter o idioma, o tom e o estilo de comentário do projeto: **português, comentando o PORQUÊ e o
   bug que a linha impede** — não o que a linha faz. É assim que os 331 comentários de bloco e os
   docstrings do arquivo funcionam como documentação viva.
8. Manter `ZERO intents privilegiadas`, os 45 comandos `guild_only`, e a máscara de chaves PIX em
   qualquer canal público (LGPD).

**Antes de qualquer entrega:**
9. `py_compile` + import do módulo + pyflakes sem apontamento novo.
10. Rodar as asserções funcionais (PIX/CRC, parse_valor, patentes, pode_comprar_vaga, carteira,
    snapshot round-trip, renderizadores com casos-limite) — tenho o harness pronto.
11. Nada de artefato gerado no git: `.db`, `.log`, `.png`, `.env` ficam fora.

**Ordem de ataque que eu recomendo** (do maior risco para o menor):
`A1 .gitignore` → `A2 validação + rollback do auto-update` → `A3 requirements.txt pinned`
→ `A6 subprocess bloqueante` → `A4 cooldowns` → `A5 cache de assinatura do painel`
→ `A7 guard da repetição diária` → `A8/A9/A10 remoção do cadáver LivePix`
→ `A11–A14 consistência e caches` → `A15–A22 polimento, README, SQL do Supabase e testes`.

Os três primeiros são pequenos, cirúrgicos e eliminam o único cenário em que este projeto perde
dinheiro, token ou disponibilidade de forma irreversível.
