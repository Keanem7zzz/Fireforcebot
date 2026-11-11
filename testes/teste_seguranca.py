"""Testes de segurança do Fire Force Bot.

O que este arquivo prova, em português:

  1. REGRESSÃO — nada do que o bot já fazia pode ter mudado de comportamento:
     PIX (código do Banco Central conferido campo a campo), carteira, patentes,
     intents desligadas e constantes que são contrato com o vigia.

  2. REDE DE SEGURANÇA DO AUTO-UPDATE — o bot se reescreve em produção a cada
     60s, então este é o teste mais importante do projeto:
       • um código QUEBRADO é recusado ANTES de substituir o arquivo;
       • se a versão nova cair 2x antes de o bot ficar pronto, ele volta sozinho
         para a cópia de segurança e pausa o auto-update;
       • a pausa é inteligente: continua enquanto a `main` tiver o mesmo código
         quebrado e some sozinha quando a `main` é corrigida;
       • queda antiga (fim do ciclo de 6h, falta de internet) NÃO dispara volta.

  3. BANCO E IMAGENS — init_db idempotente, saldo negativo bloqueado,
     transferência atômica lançando os dois lados, e os três renderizadores
     Pillow produzindo PNG válido.

  4. CACHE DO PAINEL — o painel para de gastar 8 chamadas HTTP por minuto quando
     nada mudou, mas continua respondendo TODO clique de usuário e se cura
     sozinho se alguém apagar a mensagem no Discord.

  5. /SAUDE — o comando mostra o estado verdadeiro do auto-update: "ativo",
     "desativado" ou "PAUSADO (a versão X quebrou e foi revertida)". Um arquivo
     de pausa corrompido não pode derrubar o comando.

Como rodar:
    python testes/teste_seguranca.py

Não precisa de token do Discord, nem de internet, nem de Supabase. Nada aqui
toca o banco real (ffv1.db): todo arquivo de trabalho é criado numa pasta
temporária (FF_TESTES_DIR, padrão /tmp/testes_fireforce).

Devolve código 0 se tudo passou e 1 se qualquer coisa falhou.
"""
import importlib.util, os, sys, json, time, math, asyncio, shutil, io, hashlib

AQUI = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(AQUI)
TRABALHO = os.environ.get("FF_TESTES_DIR", "/tmp/testes_fireforce")
ARQ_BOT = os.path.join(REPO, "fireforce_bot.py")
ARQ_BOA = os.path.join(TRABALHO, "versao_boa.py")
ARQ_RUIM = os.path.join(TRABALHO, "versao_ruim.py")

# Prepara a área de trabalho: uma cópia boa do bot e uma versão quebrada de
# propósito (chama uma função que não existe), para exercitar as duas redes.
shutil.rmtree(TRABALHO, ignore_errors=True)
os.makedirs(TRABALHO)
_codigo = open(ARQ_BOT, "rb").read()
open(ARQ_BOA, "wb").write(_codigo)
open(ARQ_RUIM, "wb").write(_codigo + b"\nX = funcao_que_nao_existe()\n")

spec = importlib.util.spec_from_file_location("ff", ARQ_BOT)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

ok = falha = 0
def chk(nome, cond, extra=""):
    global ok, falha
    if cond: ok += 1; print(f"  ✅ {nome}")
    else: falha += 1; print(f"  ❌ {nome} — veio {extra!r}")
def titulo(t): print(f"\n═══ {t} ═══")

VERSAO_ATUAL = m.VERSAO_BOT

# ══════════════════════════════════════════════════════════════
#  PARTE 1 — REGRESSÃO: nada do que já existia pode ter mudado
# ══════════════════════════════════════════════════════════════
titulo("PARTE 1 — regressão (identidade, PIX, carteira, patentes)")
chk(f"VERSAO_BOT declarada ({VERSAO_ATUAL}) tem formato x.y[.z]",
    bool(__import__("re").fullmatch(r"\d+\.\d+(\.\d+)?", VERSAO_ATUAL)), VERSAO_ATUAL)
chk("_HASH_CODIGO_INICIAL é sha256 do arquivo", len(m._HASH_CODIGO_INICIAL) == 64 and
    m._HASH_CODIGO_INICIAL == m._calcular_sha256_arquivo(m._ARQUIVO_BOT_PATH))
chk("comandos slash registrados (piso 45)", len(m.bot.tree.get_commands()) >= 45, len(m.bot.tree.get_commands()))
inten = m.discord.Intents.default()
for f in ("members", "presences", "message_content"):
    chk(f"intent privilegiada '{f}' desligada", getattr(inten, f) is False)
chk('_crc16("123456789") == 29B1 (valor de referência do Bacen)', m._crc16("123456789") == "29B1")

for texto, esp in [("10",10.0),("10,50",10.5),("R$ 1.234,56",1234.56),("1234.56",1234.56),
                   ("0",None),("  55  ",55.0),("1.000",1.0),("abc",None),("",None),("-5",None)]:
    chk(f"parse_valor({texto!r}) == {esp!r}", m.parse_valor(texto) == esp)
chk("formatar_moeda(1234.5) == 'R$ 1.234,50'", m.formatar_moeda(1234.5) == "R$ 1.234,50")

pts = [m.calcular_patente_por_pontos(p) for p in (0,10,50,100,150,200,250,300,349,350,500)]
chk("patentes oficiais (piso 12)", len(m.PATENTES_OFICIAIS) >= 12, len(m.PATENTES_OFICIAIS))
chk("0 pts -> Bronze", pts[0]["nome"] == "Bronze")
chk("349 -> Desafiante de Honra, falta 1 pt", pts[8]["nome"] == "Desafiante de Honra" and pts[8]["faltam_pts"] == 1)
chk("350 -> Hacker (teto)", pts[9]["nome"] == "Hacker" and pts[9]["proxima_patente"] is None)
chk("500 -> continua Hacker", pts[10]["nome"] == "Hacker")
chk("patentes nunca descem", [p["indice"] for p in pts] == sorted(p["indice"] for p in pts))

def validar_emv(p):
    if not isinstance(p, str) or len(p) < 30: return False, "curto"
    campos, i = {}, 0
    while i + 4 <= len(p):
        tag, tam = p[i:i+2], p[i+2:i+4]
        if not (tag.isdigit() and tam.isdigit()): return False, f"TLV inválido em {i}"
        v = p[i+4:i+4+int(tam)]
        if len(v) != int(tam): return False, "comprimento não bate"
        campos[tag] = v; i += 4 + int(tam)
    if i != len(p): return False, "sobraram bytes"
    if len(campos.get("63","")) != 4: return False, "sem CRC"
    if m._crc16(p[:-4]) != campos["63"]: return False, "CRC não confere"
    if campos.get("00") != "01": return False, "campo 00 != 01"
    if campos.get("58") != "BR": return False, "país != BR"
    if campos.get("53") != "986": return False, "moeda != 986"
    if "62070503***" not in p: return False, "62/05 não é ***"
    return True, "ok"

for chave, tipo, titular, valor in [("teste@email.com","aleatoria","FIRE FORCE",0.0),
        ("01234567890","cpf","José Áçênto",10.0), ("12345678000195","cnpj","Loja LTDA",1234.56),
        ("+5511999998888","celular","Suporte FF",0.01),
        ("999988887777666655554444333322221111","aleatoria","Chave Longa",99999.99),
        ("k","aleatoria","A"*60,5.0), ("x","aleatoria","Çedilha ãõ ü",7.77), ("y","aleatoria","Ok",1.0)]:
    p = m.gerar_payload_pix(chave, tipo, titular, valor)
    bom, pq = validar_emv(p)
    chk(f"PIX {tipo} {titular[:10]!r} R${valor} — {pq}", bom)
chk("titular acima de 25 chars é truncado", "5925" in m.gerar_payload_pix("k","aleatoria","A"*60,5.0))
chk("payload 100% ASCII", all(ord(c) < 128 for c in m.gerar_payload_pix("x","aleatoria","Çedilla ãõ",7.77)))

# Só o que é CONTRATO com coisa de fora (vigia, CI, Supabase). As demais são
# ajuste fino e podem mudar sem quebrar nada — testá-las seria travar o projeto.
chk("AUTO_UPDATE_EXIT_CODE == 42 (o vigia depende disso)", m.AUTO_UPDATE_EXIT_CODE == 42, m.AUTO_UPDATE_EXIT_CODE)
chk("SUPABASE_CHUNK_MAX_CHARS abaixo do teto do PostgREST", 0 < m.SUPABASE_CHUNK_MAX_CHARS <= 8_000_000, m.SUPABASE_CHUNK_MAX_CHARS)
chk("_QUEDAS_ATE_ROLLBACK >= 2 (1 queda só não é prova de nada)", m._QUEDAS_ATE_ROLLBACK >= 2, m._QUEDAS_ATE_ROLLBACK)
chk("_JANELA_QUEDA_RAPIDA_SEG cobre o arranque", 60 <= m._JANELA_QUEDA_RAPIDA_SEG <= 3600, m._JANELA_QUEDA_RAPIDA_SEG)
chk("_PAINEL_ASSINATURA_VALIDADE_SEG cura mensagem apagada", 0 < m._PAINEL_ASSINATURA_VALIDADE_SEG <= 900, m._PAINEL_ASSINATURA_VALIDADE_SEG)
for fn in ("_ConexaoSQLiteBlindada","_roteador_dinamico_componentes_persistentes","transferir_saldo_atomic",
           "movimentar_saldo","_lock_aprovacao","init_db","_registrar_e_responder_erro_ui"):
    chk(f"pilar antigo '{fn}' presente", hasattr(m, fn))
chk("supabase_configurado() é False sem secrets", m.supabase_configurado() is False)

# ══════════════════════════════════════════════════════════════
#  PARTE 2 — REDE DE SEGURANÇA DO AUTO-UPDATE (Lote 2)
# ══════════════════════════════════════════════════════════════
titulo("PARTE 2 — rede de segurança do auto-update")
SANDBOX = os.path.join(TRABALHO, "sandbox"); shutil.rmtree(SANDBOX, ignore_errors=True); os.makedirs(SANDBOX)
def apontar(nome_bot="fireforce_bot.py"):
    m._ARQUIVO_BOT_PATH = os.path.join(SANDBOX, nome_bot); m._DIRETORIO_BOT = SANDBOX
    m._ARQUIVO_BAK = m._ARQUIVO_BOT_PATH + ".bak"
    m._ARQUIVO_CANDIDATO = m._ARQUIVO_BOT_PATH + ".candidate"
    m._ARQUIVO_UPD_PENDENTE = os.path.join(SANDBOX, "ff_upd_pendente.json")
    m._ARQUIVO_PAUSA_AUTO_UPDATE = os.path.join(SANDBOX, "ff_auto_update_pausado.flag")
    m.ARQUIVO_LOG = os.path.join(SANDBOX, "fireforce.log")
apontar()
BOA, RUIM = _codigo, _codigo + b"\nX = funcao_que_nao_existe()\n"

print("  --- REDE 1: carregar o código novo num processo à parte ---")
r, d = m._validar_candidato_por_carga(BOA)
chk("código BOM é aceito", r is True, d)
chk("  e reporta quantos comandos carregaram", "comandos" in d, d)
r2, d2 = m._validar_candidato_por_carga(RUIM)
chk("código QUEBRADO é recusado", r2 is False, d2)
chk("  motivo cita NameError", "QUEBRA ao ligar" in d2 and "NameError" in d2, d2)
chk("arquivo candidato foi limpo", not os.path.exists(m._ARQUIVO_CANDIDATO))

print("  --- REDE 2: cópia .bak + marcador de atualização pendente ---")
with open(m._ARQUIVO_BOT_PATH,"wb") as f: f.write(BOA)
chk("marcador criado", m._marcar_atualizacao_pendente("99.9","abc1234","hash_ruim_x") is True)
chk("  .bak existe com a versão BOA", open(m._ARQUIVO_BAK,"rb").read() == BOA)
mk = json.load(open(m._ARQUIVO_UPD_PENDENTE, encoding="utf-8"))
chk("  marcador tem de/para/commit/hash/quedas", all(k in mk for k in ("de","para","commit","hash","quedas")))
chk("  quedas começa em 0", mk["quedas"] == 0)
m._confirmar_versao_estavel()
chk("bot subiu até o fim -> marcador e .bak liberados",
    not os.path.exists(m._ARQUIVO_UPD_PENDENTE) and not os.path.exists(m._ARQUIVO_BAK))

print("  --- simulação completa: atualização ruim cai 2x e volta sozinha ---")
m._marcar_atualizacao_pendente("99.9","deadbee","hash_ruim_x")
chk("  .bak capturou a versão BOA (ordem real)", open(m._ARQUIVO_BAK,"rb").read() == BOA)
m._aplicar_arquivos_git_sync(RUIM)
chk("  disco agora tem a versão RUIM", open(m._ARQUIVO_BOT_PATH,"rb").read() == RUIM)
try: m._verificar_rollback_no_arranque(); s1 = False
except SystemExit as e: s1 = e.code
chk("1ª queda: ainda NÃO volta", s1 is False)
chk("  contador foi a 1", json.load(open(m._ARQUIVO_UPD_PENDENTE, encoding="utf-8"))["quedas"] == 1)
try: m._verificar_rollback_no_arranque(); cod = None
except SystemExit as e: cod = e.code
chk(f"2ª queda: sai com código {m.AUTO_UPDATE_EXIT_CODE} (vigia relança em 1s)", cod == m.AUTO_UPDATE_EXIT_CODE, cod)
chk("  arquivo do bot VOLTOU para a versão boa", open(m._ARQUIVO_BOT_PATH,"rb").read() == BOA)
chk("  marcador e .bak apagados", not os.path.exists(m._ARQUIVO_UPD_PENDENTE) and not os.path.exists(m._ARQUIVO_BAK))
pausa = m._ler_pausa_auto_update()
chk("  arquivo de pausa criado", bool(pausa))
chk("  pausa guarda o hash ruim", pausa.get("hash_ruim") == "hash_ruim_x")
chk("  pausa diz a versão restaurada", pausa.get("versao_restaurada") == VERSAO_ATUAL, pausa.get("versao_restaurada"))
chk("  pausa começa sem avisar", pausa.get("avisado") is False)
chk("  pausa guarda o MOTIVO (sobrevive ao reinício)", "deadbee" in (pausa.get("motivo") or ""), pausa.get("motivo"))

print("  --- queda antiga NÃO é culpa da atualização ---")
with open(m._ARQUIVO_BOT_PATH,"wb") as f: f.write(BOA)
m._marcar_atualizacao_pendente("99.9","abc","h2"); m._aplicar_arquivos_git_sync(RUIM)
mk = json.load(open(m._ARQUIVO_UPD_PENDENTE, encoding="utf-8")); mk["quando"] = time.time()-5000; mk["quedas"] = 1
json.dump(mk, open(m._ARQUIVO_UPD_PENDENTE,"w",encoding="utf-8"))
m._remover_arquivo(m._ARQUIVO_PAUSA_AUTO_UPDATE)
try: m._verificar_rollback_no_arranque(); s2 = False
except SystemExit as e: s2 = e.code
chk("queda fora da janela de 10 min: NÃO volta", s2 is False)
chk("  rede limpa (fim de ciclo normal não é bug)", not os.path.exists(m._ARQUIVO_UPD_PENDENTE) and not os.path.exists(m._ARQUIVO_BAK))

print("  --- pausa inteligente: mesma main ruim x main corrigida ---")
m._HASH_CODIGO_INICIAL = hashlib.sha256(BOA.replace(b"\r\n", b"\n")).hexdigest()
m._remover_arquivo(m._ARQUIVO_UPD_PENDENTE); m._remover_arquivo(m._ARQUIVO_BAK)
with open(m._ARQUIVO_BOT_PATH,"wb") as f: f.write(BOA)
m.AUTO_UPDATE_SEGUNDOS = 60
def simular(bytes_remotos):
    m._buscar_codigo_remoto_git_sync = lambda: (bytes_remotos, "commitX", "")
    return asyncio.run(m._checar_e_aplicar_auto_update())
m._gravar_json_arquivo(m._ARQUIVO_PAUSA_AUTO_UPDATE, {
    "hash_ruim": hashlib.sha256(RUIM.replace(b"\r\n", b"\n")).hexdigest(),
    "versao_ruim":"99.9","versao_restaurada":VERSAO_ATUAL,"quando":time.time(),"avisado":True})
st, msg = simular(RUIM)
chk("main AINDA quebrada -> status 'pausado'", st == "pausado", f"{st}: {msg}")
chk("  pausa continua ativa", os.path.exists(m._ARQUIVO_PAUSA_AUTO_UPDATE))
chk("  bot não trocou de versão", open(m._ARQUIVO_BOT_PATH,"rb").read() == BOA)
CORRIGIDA = BOA.replace(f'VERSAO_BOT = "{VERSAO_ATUAL}"'.encode(), b'VERSAO_BOT = "13.9"')
chk("  (sanidade: a versão corrigida é diferente)", CORRIGIDA != BOA)
st2, msg2 = simular(CORRIGIDA)
chk("main corrigida -> pausa removida sozinha", not os.path.exists(m._ARQUIVO_PAUSA_AUTO_UPDATE))
chk("  e a atualização foi aplicada", st2 == "aplicando", f"{st2}: {msg2}")
chk("  disco agora tem a versão corrigida", open(m._ARQUIVO_BOT_PATH,"rb").read() == CORRIGIDA)

print("  --- casos-limite ---")
with open(m._ARQUIVO_BOT_PATH,"wb") as f: f.write(BOA)
m._remover_arquivo(m._ARQUIVO_UPD_PENDENTE)
with open(m._ARQUIVO_BAK,"wb") as f: f.write(RUIM)
try: m._verificar_rollback_no_arranque(); s3 = False
except SystemExit as e: s3 = e.code
chk(".bak órfão: não volta e é removido", s3 is False and not os.path.exists(m._ARQUIVO_BAK))
bak_original = m._ARQUIVO_BAK
m._ARQUIVO_BAK = os.path.join(SANDBOX, "pasta_inexistente", "x.bak")
chk("sem conseguir copiar -> atualização ABORTADA", m._marcar_atualizacao_pendente("99.9","abc","h") is False)
m._ARQUIVO_BAK = bak_original

print("  --- aviso no Discord (uma vez só, e só se alguém recebeu) ---")
with open(m._ARQUIVO_BOT_PATH,"wb") as f: f.write(BOA)
m._ROLLBACK_ACONTECEU = ""
m._marcar_atualizacao_pendente("99.9","deadbee","h3"); m._aplicar_arquivos_git_sync(RUIM)
m._verificar_rollback_no_arranque()
try: m._verificar_rollback_no_arranque()
except SystemExit: pass
class GuildFalso:
    id, name = 1, "Servidor Teste"
class BotFalso:
    guilds = [GuildFalso(), GuildFalso()]
bot_real = m.bot; m.bot = BotFalso()
enviados = []
async def registrar_log_falso(guild, t, r, corpo, cor): enviados.append((t, corpo))
m.registrar_log = registrar_log_falso
asyncio.run(m._avisar_rollback_se_pendente())
chk("aviso enviado em cada servidor (2 guilds = 2 avisos)", len(enviados) == 2, len(enviados))
if enviados:
    chk("  traz o MOTIVO real, não o genérico", f"v{VERSAO_ATUAL} para v99.9" in enviados[0][1], enviados[0][1][:150])
    chk("  diz qual versão está no ar", f"v{VERSAO_ATUAL}" in enviados[0][1])
chk("marcado como avisado", m._ler_pausa_auto_update().get("avisado") is True)
enviados.clear(); asyncio.run(m._avisar_rollback_se_pendente())
chk("o aviso NÃO se repete", len(enviados) == 0)
m.bot = type("B", (), {"guilds": []})()
m._remover_arquivo(m._ARQUIVO_PAUSA_AUTO_UPDATE)
with open(m._ARQUIVO_BOT_PATH,"wb") as f: f.write(BOA)
m._marcar_atualizacao_pendente("99.9","deadbee","h4"); m._aplicar_arquivos_git_sync(RUIM)
m._verificar_rollback_no_arranque()
try: m._verificar_rollback_no_arranque()
except SystemExit: pass
asyncio.run(m._avisar_rollback_se_pendente())
chk("sem servidor nenhum: NÃO marca como avisado", m._ler_pausa_auto_update().get("avisado") is not True)
m.bot = BotFalso(); enviados.clear()
asyncio.run(m._avisar_rollback_se_pendente())
chk("tenta de novo no próximo arranque e consegue", len(enviados) == 2 and m._ler_pausa_auto_update().get("avisado") is True)
m.bot = bot_real

# ══════════════════════════════════════════════════════════════
#  PARTE 3 — banco, carteira e renderização
# ══════════════════════════════════════════════════════════════
DBDIR = os.path.join(TRABALHO, "banco"); shutil.rmtree(DBDIR, ignore_errors=True); os.makedirs(DBDIR)
apontar()                                   # devolve os caminhos da rede p/ o sandbox
m.DATABASE_FILE = os.path.join(DBDIR, "teste.db"); m.ARQUIVO_LOG = DBDIR + "/ff.log"
GUILD, USER, USER2 = 111111111111111111, 222222222222222222, 333333333333333333

async def parte3():
    import aiosqlite
    titulo("PARTE 3 — banco de dados e carteira")
    t0 = time.time(); await m.init_db(); t1 = time.time()-t0; await m.init_db()
    chk(f"init_db idempotente (2x sem erro, {t1:.2f}s na 1ª)", True)
    async with aiosqlite.connect(m.DATABASE_FILE) as db:
        modo = (await (await db.execute("PRAGMA journal_mode")).fetchone())[0]
        bt   = (await (await db.execute("PRAGMA busy_timeout")).fetchone())[0]
        sy   = (await (await db.execute("PRAGMA synchronous")).fetchone())[0]
        tbs  = (await (await db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")).fetchone())[0]
        ixs  = (await (await db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND sql IS NOT NULL")).fetchone())[0]
    chk("WAL ligado", modo.lower() == "wal", modo)
    chk("busy_timeout = 30000 (blindagem global)", bt == 30000, bt)
    chk("synchronous = NORMAL", sy == 1, sy)
    chk("tabelas de usuário criadas (piso 36)", tbs >= 36, tbs)
    chk("índices explícitos criados (piso 12)", ixs >= 12, ixs)

    chk("saldo inicial = 0", await m.saldo_carteira(USER, GUILD) == 0)
    chk("crédito 150.75", await m.movimentar_saldo(USER, GUILD, 150.75, "deposito", "t", "d1") == 150.75)
    chk("débito 50.25 -> 100.50", await m.movimentar_saldo(USER, GUILD, -50.25, "saque", "t", "s1") == 100.50)
    chk("saldo_carteira confirma 100.50", await m.saldo_carteira(USER, GUILD) == 100.50)
    chk("saldo negativo BLOQUEADO (devolve None)", await m.movimentar_saldo(USER, GUILD, -99999.0, "saque", "t", "sn") is None)
    chk("saldo intacto após o bloqueio", await m.saldo_carteira(USER, GUILD) == 100.50)
    chk("NaN recusado", await m.movimentar_saldo(USER, GUILD, float("nan"), "d", "t", "n") is None)
    chk("infinito recusado", await m.movimentar_saldo(USER, GUILD, float("inf"), "d", "t", "i") is None)
    chk("texto recusado", await m.movimentar_saldo(USER, GUILD, "abc", "d", "t", "x") is None)
    chk("zerar exatamente é permitido", await m.movimentar_saldo(USER, GUILD, -100.50, "s", "t", "z") == 0.0)
    chk("permitir_negativo=True deixa ir a -0.01", await m.movimentar_saldo(USER, GUILD, -0.01, "s", "t", "pn", permitir_negativo=True) == -0.01)
    # Lote 3 (A11): o bloqueio tem que desfazer a transação explicitamente
    async with aiosqlite.connect(m.DATABASE_FILE) as db:
        em_tx = (await (await db.execute("PRAGMA journal_mode")).fetchone())[0]
    chk("banco segue utilizável depois do rollback explícito", em_tx.lower() == "wal", em_tx)

    await m.movimentar_saldo(USER, GUILD, 500.0, "deposito", "t", "repor")   # -0.01+500 = 499.99
    await m.movimentar_saldo(USER2, GUILD, 0.0, "deposito", "t", "criar2")
    t = await m.transferir_saldo_atomic(USER, USER2, GUILD, 100.0, "tr1")
    chk("transferência devolve os dois saldos", isinstance(t, tuple) and t == (399.99, 100.0), t)
    chk("transferir para si mesmo é recusado", await m.transferir_saldo_atomic(USER, USER, GUILD, 10.0, "x") is None)
    chk("transferir 0 é recusado", await m.transferir_saldo_atomic(USER, USER2, GUILD, 0.0, "x") is None)
    chk("transferir negativo é recusado", await m.transferir_saldo_atomic(USER, USER2, GUILD, -5.0, "x") is None)
    chk("transferir NaN é recusado", await m.transferir_saldo_atomic(USER, USER2, GUILD, float("nan"), "x") is None)
    chk("transferir mais do que tem é recusado", await m.transferir_saldo_atomic(USER, USER2, GUILD, 999999.0, "x") is None)
    chk("saldo preservado após a recusa", await m.saldo_carteira(USER, GUILD) == 399.99, await m.saldo_carteira(USER, GUILD))
    async with aiosqlite.connect(m.DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        lanc = {l["ref"]: dict(l) for l in await (await db.execute(
            "SELECT * FROM transacoes WHERE ref IN ('tr1:envio','tr1:recebimento')")).fetchall()}
    chk("os DOIS lados foram lançados no livro-razão", len(lanc) == 2, sorted(lanc))
    envio, receb = lanc.get("tr1:envio"), lanc.get("tr1:recebimento")
    chk("  lado da origem: -100.00 do tipo enviada",
        envio and envio["valor"] == -100.0 and envio["tipo"] == "transferencia_enviada"
        and envio["user_id"] == USER, envio)
    chk("  lado do destino: +100.00 do tipo recebida",
        receb and receb["valor"] == 100.0 and receb["tipo"] == "transferencia_recebida"
        and receb["user_id"] == USER2, receb)
    chk("  a soma dos dois lados é ZERO (dinheiro não some nem aparece)",
        envio and receb and round(envio["valor"] + receb["valor"], 2) == 0.0,
        ((envio or {}).get("valor"), (receb or {}).get("valor")))
    chk("  saldo_apos de cada lado bate com a carteira",
        envio and receb and envio["saldo_apos"] == 399.99 and receb["saldo_apos"] == 100.0,
        ((envio or {}).get("saldo_apos"), (receb or {}).get("saldo_apos")))

    foto = await m.snapshot_dump()
    chk("snapshot_dump gera todas as tabelas", isinstance(foto, dict) and len(foto.get("tabelas") or {}) >= 30, len(foto.get("tabelas") or {}))
    chk("snapshot carrega a versão do bot", foto.get("versao") == m.VERSAO_BOT, foto.get("versao"))

    titulo("PARTE 3b — renderização Pillow (gera os PNG de verdade)")
    from PIL import Image, ImageDraw, ImageFont
    FONTE = ImageFont.load_default()
    limpo = m._card_limpar_texto("a\x00b\nc\r\td", FONTE)
    chk("_card_limpar_texto tira bytes de controle", not any(c in limpo for c in "\x00\r\n\t"))
    chk("  e preserva o texto (tab vira espaço)", limpo == "abc d", limpo)
    chk("  com None devolve string", isinstance(m._card_limpar_texto(None, FONTE), str))
    draw = ImageDraw.Draw(Image.new("RGB", (2000, 400), "white"))
    curto = m._card_truncar_px(draw, "texto bem longo para testar o truncamento por pixels", FONTE, 60)
    chk("_card_truncar_px encurta texto largo", len(curto) < 51, curto)
    chk("  cabe no limite pedido", draw.textlength(curto, font=FONTE) <= 72, draw.textlength(curto, font=FONTE))
    chk("  com vazio usa o traço de fallback", m._card_truncar_px(draw, "", FONTE, 40) == "—")
    chk("  mantém texto que já cabe", m._card_truncar_px(draw, "oi", FONTE, 4000) == "oi")

    horario = {"horario": "20:00", "modo": "CS", "categoria": "Solo", "vagas_total": 48,
               "bloqueio_min": 10, "reserva": 200.0, "id": 1}
    slots = [{"numero": i, "nome": f"Jogador {i}", "nivel": 40+i, "patente": "Ouro",
              "vip": False, "uid": str(100000000+i)} for i in range(1, 13)]
    t0 = time.time(); png = m.renderizar_tabela_sala_png(horario, slots, ocupadas=12, atualizado_em="agora")
    chk(f"tabela renderizou ({time.time()-t0:.2f}s)", png[:8] == b"\x89PNG\r\n\x1a\n", len(png))
    img = Image.open(io.BytesIO(png)); chk(f"  tabela {img.size[0]}x{img.size[1]} px, HD", img.size[0] >= 1000 and img.size[1] >= 500, img.size)
    jogadores = [{"nome": f"P{i}", "kills": i, "pontos": i*10, "posicao": i} for i in range(1, 9)]
    t0 = time.time(); booyah = m.renderizar_card_booyah_png("CS", "Solo", "20:00", jogadores, numero_slot=1)
    chk(f"card booyah renderizou ({time.time()-t0:.2f}s)", booyah[:8] == b"\x89PNG\r\n\x1a\n", len(booyah))
    img2 = Image.open(io.BytesIO(booyah)); chk(f"  booyah {img2.size[0]}x{img2.size[1]} px, HD", img2.size[0] >= 800 and img2.size[1] >= 400, img2.size)
    dados = await m.obter_estatisticas_completas_jogador(GUILD, USER)
    for chave in ("patente","proxima_patente","pontos","vitorias","partidas","qtd_lines","faltam_pts"):
        chk(f"  contrato do perfil tem '{chave}'", chave in dados, sorted(dados)[:12])
    t0 = time.time()
    perfil = m.renderizar_card_perfil_png(user_id=USER, display_name="Testador", username="testador",
                                          guild_name="Liga FF", cargo_nome="Membro", dados=dados, avatar_bytes=None)
    chk(f"card de perfil renderizou ({time.time()-t0:.2f}s)", perfil[:8] == b"\x89PNG\r\n\x1a\n", len(perfil))
    img3 = Image.open(io.BytesIO(perfil)); chk(f"  perfil {img3.size[0]}x{img3.size[1]} px, HD", img3.size[0] >= 900 and img3.size[1] >= 500, img3.size)
    try:
        m.renderizar_card_perfil_png(user_id=USER, display_name="X", username="x", guild_name="G",
                                     cargo_nome="C", dados={k:v for k,v in dados.items() if k != "patente"})
        chk("A12 confirmado: perfil sem 'patente' estoura", False)
    except KeyError:
        chk("A12 confirmado: perfil sem 'patente' estoura com KeyError", True)

# ══════════════════════════════════════════════════════════════
#  PARTE 4 — Lote 3: cache de assinatura do painel (A5)
# ══════════════════════════════════════════════════════════════
async def parte4():
    import aiosqlite
    titulo("PARTE 4 — cache de assinatura do painel (A5)")
    from datetime import timedelta
    # guild/canal/mensagem falsos que CONTAM as chamadas HTTP
    class MsgFalso:
        def __init__(self, mid): self.id, self.components = mid, [object()]
        edits = 0
        async def edit(self, **kw): MsgFalso.edits += 1; self.ultimo = kw
    class CanalFalso:
        def __init__(self, mid): self.id, self.mid = 555, mid
        fetches = 0; sends = 0
        async def fetch_message(self, mid):
            CanalFalso.fetches += 1
            if mid != self.mid:
                from types import SimpleNamespace
                raise m.discord.NotFound(SimpleNamespace(status=404, reason="Not Found"),
                                         {"code": 10008, "message": "Unknown Message"})
            return MsgFalso(mid)
        async def send(self, **kw):
            CanalFalso.sends += 1
            self.mid = 999000 + CanalFalso.sends
            return MsgFalso(self.mid)
    class GuildFalso:
        def __init__(self, gid, canal): self.id, self._c = gid, canal
        def get_channel(self, cid): return self._c if cid == self._c.id else None

    agora = m.agora_brt() + timedelta(hours=3)
    hhmm = agora.strftime("%H:%M")
    async with aiosqlite.connect(m.DATABASE_FILE) as db:
        await db.execute("INSERT INTO paineis (id, guild_id, channel_id, message_id, tipo, categoria, repetir_diario) "
                         "VALUES (777, ?, 555, 424242, 'solo', 'basico', 0)", (GUILD,))
        for i, hora in enumerate((hhmm, (agora+timedelta(hours=1)).strftime("%H:%M"))):
            await db.execute("INSERT INTO horarios (id, guild_id, painel_id, tipo, categoria, horario, valor, "
                             "premiacao, vagas_total, lotes_usados, ativo, data_ciclo, encerrado_hoje) "
                             "VALUES (?, ?, 777, 'solo', 'basico', ?, 25.0, 'R$ 100', 48, 0, 1, ?, 0)",
                             (8800+i, GUILD, hora, m.agora_brt().strftime("%Y-%m-%d")))
        await db.execute("INSERT INTO slots (horario_id, guild_id, comprador_id, comprador_nome, numero, confirmado, criado_em) "
                         "VALUES (8800, ?, ?, 'Comprador Um', 1, 1, ?)", (GUILD, USER, m.agora_brt().isoformat()))
        await db.commit()
    canal = CanalFalso(424242); guild = GuildFalso(GUILD, canal)
    m._PAINEL_ASSINATURA_CACHE.clear()

    await m.rebuild_painel(guild, 777)
    chk("1ª chamada publica o painel", MsgFalso.edits == 1 and CanalFalso.fetches == 1, (MsgFalso.edits, CanalFalso.fetches))
    chk("  assinatura foi guardada", 777 in m._PAINEL_ASSINATURA_CACHE)

    MsgFalso.edits = CanalFalso.fetches = 0
    for _ in range(4): await m.rebuild_painel(guild, 777)
    chk("4 chamadas seguidas sem mudança -> ZERO HTTP", MsgFalso.edits == 0 and CanalFalso.fetches == 0, (MsgFalso.edits, CanalFalso.fetches))

    MsgFalso.edits = CanalFalso.fetches = 0
    async with aiosqlite.connect(m.DATABASE_FILE) as db:      # alguém compra uma vaga
        await db.execute("INSERT INTO slots (horario_id, guild_id, comprador_id, comprador_nome, numero, confirmado, criado_em) "
                         "VALUES (8800, ?, ?, 'Comprador Dois', 2, 1, ?)", (GUILD, USER2, m.agora_brt().isoformat()))
        await db.commit()
    await m.rebuild_painel(guild, 777)
    chk("mudou no banco -> o painel é reeditado na hora", MsgFalso.edits == 1, MsgFalso.edits)

    MsgFalso.edits = CanalFalso.fetches = 0
    m._PAINEL_ASSINATURA_CACHE.clear()
    await m.rebuild_painel(guild, 777, page=0)                 # sem interaction = caminho de fundo
    chk("cache limpo -> republica (não fica preso no vazio)", MsgFalso.edits == 1, MsgFalso.edits)

    # clique de usuário NUNCA pode ser dispensado: o edit É a resposta ao clique
    MsgFalso.edits = CanalFalso.fetches = 0
    class InteracaoFalsa:
        def __init__(self): self.message = MsgFalso(424242); self.chamadas = 0
        class _Resp:
            def __init__(self, dono): self.d = dono
            async def edit_message(self, **kw): self.d.chamadas += 1
        @property
        def response(self): return InteracaoFalsa._Resp(self)
    inter = InteracaoFalsa()
    await m.rebuild_painel(guild, 777, interaction=inter)
    chk("clique do usuário responde SEMPRE (mesmo com cache cheio)", inter.chamadas == 1, inter.chamadas)
    chk("  e não usa fetch_message (é resposta, não edição avulsa)", CanalFalso.fetches == 0, CanalFalso.fetches)

    # mensagem apagada no Discord -> recria e não fica preso na assinatura velha
    MsgFalso.edits = CanalFalso.fetches = CanalFalso.sends = 0
    canal.mid = 1                                              # força NotFound
    await m.rebuild_painel(guild, 777)
    chk("mensagem sumiu DENTRO da validade -> ainda economiza HTTP", CanalFalso.sends == 0, CanalFalso.sends)
    validade_original = m._PAINEL_ASSINATURA_VALIDADE_SEG
    m._PAINEL_ASSINATURA_VALIDADE_SEG = 0                      # simula o prazo vencendo
    await m.rebuild_painel(guild, 777)
    chk("prazo vencido -> recria a mensagem sozinha", CanalFalso.sends == 1, CanalFalso.sends)
    chk("  e o cache tem mesmo prazo de validade", validade_original == 300, validade_original)
    m._PAINEL_ASSINATURA_VALIDADE_SEG = validade_original
    async with aiosqlite.connect(m.DATABASE_FILE) as db:
        novo_id = (await (await db.execute("SELECT message_id FROM paineis WHERE id=777")).fetchone())[0]
    chk("  e grava o novo message_id no banco", novo_id != 424242, novo_id)

    chk("cache tem teto (não cresce para sempre)", m._PAINEL_ASSINATURA_MAX == 300, m._PAINEL_ASSINATURA_MAX)

# ══════════════════════════════════════════════════════════════
#  PARTE 5 — /saude mostra o estado real do auto-update
# ══════════════════════════════════════════════════════════════
async def parte5():
    titulo("PARTE 5 — /saude reflete o estado do auto-update")
    class Usuario: id, name, bot = 1, "Dono", False
    class Guild:   id, name = GUILD, "Liga Teste"
    class Followup:
        def __init__(self_, d): self_.d = d
        async def send(self_, **kw): self_.d.enviado = kw
    class Resp:
        def __init__(self_, d): self_.d = d
        async def send_message(self_, **kw): self_.d.enviado = kw
        async def defer(self_, **kw): self_.d.deferido = True
    class Inter:
        def __init__(self_):
            self_.enviado, self_.deferido, self_.guild = None, False, Guild()
            self_.user = Usuario(); self_.response = Resp(self_); self_.followup = Followup(self_)
    dono_original = m.e_dono_ou_gerente
    m.e_dono_ou_gerente = lambda u: asyncio.sleep(0, True)
    cb = m.cmd_saude.callback
    def corpo(it):
        e = (it.enviado or {}).get("embed")
        return "\n".join(f"{f.name}\n{f.value}" for f in e.fields) if e else ""
    try:
        pausa_original = m._ARQUIVO_PAUSA_AUTO_UPDATE
        m._ARQUIVO_PAUSA_AUTO_UPDATE = os.path.join(DBDIR, "pausa.flag")
        for rotulo, dados in (("livre", None), ("pausado", {
                "hash_ruim": "abc", "versao_ruim": "99.9", "versao_restaurada": m.VERSAO_BOT,
                "motivo": "a main quebrou", "quando": time.time(), "avisado": True})):
            if dados:
                json.dump(dados, open(m._ARQUIVO_PAUSA_AUTO_UPDATE, "w", encoding="utf-8"))
            else:
                m._remover_arquivo(m._ARQUIVO_PAUSA_AUTO_UPDATE)
            it = Inter(); await cb(it); c = corpo(it)
            chk(f"/saude responde com o auto-update {rotulo}", it.deferido and bool(it.enviado))
            chk(f"  mostra a versão v{m.VERSAO_BOT} e o commit",
                f"v{m.VERSAO_BOT}" in c and "Commit: `" in c, c[:200])
            if dados:
                chk("  mostra PAUSADO e qual versão quebrou", "PAUSADO" in c and "99.9" in c, c[:300])
                chk("  promete voltar sozinho quando a main corrigir", "Volta a atualizar sozinho" in c)
            else:
                chk("  mostra ativo/desativado, nunca PAUSADO",
                    (("✅ ativo" in c) or ("⏸️ desativado" in c)) and "PAUSADO" not in c, c[:300])

        # arquivo de pausa corrompido não pode derrubar o comando
        open(m._ARQUIVO_PAUSA_AUTO_UPDATE, "w", encoding="utf-8").write("{json quebrado")
        it = Inter(); await cb(it)
        chk("/saude sobrevive a arquivo de pausa corrompido", bool(it.enviado) and "PAUSADO" not in corpo(it))

        # fora do servidor, recusa com educação
        it = Inter(); it.guild = None; await cb(it)
        chk("/saude recusa fora do servidor", "Só no servidor" in ((it.enviado or {}).get("embed").title or ""))
        m._ARQUIVO_PAUSA_AUTO_UPDATE = pausa_original
    finally:
        m.e_dono_ou_gerente = dono_original

asyncio.run(parte3())
asyncio.run(parte4())
asyncio.run(parte5())

print(f"\n{'='*60}\n  SUITE COMPLETA: {ok} passaram, {falha} falharam\n{'='*60}")
sys.exit(1 if falha else 0)
