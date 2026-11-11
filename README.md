# 🔥 Fire Force Bot

Bot premium de gestão de **diários de Free Fire** para a Liga Oficial de Diários.
Um único arquivo Python (`fireforce_bot.py`, ~23.500 linhas) que cuida de
inscrições, carteira com PIX, tabelas oficiais em imagem HD, rankings, tickets de
atendimento e backup em nuvem.

---

## 📌 O que ele faz

| Área | Resumo |
|---|---|
| **Inscrições** | Painéis com seletor de horário, vagas Solo/Duo/Trio/Squad, fila de espera, bloqueio automático faltando X minutos |
| **Carteira** | Saldo privado por jogador, depósito e saque via PIX, transferência atômica entre jogadores, livro-caixa da organização |
| **PIX** | Gera o BRCode "copia e cola" oficial do Banco Central (com CRC-16 válido) e QR Code; concilia pagamentos recebidos |
| **Free Fire** | Consulta de ID com 3 provedores em corrida, cache de 24 h, avatar e clã, verificação de nível mínimo |
| **Imagens HD** | Tabela oficial da sala, card de perfil com patente e card de Booyah, tudo renderizado com Pillow |
| **Competitivo** | 12 patentes (Bronze ➜ Hacker), vitórias, winrate, sequência, linhas salvas, rankings por 7 categorias |
| **Equipe** | Carteira de trabalho do Suporte, comissões, escala ON/OFF, tickets com canal privado |
| **Infra** | Backup gzip no Supabase, auto-update sem desligar a máquina, rollback automático, logs rotativos |

---

## 🧱 Como ele fica no ar (arquitetura de corredores)

O bot **não roda num servidor fixo**. Ele roda no GitHub Actions, que dá ~6 horas
de máquina por execução. A solução foi encadear corredores:

```
  ┌─────────────────────────────────────────────────────────┐
  │ fireforce.yml  (windows-latest + RDP + Tailscale)       │
  │                                                          │
  │  1. instala Python e as dependências (requirements.txt)  │
  │  2. gera os .ps1 e escreve o .env a partir dos segredos  │
  │  3. liga o bot                                           │
  │  4. fica de vigia: se o processo sumir, religa           │
  │  5. faltando ~15 min, DISPARA o próximo corredor         │
  │  6. espera o sucessor entrar e então desliga a máquina   │
  └─────────────────────────────────────────────────────────┘
              │                              ▲
              ▼                              │
      batimento.yml                  supabase_keepalive.yml
      (commit nos dias 1 e 15        (ping de 2 em 2 dias para o
       para o repositório não         projeto Supabase não dormir)
       ser arquivado)
```

Quando o bot se atualiza sozinho, ele encerra com **código 42** — o vigia
(`vigia_bot.ps1`) reconhece esse código e religa em 1 segundo, em vez dos 5
segundos de uma queda comum.

---

## 🛡️ Rede de segurança do auto-update

Esta é a parte mais importante do projeto: o bot puxa a `main` a cada 60 segundos
e **se reescreve em produção**. Um código errado aí derruba tudo, então há duas
redes antes de qualquer troca:

**REDE 1 — o código novo é carregado antes de substituir o arquivo.**
`_validar_candidato_por_carga()` grava o candidato num arquivo temporário e o
importa **num processo Python separado**. Só passa se o processo carregar sem
exceção, tiver a assinatura `VERSAO_BOT` e registrar os comandos slash. Um
`NameError` numa função que só é chamada depois (e que portanto o `ast.parse`
não pega) é barrado aqui.

**REDE 2 — cópia de segurança e rollback.**
Antes de trocar o arquivo, o bot copia a versão boa para `fireforce_bot.py.bak`
e abre um marcador `ff_upd_pendente.json`. O marcador só é apagado quando o bot
**termina de subir**. Se ele cair 2 vezes em menos de 10 minutos com o marcador
aberto, o arranque seguinte:

1. recoloca a versão boa a partir do `.bak`,
2. cria `ff_auto_update_pausado.flag` com o hash do código que quebrou,
3. avisa a equipe no Discord (uma vez só, e só se alguém realmente recebeu),
4. sai com código 42 para o vigia relançar já com a versão boa.

A pausa é **inteligente**: enquanto a `main` tiver exatamente o mesmo hash
quebrado, o bot se recusa a atualizar. Assim que a `main` recebe uma correção
(hash diferente), ele apaga o arquivo de pausa e volta a se atualizar sozinho.
O vigia também lê esse arquivo e deixa de baixar a `main` por cima da versão
restaurada.

> Quedas depois que o bot ficou pronto **não** contam: o fim normal do ciclo de
> 6 horas, falta de internet ou reinício do host não disparam rollback.

---

## ✅ Checagem antes de publicar

```bash
python checagem_ci.py fireforce_bot.py
```

Roda 7 verificações e devolve código 0 (aprovado) ou 1 (reprovado):

1. o arquivo é UTF-8 válido e legível
2. a sintaxe Python está correta
3. existe a assinatura `VERSAO_BOT`
4. compila de verdade (`py_compile`)
5. **carrega o módulo num processo separado** e conta os comandos slash
6. nenhuma intent privilegiada foi ligada (`members`, `presences`, `message_content`)
7. `pyflakes` não acha nenhum nome inexistente

O mesmo conjunto roda automaticamente no GitHub Actions
(`.github/workflows/ci.yml`) em todo pull request e em todo push na `main`,
junto com uma verificação de que nenhum segredo foi parar no repositório.

---

## 🚀 Rodando na sua máquina

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python fireforce_bot.py
```

As dependências têm **versão travada** de propósito: cada máquina nova do GitHub
Actions instala tudo do zero, e sem o travamento uma versão nova da biblioteca do Discord
ou do Pillow quebraria o bot sem você ter mexido em uma linha.

### Configuração

Crie um arquivo `.env` **na mesma pasta do bot** (ou use variáveis de ambiente —
elas têm prioridade):

```env
DISCORD_TOKEN=seu_token_aqui

# Supabase (backup em nuvem)
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=sua_chave
SUPABASE_ANON_KEY=sua_chave_anon
SUPABASE_ID=nome_do_seu_cofre

# Auto-update
GITHUB_TOKEN=token_para_o_bot_se_atualizar
AUTO_UPDATE=1
AUTO_UPDATE_SEGUNDOS=60
```

No GitHub, os mesmos valores ficam em **Settings → Secrets and variables →
Actions → aba Secrets** (é a aba *Secrets*, não a *Variables*). A máquina que roda
o bot é nova a cada ciclo e escreve o `.env` sozinha a partir desses segredos —
você nunca precisa editar `.env` na mão no RDP.

Sem o `DISCORD_TOKEN` o bot explica na tela, em português, o passo a passo para
conseguir um — e não derruba nada.

> 🔒 O `.env`, o banco `ffv1.db`, os logs e as flags ficam fora do Git
> (veja o `.gitignore`). Nunca publique o token.

### Intents

O bot roda **sem nenhuma intent privilegiada** (`members`, `presences` e
`message_content` ficam desligadas). Isso não é acidente: reduz o consumo para
cerca de 55 MB de RAM e dispensa aprovação do Discord. Todo o código usa
substitutos próprios (`mencao()`, `membro_do_guild()`, `_GuildRef`) em vez do
cache de membros. **Não ligue essas intents** — a checagem de CI reprova.

---

## ☁️ Supabase

O bot usa o Supabase para duas coisas diferentes:

- **`fireforce_estado`** — o cofre: banco local inteiro comprimido (gzip + base64),
  fatiado em blocos quando passa de 1,8 milhão de caracteres.
- **`ff_config`, `ff_cargos`, `ff_staff_online`, `ff_rankings`** — tabelas de
  leitura, para você consultar de fora (painel, planilha, site).

### Os segredos que este projeto usa

| Segredo | Para quê |
|---|---|
| `DISCORD_TOKEN` | O bot ligar. Único absolutamente indispensável. |
| `SUPABASE_URL` | Endereço do projeto Supabase (backup em nuvem). |
| `SUPABASE_KEY` | Chave usada nas chamadas ao Supabase. |
| `SUPABASE_ANON_KEY` | Chave de reserva: entra quando não há `SUPABASE_KEY`. |
| `SUPABASE_ID` | Nome do "cofre" onde o backup fica guardado. |
| `RDP_SENHA` | Só o workflow: cria o usuário da máquina Windows. |
| `TAILSCALE_AUTHKEY` | Só o workflow: entra na rede privada. |

`SUPABASE_SERVICE_ROLE_KEY` **não é usado por este projeto**. Ela existe no código
desde antes (é a primeira de uma fila de reserva), mas aqui o Supabase funciona
com a `SUPABASE_KEY`/`SUPABASE_ANON_KEY`. Não crie esse segredo à toa: a chave
service role ignora toda a proteção (RLS) do Supabase, então ela só deve existir
se você souber exatamente por quê.

A fila de escolha, se um dia quiser entender: o bot pega a primeira que existir
entre `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_KEY` e `SUPABASE_ANON_KEY`.

> ⚠️ **Não "endureça" o RLS do seu projeto Supabase.** Do jeito que está hoje ele
> aceita a chave que o bot usa e o backup funciona. Bloquear essa chave derruba a
> sincronização na hora.

### As tabelas

O bot **só faz upsert — ele nunca cria tabela**. As 5 tabelas precisam já existir
no seu projeto; se faltarem, a sincronização falha com
`42P01 (relation does not exist)`. Elas não fazem parte deste repositório: quem
cria é o seu projeto Supabase, do jeito que você sempre fez.

---

## 📂 Arquivos do repositório

| Arquivo | O que é |
|---|---|
| `fireforce_bot.py` | O bot inteiro. **Não divida em módulos**: o auto-update e o rollback trocam exatamente este arquivo. |
| `checagem_ci.py` | Portão de qualidade antes de publicar (também usado pelo CI). |
| `requirements.txt` | Dependências com versão travada. |
| `.github/workflows/fireforce.yml` | O corredor principal: máquina Windows, vigia e sucessão. |
| `.github/workflows/ci.yml` | Checagem automática em PR e push. |
| `.github/workflows/batimento.yml` | Commit nos dias 1 e 15 para o repositório não arquivar. |
| `.github/workflows/supabase_keepalive.yml` | Ping de 2 em 2 dias para o projeto Supabase não dormir. |
| `ANALISE_TECNICA.md` | Análise técnica completa: arquitetura, pilares de qualidade e achados. |

Em tempo de execução o bot cria, **na pasta dele**, `ffv1.db`, `fireforce.log`,
`fireforce_bot.py.bak` e as flags — todos ignorados pelo Git.

---

## 🎮 Os 45 comandos

O `/help` filtra sozinho pelo cargo de quem chama (Jogador, Suporte, ADM,
Dono & Gerente, Dono).

<details>
<summary>Clique para ver a lista completa</summary>

| Comando | Descrição |
|---|---|
| `/addsaldo` | 🛠️ Ajustar carteira pessoal ou de trabalho (Dono e Gerente) |
| `/admin` | 🎛️ Central executiva unificada (Patentes, Vaga VIP, Manutenção, Relatório, Blacklist e Backup) |
| `/anunciar` | 📢 Preparar e revisar um anúncio oficial antes de publicar |
| `/backup` | ☁️ Salvar o estado do bot no Supabase agora |
| `/blacklist` | 🚫 Gerenciar Blacklist de IDs do Free Fire (banir, remover e listar) |
| `/booyah` | 🔥 Definir o canal de Booyah ou publicar um Booyah oficial com foto FF, nick e clã |
| `/carteira` | 💰 Abrir sua carteira privada |
| `/config` | ⚙️ Ajustes financeiros, bloqueio de diário, canais de log e rodízio do suporte |
| `/cupom` | 🎟️ Aplicar cupom de desconto na sua inscrição |
| `/dados` | ☁️ Ver o status da sincronização (Supabase, linhas, último envio) |
| `/diagnostico` | 🩺 Conferir permissões, cargos, categorias e integrações |
| `/diario` | 🔥 Criar um painel fixo de inscrições no canal atual |
| `/divulgacao` | 📣 Publicar painel minimalista para contratação de divulgação paga (Dono e Gerente) |
| `/embed` | 📝 Criar e personalizar uma embed |
| `/evento` | 🎉 Criar e gerenciar eventos (Dono e Gerente) |
| `/extrato` | 📜 Ver o extrato completo da carteira |
| `/help` | ❓ Ver os comandos disponíveis para o seu cargo |
| `/info` | ℹ️ Exibir informações técnicas do bot |
| `/ish` | 🔑 Definir o ID e a Senha da sala de um diário |
| `/lines` | ⚡ Gerenciar suas Lines Salvas e Favoritas (Solo, Duo, Trio, Squad) |
| `/logs` | 🧾 Configurar e ver os logs do bot (Dono e Gerente) |
| `/meu_ticket_fechar` | 🔒 Fechar seu atendimento aberto neste canal |
| `/painel` | 📊 Gerenciar horários, preços e premiações dos diários |
| `/painelcarteira` | 💳 Publicar o painel público de acesso à carteira |
| `/painelcupom` | 🎟️ Painel de administração de cupons de desconto |
| `/painelranking` | 🏆 Publicar o painel minimalista de rankings no canal |
| `/parceria` | 🤝 Gerenciar sistema de parcerias e Vitrine de Parceiros (Dono e Gerente) |
| `/perfil` | 🎖️ Ficha competitiva HD: card visual, patente, vitórias, winrate e sequência |
| `/pix` | 🏦 Cadastrar chave PIX do ADM ou consultar ganhos no PIX |
| `/relatorio` | 📊 Painel executivo de faturamento, ADMs e ocupação de horários |
| `/removervitoria` | 📉 Remover vitórias lançadas por engano (preserva seguidas/diários e ajusta patente) |
| `/reparar_pendencias` | 🩺 Dono: corrigir tickets órfãos e pendências travadas |
| `/reset` | ⚠️ Arquivar diários e remover painéis de inscrição |
| `/restaurar` | ☁️ Restaurar o estado salvo no Supabase |
| `/saude` | 🩺 Como está o bot agora: no ar, Supabase e pendências |
| `/setup` | ⚙️ Configurar cargos e categorias do servidor |
| `/staff` | 👥 Painel minimalista de status da equipe |
| `/ticket` | 🎫 Publicar painel minimalista de atendimento no canal |
| `/tickets_fechar` | 🧹 Dono: fechar tickets regulares por filtro |
| `/trabalho` | 💼 Carteira de trabalho semanal do Suporte |
| `/transferir` | 📤 Transferir saldo pra outro jogador |
| `/vaga` | 📢 Anunciar uma vaga na equipe (Dono e Gerente) |
| `/vagavip` | 🎟️ [Discreto] Liberar Vaga VIP / Passe Livre ou sortear 3 membros ativos |
| `/verificar` | 🔍 Consultar um ID do Free Fire e checar se está na Blacklist |
| `/vitoria` | 🏆 Registrar uma vitória (top 1) no ranking de um jogador |

</details>

---

## 🔧 Antes de mexer no código

1. **Rode `python checagem_ci.py`** — se reprovar, não publique.
2. **Não ligue intents privilegiadas.** O CI reprova e o consumo de RAM dispara.
3. **Não divida o arquivo em módulos.** O auto-update usa `os.replace` num único
   arquivo e o vigia usa `git checkout -f origin/main -- fireforce_bot.py`.
4. **Mexeu em dinheiro?** Use `BEGIN IMMEDIATE` + uma transação só, como em
   `transferir_saldo_atomic` e `movimentar_saldo`. Nunca duas conexões.
5. **Criou uma View ou Modal com `custom_id` fixo?** Registre no
   `_roteador_dinamico_componentes_persistentes`, senão os botões publicados
   morrem depois de um restart.
6. **Subiu a versão?** Bata `VERSAO_BOT`. É ela que aparece no log de cada
   servidor como `vX ➜ vY` quando o bot se atualiza.
7. **Não coloque segredo no código.** Use `.env` ou os segredos do GitHub.

---

*Feito para a Liga Oficial de Diários Free Fire.*
