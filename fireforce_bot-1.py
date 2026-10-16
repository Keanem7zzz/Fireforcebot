# ══════════════════════════════════════════════════════════════
#  🔥 FIRE FORCE — BOT PREMIUM v10.0
#  Liga de Diário Free Fire
#
#  • Consulta de ID do Free Fire confiável (corrida de provedores + regiões
#    + cache de 24h + disjuntor) — seção 'CONSULTA DE ID FREE FIRE'
#  • Tabela do diário em TEXTO: "1. (nick)" — sem imagem, sem contador
#  • Vaga e acesso liberados depois do pagamento aprovado (staff, saldo ou LivePix)
#  • CARTEIRA: depósito/saque PIX via LivePix, transferência, saldo que paga vaga
#  • COMISSÃO DE ADM 25% (R$ 2,50 a cada R$ 10,00) + LOGS + reserva de R$ 200
#
#  pip install discord.py aiohttp qrcode[pil] aiosqlite Pillow
# ══════════════════════════════════════════════════════════════
import sys
import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import aiohttp
import base64
import gzip
import json
import logging
import os
import re
import time
import qrcode
import io
import asyncio
import datetime
from typing import Optional, List, Dict

# ==================== .env DA PASTA DO BOT ====================
def _carregar_env_do_arquivo() -> int:
    """Lê o .env que fica na MESMA pasta do bot (se existir).

    Serve pra guardar o token e as chaves num arquivo .env, sem mexer no
    código: vale pra rodar no PC, no RDP ou em qualquer host. O que já estiver
    nas variáveis de ambiente (GitHub Actions/Segredos) tem PRIORIDADE.

    Aceita linhas "CHAVE=valor", comentários com # e aspas no valor.
    """
    try:
        pasta = os.path.dirname(os.path.abspath(__file__))
    except Exception:
        pasta = "."
    total = 0
    for nome in (".env", "config.env"):
        caminho = os.path.join(pasta, nome)
        if not os.path.exists(caminho):
            continue
        try:
            with open(caminho, "r", encoding="utf-8-sig", errors="replace") as arquivo:
                for linha in arquivo:
                    linha = linha.strip()
                    if not linha or linha.startswith("#") or "=" not in linha:
                        continue
                    chave, _, valor = linha.partition("=")
                    chave = chave.strip().lstrip("export ").strip()
                    valor = valor.strip().strip('"').strip("'")
                    if chave and valor and chave not in os.environ:
                        os.environ[chave] = valor
                        total += 1
        except Exception:
            continue
    return total


_ENV_LIDOS = _carregar_env_do_arquivo()

# ==================== CONFIGURAÇÃO GLOBAL ====================
TOKEN = "SEU_TOKEN_AQUI"
DATABASE_FILE = "fireforce_v10.db"
VERSAO_BOT = "10.0"

# Usava uma versão antiga? O bot renomeia o banco sozinho (nada se perde).
for _antigo in ("fireforce_v4.db", "fireforce_v9.db", "fireforce_v6.db"):
    if (not os.path.exists(DATABASE_FILE)) and os.path.exists(_antigo):
        try:
            os.rename(_antigo, DATABASE_FILE)
            print(f"  📦 Banco antigo migrado: {_antigo} → {DATABASE_FILE}")
        except Exception:
            pass

# ==================== CARTEIRA • LIVEPIX • LOGS ====================
# Credenciais da API oficial do LivePix (livepix.gg → Configurações → API).
# Pode ficar vazio: o bot funciona no modo manual (a equipe confirma na mão).
LIVEPIX_CLIENT_ID = os.getenv("LIVEPIX_CLIENT_ID", "")
LIVEPIX_CLIENT_SECRET = os.getenv("LIVEPIX_CLIENT_SECRET", "")
# Permissões pedidas no OAuth2. Se a LivePix recusar, use o padrão documentado:
#   "account:read wallet:read webhooks"
LIVEPIX_SCOPES = os.getenv("LIVEPIX_SCOPES", "account:read wallet:read webhooks")
LIVEPIX_OAUTH_URL = "https://oauth.livepix.gg/oauth2/token"
LIVEPIX_API = "https://api.livepix.gg/v2"
LIVEPIX_PAINEL = "https://livepix.gg"

CARTEIRA_RESERVA = 200.0        # R$ que a org SEMPRE tenta manter livres
CARTEIRA_COMISSAO_PCT = 25.0    # R$ 2,50 a cada R$ 10,00 → 25% pro ADM
CARTEIRA_SAQUE_MIN = 5.0
CARTEIRA_DEPOSITO_MIN = 1.0
CARTEIRA_JANELA_MIN = 5         # janela da confirmação automática (minutos)
LIVEPIX_INTERVALO = 25          # segundos entre consultas à LivePix
LIVEPIX_PAGAMENTOS_LIMITE = 50  # quantos pagamentos o bot lê por consulta
LIVEPIX_LIMITE_BOOT = 200       # varredura maior no arranque (bot ficou fora)
ARQUIVO_LOG = "fireforce.log"
LOG_TAMANHO_MAX = 2 * 1024 * 1024
TICKET_FECHAR_SEGUNDOS = 15      # espera antes de apagar o canal do atendimento
DEPOSITO_FECHAR_SEGUNDOS = 20    # espera antes de apagar o canal do depósito

_CACHE_LOGS = {}                # guild_id -> (canal_id, timestamp)
_ULTIMO_AVISO_RESERVA = {}      # guild_id -> timestamp do aviso de caixa baixo

# Fuso horário oficial de Brasília (UTC-3)
TZ_BRASILIA = datetime.timezone(datetime.timedelta(hours=-3))

def agora_brt() -> datetime.datetime:
    """Retorna o horário atual ajustado para o Fuso de Brasília (UTC-3)"""
    return datetime.datetime.now(TZ_BRASILIA)

CORES_DICCIONARIO = {
    "Vermelho": 0xFF0000,
    "Vermelho Escuro": 0x8B0000,
    "Carmesim": 0xDC143C,
    "Laranja": 0xFF8C00,
    "Laranja Claro": 0xFFA500,
    "Âmbar": 0xFFBF00,
    "Amarelo": 0xFFD700,
    "Verde": 0x00FF00,
    "Verde Escuro": 0x006400,
    "Esmeralda": 0x2ECC71,
    "Verde Lima": 0x32CD32,
    "Menta": 0x00FF7F,
    "Azul": 0x3498DB,
    "Azul Escuro": 0x00008B,
    "Azul Royal": 0x4169E1,
    "Turquesa": 0x00CED1,
    "Ciano": 0x00FFFF,
    "Roxo": 0x9B59B6,
    "Roxo Escuro": 0x800080,
    "Violeta": 0xEE82EE,
    "Magenta": 0xFF00FF,
    "Rosa": 0xFF69B4,
    "Rosa Choque": 0xFF1493,
    "Coral": 0xFF7F50,
    "Dourado": 0xF1C40F,
    "Prata": 0xBCC0C0,
    "Bronze": 0xCD7F32,
    "Índigo": 0x4B0082,
    "Teal": 0x008080,
    "Cinza": 0x95A5A6,
    "Cinza Escuro": 0x2C3E50,
    "Branco": 0xFEFEFE,
    "Preto": 0x010101,
    "Fire Force": 0xFF4500,
}

LOTES_POR_MODO = {
    "solo": 48,
    "duo": 24,
    "trio": 16,
    "squad": 12
}

JOGADORES_POR_LOTE = {
    "solo": 1,
    "duo": 2,
    "trio": 3,
    "squad": 4
}

# ✅ ZERO INTENTS PRIVILEGIADAS — o bot roda em qualquer servidor, de qualquer
#    tamanho, SEM precisar de verificação do Discord.
#
#    • Membros:       NÃO usamos. Menções são feitas por ID (<@123>) e, quando
#                     precisamos do membro de verdade (liberar acesso a canal),
#                     o membro_do_guild() busca na API na hora.
#    • Presenças:     NÃO usamos (status online/offline).
#    • Mensagens:     NÃO lemos conteúdo (só slash commands, que não precisam).
#
#    Resultado: ~55 MB de RAM fixo, sem cache de membros — independe do tamanho
#    do servidor e sem risco de bloqueio por intent privilegiada.
#
#    Se algum dia quiser ligar o intent de membros (não é necessário):
#    descomente a linha abaixo e ative no Developer Portal > Bot > Privileged
#    Gateway Intents (bots em +100 servidores exigem verificação pra isso).
intents = discord.Intents.default()      # guilds, messages, reactions, etc.
intents.members = False                  # sem intent privilegiada de membros
intents.presences = False
intents.message_content = False
intents.voice_states = False

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# 🔒 Trava de aprovação: dois staffs clicando "Aprovar" no MESMO segundo (ou host
# lento) não podem dar a MESMA vaga para dois jogadores diferentes.
_lock_aprovacao = asyncio.Lock()

# O discord.py avisa "Privileged message content intent is missing" em qualquer
# bot sem comando de prefixo ("!"). O Fire Force é 100% slash (/), então o aviso
# é inofensivo — filtramos só ELE, sem esconder nenhum outro alerta real.
class _FiltroAvisoIntents(logging.Filter):
    def filter(self, registro):
        return "Privileged message content intent" not in registro.getMessage()


logging.getLogger("discord.ext.commands.bot").addFilter(_FiltroAvisoIntents())


def mencao(user_id) -> str:
    """Menção por ID — funciona sempre, mesmo sem o intent de membros e mesmo
    se a pessoa não estiver no cache (é só texto <@id>)."""
    return f"<@{int(user_id)}>"


async def membro_do_guild(guild: discord.Guild, user_id: int):
    """Pega o membro do cache; se não estiver, busca via API (economiza RAM:
    o bot funciona igual mesmo sem o cache cheio de membros)."""
    if not guild:
        return None
    try:
        membro = guild.get_member(int(user_id))
        if membro:
            return membro
    except Exception:
        pass
    try:
        return await guild.fetch_member(int(user_id))
    except Exception:
        return None


# ==================== BANCO DE DADOS ====================

async def init_db():
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS config (
            guild_id INTEGER PRIMARY KEY,
            cargo_dono INTEGER,
            cargo_gerente INTEGER,
            cargo_mediador INTEGER,
            cargo_suporte INTEGER,
            cat_premium INTEGER,
            cat_basico INTEGER,
            cat_pagamentos INTEGER,
            cat_tickets INTEGER,
            cor TEXT DEFAULT 'Fire Force'
        );

        CREATE TABLE IF NOT EXISTS paineis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            channel_id INTEGER,
            message_id INTEGER,
            tipo TEXT,
            categoria TEXT
        );

        CREATE TABLE IF NOT EXISTS horarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            painel_id INTEGER,
            tipo TEXT,
            categoria TEXT,
            horario TEXT,
            valor REAL,
            premiacao TEXT DEFAULT 'Por Kill',
            vagas_total INTEGER DEFAULT 48,
            lotes_usados INTEGER DEFAULT 0,
            ativo INTEGER DEFAULT 1,
            sala_id TEXT,
            sala_senha TEXT,
            canal_tabela INTEGER,
            msg_tabela INTEGER,
            FOREIGN KEY (painel_id) REFERENCES paineis(id)
        );

        CREATE TABLE IF NOT EXISTS slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            horario_id INTEGER,
            guild_id INTEGER,
            comprador_id INTEGER,
            comprador_nome TEXT,
            numero INTEGER,
            confirmado INTEGER DEFAULT 0,
            canal_pag INTEGER,
            criado_em TEXT,
            valor_cobrado REAL,
            cupom_id INTEGER,
            FOREIGN KEY (horario_id) REFERENCES horarios(id)
        );

        CREATE TABLE IF NOT EXISTS slot_jogadores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot_id INTEGER,
            posicao INTEGER,
            ff_uid TEXT,
            ff_nome TEXT,
            ff_nivel INTEGER DEFAULT 0,
            discord_nome TEXT,
            FOREIGN KEY (slot_id) REFERENCES slots(id)
        );

        CREATE TABLE IF NOT EXISTS pix (
            user_id INTEGER,
            guild_id INTEGER,
            tipo TEXT,
            chave TEXT,
            titular TEXT,
            PRIMARY KEY (user_id, guild_id)
        );

        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            channel_id INTEGER,
            user_id INTEGER,
            status TEXT DEFAULT 'aberto',
            criado_em TEXT
        );

        CREATE TABLE IF NOT EXISTS staff_status (
            user_id INTEGER,
            guild_id INTEGER,
            online INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, guild_id)
        );

        CREATE TABLE IF NOT EXISTS salas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            tipo TEXT,
            categoria TEXT,
            horario TEXT,
            sala_id TEXT,
            sala_senha TEXT,
            enviado INTEGER DEFAULT 0,
            criado_em TEXT
        );

        CREATE TABLE IF NOT EXISTS cupons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            codigo TEXT,
            tipo_desconto TEXT,
            valor REAL,
            usos_max INTEGER,
            usos_por_user INTEGER,
            usos_atuais INTEGER DEFAULT 0,
            expira_em TEXT
        );

        CREATE TABLE IF NOT EXISTS cupons_usados (
            cupom_id INTEGER,
            user_id INTEGER,
            usos INTEGER DEFAULT 0,
            PRIMARY KEY (cupom_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS ff_cache (
            uid TEXT PRIMARY KEY,
            nick TEXT,
            nivel INTEGER DEFAULT 0,
            regiao TEXT,
            rank TEXT,
            prime INTEGER DEFAULT 0,
            cla TEXT,
            provedor TEXT,
            atualizado_em TEXT
        );

        -- ===== SISTEMA FINANCEIRO (carteira + LivePix + logs) =====
        CREATE TABLE IF NOT EXISTS carteira (
            user_id INTEGER,
            guild_id INTEGER,
            saldo REAL DEFAULT 0,
            atualizado_em TEXT,
            PRIMARY KEY (user_id, guild_id)
        );

        CREATE TABLE IF NOT EXISTS transacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            user_id INTEGER,
            tipo TEXT,
            valor REAL,
            saldo_apos REAL,
            descricao TEXT,
            ref TEXT,
            criado_em TEXT
        );

        CREATE TABLE IF NOT EXISTS depositos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            user_id INTEGER,
            valor REAL,
            nome_pagador TEXT,
            status TEXT DEFAULT 'na_janela',
            livepix_id TEXT,
            criado_em TEXT,
            expira_em TEXT,
            creditado_em TEXT
        );

        CREATE TABLE IF NOT EXISTS saques (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            user_id INTEGER,
            valor REAL,
            chave_pix TEXT,
            titular TEXT,
            status TEXT DEFAULT 'na_fila',
            criado_em TEXT,
            processado_em TEXT,
            processado_por INTEGER
        );

        CREATE TABLE IF NOT EXISTS livro_caixa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            tipo TEXT,
            valor REAL,
            descricao TEXT,
            ref TEXT,
            criado_em TEXT
        );

        CREATE TABLE IF NOT EXISTS comissoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            staff_id INTEGER,
            slot_id INTEGER,
            horario_id INTEGER,
            valor_base REAL,
            comissao REAL,
            dia TEXT,
            criado_em TEXT
        );

        CREATE TABLE IF NOT EXISTS livepix_vistos (
            id TEXT PRIMARY KEY,
            tipo TEXT,
            criado_em TEXT
        );

        CREATE TABLE IF NOT EXISTS relatorios_dia (
            guild_id INTEGER,
            dia TEXT,
            enviado_em TEXT,
            PRIMARY KEY (guild_id, dia)
        );

        -- ===== ATENDIMENTO v2 • CARTEIRA DE TRABALHO • EVENTOS • RANKINGS =====
        CREATE TABLE IF NOT EXISTS carteira_trabalho (
            user_id INTEGER,
            guild_id INTEGER,
            saldo REAL DEFAULT 0,
            atualizado_em TEXT,
            PRIMARY KEY (user_id, guild_id)
        );

        CREATE TABLE IF NOT EXISTS ganhos_trabalho (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            user_id INTEGER,
            tipo TEXT,
            valor REAL,
            saldo_apos REAL,
            descricao TEXT,
            ref TEXT,
            criado_em TEXT
        );

        CREATE TABLE IF NOT EXISTS avaliacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            ticket_id INTEGER,
            avaliador_id INTEGER,
            atendente_id INTEGER,
            nota REAL,
            descricao TEXT,
            valor_pago REAL,
            criado_em TEXT
        );

        CREATE TABLE IF NOT EXISTS eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            nome TEXT,
            descricao TEXT,
            aposta_min REAL DEFAULT 10,
            kills_min INTEGER DEFAULT 3,
            bonus REAL DEFAULT 5,
            top_min INTEGER DEFAULT 0,
            modos TEXT DEFAULT 'todos',
            categorias TEXT DEFAULT 'todas',
            ativo INTEGER DEFAULT 1,
            canal_id INTEGER,
            msg_id INTEGER,
            criado_em TEXT,
            fim_em TEXT
        );

        CREATE TABLE IF NOT EXISTS evento_participantes (
            evento_id INTEGER,
            user_id INTEGER,
            slot_id INTEGER,
            valor REAL,
            kills INTEGER DEFAULT 0,
            posicao INTEGER DEFAULT 0,
            bonus_pago REAL DEFAULT 0,
            criado_em TEXT,
            PRIMARY KEY (evento_id, slot_id)
        );

        CREATE TABLE IF NOT EXISTS vitorias (
            user_id INTEGER,
            guild_id INTEGER,
            qtd INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, guild_id)
        );

        CREATE TABLE IF NOT EXISTS chaves_salvas (
            user_id INTEGER,
            guild_id INTEGER,
            tipo TEXT,
            chave TEXT,
            titular TEXT,
            atualizado_em TEXT,
            PRIMARY KEY (user_id, guild_id)
        );

        CREATE TABLE IF NOT EXISTS sync_meta (
            chave TEXT PRIMARY KEY,
            valor TEXT
        );

        CREATE TABLE IF NOT EXISTS checkouts (
            referencia TEXT PRIMARY KEY,
            guild_id INTEGER,
            tipo TEXT,
            alvo_id INTEGER,
            valor REAL,
            link TEXT,
            user_id INTEGER,
            nick TEXT,
            horario_id INTEGER,
            canal_id INTEGER,
            status TEXT DEFAULT 'aberto',
            valor_pago REAL DEFAULT 0,
            prova TEXT,
            criado_em TEXT,
            pago_em TEXT
        );
        """)

        try:
            await db.execute("UPDATE tickets SET tipo = 'suporte' WHERE tipo IN ('financeiro', 'mediador')")
        except Exception:
            pass

        try:
            await db.execute("ALTER TABLE horarios ADD COLUMN vagas_total INTEGER DEFAULT 48")
        except Exception:
            pass

        try:
            await db.execute("ALTER TABLE slots ADD COLUMN valor_cobrado REAL")
        except Exception:
            pass

        try:
            await db.execute("ALTER TABLE slots ADD COLUMN cupom_id INTEGER")
        except Exception:
            pass

        for _coluna, _tipo in (("canal_logs", "INTEGER"), ("livepix_link", "TEXT"), ("reserva", "REAL"),
                               ("comissao_pct", "REAL"), ("saque_min", "REAL"), ("deposito_min", "REAL"),
                               ("janela_min", "INTEGER"), ("canal_logs_suporte", "INTEGER"),
                               ("canal_cupons", "INTEGER"), ("canal_eventos", "INTEGER"),
                               ("canal_rankings", "INTEGER"), ("dia_fechamento", "INTEGER"),
                               ("nota_valores", "TEXT"),
                               ("canal_log_deposito", "INTEGER"),
                               ("canal_log_saque", "INTEGER"),
                               ("canal_log_pagamento", "INTEGER")):
            try:
                await db.execute(f"ALTER TABLE config ADD COLUMN {_coluna} {_tipo}")
            except Exception:
                pass

        for _tabela, _coluna, _tipo in (
            ("tickets", "tipo", "TEXT"), ("tickets", "assumido_por", "INTEGER"), ("tickets", "assumido_em", "TEXT"),
            ("tickets", "nota", "REAL"), ("tickets", "nota_desc", "TEXT"), ("tickets", "pago_nota", "REAL"),
            ("tickets", "fechado_em", "TEXT"), ("tickets", "fechado_por", "INTEGER"),
            ("cupons", "msg_id", "INTEGER"), ("cupons", "canal_id", "INTEGER"),
            ("cupons", "esgotado_avisado", "INTEGER DEFAULT 0"), ("cupons", "ativo", "INTEGER DEFAULT 1"),
            ("depositos", "canal_id", "INTEGER"), ("depositos", "assumido_por", "INTEGER"),
            ("depositos", "apelidos", "TEXT"),
            ("saques", "tipo", "TEXT DEFAULT 'jogador'"),
            ("saques", "saldo_antes", "REAL"),
            ("saques", "saldo_apos", "REAL"),
            ("saques", "retirada_em", "TEXT"),
            ("saques", "retirada_prova", "TEXT"),
            ("slots", "assumido_por", "INTEGER"),
            ("slots", "apelidos", "TEXT"),
        ):
            try:
                await db.execute(f"ALTER TABLE {_tabela} ADD COLUMN {_coluna} {_tipo}")
            except Exception:
                pass

        await db.commit()


# ==================== FUNÇÕES AUXILIARES ====================

def formatar_moeda(valor) -> str:
    """R$ 5,00 (padrão brasileiro)."""
    try:
        numero = float(valor or 0)
    except Exception:
        numero = 0.0
    texto = f"{numero:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def arredondar(valor) -> float:
    """Arredonda pra 2 casas (dinheiro nunca fica com 3,99999)."""
    try:
        return round(float(valor or 0) + 1e-9, 2)
    except Exception:
        return 0.0


def obter_cor(nome: str) -> int:
    return CORES_DICCIONARIO.get(nome, 0xFF4500)


def criar_embed(titulo: str = "", descricao: str = "", cor_nome: str = "Fire Force", **kwargs) -> discord.Embed:
    embed = discord.Embed(
        title=titulo,
        description=descricao,
        color=obter_cor(cor_nome),
        timestamp=agora_brt()
    )
    
    footer_text = kwargs.get("footer", "Fire Force • Liga Profissional")
    footer_icon = kwargs.get("footer_icon", None)
    embed.set_footer(text=footer_text, icon_url=footer_icon)

    if kwargs.get("thumb"):
        embed.set_thumbnail(url=kwargs["thumb"])
    if kwargs.get("image"):
        embed.set_image(url=kwargs["image"])
    if kwargs.get("author"):
        embed.set_author(name=kwargs["author"], icon_url=kwargs.get("author_icon"))

    return embed


async def obter_config(guild_id: int) -> dict:
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM config WHERE guild_id = ?", (guild_id,))
        row = await cursor.fetchone()
        return dict(row) if row else {}


async def salvar_config(guild_id: int, **kwargs):
    async with aiosqlite.connect(DATABASE_FILE) as db:
        existente = await obter_config(guild_id)
        if existente:
            campos = ", ".join(f"{chave} = ?" for chave in kwargs)
            valores = tuple(kwargs.values()) + (guild_id,)
            await db.execute(f"UPDATE config SET {campos} WHERE guild_id = ?", valores)
        else:
            kwargs["guild_id"] = guild_id
            colunas = ", ".join(kwargs.keys())
            placeholders = ", ".join("?" for _ in kwargs)
            valores = tuple(kwargs.values())
            await db.execute(f"INSERT INTO config ({colunas}) VALUES ({placeholders})", valores)
        await db.commit()


async def e_staff(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    cfg = await obter_config(member.guild.id)
    cargos_permitidos = [
        cfg.get("cargo_dono"),
        cfg.get("cargo_gerente"),
        cfg.get("cargo_mediador")
    ]
    return any(role.id in cargos_permitidos for role in member.roles if role.id)


async def e_dono_ou_gerente(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    cfg = await obter_config(member.guild.id)
    cargos_permitidos = [
        cfg.get("cargo_dono"),
        cfg.get("cargo_gerente")
    ]
    return any(role.id in cargos_permitidos for role in member.roles if role.id)


async def e_suporte(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    cfg = await obter_config(member.guild.id)
    cargos_permitidos = [
        cfg.get("cargo_suporte"),
        cfg.get("cargo_dono"),
        cfg.get("cargo_gerente"),
        cfg.get("cargo_mediador")
    ]
    return any(role.id in cargos_permitidos for role in member.roles if role.id)


def horario_para_datetime(horario_str: str) -> datetime.datetime:
    partes = horario_str.strip().split(":")
    hora = int(partes[0])
    minuto = int(partes[1])
    hoje = agora_brt().date()
    dt_local = datetime.datetime.combine(hoje, datetime.time(hora, minuto))
    return dt_local.replace(tzinfo=TZ_BRASILIA)


def pode_comprar_vaga(horario_str: str, lotes_usados: int, lotes_total: int) -> tuple[bool, str]:
    if lotes_usados >= lotes_total:
        return False, "Todas as vagas/lotes deste diário foram preenchidos."
    
    tempo_restante = (horario_para_datetime(horario_str) - agora_brt()).total_seconds()
    if tempo_restante < 0:
        return False, "O horário deste diário já passou."
    
    if tempo_restante < 600:  # 10 minutos
        minutos = int(tempo_restante // 60)
        return False, f"As inscrições fecham 10 minutos antes do início. Restam apenas {minutos} min."
    
    return True, "Liberado"


def formatar_rotulo_diario(tipo: str, categoria: str) -> str:
    tipo_emojis = {"solo": "🎯", "duo": "👥", "trio": "👨‍👩‍👦", "squad": "👨‍👩‍👧‍👦"}
    cat_emojis = "💎" if categoria == "premium" else "🪙"
    emoji_tipo = tipo_emojis.get(tipo.lower(), "🎮")
    return f"{emoji_tipo} {tipo.title()} {cat_emojis} {categoria.title()}"


def texto_slot(tipo: str) -> str:
    return "Vaga" if tipo.lower() == "solo" else "Lote"


def texto_slots_plural(tipo: str) -> str:
    return "Vagas" if tipo.lower() == "solo" else "Lotes"


# ==================== CONSULTA DE ID FREE FIRE (API v2) ====================
# Como funciona (por que agora funciona de verdade):
#   1. Vários provedores com CORRIDA (hedged requests): o 1º que responder vence
#      e os outros são cancelados — nenhum "servidor dormindo" trava a consulta.
#   2. Fallback automático de região (BR, NA, SAC, US, ME, SG...) — ID que não
#      aparece no BR é procurado nos outros servidores.
#   3. CACHE no banco (24h): consulta repetida é instantânea e funciona mesmo
#      com a internet/provedor fora do ar (usa o último dado salvo).
#   4. DISJUNTOR (circuit breaker): provedor que falha 3x entra em descanso por
#      5 minutos e é ignorado — não atrasa quem está funcionando.
#   5. Sessão HTTP reaproveitada, timeout curto e mensagens de erro honestas.

FF_API_TIMEOUT = 13           # segundos por requisição (aguenta os picos de lentidão do provedor)
FF_CACHE_HORAS = 24           # validade do cache (nick/level quase não mudam)
FF_CACHE_NEGATIVO_SEGUNDOS = 300   # "ID não existe" fica memorizado por 5 min
FF_MAX_REGIOES = 5            # quantas regiões testar quando não achar
FF_ESPERA_CONFIRMACAO = 2.0   # segundos esperando outro provedor contestar "não existe"
FF_ATRASO_CORRIDA = 0.35      # atraso entre disparos dos provedores
FF_FALHAS_PARA_ABRIR = 3      # falhas seguidas para colocar um provedor em descanso
FF_DESCANSO_SEGUNDOS = 300    # tempo de descanso do provedor problemático

# Ordem de regiões testadas (BR primeiro — maioria dos usuários do bot)
FF_REGIOES = ["BR", "NA", "SAC", "US", "EU", "ME", "SG", "IND", "ID", "TH", "VN", "PK", "BD", "CIS", "TW"]

# Provedores. Em 12/10/2026 só o primeiro está de pé — os dois que o bot usava
# antes (free-ff-api e freefireinfo, ambos no Render) morreram: respondem 404
# em TODAS as rotas. Ficaram só como histórico; se voltarem, basta descomentar.
FF_PROVEDORES = [
    {
        "nome": "freefireapis.lat",
        "url": "https://freefireapis.lat/info-player?uid={uid}&region={region}",
    },
    # {
    #     "nome": "free-ff-api (Render)",
    #     "url": "https://free-ff-api-src-5plp.onrender.com/api/v1/account?region={region}&uid={uid}",
    # },
    # {
    #     "nome": "freefireinfo (Render)",
    #     "url": "https://freefireinfo-zy9l.onrender.com/api/v1/player-profile?uid={uid}&region={region}",
    # },
]

# status de cada provedor (disjuntor)
_FF_SAUDE: Dict[str, dict] = {}
_FF_SESSAO = None
_FF_NAO_ENCONTRADOS: Dict[str, float] = {}   # uid -> quando foi marcado como inexistente


# ---------- sessão HTTP reaproveitada ----------

def _ff_sessao():
    global _FF_SESSAO
    if _FF_SESSAO is None or _FF_SESSAO.closed:
        timeout = aiohttp.ClientTimeout(total=FF_API_TIMEOUT, connect=5)
        conector = aiohttp.TCPConnector(limit=16, ttl_dns_cache=600)
        _FF_SESSAO = aiohttp.ClientSession(
            timeout=timeout,
            connector=conector,
            headers={"User-Agent": "FireForceBot/6.0 (+discord league manager)"},
        )
    return _FF_SESSAO


# ---------- disjuntor ----------

def _ff_provedor_disponivel(nome: str) -> bool:
    info = _FF_SAUDE.get(nome)
    if not info:
        return True
    aberto_ate = info.get("aberto_ate") or 0
    if aberto_ate and time.time() < aberto_ate:
        return False
    return True


def _ff_marcar_falha(nome: str, erro) -> None:
    info = _FF_SAUDE.setdefault(nome, {"falhas": 0, "aberto_ate": 0, "ultimo_erro": ""})
    info["falhas"] += 1
    info["ultimo_erro"] = str(erro)[:140]
    if info["falhas"] >= FF_FALHAS_PARA_ABRIR:
        info["aberto_ate"] = time.time() + FF_DESCANSO_SEGUNDOS
        info["falhas"] = 0
        print(f"🔌 [FF API] provedor '{nome}' em descanso por {FF_DESCANSO_SEGUNDOS}s — {info['ultimo_erro']}")


def _ff_marcar_sucesso(nome: str) -> None:
    _FF_SAUDE[nome] = {"falhas": 0, "aberto_ate": 0, "ultimo_erro": ""}


# ---------- leitura da resposta (aceita vários formatos) ----------

_CHAVES_NOME = ("nickname", "accountname", "name", "username", "nick")
_CHAVES_NIVEL = ("level", "accountlevel", "nivel", "account_level")
_CHAVES_REGIAO = ("region", "accountregion", "server", "regiao")
_CHAVES_RANK = ("rank", "brrank", "rankname")
_CHAVES_PRIME = ("primelevel", "prime_level")
_CHAVES_CLA = ("clanname", "guildname")


def _ff_procurar(objeto, chaves, profundidade=0):
    """Procura uma chave (case-insensitive) em qualquer nível do JSON."""
    if profundidade > 6:
        return None
    if isinstance(objeto, dict):
        # primeiro nas chaves diretas
        for chave_busca in chaves:
            for chave, valor in objeto.items():
                if chave.lower() == chave_busca and valor not in (None, "", 0, []):
                    return valor
        # depois nos sub-objetos (basicInfo, data, result, player...)
        for sub in ("basicInfo", "basic_info", "data", "result", "player", "account", "profile"):
            if isinstance(objeto.get(sub), dict):
                achado = _ff_procurar(objeto[sub], chaves, profundidade + 1)
                if achado not in (None, "", 0, []):
                    return achado
        # por último, em qualquer dicionário aninhado
        for valor in objeto.values():
            if isinstance(valor, (dict, list)):
                achado = _ff_procurar(valor, chaves, profundidade + 1)
                if achado not in (None, "", 0, []):
                    return achado
    elif isinstance(objeto, list):
        for item in objeto[:5]:
            achado = _ff_procurar(item, chaves, profundidade + 1)
            if achado not in (None, "", 0, []):
                return achado
    return None


def _ff_extrair(dados) -> Optional[dict]:
    """Extrai nick/nível/região/rank/clã de qualquer formato de resposta."""
    if not isinstance(dados, (dict, list)):
        return None

    nome = _ff_procurar(dados, _CHAVES_NOME)
    if not nome or not isinstance(nome, (str, int)):
        return None
    nome = str(nome).strip()
    if len(nome) < 1 or nome.lower() in ("null", "none", "undefined"):
        return None

    nivel = _ff_procurar(dados, _CHAVES_NIVEL)
    try:
        nivel = int(float(str(nivel).replace(".", "").replace(",", ""))) if nivel else 0
    except Exception:
        nivel = 0

    regiao = _ff_procurar(dados, _CHAVES_REGIAO)
    regiao = str(regiao).upper() if isinstance(regiao, (str, int)) else ""

    rank = _ff_procurar(dados, _CHAVES_RANK)
    if isinstance(rank, int):
        rank = ""
    elif rank:
        rank = str(rank)[:28]

    prime = _ff_procurar(dados, _CHAVES_PRIME)
    try:
        prime = int(prime) if prime else 0
    except Exception:
        prime = 0

    cla = _ff_procurar(dados, _CHAVES_CLA)
    cla = str(cla)[:26] if cla else ""

    return {"nome": nome, "nivel": nivel, "regiao": regiao, "rank": rank, "prime": prime, "cla": cla}


def _ff_uid_invalido(dados) -> bool:
    """O provedor respondeu que o UID é inválido (formato)."""
    if not isinstance(dados, dict):
        return False
    texto = json.dumps(dados, ensure_ascii=False).upper()
    return any(p in texto for p in ("INVALID_UID", "INVALID UID", "MUST BE AN INTEGER", "INVALID PARAMETER"))


def _ff_nao_encontrado(dados) -> bool:
    """A resposta diz claramente que o jogador não existe?"""
    if not isinstance(dados, dict):
        return False
    texto = json.dumps(dados, ensure_ascii=False).upper()
    return any(p in texto for p in ("PLAYER_NOT_FOUND", "NOT FOUND", "USER_NOT_FOUND", "NOTFOUND"))


# ---------- cache no banco ----------

async def _ff_cache_ler(uid: str) -> Optional[dict]:
    try:
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            linha = await (await db.execute("SELECT * FROM ff_cache WHERE uid = ?", (uid,))).fetchone()
        return dict(linha) if linha else None
    except Exception:
        return None


async def _ff_cache_salvar(uid: str, jogador: dict, provedor: str) -> None:
    try:
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute(
                "INSERT OR REPLACE INTO ff_cache (uid, nick, nivel, regiao, rank, prime, cla, provedor, atualizado_em) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (uid, jogador.get("nome", ""), jogador.get("nivel", 0), jogador.get("regiao", ""),
                 jogador.get("rank", ""), jogador.get("prime", 0), jogador.get("cla", ""),
                 provedor, agora_brt().isoformat())
            )
            await db.commit()
    except Exception as erro:
        print("Erro ao salvar cache do FF:", erro)


def _ff_cache_valido(linha: dict) -> bool:
    try:
        salvo = datetime.datetime.fromisoformat(linha["atualizado_em"])
        if salvo.tzinfo is None:
            salvo = salvo.replace(tzinfo=TZ_BRASILIA)
        return (agora_brt() - salvo).total_seconds() < FF_CACHE_HORAS * 3600
    except Exception:
        return False


# ---------- requisição a um provedor ----------

async def _ff_pedir(provedor: dict, uid: str, regiao: str) -> Optional[dict]:
    """Devolve o jogador, None se o ID não existe, ou levanta erro se o provedor falhou.

    Importante: vários provedores respondem "jogador não encontrado" com HTTP 404
    e um JSON explicando — isso NÃO é provedor caído, então o corpo é lido antes
    de julgar pelo status (era o que fazia a consulta parecer "fora do ar")."""
    url = provedor["url"].format(uid=uid, region=regiao)
    sessao = _ff_sessao()
    async with sessao.get(url) as resposta:
        corpo = await resposta.text()
        status = resposta.status

    dados = None
    try:
        dados = json.loads(corpo)
    except Exception:
        dados = None

    if dados is not None:
        jogador = _ff_extrair(dados)
        if jogador:
            return jogador
        if _ff_nao_encontrado(dados) or _ff_uid_invalido(dados):
            return None                      # provedor vivo; o ID é que não existe

    if status == 429:
        raise RuntimeError("limite de uso (429)")
    if status >= 500:
        raise RuntimeError(f"servidor fora ({status})")
    if status != 200:
        raise RuntimeError(f"endpoint indisponível (http {status})")
    return None


async def _ff_tentar_provedor(provedor: dict, uid: str):
    """Procura o ID no provedor. Retorna (status, dados, provedor).

    1º tenta a região principal (BR) — resolve a maioria e é rápido.
    Se não achar, dispara as outras regiões TODAS EM PARALELO: assim o tempo
    total continua sendo ~1 requisição, em vez de somar o tempo de cada região
    (era o que fazia a consulta parecer "fora do ar" nos picos de lentidão)."""
    nome = provedor["nome"]
    if not _ff_provedor_disponivel(nome):
        return ("descartado", "em descanso", nome)

    regioes = FF_REGIOES[:FF_MAX_REGIOES]

    try:
        jogador = await _ff_pedir(provedor, uid, regioes[0])
    except asyncio.CancelledError:
        raise
    except Exception as erro:
        _ff_marcar_falha(nome, erro)
        return ("erro", str(erro), nome)

    if jogador:
        _ff_marcar_sucesso(nome)
        jogador["regiao"] = jogador.get("regiao") or regioes[0]
        return ("ok", jogador, nome)

    # não achou no BR: procura nas outras regiões ao mesmo tempo
    outras = regioes[1:]
    tarefas = [asyncio.create_task(_ff_pedir(provedor, uid, regiao)) for regiao in outras]
    try:
        pendentes = set(tarefas)
        while pendentes:
            prontas, pendentes = await asyncio.wait(
                pendentes, return_when=asyncio.FIRST_COMPLETED, timeout=FF_API_TIMEOUT + 2
            )
            if not prontas:
                break
            for tarefa in prontas:
                try:
                    resultado = tarefa.result()
                except Exception:
                    continue
                if resultado:
                    _ff_marcar_sucesso(nome)
                    resultado["regiao"] = resultado.get("regiao") or "?"
                    return ("ok", resultado, nome)
    finally:
        for tarefa in tarefas:
            tarefa.cancel()

    _ff_marcar_sucesso(nome)  # respondeu bem, o ID é que não existe
    return ("nao_encontrado", None, nome)


async def _ff_disparar(provedor: dict, uid: str, atraso: float):
    if atraso:
        await asyncio.sleep(atraso)
    return await _ff_tentar_provedor(provedor, uid)


# ---------- função principal ----------

async def verificar_ff(uid: str, forcar: bool = False) -> dict:
    """Consulta um ID do Free Fire de forma confiável (corrida + regiões + cache).

    Retorno em caso de sucesso:
        {"ok": True, "nome":..., "nivel":..., "regiao":..., "rank":..., "prime":...,
         "cla":..., "provedor":..., "cache": bool, "aviso": str|None, "atualizado": str}
    """
    uid = str(uid or "").strip()
    if not uid.isdigit() or not (5 <= len(uid) <= 15):
        return {"ok": False, "motivo": "formato",
                "mensagem": "O ID precisa ter de 5 a 15 números (só dígitos)."}

    # 0) já foi marcado como inexistente há pouco? evita bater na API de novo
    if not forcar:
        quando = _FF_NAO_ENCONTRADOS.get(uid)
        if quando and (time.time() - quando) < FF_CACHE_NEGATIVO_SEGUNDOS:
            return {"ok": False, "motivo": "nao_encontrado",
                    "mensagem": "Não encontrei esse ID em nenhuma região de Free Fire. Confira os números."}

    # 1) cache fresco
    salvo = await _ff_cache_ler(uid)
    if salvo and not forcar and _ff_cache_valido(salvo):
        return {
            "ok": True, "nome": salvo["nick"], "nivel": salvo["nivel"], "regiao": salvo["regiao"],
            "rank": salvo["rank"] or "", "prime": salvo["prime"] or 0, "cla": salvo["cla"] or "",
            "provedor": salvo["provedor"] or "cache", "cache": True, "aviso": None,
            "atualizado": salvo["atualizado_em"],
        }

    # 2) corrida entre os provedores disponíveis
    disponiveis = [p for p in FF_PROVEDORES if _ff_provedor_disponivel(p["nome"])]
    if not disponiveis:
        disponiveis = FF_PROVEDORES  # todos em descanso: tenta o primeiro mesmo assim

    tarefas = [
        asyncio.create_task(_ff_disparar(provedor, uid, indice * FF_ATRASO_CORRIDA))
        for indice, provedor in enumerate(disponiveis)
    ]

    achado = None
    erros = []
    nao_encontrado = False
    pendentes = set(tarefas)
    prazo_total = time.time() + FF_API_TIMEOUT + FF_ATRASO_CORRIDA * len(disponiveis) + 2
    confirmacao_ate = None       # se alguém diz "não existe", damos 3s para outro discordar

    try:
        while pendentes and not achado:
            agora_loop = time.time()
            if agora_loop >= prazo_total:
                erros.append("tempo esgotado")
                break
            if confirmacao_ate and agora_loop >= confirmacao_ate:
                break
            espera = prazo_total - agora_loop
            if confirmacao_ate:
                espera = min(espera, confirmacao_ate - agora_loop)

            prontas, pendentes = await asyncio.wait(
                pendentes, return_when=asyncio.FIRST_COMPLETED, timeout=max(0.1, espera)
            )
            if not prontas:
                if confirmacao_ate:
                    break
                erros.append("tempo esgotado")
                break
            for tarefa in prontas:
                try:
                    status, dados, nome = tarefa.result()
                except Exception as erro:
                    erros.append(str(erro))
                    continue
                if status == "ok" and dados:
                    achado = (dados, nome)
                    break
                if status == "nao_encontrado":
                    nao_encontrado = True
                    if confirmacao_ate is None:
                        confirmacao_ate = time.time() + FF_ESPERA_CONFIRMACAO
                elif status == "erro":
                    erros.append(f"{nome}: {dados}")
    finally:
        for tarefa in pendentes:
            tarefa.cancel()

    if achado:
        jogador, provedor = achado
        await _ff_cache_salvar(uid, jogador, provedor)
        return {
            "ok": True, "nome": jogador["nome"], "nivel": jogador["nivel"], "regiao": jogador["regiao"],
            "rank": jogador.get("rank", ""), "prime": jogador.get("prime", 0), "cla": jogador.get("cla", ""),
            "provedor": provedor, "cache": False, "aviso": None,
            "atualizado": agora_brt().isoformat(),
        }

    # 3) não achou em nenhum provedor: era "não existe" ou "tudo fora"?
    if nao_encontrado:
        _FF_NAO_ENCONTRADOS[uid] = time.time()
        return {"ok": False, "motivo": "nao_encontrado",
                "mensagem": "Não encontrei esse ID em nenhuma região de Free Fire. Confira os números."}

    if salvo:  # 4) provedores fora do ar, mas temos cache antigo: melhor que nada
        return {
            "ok": True, "nome": salvo["nick"], "nivel": salvo["nivel"], "regiao": salvo["regiao"],
            "rank": salvo["rank"] or "", "prime": salvo["prime"] or 0, "cla": salvo["cla"] or "",
            "provedor": salvo["provedor"] or "cache", "cache": True,
            "aviso": "Os servidores de consulta estão instáveis agora — mostrando o último dado salvo.",
            "atualizado": salvo["atualizado_em"],
        }

    return {"ok": False, "motivo": "offline",
            "mensagem": "Os servidores de consulta não responderam agora (instabilidade ou manutenção). "
                        "Tente de novo em alguns segundos."}


async def _ff_fechar_sessao():
    """Fecha a sessão HTTP com elegância."""
    global _FF_SESSAO
    if _FF_SESSAO and not _FF_SESSAO.closed:
        await _FF_SESSAO.close()
    _FF_SESSAO = None


def ff_status_provedores() -> str:
    """Resumo da saúde dos provedores (usado no /info)."""
    linhas = []
    for provedor in FF_PROVEDORES:
        info = _FF_SAUDE.get(provedor["nome"], {})
        aberto_ate = info.get("aberto_ate") or 0
        if aberto_ate and time.time() < aberto_ate:
            linhas.append(f"🔴 `{provedor['nome']}` em descanso ({int(aberto_ate - time.time())}s)")
        else:
            linhas.append(f"🟢 `{provedor['nome']}` ativo")
    return "\n".join(linhas)


# ---------- busca na base local do bot ----------

_INVISIVEIS = ["\u3164", "\u2800", "\u200b", "\u200c", "\u200d", "\u2060", "\ufeff", "\u00a0"]


def _nick_limpo(nick: str) -> str:
    """Tira espaços invisíveis/zerowidth que os jogadores usam no nick."""
    texto = str(nick or "")
    for caractere in _INVISIVEIS:
        texto = texto.replace(caractere, " ")
    return " ".join(texto.split())


async def consultar_jogador_local(busca: str) -> dict:
    """Procura um jogador pelos nicks que ele usou nas inscrições do bot."""
    busca = (busca or "").strip()
    if not busca:
        return {"ok": False}

    consulta = """
        SELECT j.ff_nome, s.criado_em, s.numero, h.tipo, h.categoria, h.horario
        FROM slot_jogadores j
        JOIN slots s ON s.id = j.slot_id
        JOIN horarios h ON h.id = s.horario_id
        WHERE s.confirmado = 1
          AND (LOWER(j.ff_nome) = LOWER(?) OR LOWER(j.ff_nome) LIKE LOWER(?))
        ORDER BY s.criado_em DESC
    """
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        linhas = await (await db.execute(consulta, (busca, f"%{busca}%"))).fetchall()

        # nick do Free Fire costuma ter caracteres invisíveis: se a busca direta
        # falhar, compara o "nick limpo" de todas as inscrições do bot.
        if not linhas:
            todas = await (await db.execute(
                """
                SELECT j.ff_nome, s.criado_em, s.numero, h.tipo, h.categoria, h.horario
                FROM slot_jogadores j
                JOIN slots s ON s.id = j.slot_id
                JOIN horarios h ON h.id = s.horario_id
                WHERE s.confirmado = 1
                ORDER BY s.criado_em DESC
                """
            )).fetchall()
            alvo = _nick_limpo(busca).lower()
            linhas = [linha for linha in todas if alvo and (
                _nick_limpo(linha["ff_nome"]).lower() == alvo
                or alvo in _nick_limpo(linha["ff_nome"]).lower()
            )]

    if not linhas:
        return {"ok": False}
    principal = linhas[0]
    return {
        "ok": True,
        "nome": principal["ff_nome"] or "—",
        "partidas": len(linhas),
        "ultimo": f"{formatar_rotulo_diario(principal['tipo'], principal['categoria'])} • {principal['horario']}",
    }


# ==================== PIX PAYLOAD GENERATOR ====================

def _crc16(payload: str) -> str:
    crc = 0xFFFF
    for char in payload:
        crc ^= ord(char) << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc = crc << 1
            crc &= 0xFFFF
    return format(crc, '04X')


# ==================== TABELA EM TEXTO — "1. (NICK)" ====================
# Nada de imagem e nada de contador de pagamento: só a lista das vagas.
#    1. ()
#    2. (ㅤFXㅤWINNER)
#    3. ()
# Fica no canal do diário e se atualiza sozinha a cada 15 segundos.

def montar_lista_vagas(tipo: str, slots_data: list) -> str:
    """Lista numerada dos lotes: `N. (nomes)` — vazio vira `N. ()`."""
    total = LOTES_POR_MODO.get((tipo or "solo").lower(), len(slots_data or []))
    linhas = []
    for indice in range(total):
        slot = slots_data[indice] if slots_data and indice < len(slots_data) else {}
        nicks = []
        if slot.get("confirmado"):
            for jogador in (slot.get("jogadores") or []):
                nick = (jogador.get("ff_nome") if isinstance(jogador, dict) else jogador) or ""
                nick = str(nick).strip()
                if nick:
                    nicks.append(nick)
        linhas.append(f"{indice + 1:>2}. ({', '.join(nicks)})")
    return "\n".join(linhas)


def montar_embed_tabela(horario: dict, slots_data: list, ocupadas: int = 0,
                        atualizado_em: str = "") -> discord.Embed:
    """Embed com a lista das vagas em texto (layout simples, como era antes)."""
    tipo = (horario.get("tipo") or "solo").lower()
    categoria = horario.get("categoria") or "premium"
    total = LOTES_POR_MODO.get(tipo, 48)
    lista = montar_lista_vagas(tipo, slots_data)

    descricao = (
        f"**🏆 Premiação:** `{horario.get('premiacao') or 'Por Kill'}`"
        f"  •  **💰 Valor:** `{formatar_moeda(horario.get('valor'))}`\n"
        f"**🎫 {texto_slots_plural(tipo)}:** `{ocupadas}/{total}`\n\n"
        f"```\n{lista}\n```"
    )

    return criar_embed(
        titulo=f"🔥 {formatar_rotulo_diario(tipo, categoria)} — {horario.get('horario', '--:--')}",
        descricao=descricao,
        cor_nome="Fire Force",
        footer=("Atualização automática a cada 15s" + (f" • {atualizado_em}" if atualizado_em else ""))
    )


async def obter_slots_data(horario_id: int) -> list:
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        horario = await (await db.execute("SELECT * FROM horarios WHERE id = ?", (horario_id,))).fetchone()
        if not horario:
            return []

        total = LOTES_POR_MODO[horario["tipo"]]
        resultado = []

        for numero in range(1, total + 1):
            slot = await (await db.execute(
                "SELECT * FROM slots WHERE horario_id = ? AND numero = ? AND confirmado = 1",
                (horario_id, numero)
            )).fetchone()

            if slot:
                jogadores = await (await db.execute(
                    "SELECT ff_nome FROM slot_jogadores WHERE slot_id = ? ORDER BY posicao",
                    (slot["id"],)
                )).fetchall()
                resultado.append({
                    "numero": numero,
                    "confirmado": True,
                    "jogadores": [{"ff_nome": j["ff_nome"]} for j in jogadores],
                })
            else:
                resultado.append({"numero": numero, "confirmado": False, "jogadores": []})

    return resultado


async def atualizar_tabela(guild: discord.Guild, horario_id: int):
    """Edita (ou publica) a tabela em texto no canal do diário."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        horario = await (await db.execute("SELECT * FROM horarios WHERE id = ?", (horario_id,))).fetchone()
        if not horario or not horario["canal_tabela"]:
            return
        ocupadas = (await (await db.execute(
            "SELECT COUNT(*) FROM slots WHERE horario_id = ?", (horario_id,)
        )).fetchone())[0]

    canal = guild.get_channel(horario["canal_tabela"])
    if not canal:
        return

    dados_slots = await obter_slots_data(horario_id)
    embed = montar_embed_tabela(
        dict(horario), dados_slots, ocupadas,
        atualizado_em=agora_brt().strftime("%H:%M:%S")
    )

    if horario["msg_tabela"]:
        try:
            mensagem = await canal.fetch_message(horario["msg_tabela"])
            await mensagem.edit(embed=embed)
            return
        except discord.NotFound:
            pass

    nova_msg = await canal.send(embed=embed)
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute("UPDATE horarios SET msg_tabela = ? WHERE id = ?", (nova_msg.id, horario_id))
        await db.commit()


async def criar_canal_tabela(guild: discord.Guild, horario_id: int):
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        horario = await (await db.execute("SELECT * FROM horarios WHERE id = ?", (horario_id,))).fetchone()
        if not horario or horario["canal_tabela"]:
            return horario["canal_tabela"] if horario else None

    cfg = await obter_config(guild.id)
    cat_chave = "cat_premium" if horario["categoria"] == "premium" else "cat_basico"
    categoria_canal = guild.get_channel(cfg.get(cat_chave))

    horario_limpo = horario["horario"].replace(":", "h")
    
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, attach_files=True)
    }

    for cargo_key in ["cargo_dono", "cargo_gerente", "cargo_mediador"]:
        if cfg.get(cargo_key):
            role = guild.get_role(cfg[cargo_key])
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    canal = await guild.create_text_channel(
        f"🔥│{horario['tipo']}-{horario['categoria']}-{horario_limpo}",
        category=categoria_canal,
        overwrites=overwrites
    )

    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute("UPDATE horarios SET canal_tabela = ? WHERE id = ?", (canal.id, horario_id))
        await db.commit()

    return canal.id


async def add_jogador_canal_tabela(guild: discord.Guild, horario_id: int, user: discord.User):
    """Libera a leitura do canal do diário para o comprador.
    Sem o intent de membros, o membro é buscado na API na hora — se a pessoa
    já tiver saído do servidor, apenas ignora (nada quebra)."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        horario = await (await db.execute("SELECT * FROM horarios WHERE id = ?", (horario_id,))).fetchone()
        if not horario or not horario["canal_tabela"]:
            return

    canal = guild.get_channel(horario["canal_tabela"])
    if not canal:
        return

    membro = user if isinstance(user, discord.Member) else await membro_do_guild(guild, getattr(user, "id", user))
    if not membro:
        return
    try:
        await canal.set_permissions(membro, view_channel=True, send_messages=False, add_reactions=False)
    except Exception as erro:
        print("Não deu para liberar o acesso do comprador:", erro)


# ==================== GERENCIADOR DE PAINEL FIXO ====================

async def rebuild_painel(guild: discord.Guild, painel_id: int):
    """Painel público de inscrições."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        painel = await (await db.execute("SELECT * FROM paineis WHERE id = ?", (painel_id,))).fetchone()
        if not painel:
            return
        horarios = await (await db.execute(
            "SELECT * FROM horarios WHERE painel_id = ? AND ativo = 1 ORDER BY horario", (painel_id,)
        )).fetchall()

        ocupacao = {}
        for h in horarios:
            ocupacao[h["id"]] = (await (await db.execute(
                "SELECT COUNT(*) FROM slots WHERE horario_id = ?", (h["id"],)
            )).fetchone())[0]

    canal = guild.get_channel(painel["channel_id"])
    if not canal:
        return

    tipo = painel["tipo"]
    categoria = painel["categoria"]
    total = LOTES_POR_MODO[tipo]
    rotulo_plural = texto_slots_plural(tipo)
    jogadores_lote = JOGADORES_POR_LOTE[tipo]

    embed = criar_embed(
        titulo=f"🔥 {formatar_rotulo_diario(tipo, categoria)}",
        descricao=f"**Modo:** {tipo.title()} ({jogadores_lote} jogador{'es' if jogadores_lote > 1 else ''} por {texto_slot(tipo).lower()})\n"
                  f"**{rotulo_plural} por horário:** {total}\n"
                  f"**Inscrição:** informe apenas o **nick** do jogo.\n\n"
                  f"{'═' * 35}",
        cor_nome="Dourado" if categoria == "premium" else "Prata",
        footer="Fire Force • Selecione abaixo para realizar a inscrição"
    )

    opcoes_select = []

    if horarios:
        for h in horarios:
            h_dict = dict(h)
            ocupadas = ocupacao.get(h_dict["id"], 0)
            pode, _ = pode_comprar_vaga(h_dict["horario"], ocupadas, total)
            restantes = max(0, total - ocupadas)
            status_str = "🟢 ABERTO" if pode else "🔴 FECHADO"
            diferenca = (horario_para_datetime(h_dict["horario"]) - agora_brt()).total_seconds()
            tempo_str = f"{int(diferenca // 60)}min" if diferenca > 0 else "Encerrado"
            premiacao_txt = h_dict.get("premiacao", "Por Kill")

            embed.add_field(
                name=f"⏰ {h_dict['horario']} — {status_str}",
                value=f"> 💰 `{formatar_moeda(h_dict['valor'])}`\n"
                      f"> 🎫 `{restantes}/{total}` {rotulo_plural.lower()}\n"
                      f"> 🏆 `{premiacao_txt}`\n"
                      f"> ⏳ `{tempo_str}`",
                inline=False
            )

            if pode:
                opcoes_select.append(discord.SelectOption(
                    label=f"{h_dict['horario']} — {formatar_moeda(h_dict['valor'])}",
                    value=str(h_dict["id"]),
                    description=f"{restantes} vagas livres | {premiacao_txt}"[:100],
                    emoji="🎮"
                ))
    else:
        embed.add_field(name="📭", value="> Nenhum horário cadastrado no momento.", inline=False)

    try:
        msg = await canal.fetch_message(painel["message_id"])
        await msg.edit(embed=embed, view=PainelInscricaoView(opcoes_select, tipo) if opcoes_select else None)
    except discord.NotFound:
        msg = await canal.send(embed=embed, view=PainelInscricaoView(opcoes_select, tipo) if opcoes_select else None)
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute("UPDATE paineis SET message_id = ? WHERE id = ?", (msg.id, painel_id))
            await db.commit()


class HorarioSelectMenu(discord.ui.Select):
    def __init__(self, opcoes: list, tipo: str):
        super().__init__(
            placeholder=f"🎮 Selecione para comprar {texto_slot(tipo).lower()}...",
            options=opcoes,
            row=0
        )
        self.tipo = tipo

    async def callback(self, interaction: discord.Interaction):
        horario_id = int(self.values[0])
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            horario = await (await db.execute("SELECT * FROM horarios WHERE id = ?", (horario_id,))).fetchone()
            if not horario:
                return await interaction.response.send_message(
                    embed=criar_embed("❌ Erro", "Horário não localizado.", "Vermelho"),
                    ephemeral=True
                )
            
            ja_comprou = await (await db.execute("SELECT 1 FROM slots WHERE horario_id = ? AND comprador_id = ?", (horario_id, interaction.user.id))).fetchone()
            if ja_comprou:
                return await interaction.response.send_message(
                    embed=criar_embed("⚠️ Atenção", f"Você já adquiriu {texto_slot(horario['tipo']).lower()} para este horário.", "Amarelo"),
                    ephemeral=True
                )

        pode, motivo = pode_comprar_vaga(horario["horario"], horario["lotes_usados"], LOTES_POR_MODO[horario["tipo"]])
        if not pode:
            return await interaction.response.send_message(
                embed=criar_embed("❌ Indisponível", motivo, "Vermelho"),
                ephemeral=True
            )

        modal = ComprarSlotModal(
            horario_id=horario_id,
            tipo=horario["tipo"],
            jogadores_qtd=JOGADORES_POR_LOTE[horario["tipo"]],
            valor=horario["valor"],
            horario_str=horario["horario"],
            categoria=horario["categoria"]
        )
        await interaction.response.send_modal(modal)


class PainelInscricaoView(discord.ui.View):
    def __init__(self, opcoes: list, tipo: str):
        super().__init__(timeout=None)
        if opcoes:
            select = HorarioSelectMenu(opcoes, tipo)
            select.custom_id = f"ff_psel_{opcoes[0].value}"
            self.add_item(select)


# ==================== MODAL DE COMPRA DE SLOT ====================

class ComprarSlotModal(discord.ui.Modal):
    """Inscrição simples: só o NICK do jogo (sem API, sem ID, sem level).

    Importante: ao enviar, o bot cria apenas o canal de pagamento e uma
    RESERVA pendente. A vaga de verdade, o número do lote e o acesso ao canal
    do diário só são liberados quando a equipe confirmar o pagamento."""

    def __init__(self, horario_id: int, tipo: str, jogadores_qtd: int, valor: float, horario_str: str, categoria: str):
        self.horario_id = horario_id
        self.tipo = tipo
        self.jogadores_qtd = jogadores_qtd
        self.valor = valor
        self.horario_str = horario_str
        self.categoria = categoria

        rotulo = texto_slot(tipo)
        super().__init__(title=f"🎮 Comprar {rotulo} — {tipo.title()}")

        self.campos_jogadores = []
        for indice in range(1, jogadores_qtd + 1):
            campo = discord.ui.TextInput(
                label=f"Nick no Free Fire — Jogador {indice}" + (" (você)" if indice == 1 else ""),
                placeholder="Ex: FF⚡REI",
                max_length=28,
                required=True
            )
            self.add_item(campo)
            self.campos_jogadores.append(campo)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        nicks = []
        for indice, campo in enumerate(self.campos_jogadores, 1):
            nick = " ".join((campo.value or "").split())
            if len(nick) < 2:
                return await interaction.followup.send(
                    embed=criar_embed(
                        "❌ Nick inválido",
                        f"**Jogador {indice}:** escreva o nick como está no jogo.",
                        "Vermelho"
                    ),
                    ephemeral=True
                )
            nicks.append(nick)

        if len({n.lower() for n in nicks}) != len(nicks):
            return await interaction.followup.send(
                embed=criar_embed("❌ Nicks repetidos", "Cada jogador precisa ter um nick diferente.", "Vermelho"),
                ephemeral=True
            )

        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            horario = await (await db.execute("SELECT * FROM horarios WHERE id = ?", (self.horario_id,))).fetchone()
            if not horario:
                return await interaction.followup.send(
                    embed=criar_embed("❌ Erro", "Horário não encontrado.", "Vermelho"),
                    ephemeral=True
                )
            ocupadas = (await (await db.execute(
                "SELECT COUNT(*) FROM slots WHERE horario_id = ?", (self.horario_id,)
            )).fetchone())[0]

        total_vagas = LOTES_POR_MODO[horario["tipo"]]
        pode, motivo = pode_comprar_vaga(horario["horario"], ocupadas, total_vagas)
        if not pode:
            return await interaction.followup.send(
                embed=criar_embed("❌ Indisponível", motivo, "Vermelho"),
                ephemeral=True
            )

        cfg = await obter_config(interaction.guild.id)
        cat_pag = interaction.guild.get_channel(cfg.get("cat_pagamentos"))

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
        }
        for cargo_key in ["cargo_dono", "cargo_gerente", "cargo_mediador"]:
            if cfg.get(cargo_key):
                role = interaction.guild.get_role(cfg[cargo_key])
                if role:
                    overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        canal_pagamento = await interaction.guild.create_text_channel(
            f"💳│{interaction.user.display_name}",
            category=cat_pag,
            overwrites=overwrites
        )

        rotulo = texto_slot(self.tipo)

        # ---- registro da RESERVA (numero = 0, nada de vaga, nada de acesso) ----
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            pix = await (await db.execute(
                "SELECT p.* FROM pix p JOIN staff_status s ON p.user_id = s.user_id AND p.guild_id = s.guild_id "
                "WHERE p.guild_id = ? AND s.online = 1 LIMIT 1",
                (interaction.guild.id,)
            )).fetchone()
            if not pix:
                pix = await (await db.execute("SELECT * FROM pix WHERE guild_id = ? LIMIT 1", (interaction.guild.id,))).fetchone()

            cursor = await db.execute(
                "INSERT INTO slots (horario_id, guild_id, comprador_id, comprador_nome, apelidos, numero, "
                "confirmado, canal_pag, criado_em, valor_cobrado) VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?, ?)",
                (self.horario_id, interaction.guild.id, interaction.user.id, interaction.user.display_name,
                 "|".join([apelidos_do_usuario(interaction.user)] + [str(n).strip() for n in nicks if str(n).strip()])[:200],
                 canal_pagamento.id, agora_brt().isoformat(), self.valor)
            )
            slot_id = cursor.lastrowid

            for pos, nick in enumerate(nicks, 1):
                await db.execute(
                    "INSERT INTO slot_jogadores (slot_id, posicao, ff_uid, ff_nome, ff_nivel, discord_nome) VALUES (?, ?, ?, ?, ?, ?)",
                    (slot_id, pos, "", nick, 0, interaction.user.display_name if pos == 1 else "")
                )
            await db.commit()

        lista_nicks = "\n".join(f"> 👤 **J{i}:** `{n}`" for i, n in enumerate(nicks, 1))

        embed_pagamento = criar_embed(
            titulo=f"💳 Pagamento — {rotulo} (reserva)",
            descricao=f"**Comprador:** {interaction.user.mention}\n\n"
                      f"╔══════════════════════════════════╗\n"
                      f"║  🏷️  {formatar_rotulo_diario(self.tipo, self.categoria)}\n"
                      f"║  ⏰  `{self.horario_str}`\n"
                      f"║  💰  `{formatar_moeda(self.valor)}`\n"
                      f"║  🎫  Reserva — vaga liberada após o pagamento\n"
                      f"╚══════════════════════════════════╝\n\n"
                      f"**Jogadores:**\n{lista_nicks}",
            cor_nome="Amarelo",
            thumb=interaction.user.display_avatar.url,
            footer="Fire Force • Reserva de vaga"
        )

        mencoes_staff = []
        for cargo_key in ["cargo_dono", "cargo_gerente", "cargo_mediador"]:
            if cfg.get(cargo_key):
                role = interaction.guild.get_role(cfg[cargo_key])
                if role:
                    mencoes_staff.append(role.mention)

        instrucoes = (
            "> 1️⃣ Faça o PIX no valor acima\n"
            "> 2️⃣ Envie o comprovante aqui neste canal\n"
            "> 3️⃣ A equipe valida o comprovante e libera tudo pra você\n\n"
            "> 🔒 **A vaga, o número do lote e o acesso ao canal do diário só são liberados depois da aprovação do pagamento.**\n"
            "> 🎟️ Tem cupom? Use `/cupom <codigo>` aqui antes de pagar."
        )

        # ---- PIX agora é 100% LivePix: gera o checkout com o valor exato ----
        link = await link_pagamento(interaction.guild.id, self.valor, tipo="diario", alvo_id=slot_id,
                                    user_id=interaction.user.id, nick=nicks[0] if nicks else "",
                                    horario_id=self.horario_id, canal_id=canal_pagamento.id)

        if link:
            embed_pagamento.add_field(
                name="💳 PIX via LivePix",
                value=f"> **Valor exato:** `{formatar_moeda(self.valor)}`\n"
                      f"> **Nome no pagamento:** `{interaction.user.display_name}`\n"
                      f"> **Link:** {link}",
                inline=False
            )
            embed_pagamento.add_field(
                name="⚡ Liberação automática",
                value="> Pague pelo LivePix escrevendo **o seu nome** no campo de mensagem.\n"
                      "> Assim que o PIX aparecer, a vaga é liberada **sozinha** — sem esperar a equipe.\n"
                      "> Pagou depois de 5 minutos? Sem problema: a equipe valida manualmente pra você.",
                inline=False
            )
        else:
            embed_pagamento.add_field(
                name="💳 PIX via LivePix",
                value=f"> **Valor exato:** `{formatar_moeda(self.valor)}`\n"
                      f"> Fale com a equipe pra receber o link de pagamento.",
                inline=False
            )
        embed_pagamento.add_field(
            name="💰 Tem saldo na carteira?",
            value="> Clique em **💰 Pagar com saldo** aqui embaixo e a vaga é liberada **na hora**.",
            inline=False
        )

        arquivo_qr = None
        if link:
            try:
                arquivo_qr = discord.File(gerar_qr_url(link), "pagamento.png")
                embed_pagamento.set_image(url="attachment://pagamento.png")
            except Exception:
                arquivo_qr = None

        # 🎉 evento rolando? avisa (e inscreve) quem está dentro da aposta mínima
        try:
            evento = await evento_ativo(interaction.guild.id, self.valor, self.tipo, self.categoria)
            if evento:
                await registrar_participante(evento, slot_id, interaction.user.id, self.valor)
                embed_pagamento.add_field(
                    name=f"🎉 EVENTO: {evento['nome']}",
                    value=f"> ✅ **Você está participando!** Sua inscrição de `{formatar_moeda(self.valor)}` "
                          f"bateu a aposta mínima de `{formatar_moeda(evento['aposta_min'])}`.\n"
                          f"> 🎯 Faça `{evento['kills_min']}` kills"
                          + (f" ou fique no `top {evento['top_min']}`" if evento['top_min'] else "")
                          + f" e ganhe `{formatar_moeda(evento['bonus'])}` de BÔNUS na carteira!\n"
                          + (f"> 📝 {evento['descricao'][:150]}" if evento['descricao'] else ""),
                    inline=False)
        except Exception as erro:
            _log_arquivo(f"[EVENTO] erro ao inscrever: {erro}")

        enviar = dict(content=f"{interaction.user.mention} {' '.join(mencoes_staff)}",
                      embed=embed_pagamento, view=PagamentoAcaoView())
        if arquivo_qr:
            enviar["file"] = arquivo_qr
        await canal_pagamento.send(**enviar)

        await interaction.followup.send(
            embed=criar_embed(
                "✅ Reserva Criada",
                f"{rotulo} reservado(a) para **{self.horario_str}**!\n"
                f"> Pague em {canal_pagamento.mention} — a vaga é liberada quando a equipe confirmar o pagamento.",
                "Esmeralda"
            ),
            ephemeral=True
        )
        await rebuild_painel(interaction.guild, horario["painel_id"])


# ==================== GERENCIAMENTO DE PAGAMENTOS ====================

async def _fechar_canal_reserva(canal, mensagem: str, titulo: str = "⌛ Reserva Encerrada"):
    """Avisa no canal de pagamento e apaga ele depois de alguns segundos."""
    try:
        embed = criar_embed(titulo, mensagem, "Amarelo")
        try:
            await canal.send(embed=embed)
        except Exception:
            await canal.send(mensagem)
        await asyncio.sleep(25)
        await canal.delete()
    except Exception:
        pass


class PagamentoAcaoView(discord.ui.View):
    """Botões da equipe. Nada de vaga e nada de acesso antes do ✅."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Confirmar Pagamento", style=discord.ButtonStyle.green, emoji="✅", custom_id="ff_pagok")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await e_staff(interaction.user):
            return await interaction.response.send_message(
                embed=criar_embed("❌ Sem Permissão", "Apenas membros da equipe podem confirmar pagamentos.", "Vermelho"),
                ephemeral=True
            )

        # 🔒 trava: sem isso dois staffs aprovando juntos davam a MESMA vaga
        async with _lock_aprovacao:
            async with aiosqlite.connect(DATABASE_FILE) as db:
                db.row_factory = aiosqlite.Row
                slot = await (await db.execute(
                    "SELECT * FROM slots WHERE canal_pag = ? AND confirmado = 0", (interaction.channel.id,)
                )).fetchone()

                if not slot:
                    return await interaction.response.send_message(
                        embed=criar_embed("❌ Inválido", "Este pagamento já foi aprovado, cancelado ou não existe.", "Vermelho"),
                        ephemeral=True
                    )

                horario = await (await db.execute("SELECT * FROM horarios WHERE id = ?", (slot["horario_id"],))).fetchone()
                if not horario:
                    return await interaction.response.send_message(
                        embed=criar_embed("❌ Erro", "Horário não encontrado.", "Vermelho"),
                        ephemeral=True
                    )

                total_vagas = LOTES_POR_MODO[horario["tipo"]]
                confirmados = (await (await db.execute(
                    "SELECT COUNT(*) FROM slots WHERE horario_id = ? AND confirmado = 1", (slot["horario_id"],)
                )).fetchone())[0]

                if confirmados >= total_vagas:
                    return await interaction.response.send_message(
                        embed=criar_embed(
                            "❌ Sala lotada",
                            f"A sala já está lotada ({total_vagas}/{total_vagas}).\nUse **Recusar** para liberar este pagamento.",
                            "Vermelho"
                        ),
                        ephemeral=True
                    )

                numero_final = confirmados + 1
                await db.execute("UPDATE slots SET confirmado = 1, numero = ? WHERE id = ?", (numero_final, slot["id"]))
                await db.execute("UPDATE horarios SET lotes_usados = ? WHERE id = ?", (numero_final, slot["horario_id"]))
                await db.commit()

        # 🙋 ninguém assumiu? quem confirmou assume (e leva a comissão)
        if not slot["assumido_por"]:
            async with aiosqlite.connect(DATABASE_FILE) as db:
                await db.execute("UPDATE slots SET assumido_por = ? WHERE id = ?",
                                 (interaction.user.id, slot["id"]))
                await db.commit()
            slot = dict(slot)
            slot["assumido_por"] = interaction.user.id

        # 💰 receita no caixa + comissão de quem assumiu (carteira de trabalho) + logs
        try:
            await pos_aprovacao(interaction.guild, dict(slot), dict(horario),
                                staff_id=slot["assumido_por"], origem="staff")
        except Exception as erro:
            print("Erro no pós-aprovação:", erro)

        rotulo = texto_slot(horario["tipo"])

        # ---- só agora a vaga existe: cria o canal do diário (se for a 1ª venda),
        #      libera o acesso do comprador e publica/atualiza a tabela ----
        try:
            canal_tabela_id = await criar_canal_tabela(interaction.guild, slot["horario_id"])
        except Exception as erro:
            canal_tabela_id = None
            print("Erro ao criar canal do diário:", erro)

        comprador = await membro_do_guild(interaction.guild, slot["comprador_id"])
        if comprador:
            await add_jogador_canal_tabela(interaction.guild, slot["horario_id"], comprador)

        try:
            await atualizar_tabela(interaction.guild, slot["horario_id"])
        except Exception as erro:
            print("Erro ao atualizar tabela:", erro)
        await rebuild_painel(interaction.guild, horario["painel_id"])

        try:
            await interaction.channel.edit(name=f"✅│{rotulo.lower()}-{numero_final}")
        except Exception:
            pass

        canal_tabela = interaction.guild.get_channel(canal_tabela_id) if canal_tabela_id else None
        acesso_txt = f"\n> 📊 Acompanhe no canal {canal_tabela.mention} — seu acesso já foi liberado!" if canal_tabela else ""

        jogadores_do_slot = await _jogadores_do_slot(slot["id"])
        nicks_txt = ", ".join("`" + (j["ff_nome"] or "???") + "`" for j in jogadores_do_slot) or "`???`"

        embed_sucesso = criar_embed(
            titulo="✅ Pagamento Aprovado!",
            descricao=f"**Aprovado por:** {interaction.user.mention}\n"
                      f"**{rotulo}:** `#{numero_final}`\n"
                      f"**Jogador(es):** {nicks_txt}\n\n"
                      f"🔓 Vaga liberada e acesso concedido."
                      f"{acesso_txt}\n\n"
                      f"📩 **ID e senha da sala** são enviados automaticamente **5 minutos antes** do início.",
            cor_nome="Esmeralda",
            footer=f"Fire Force • {rotulo} #{numero_final}"
        )
        await interaction.response.send_message(
            content=mencao(slot["comprador_id"]), embed=embed_sucesso
        )

        try:
            async for msg in interaction.channel.history(limit=6):
                if msg.author == interaction.guild.me and msg.components:
                    await msg.edit(view=None)
                    break
        except Exception:
            pass

    @discord.ui.button(label="Assumir", style=discord.ButtonStyle.gray, emoji="🙋", custom_id="ff_pagassumir")
    async def assumir_pagamento(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Primeiro staff que clicar assume o pagamento — e leva a comissão."""
        if not await e_staff(interaction.user):
            return await interaction.response.send_message(
                embed=criar_embed("❌ Sem Permissão", "Apenas a equipe (ADM/mediador/gerência).", "Vermelho"),
                ephemeral=True)
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            slot = await (await db.execute(
                "SELECT * FROM slots WHERE canal_pag = ? AND confirmado = 0", (interaction.channel.id,))).fetchone()
        if not slot:
            return await interaction.response.send_message(
                embed=criar_embed("❌ Indisponível", "Este pagamento já foi resolvido.", "Vermelho"), ephemeral=True)
        if slot["assumido_por"] and slot["assumido_por"] != interaction.user.id:
            return await interaction.response.send_message(
                embed=criar_embed("🙋 Já foi assumido",
                                  f"{mencao(slot['assumido_por'])} está mediando este pagamento.", "Amarelo"),
                ephemeral=True)
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute("UPDATE slots SET assumido_por = ? WHERE id = ?", (interaction.user.id, slot["id"]))
            await db.commit()
        marcar_sujo()
        await interaction.response.send_message(
            embed=criar_embed("🙋 Pagamento assumido",
                              f"{interaction.user.mention} assumiu este pagamento.\n"
                              f"> 💸 A comissão de aprovação é dele.\n"
                              f"> Confirme quando o PIX cair (ou deixe o bot detectar sozinho).", "Esmeralda"))
        await registrar_log_suporte(
            interaction.guild, "💳 PAGAMENTO", "🙋 Pagamento assumido",
            f"{mencao(interaction.user.id)} assumiu o pagamento de {mencao(slot['comprador_id'])} "
            f"(vaga reservada, `{formatar_moeda(slot['valor_cobrado'])}`).", "Verde")

    @discord.ui.button(label="Pagar com saldo", style=discord.ButtonStyle.blurple, emoji="💰", custom_id="ff_pagarsaldo")
    async def pagar_com_saldo_botao(self, interaction: discord.Interaction, button: discord.ui.Button):
        """O próprio jogador paga a reserva com o saldo da carteira — vaga na hora."""
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            slot = await (await db.execute(
                "SELECT * FROM slots WHERE canal_pag = ? AND confirmado = 0", (interaction.channel.id,)
            )).fetchone()

        if not slot:
            return await interaction.response.send_message(
                embed=criar_embed("❌ Indisponível", "Esta reserva já foi liberada ou cancelada.", "Vermelho"),
                ephemeral=True
            )
        if int(slot["comprador_id"]) != interaction.user.id:
            return await interaction.response.send_message(
                embed=criar_embed("❌ Só o dono da reserva",
                                  f"Quem paga com saldo é quem reservou: {mencao(slot['comprador_id'])}.", "Vermelho"),
                ephemeral=True
            )

        ok, mensagem, numero = await pagar_com_saldo(interaction.guild, slot["id"], interaction.user.id)
        await interaction.response.send_message(
            embed=criar_embed("✅ Pago com saldo" if ok else "❌ Não foi possível",
                              mensagem, "Esmeralda" if ok else "Vermelho"),
            ephemeral=True
        )

    @discord.ui.button(label="Recusar / Cancelar", style=discord.ButtonStyle.red, emoji="❌", custom_id="ff_pagno")
    async def recusar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await e_staff(interaction.user):
            return await interaction.response.send_message(
                embed=criar_embed("❌ Sem Permissão", "Apenas membros da equipe podem cancelar reservas.", "Vermelho"),
                ephemeral=True
            )

        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            slot = await (await db.execute(
                "SELECT * FROM slots WHERE canal_pag = ? AND confirmado = 0", (interaction.channel.id,)
            )).fetchone()

            horario = None
            if slot:
                if slot["cupom_id"]:
                    await db.execute("UPDATE cupons SET usos_atuais = usos_atuais - 1 WHERE id = ?", (slot["cupom_id"],))
                    await db.execute("UPDATE cupons_usados SET usos = usos - 1 WHERE cupom_id = ? AND user_id = ?",
                                     (slot["cupom_id"], slot["comprador_id"]))

                horario = await (await db.execute("SELECT * FROM horarios WHERE id = ?", (slot["horario_id"],))).fetchone()

                await db.execute("DELETE FROM slot_jogadores WHERE slot_id = ?", (slot["id"],))
                await db.execute("DELETE FROM slots WHERE id = ?", (slot["id"],))

                if horario:
                    confirmados = (await (await db.execute(
                        "SELECT COUNT(*) FROM slots WHERE horario_id = ? AND confirmado = 1", (slot["horario_id"],)
                    )).fetchone())[0]
                    await db.execute("UPDATE horarios SET lotes_usados = ? WHERE id = ?", (confirmados, slot["horario_id"]))
                await db.commit()

        if horario:
            await rebuild_painel(interaction.guild, horario["painel_id"])

        await interaction.response.send_message(
            embed=criar_embed("❌ Reserva Cancelada", "Nada foi cobrado e a vaga continua livre. Este canal será excluído em 10s.", "Vermelho Escuro")
        )
        await asyncio.sleep(10)
        try:
            await interaction.channel.delete()
        except Exception:
            pass


async def _jogadores_do_slot(slot_id: int) -> list:
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        return await (await db.execute(
            "SELECT ff_nome FROM slot_jogadores WHERE slot_id = ? ORDER BY posicao", (slot_id,)
        )).fetchall()


# ==================== SISTEMA DE CUPONS ====================

class GerenciadorCupomView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=600)

    @discord.ui.button(label="Criar Cupom", style=discord.ButtonStyle.green, emoji="🎟️")
    async def criar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await e_dono_ou_gerente(interaction.user):
            return await interaction.response.send_message(
                embed=criar_embed("❌ Sem Permissão", "Apenas Dono ou Gerente.", "Vermelho"),
                ephemeral=True
            )
        await interaction.response.send_modal(CriarCupomModal())

    @discord.ui.button(label="Remover Cupom", style=discord.ButtonStyle.red, emoji="🗑️")
    async def remover(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await e_dono_ou_gerente(interaction.user):
            return await interaction.response.send_message(
                embed=criar_embed("❌ Sem Permissão", "Apenas Dono ou Gerente.", "Vermelho"),
                ephemeral=True
            )

        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            cupons = await (await db.execute("SELECT * FROM cupons WHERE guild_id = ?", (interaction.guild.id,))).fetchall()

        if not cupons:
            return await interaction.response.send_message(
                embed=criar_embed("⚠️ Vazio", "Nenhum cupom cadastrado neste servidor.", "Amarelo"),
                ephemeral=True
            )

        opcoes = [
            discord.SelectOption(
                label=c['codigo'],
                value=str(c['id']),
                description=f"Desconto: {c['valor']}{'%' if c['tipo_desconto'] == 'pct' else ' R$'}"
            ) for c in cupons
        ]
        await interaction.response.send_message(
            embed=criar_embed("🗑️ Excluir Cupom", "Selecione o cupom que deseja apagar:", "Vermelho"),
            view=RemoverCupomView(opcoes),
            ephemeral=True
        )

    @discord.ui.button(label="Listar Cupons", style=discord.ButtonStyle.blurple, emoji="📋")
    async def listar(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            cupons = await (await db.execute("SELECT * FROM cupons WHERE guild_id = ?", (interaction.guild.id,))).fetchall()

        if not cupons:
            return await interaction.response.send_message(
                embed=criar_embed("📋 Cupons", "Nenhum cupom ativo no momento.", "Cinza"),
                ephemeral=True
            )

        embed = criar_embed("🎟️ Cupons Cadastrados", "", "Fire Force")
        for c in cupons:
            val_txt = f"{c['valor']}%" if c['tipo_desconto'] == "pct" else formatar_moeda(c['valor'])
            usos_txt = f"{c['usos_atuais']}/{c['usos_max'] if c['usos_max'] > 0 else '∞'}"
            exp_txt = c['expira_em'] if c['expira_em'] else "Sem expiração"

            embed.add_field(
                name=f"🎫 {c['codigo']}",
                value=f"> Desconto: `{val_txt}`\n"
                      f"> Limite Global: `{usos_txt}`\n"
                      f"> Limite por Usuário: `{c['usos_por_user']}`\n"
                      f"> Expiração: `{exp_txt}`",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)


class CriarCupomModal(discord.ui.Modal, title="🎟️ Criar Cupom de Desconto"):
    codigo = discord.ui.TextInput(label="Código do Cupom", placeholder="Ex: DESCONTO10", max_length=20)
    desconto = discord.ui.TextInput(label="Desconto (Ex: 10% ou 5.00)", placeholder="10% ou 5.00", max_length=10)
    usos_totais = discord.ui.TextInput(label="Limite Total de Usos (0 = Infinito)", placeholder="0", default="0")
    usos_usuario = discord.ui.TextInput(label="Limite por Usuário", placeholder="1", default="1")
    expiracao = discord.ui.TextInput(label="Expira em (DD/MM/YYYY) (Opcional)", placeholder="31/12/2026", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        cod = self.codigo.value.strip().upper()
        raw_desc = self.desconto.value.strip().replace(",", ".")

        try:
            if raw_desc.endswith("%"):
                tipo_desc = "pct"
                val_desc = float(raw_desc[:-1])
            else:
                tipo_desc = "fixo"
                val_desc = float(raw_desc.replace("R$", "").strip())

            u_totais = int(self.usos_totais.value)
            u_user = int(self.usos_usuario.value)
            dt_expira = self.expiracao.value.strip()

            if dt_expira:
                datetime.datetime.strptime(dt_expira, "%d/%m/%Y")
        except ValueError:
            return await interaction.response.send_message(
                embed=criar_embed("❌ Erro", "Formatos numéricos ou de data inválidos.", "Vermelho"),
                ephemeral=True
            )

        async with aiosqlite.connect(DATABASE_FILE) as db:
            existente = await (await db.execute("SELECT 1 FROM cupons WHERE guild_id = ? AND codigo = ?", (interaction.guild.id, cod))).fetchone()
            if existente:
                return await interaction.response.send_message(
                    embed=criar_embed("⚠️ Código Existente", f"Já existe um cupom com o código `{cod}`.", "Amarelo"),
                    ephemeral=True
                )

            cursor = await db.execute(
                "INSERT INTO cupons (guild_id, codigo, tipo_desconto, valor, usos_max, usos_por_user, expira_em) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (interaction.guild.id, cod, tipo_desc, val_desc, u_totais, u_user, dt_expira)
            )
            cupom_id = cursor.lastrowid
            await db.commit()
        marcar_sujo()

        await anunciar_cupom(interaction.guild, cupom_id)
        canal_cupom = None
        try:
            canal_cupom = interaction.guild.get_channel(int(await cfgv(interaction.guild.id, "canal_cupons", 0)))
        except Exception:
            canal_cupom = None
        await interaction.response.send_message(
            embed=criar_embed("✅ Cupom Criado",
                              f"O cupom `{cod}` foi registrado com sucesso!"
                              + (f"\n> 📣 Anúncio publicado em {canal_cupom.mention} (marcando todo mundo)."
                                 if canal_cupom else
                                 "\n> 💡 Configure o canal de cupons com `/config canal_cupons:#canal` "
                                 "pra anunciar automaticamente."),
                              "Esmeralda"),
            ephemeral=True
        )


class RemoverCupomSelect(discord.ui.Select):
    def __init__(self, opcoes: list):
        super().__init__(placeholder="Selecione o cupom...", options=opcoes)

    async def callback(self, interaction: discord.Interaction):
        cupom_id = int(self.values[0])
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute("DELETE FROM cupons WHERE id = ?", (cupom_id,))
            await db.commit()

        await interaction.response.send_message(
            embed=criar_embed("✅ Removido", "Cupom excluído com sucesso.", "Esmeralda"),
            ephemeral=True
        )


class RemoverCupomView(discord.ui.View):
    def __init__(self, opcoes: list):
        super().__init__(timeout=120)
        self.add_item(RemoverCupomSelect(opcoes))


# ==================== PAINEL ADMIN (GERENCIAR HORÁRIOS) ====================

class PainelAdminView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=600)

    @discord.ui.button(label="Adicionar Horário", style=discord.ButtonStyle.green, emoji="➕", row=0)
    async def add_horario(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await e_dono_ou_gerente(interaction.user):
            return await interaction.response.send_message(
                embed=criar_embed("❌ Sem Permissão", "Apenas Dono ou Gerente.", "Vermelho"),
                ephemeral=True
            )

        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            paineis = await (await db.execute("SELECT * FROM paineis WHERE guild_id = ?", (interaction.guild.id,))).fetchall()

        if not paineis:
            return await interaction.response.send_message(
                embed=criar_embed("⚠️ Nenhum Painel", "Crie um painel com `/diario` antes de adicionar horários.", "Amarelo"),
                ephemeral=True
            )

        opcoes = [
            discord.SelectOption(
                label=formatar_rotulo_diario(p['tipo'], p['categoria']),
                value=str(p['id'])
            ) for p in paineis
        ]
        await interaction.response.send_message(
            embed=criar_embed("➕ Selecionar Painel", "Escolha qual painel receberá o novo horário:", "Azul"),
            view=SelecionarPainelView(opcoes),
            ephemeral=True
        )

    @discord.ui.button(label="Remover Horário", style=discord.ButtonStyle.red, emoji="🗑️", row=0)
    async def rem_horario(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await e_dono_ou_gerente(interaction.user):
            return await interaction.response.send_message(
                embed=criar_embed("❌ Sem Permissão", "Apenas Dono ou Gerente.", "Vermelho"),
                ephemeral=True
            )

        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            horarios = await (await db.execute(
                "SELECT h.*, p.tipo as pt, p.categoria as pc FROM horarios h JOIN paineis p ON h.painel_id = p.id WHERE h.guild_id = ? AND h.ativo = 1",
                (interaction.guild.id,)
            )).fetchall()

        if not horarios:
            return await interaction.response.send_message(
                embed=criar_embed("⚠️ Vazio", "Nenhum horário ativo para remover.", "Amarelo"),
                ephemeral=True
            )

        opcoes = [
            discord.SelectOption(
                label=f"{h['horario']} — {formatar_rotulo_diario(h['pt'], h['pc'])}",
                value=str(h['id'])
            ) for h in horarios
        ]
        await interaction.response.send_message(
            embed=criar_embed("🗑️ Remover Horário", "Selecione o horário que deseja desativar:", "Vermelho"),
            view=RemoverHorarioSelectView(opcoes),
            ephemeral=True
        )

    @discord.ui.button(label="Alterar Valor", style=discord.ButtonStyle.gray, emoji="💰", row=0)
    async def alt_valor(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await e_dono_ou_gerente(interaction.user):
            return await interaction.response.send_message(
                embed=criar_embed("❌ Sem Permissão", "Apenas Dono ou Gerente.", "Vermelho"),
                ephemeral=True
            )
        await interaction.response.send_modal(AlterarValorModal())

    @discord.ui.button(label="Listar Tudo", style=discord.ButtonStyle.blurple, emoji="📋", row=1)
    async def listar(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            horarios = await (await db.execute(
                "SELECT h.*, p.tipo as pt, p.categoria as pc FROM horarios h JOIN paineis p ON h.painel_id = p.id WHERE h.guild_id = ? AND h.ativo = 1 ORDER BY h.horario",
                (interaction.guild.id,)
            )).fetchall()

        if not horarios:
            return await interaction.response.send_message(
                embed=criar_embed("📋 Horários", "Nenhum horário ativo.", "Cinza"),
                ephemeral=True
            )

        embed = criar_embed("📋 Horários Ativos", "", "Fire Force")
        for h in horarios:
            pode, _ = pode_comprar_vaga(h["horario"], h["lotes_usados"], LOTES_POR_MODO[h["pt"]])
            icon = "🟢" if pode else "🔴"
            rot = texto_slots_plural(h["pt"])
            restantes = LOTES_POR_MODO[h["pt"]] - h["lotes_usados"]

            embed.add_field(
                name=f"{icon} ID:{h['id']} — {formatar_rotulo_diario(h['pt'], h['pc'])} — {h['horario']}",
                value=f"> Valor: `{formatar_moeda(h['valor'])}`\n"
                      f"> {rot}: `{restantes}` disponíveis\n"
                      f"> Premiação: `{h['premiacao']}`",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Premiação", style=discord.ButtonStyle.gray, emoji="🏆", row=1)
    async def premiacao(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await e_dono_ou_gerente(interaction.user):
            return await interaction.response.send_message(
                embed=criar_embed("❌ Sem Permissão", "Apenas Dono ou Gerente.", "Vermelho"),
                ephemeral=True
            )
        await interaction.response.send_modal(AlterarPremiacaoModal())


class SelecionarPainelSelect(discord.ui.Select):
    def __init__(self, opcoes: list):
        super().__init__(placeholder="Selecione o painel...", options=opcoes)

    async def callback(self, interaction: discord.Interaction):
        painel_id = int(self.values[0])
        await interaction.response.send_modal(AdicionarHorarioModal(painel_id))


class SelecionarPainelView(discord.ui.View):
    def __init__(self, opcoes: list):
        super().__init__(timeout=120)
        self.add_item(SelecionarPainelSelect(opcoes))


class AdicionarHorarioModal(discord.ui.Modal, title="➕ Adicionar Novo Horário"):
    horario = discord.ui.TextInput(label="Horário (HH:MM)", placeholder="Ex: 20:00", max_length=5)
    valor = discord.ui.TextInput(label="Valor da Inscrição (R$)", placeholder="Ex: 6.00", max_length=10)
    premiacao = discord.ui.TextInput(
        label="Premiação (Livre)",
        placeholder="Ex: Por Kill R$ 2.00 | Top 1 R$ 50",
        max_length=200,
        required=False
    )

    def __init__(self, painel_id: int):
        super().__init__()
        self.painel_id = painel_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            hp = self.horario.value.strip().split(":")
            horario_fmt = f"{int(hp[0]):02d}:{int(hp[1]):02d}"
            val = float(self.valor.value.replace(",", "."))
        except ValueError:
            return await interaction.response.send_message(
                embed=criar_embed("❌ Erro", "Valores numéricos ou de horário inválidos.", "Vermelho"),
                ephemeral=True
            )

        if (horario_para_datetime(horario_fmt) - agora_brt()).total_seconds() < 600:
            return await interaction.response.send_message(
                embed=criar_embed("❌ Erro", "Não é possível cadastrar horários com menos de 10 minutos de antecedência.", "Vermelho"),
                ephemeral=True
            )

        prem = self.premiacao.value.strip() or "Por Kill"

        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            painel = await (await db.execute("SELECT * FROM paineis WHERE id = ?", (self.painel_id,))).fetchone()
            if not painel:
                return await interaction.response.send_message(
                    embed=criar_embed("❌ Erro", "Painel não encontrado.", "Vermelho"),
                    ephemeral=True
                )

            await db.execute(
                "INSERT INTO horarios (guild_id, painel_id, tipo, categoria, horario, valor, premiacao, vagas_total) VALUES (?, ?, ?, ?, ?, ?, ?, 48)",
                (interaction.guild.id, self.painel_id, painel["tipo"], painel["categoria"], horario_fmt, val, prem)
            )
            await db.commit()

        await rebuild_painel(interaction.guild, self.painel_id)
        await interaction.response.send_message(
            embed=criar_embed("✅ Horário Cadastrado", f"Horário `{horario_fmt}` adicionado no valor de `{formatar_moeda(val)}`!", "Esmeralda"),
            ephemeral=True
        )


class RemoverHorarioSelect(discord.ui.Select):
    def __init__(self, opcoes: list):
        super().__init__(placeholder="Selecione o horário para remover...", options=opcoes)

    async def callback(self, interaction: discord.Interaction):
        horario_id = int(self.values[0])
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            horario = await (await db.execute("SELECT * FROM horarios WHERE id = ?", (horario_id,))).fetchone()
            await db.execute("UPDATE horarios SET ativo = 0 WHERE id = ?", (horario_id,))
            await db.commit()

            if horario:
                await rebuild_painel(interaction.guild, horario["painel_id"])

        await interaction.response.send_message(
            embed=criar_embed("✅ Removido", "Horário desativado com sucesso.", "Esmeralda"),
            ephemeral=True
        )


class RemoverHorarioSelectView(discord.ui.View):
    def __init__(self, opcoes: list):
        super().__init__(timeout=120)
        self.add_item(RemoverHorarioSelect(opcoes))


class AlterarValorModal(discord.ui.Modal, title="💰 Alterar Valor do Horário"):
    horario_id = discord.ui.TextInput(label="ID do Horário (consulte na lista)", placeholder="1")
    novo_valor = discord.ui.TextInput(label="Novo Valor (R$)", placeholder="8.00")

    async def on_submit(self, interaction: discord.Interaction):
        try:
            hid = int(self.horario_id.value)
            val = float(self.novo_valor.value.replace(",", "."))
            async with aiosqlite.connect(DATABASE_FILE) as db:
                db.row_factory = aiosqlite.Row
                horario = await (await db.execute("SELECT * FROM horarios WHERE id = ?", (hid,))).fetchone()
                if not horario:
                    return await interaction.response.send_message(
                        embed=criar_embed("❌ Erro", "Horário não encontrado.", "Vermelho"),
                        ephemeral=True
                    )

                await db.execute("UPDATE horarios SET valor = ? WHERE id = ?", (val, hid))
                await db.commit()

                await rebuild_painel(interaction.guild, horario["painel_id"])

            await interaction.response.send_message(
                embed=criar_embed("✅ Atualizado", f"Novo valor do horário #{hid}: `{formatar_moeda(val)}`", "Esmeralda"),
                ephemeral=True
            )
        except ValueError:
            await interaction.response.send_message(
                embed=criar_embed("❌ Erro", "Digite valores válidos.", "Vermelho"),
                ephemeral=True
            )


class AlterarPremiacaoModal(discord.ui.Modal, title="🏆 Alterar Premiação"):
    horario_id = discord.ui.TextInput(label="ID do Horário", placeholder="1")
    premiacao = discord.ui.TextInput(label="Nova Descrição da Premiação", placeholder="Ex: Por Kill R$ 2.00 | Top 1 R$ 50", max_length=200)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            hid = int(self.horario_id.value)
            async with aiosqlite.connect(DATABASE_FILE) as db:
                db.row_factory = aiosqlite.Row
                horario = await (await db.execute("SELECT * FROM horarios WHERE id = ?", (hid,))).fetchone()
                if not horario:
                    return await interaction.response.send_message(
                        embed=criar_embed("❌ Erro", "Horário não encontrado.", "Vermelho"),
                        ephemeral=True
                    )

                await db.execute("UPDATE horarios SET premiacao = ? WHERE id = ?", (self.premiacao.value.strip(), hid))
                await db.commit()

                await rebuild_painel(interaction.guild, horario["painel_id"])

            await interaction.response.send_message(
                embed=criar_embed("✅ Atualizado", f"Premiação do horário #{hid} atualizada!", "Esmeralda"),
                ephemeral=True
            )
        except ValueError:
            await interaction.response.send_message(
                embed=criar_embed("❌ Erro", "ID inválido.", "Vermelho"),
                ephemeral=True
            )


# ==================== CONFIGURAÇÃO INICIAL (SETUP) ====================

class SetupCargosView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="👑 Cargo de Dono...", row=0)
    async def dono(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        await salvar_config(interaction.guild.id, cargo_dono=select.values[0].id)
        await interaction.response.send_message(
            embed=criar_embed("✅ Cargos", f"Dono definido como {select.values[0].mention}", "Esmeralda"),
            ephemeral=True
        )

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="🛡️ Cargo de Gerente...", row=1)
    async def gerente(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        await salvar_config(interaction.guild.id, cargo_gerente=select.values[0].id)
        await interaction.response.send_message(
            embed=criar_embed("✅ Cargos", f"Gerente definido como {select.values[0].mention}", "Esmeralda"),
            ephemeral=True
        )

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="⚔️ Cargo de Mediador...", row=2)
    async def mediador(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        await salvar_config(interaction.guild.id, cargo_mediador=select.values[0].id)
        await interaction.response.send_message(
            embed=criar_embed("✅ Cargos", f"Mediador definido como {select.values[0].mention}", "Esmeralda"),
            ephemeral=True
        )

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="🎧 Cargo de Suporte...", row=3)
    async def suporte(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        await salvar_config(interaction.guild.id, cargo_suporte=select.values[0].id)
        await interaction.response.send_message(
            embed=criar_embed("✅ Cargos", f"Suporte definido como {select.values[0].mention}", "Esmeralda"),
            ephemeral=True
        )


class SetupCategoriasView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="💎 Categoria Diários Premium...", channel_types=[discord.ChannelType.category], row=0)
    async def premium(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await salvar_config(interaction.guild.id, cat_premium=select.values[0].id)
        await interaction.response.send_message(
            embed=criar_embed("✅ Categorias", f"Premium -> {select.values[0].mention}", "Esmeralda"),
            ephemeral=True
        )

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="🪙 Categoria Diários Básico...", channel_types=[discord.ChannelType.category], row=1)
    async def basico(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await salvar_config(interaction.guild.id, cat_basico=select.values[0].id)
        await interaction.response.send_message(
            embed=criar_embed("✅ Categorias", f"Básico -> {select.values[0].mention}", "Esmeralda"),
            ephemeral=True
        )

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="💳 Categoria Pagamentos...", channel_types=[discord.ChannelType.category], row=2)
    async def pagamentos(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await salvar_config(interaction.guild.id, cat_pagamentos=select.values[0].id)
        await interaction.response.send_message(
            embed=criar_embed("✅ Categorias", f"Pagamentos -> {select.values[0].mention}", "Esmeralda"),
            ephemeral=True
        )

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="🎫 Categoria Tickets...", channel_types=[discord.ChannelType.category], row=3)
    async def tickets(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        await salvar_config(interaction.guild.id, cat_tickets=select.values[0].id)
        await interaction.response.send_message(
            embed=criar_embed("✅ Categorias", f"Tickets -> {select.values[0].mention}", "Esmeralda"),
            ephemeral=True
        )


class SetupMainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=600)

    @discord.ui.button(label="Cargos", style=discord.ButtonStyle.blurple, emoji="👑", row=0)
    async def cargos(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                embed=criar_embed("❌ Erro", "Apenas administradores.", "Vermelho"),
                ephemeral=True
            )
        await interaction.response.send_message(
            embed=criar_embed("👑 Configurar Cargos", "Selecione a atribuição para cada função:", "Azul Royal"),
            view=SetupCargosView(),
            ephemeral=True
        )

    @discord.ui.button(label="Categorias", style=discord.ButtonStyle.green, emoji="📂", row=0)
    async def categorias(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                embed=criar_embed("❌ Erro", "Apenas administradores.", "Vermelho"),
                ephemeral=True
            )
        await interaction.response.send_message(
            embed=criar_embed("📂 Configurar Categorias", "Selecione as categorias correspondentes aos módulos:", "Esmeralda"),
            view=SetupCategoriasView(),
            ephemeral=True
        )

    @discord.ui.button(label="Ver Configuração", style=discord.ButtonStyle.gray, emoji="📋", row=0)
    async def ver(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = await obter_config(interaction.guild.id)
        embed = criar_embed("📋 Configurações Atuais", "", cfg.get("cor", "Fire Force"))

        cargos_str = ""
        for nome, chave in [("Dono", "cargo_dono"), ("Gerente", "cargo_gerente"), ("Mediador", "cargo_mediador"), ("Suporte", "cargo_suporte")]:
            role = interaction.guild.get_role(cfg.get(chave, 0)) if cfg.get(chave) else None
            cargos_str += f"> **{nome}:** {role.mention if role else '`Não definido`'}\n"
        embed.add_field(name="👑 Cargos", value=cargos_str, inline=False)

        cats_str = ""
        for nome, chave in [("Premium", "cat_premium"), ("Básico", "cat_basico"), ("Pagamentos", "cat_pagamentos"), ("Tickets", "cat_tickets")]:
            canal = interaction.guild.get_channel(cfg.get(chave, 0)) if cfg.get(chave) else None
            cats_str += f"> **{nome}:** {canal.mention if canal else '`Não definida`'}\n"
        embed.add_field(name="📂 Categorias", value=cats_str, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


# ==================== SISTEMA DE TICKETS ====================

# (painel/controle de ticket antigos removidos — substituídos pelo ATENDIMENTO v2)


class TicketRenomearModal(discord.ui.Modal, title="✏️ Renomear Canal"):
    nome = discord.ui.TextInput(label="Novo nome do canal", max_length=100)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.channel.edit(name=self.nome.value)
        await interaction.response.send_message(
            embed=criar_embed("✅ Renomeado", f"Canal alterado para: `{self.nome.value}`", "Esmeralda"),
            ephemeral=True
        )


class TicketAddSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(placeholder="Selecione o usuário para adicionar...")

    async def callback(self, interaction: discord.Interaction):
        usuario = self.values[0]
        await interaction.channel.set_permissions(usuario, view_channel=True, send_messages=True)
        await interaction.response.send_message(f"✅ {usuario.mention} foi adicionado ao atendimento.")


class TicketAddView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(TicketAddSelect())


class TicketRemSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(placeholder="Selecione o usuário para remover...")

    async def callback(self, interaction: discord.Interaction):
        usuario = self.values[0]
        await interaction.channel.set_permissions(usuario, overwrite=None)
        await interaction.response.send_message(f"✅ {usuario.mention} foi removido do atendimento.")


class TicketRemView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(TicketRemSelect())


# ==================== STAFF ONLINE / OFFLINE ====================

class StaffPainelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Online", style=discord.ButtonStyle.green, emoji="🟢", custom_id="ff_son_v4")
    async def online(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await e_staff(interaction.user):
            return await interaction.response.send_message(embed=criar_embed("❌ Erro", "Apenas staff.", "Vermelho"), ephemeral=True)

        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute("INSERT OR REPLACE INTO staff_status VALUES (?, ?, 1)", (interaction.user.id, interaction.guild.id))
            await db.commit()
        marcar_sujo()

        await self._atualizar_painel(interaction)
        await interaction.response.send_message(embed=criar_embed("🟢 Status", "Você agora está ON.", "Esmeralda"), ephemeral=True)

    @discord.ui.button(label="Offline", style=discord.ButtonStyle.red, emoji="🔴", custom_id="ff_soff_v4")
    async def offline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await e_staff(interaction.user):
            return await interaction.response.send_message(embed=criar_embed("❌ Erro", "Apenas staff.", "Vermelho"), ephemeral=True)

        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute("INSERT OR REPLACE INTO staff_status VALUES (?, ?, 0)", (interaction.user.id, interaction.guild.id))
            await db.commit()
        marcar_sujo()

        await self._atualizar_painel(interaction)
        await interaction.response.send_message(embed=criar_embed("🔴 Status", "Você agora está OFF.", "Vermelho"), ephemeral=True)

    async def _atualizar_painel(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute("SELECT * FROM staff_status WHERE guild_id = ?", (interaction.guild.id,))).fetchall()

        on_txt, off_txt = "", ""
        for r in rows:
            quem = mencao(r["user_id"])          # funciona sem intent de membros
            if r["online"]:
                on_txt += f"> 🟢 {quem}\n"
            else:
                off_txt += f"> 🔴 {quem}\n"

        embed = criar_embed("👥 Status da Equipe", "", "Fire Force")
        embed.add_field(name="✅ Disponíveis", value=on_txt or "> *Nenhum*", inline=True)
        embed.add_field(name="⛔ Indisponíveis", value=off_txt or "> *Nenhum*", inline=True)

        try:
            await interaction.message.edit(embed=embed, view=StaffPainelView())
        except Exception:
            pass


# ==================== EMBED BUILDER ====================

class EmbedCorSelect(discord.ui.Select):
    def __init__(self, page: int = 0):
        nomes = list(CORES_DICCIONARIO.keys())
        start = page * 25
        super().__init__(
            placeholder="🎨 Selecione a cor da embed...",
            options=[discord.SelectOption(label=n, value=n) for n in nomes[start:start+25]],
            row=page
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.cor = self.values[0]
        await interaction.response.send_message(
            embed=criar_embed("🎨 Cor Selecionada", f"Cor definida como: **{self.values[0]}**", self.values[0]),
            ephemeral=True
        )


class EmbedBuilderView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.cor = "Fire Force"
        self.add_item(EmbedCorSelect(0))
        if len(CORES_DICCIONARIO) > 25:
            self.add_item(EmbedCorSelect(1))

    @discord.ui.button(label="Montar Embed", style=discord.ButtonStyle.green, emoji="📝", row=2)
    async def montar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedBuilderModal(self.cor))


class EmbedBuilderModal(discord.ui.Modal, title="📝 Construtor de Embed"):
    titulo = discord.ui.TextInput(label="Título da Embed", max_length=256)
    descricao = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.paragraph, max_length=4000)
    footer = discord.ui.TextInput(label="Rodapé (Opcional)", required=False)
    imagem = discord.ui.TextInput(label="URL Imagem Grande (Opcional)", required=False)
    thumbnail = discord.ui.TextInput(label="URL Thumbnail (Opcional)", required=False)

    def __init__(self, cor: str):
        super().__init__()
        self.cor = cor

    async def on_submit(self, interaction: discord.Interaction):
        embed = criar_embed(
            titulo=self.titulo.value,
            descricao=self.descricao.value,
            cor_nome=self.cor,
            footer=self.footer.value or "Fire Force",
            author=interaction.user.display_name,
            author_icon=interaction.user.display_avatar.url
        )
        if self.imagem.value:
            embed.set_image(url=self.imagem.value)
        if self.thumbnail.value:
            embed.set_thumbnail(url=self.thumbnail.value)

        await interaction.response.send_message(embed=embed)


# ==================== ENVIO DE SALA (ID E SENHA) ====================

async def enviar_sala(guild: discord.Guild, tipo: str, categoria: str, horario: str, sala_id: str, sala_senha: str):
    """Avisa todo mundo que a sala abriu: ID, senha e a tabela em texto."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        horarios = await (await db.execute(
            "SELECT * FROM horarios WHERE guild_id = ? AND tipo = ? AND categoria = ? AND horario = ?",
            (guild.id, tipo, categoria, horario)
        )).fetchall()

        if not horarios:
            return 0

        total_jogadores = 0
        mencoes = []

        for h in horarios:
            if not h["canal_tabela"]:
                continue
            canal = guild.get_channel(h["canal_tabela"])
            if not canal:
                continue

            lotes = await (await db.execute(
                "SELECT * FROM slots WHERE horario_id = ? AND confirmado = 1", (h["id"],)
            )).fetchall()
            for lote in lotes:
                # menção por ID: não depende do intent de membros nem de cache
                mencoes.append(mencao(lote["comprador_id"]))

                jogadores = await (await db.execute(
                    "SELECT * FROM slot_jogadores WHERE slot_id = ?", (lote["id"],)
                )).fetchall()
                total_jogadores += len(jogadores)

            ocupadas = (await (await db.execute(
                "SELECT COUNT(*) FROM slots WHERE horario_id = ?", (h["id"],)
            )).fetchone())[0]

            slots_data = await obter_slots_data(h["id"])

            embed_sala = criar_embed(
                titulo="🚨 SALA LIBERADA!",
                descricao=f"**{formatar_rotulo_diario(tipo, categoria)}** — `{horario}`\n"
                          f"**⏰ O diário começa em menos de 5 minutos!**\n\n"
                          f"**🆔 ID da sala** (toque para copiar)\n```\n{sala_id}\n```\n"
                          f"**🔑 Senha**\n```\n{sala_senha}\n```",
                cor_nome="Esmeralda",
                footer="Fire Force • Boa sorte e bom jogo!"
            )
            embed_tabela = montar_embed_tabela(
                dict(h), slots_data, ocupadas,
                atualizado_em=agora_brt().strftime("%H:%M:%S")
            )

            mencoes_str = " ".join(mencoes)
            aviso = f"🚨🚨🚨 {mencoes_str} 🚨🚨🚨" if mencoes_str else "🚨🚨🚨 **SALA LIBERADA!** 🚨🚨🚨"

            if len(aviso) > 1900:
                await canal.send("🚨🚨🚨 **SALA LIBERADA!** 🚨🚨🚨", embeds=[embed_sala, embed_tabela])
                chunk = ""
                for mencao_txt in mencoes:
                    if len(chunk) + len(mencao_txt) > 1800:
                        await canal.send(chunk)
                        chunk = mencao_txt + " "
                    else:
                        chunk += mencao_txt + " "
                if chunk:
                    await canal.send(chunk)
            else:
                await canal.send(aviso, embeds=[embed_sala, embed_tabela])

            await db.execute("UPDATE horarios SET sala_id = ?, sala_senha = ? WHERE id = ?",
                             (sala_id, sala_senha, h["id"]))

        await db.commit()
        return total_jogadores


# ==================== LOOPS DE TAREFAS ====================

RESERVA_MINUTOS = 30          # reserva sem pagamento confirmado expira nesse tempo
LOOP_VERIFICACAO = 30         # de quanto em quanto tempo roda a checagem


async def loop_expirar():
    """Encerra diários que já passaram, cancela reservas sem pagamento e
    fecha os canais de pagamento pendentes."""
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            agora = agora_brt()
            avisos = []          # (canal, titulo, mensagem)
            paineis_para_atualizar = []

            async with aiosqlite.connect(DATABASE_FILE) as db:
                db.row_factory = aiosqlite.Row

                # ---------- 1) reservas pendentes antigas (pagamento não confirmado) ----------
                limite = (agora - datetime.timedelta(minutes=RESERVA_MINUTOS)).isoformat()
                pendentes_antigas = await (await db.execute(
                    "SELECT * FROM slots WHERE confirmado = 0 AND criado_em < ?", (limite,)
                )).fetchall()

                for p in pendentes_antigas:
                    await db.execute("DELETE FROM slot_jogadores WHERE slot_id = ?", (p["id"],))
                    await db.execute("DELETE FROM slots WHERE id = ?", (p["id"],))
                    guild = bot.get_guild(p["guild_id"])
                    canal = guild.get_channel(p["canal_pag"]) if guild and p["canal_pag"] else None
                    if canal:
                        avisos.append((
                            canal,
                            "⌛ Reserva Expirada",
                            f"A reserva ficou **{RESERVA_MINUTOS} minutos** sem pagamento e foi cancelada.\n"
                            f"Sem problema: é só fazer a inscrição novamente quando quiser."
                        ))
                if pendentes_antigas:
                    await db.commit()

                # ---------- 2) diários que já começaram ----------
                horarios = await (await db.execute("SELECT * FROM horarios WHERE ativo = 1")).fetchall()
                for h in horarios:
                    if (horario_para_datetime(h["horario"]) - agora).total_seconds() >= 0:
                        continue

                    await db.execute("UPDATE horarios SET ativo = 0 WHERE id = ?", (h["id"],))

                    pendentes = await (await db.execute(
                        "SELECT * FROM slots WHERE horario_id = ? AND confirmado = 0", (h["id"],)
                    )).fetchall()
                    for p in pendentes:
                        await db.execute("DELETE FROM slot_jogadores WHERE slot_id = ?", (p["id"],))
                        await db.execute("DELETE FROM slots WHERE id = ?", (p["id"],))
                        guild = bot.get_guild(p["guild_id"])
                        canal = guild.get_channel(p["canal_pag"]) if guild and p["canal_pag"] else None
                        if canal:
                            avisos.append((canal, "⌛ Reserva Encerrada",
                                           "O diário já começou e esta reserva foi cancelada."))

                    confirmadas = (await (await db.execute(
                        "SELECT COUNT(*) FROM slots WHERE horario_id = ? AND confirmado = 1", (h["id"],)
                    )).fetchone())[0]
                    await db.execute("UPDATE horarios SET lotes_usados = ? WHERE id = ?", (confirmadas, h["id"]))
                    paineis_para_atualizar.append((h["guild_id"], h["painel_id"]))

                await db.commit()

            # ---------- ações fora do banco ----------
            for guild_id, painel_id in paineis_para_atualizar:
                guild = bot.get_guild(guild_id)
                if guild:
                    try:
                        await rebuild_painel(guild, painel_id)
                    except Exception:
                        pass

            for canal, titulo, mensagem in avisos:
                asyncio.create_task(_fechar_canal_reserva(canal, mensagem, titulo))

        except Exception as e:
            print("Erro no loop de expiração:", e)
        await asyncio.sleep(LOOP_VERIFICACAO)


async def loop_salas():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            agora = agora_brt()
            async with aiosqlite.connect(DATABASE_FILE) as db:
                db.row_factory = aiosqlite.Row
                salas = await (await db.execute("SELECT * FROM salas WHERE enviado = 0")).fetchall()

            for s in salas:
                diferenca = (horario_para_datetime(s["horario"]) - agora).total_seconds()
                if 0 < diferenca <= 300:  # 5 minutos
                    guild = bot.get_guild(s["guild_id"])
                    if guild:
                        await enviar_sala(guild, s["tipo"], s["categoria"], s["horario"], s["sala_id"], s["sala_senha"])

                    async with aiosqlite.connect(DATABASE_FILE) as db:
                        await db.execute("UPDATE salas SET enviado = 1 WHERE id = ?", (s["id"],))
                        await db.commit()
        except Exception as e:
            print("Erro no loop de salas:", e)
        await asyncio.sleep(15)


async def loop_tabelas():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            async with aiosqlite.connect(DATABASE_FILE) as db:
                db.row_factory = aiosqlite.Row
                horarios = await (await db.execute("SELECT * FROM horarios WHERE ativo = 1 AND canal_tabela IS NOT NULL AND canal_tabela > 0")).fetchall()

            for h in horarios:
                for guild in bot.guilds:
                    if guild.id == h["guild_id"]:
                        try:
                            await atualizar_tabela(guild, h["id"])
                        except Exception as e:
                            print(f"Erro ao atualizar tabela #{h['id']}:", e)
        except Exception as e:
            print("Erro no loop de tabelas:", e)
        await asyncio.sleep(15)


# ==================== SLASH COMMANDS ====================

@bot.tree.command(name="setup", description="⚙️ Configurar o servidor (Cargos e Categorias)")
@app_commands.default_permissions(administrator=True)
async def cmd_setup(interaction: discord.Interaction):
    await interaction.response.send_message(
        embed=criar_embed("⚙️ Configuração Inicial", "Selecione as opções abaixo para configurar o servidor:", "Fire Force"),
        view=SetupMainView(),
        ephemeral=True
    )


@bot.tree.command(name="reset", description="⚠️ Resetar e excluir todos os painéis e horários de diários")
@app_commands.default_permissions(administrator=True)
async def cmd_reset(interaction: discord.Interaction):
    if not await e_dono_ou_gerente(interaction.user):
        return await interaction.response.send_message(
            embed=criar_embed("❌ Sem Permissão", "Apenas Dono ou Gerente podem usar este comando.", "Vermelho"),
            ephemeral=True
        )

    await interaction.response.defer(ephemeral=True)

    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        paineis = await (await db.execute("SELECT * FROM paineis WHERE guild_id = ?", (interaction.guild.id,))).fetchall()
        
        for p in paineis:
            canal = interaction.guild.get_channel(p["channel_id"])
            if canal:
                try:
                    msg = await canal.fetch_message(p["message_id"])
                    await msg.delete()
                except Exception:
                    pass

        await db.execute("DELETE FROM horarios WHERE guild_id = ?", (interaction.guild.id,))
        await db.execute("DELETE FROM paineis WHERE guild_id = ?", (interaction.guild.id,))
        await db.commit()

    await interaction.followup.send(
        embed=criar_embed("✅ Reset Concluído", "Todos os painéis e horários de diários foram excluídos.", "Esmeralda")
    )


@bot.tree.command(name="diario", description="🔥 Criar um painel fixo de inscrições no canal atual")
@app_commands.describe(tipo="Modo de jogo", categoria="Categoria da competição")
@app_commands.choices(
    tipo=[app_commands.Choice(name=n, value=v) for n, v in [("Solo", "solo"), ("Duo", "duo"), ("Trio", "trio"), ("Squad", "squad")]],
    categoria=[app_commands.Choice(name="Premium 💎", value="premium"), app_commands.Choice(name="Básico 🪙", value="basico")]
)
@app_commands.default_permissions(administrator=True)
async def cmd_diario(interaction: discord.Interaction, tipo: app_commands.Choice[str], categoria: app_commands.Choice[str]):
    if not await e_dono_ou_gerente(interaction.user):
        return await interaction.response.send_message(
            embed=criar_embed("❌ Sem Permissão", "Apenas Dono ou Gerente.", "Vermelho"),
            ephemeral=True
        )

    msg = await interaction.channel.send(embed=criar_embed("🔥 Inicializando Painel...", "Preparando as informações...", "Fire Force"))

    async with aiosqlite.connect(DATABASE_FILE) as db:
        cursor = await db.execute(
            "INSERT INTO paineis (guild_id, channel_id, message_id, tipo, categoria) VALUES (?, ?, ?, ?, ?)",
            (interaction.guild.id, interaction.channel.id, msg.id, tipo.value, categoria.value)
        )
        painel_id = cursor.lastrowid
        await db.commit()

    await rebuild_painel(interaction.guild, painel_id)
    await interaction.response.send_message(
        embed=criar_embed("✅ Painel Criado", "Painel registrado com sucesso. Use `/painel` para gerenciar os horários deste diário.", "Esmeralda"),
        ephemeral=True
    )


@bot.tree.command(name="painel", description="📊 Gerenciar horários, preços e premiações dos diários")
@app_commands.default_permissions(administrator=True)
async def cmd_painel(interaction: discord.Interaction):
    if not await e_dono_ou_gerente(interaction.user):
        return await interaction.response.send_message(
            embed=criar_embed("❌ Sem Permissão", "Apenas Dono ou Gerente.", "Vermelho"),
            ephemeral=True
        )

    await interaction.response.send_message(
        embed=criar_embed("📊 Gerenciador de Diários", "Escolha a ação desejada no painel abaixo:", "Fire Force"),
        view=PainelAdminView(),
        ephemeral=True
    )


@bot.tree.command(name="painelcupom", description="🎟️ Painel de administração de cupons de desconto")
@app_commands.default_permissions(administrator=True)
async def cmd_painelcupom(interaction: discord.Interaction):
    if not await e_dono_ou_gerente(interaction.user):
        return await interaction.response.send_message(
            embed=criar_embed("❌ Sem Permissão", "Apenas Dono ou Gerente.", "Vermelho"),
            ephemeral=True
        )

    await interaction.response.send_message(
        embed=criar_embed("🎟️ Gestão de Cupons", "Gerencie os cupons de desconto do servidor:", "Fire Force"),
        view=GerenciadorCupomView(),
        ephemeral=True
    )


@bot.tree.command(name="cupom", description="🎟️ Aplicar cupom de desconto na sua inscrição")
@app_commands.describe(codigo="Código promocional do cupom")
async def cmd_cupom(interaction: discord.Interaction, codigo: str):
    await interaction.response.defer(ephemeral=True)
    cod = codigo.strip().upper()

    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        slot = await (await db.execute(
            "SELECT * FROM slots WHERE comprador_id = ? AND guild_id = ? AND confirmado = 0 ORDER BY id DESC LIMIT 1",
            (interaction.user.id, interaction.guild.id)
        )).fetchone()

        if not slot:
            return await interaction.followup.send(
                embed=criar_embed("❌ Erro", "Você não possui nenhum canal de pagamento ativo.", "Vermelho"),
                ephemeral=True
            )

        if slot["cupom_id"]:
            return await interaction.followup.send(
                embed=criar_embed("⚠️ Cupom Já Usado", "Você já aplicou um cupom neste pagamento.", "Amarelo"),
                ephemeral=True
            )

        cupom = await (await db.execute("SELECT * FROM cupons WHERE guild_id = ? AND codigo = ?", (interaction.guild.id, cod))).fetchone()
        if not cupom:
            return await interaction.followup.send(
                embed=criar_embed("❌ Cupom inválido",
                    "**Cupom inválido, não encontrado, expirado ou esgotado.**\n"
                    "Confere o código e tenta de novo — o cupom é tudo em maiúsculo e sem espaço. 💛",
                    "Vermelho"),
                ephemeral=True
            )

        if cupom["expira_em"]:
            exp_date = datetime.datetime.strptime(cupom["expira_em"], "%d/%m/%Y")
            if agora_brt().replace(tzinfo=None) > exp_date:
                return await interaction.followup.send(
                    embed=criar_embed("❌ Cupom inválido",
                        "**Cupom inválido, não encontrado, expirado ou esgotado.**\n"
                        "Confere o código e tenta de novo — o cupom é tudo em maiúsculo e sem espaço. 💛",
                        "Vermelho"),
                    ephemeral=True
                )

        if cupom["usos_max"] > 0 and cupom["usos_atuais"] >= cupom["usos_max"]:
            return await interaction.followup.send(
                embed=criar_embed("❌ Cupom inválido",
                    "**Cupom inválido, não encontrado, expirado ou esgotado.**\n"
                    "Confere o código e tenta de novo — o cupom é tudo em maiúsculo e sem espaço. 💛",
                    "Vermelho"),
                ephemeral=True
            )

        uso_usr = await (await db.execute("SELECT usos FROM cupons_usados WHERE cupom_id = ? AND user_id = ?", (cupom["id"], interaction.user.id))).fetchone()
        qtd_usos = uso_usr["usos"] if uso_usr else 0

        if cupom["usos_por_user"] > 0 and qtd_usos >= cupom["usos_por_user"]:
            return await interaction.followup.send(
embed=criar_embed(
                    "🚫 Cupom já usado por você",
                    "Esse cupom tem limite por jogador e o seu já foi usado.\n"
                    "> 🎟️ Cada jogador tem a própria cota — pergunta pra equipe se tiver mais cupom rolando. 💛",
                    "Amarelo"),
                ephemeral=True
            )

        valor_original = slot["valor_cobrado"]
        if cupom["tipo_desconto"] == "pct":
            desc_val = valor_original * (cupom["valor"] / 100.0)
        else:
            desc_val = cupom["valor"]

        novo_valor = max(0.0, valor_original - desc_val)

        await db.execute("UPDATE slots SET valor_cobrado = ?, cupom_id = ? WHERE id = ?", (novo_valor, cupom["id"], slot["id"]))
        await db.execute("UPDATE cupons SET usos_atuais = usos_atuais + 1 WHERE id = ?", (cupom["id"],))

        if uso_usr:
            await db.execute("UPDATE cupons_usados SET usos = usos + 1 WHERE cupom_id = ? AND user_id = ?", (cupom["id"], interaction.user.id))
        else:
            await db.execute("INSERT INTO cupons_usados (cupom_id, user_id, usos) VALUES (?, ?, 1)", (cupom["id"], interaction.user.id))

        await db.commit()

    canal_pag = interaction.guild.get_channel(slot["canal_pag"])
    link = await link_pagamento(interaction.guild.id, novo_valor, tipo="diario", alvo_id=slot["id"],
                               user_id=slot["comprador_id"], nick="",
                               horario_id=slot["horario_id"], canal_id=slot["canal_pag"] or 0)
    if canal_pag and link:
        arquivo_qr = None
        try:
            arquivo_qr = discord.File(gerar_qr_url(link), "pagamento.png")
        except Exception:
            arquivo_qr = None
        try:
            async for msg in canal_pag.history(limit=10, oldest_first=True):
                if msg.author == interaction.guild.me and msg.embeds:
                    emb = msg.embeds[0]
                    str_desc = f"{cupom['valor']}%" if cupom["tipo_desconto"] == "pct" else formatar_moeda(cupom["valor"])
                    emb.add_field(
                        name="🎟️ Cupom Aplicado",
                        value=f"> Código: `{cod}`\n> Desconto: `{str_desc}`\n> **Novo Valor Total: {formatar_moeda(novo_valor)}**",
                        inline=False
                    )

                    for idx, campo in enumerate(emb.fields):
                        if "PIX via LivePix" in campo.name or "Chave PIX" in campo.name or "Copia e Cola" in campo.name:
                            emb.set_field_at(idx, name="💳 PIX via LivePix",
                                             value=f"> **Valor exato:** `{formatar_moeda(novo_valor)}`\n> **Link:** {link}",
                                             inline=False)

                    if arquivo_qr:
                        emb.set_image(url="attachment://pagamento.png")
                        await msg.edit(embed=emb, attachments=[arquivo_qr])
                    else:
                        await msg.edit(embed=emb)
                    break
        except Exception as e:
            print("Erro ao atualizar o pagamento com desconto:", e)

    await interaction.followup.send(
        embed=criar_embed("🎟️ Desconto Aplicado", f"Cupom `{cod}` validado! Novo valor a pagar: **{formatar_moeda(novo_valor)}**.\nConfira os dados atualizados no seu canal de pagamento.", "Esmeralda"),
        ephemeral=True
    )


@bot.tree.command(name="ish", description="🔑 Definir o ID e a Senha da sala de um diário")
@app_commands.describe(tipo="Modo de jogo", categoria="Categoria", horario="Horário (HH:MM)", sala_id="ID da sala no FF", senha="Senha da sala")
@app_commands.choices(
    tipo=[app_commands.Choice(name=n, value=v) for n, v in [("Solo", "solo"), ("Duo", "duo"), ("Trio", "trio"), ("Squad", "squad")]],
    categoria=[app_commands.Choice(name="Premium 💎", value="premium"), app_commands.Choice(name="Básico 🪙", value="basico")]
)
async def cmd_ish(interaction: discord.Interaction, tipo: app_commands.Choice[str], categoria: app_commands.Choice[str], horario: str, sala_id: str, senha: str):
    if not await e_dono_ou_gerente(interaction.user):
        return await interaction.response.send_message(
            embed=criar_embed("❌ Sem Permissão", "Apenas Dono ou Gerente.", "Vermelho"),
            ephemeral=True
        )

    try:
        partes = horario.strip().split(":")
        horario_fmt = f"{int(partes[0]):02d}:{int(partes[1]):02d}"
    except Exception:
        return await interaction.response.send_message(
            embed=criar_embed("❌ Formato Incorreto", "Digite o horário no formato HH:MM.", "Vermelho"),
            ephemeral=True
        )

    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        horario_db = await (await db.execute(
            "SELECT 1 FROM horarios WHERE guild_id = ? AND tipo = ? AND categoria = ? AND horario = ?",
            (interaction.guild.id, tipo.value, categoria.value, horario_fmt)
        )).fetchone()

        if not horario_db:
            return await interaction.response.send_message(
                embed=criar_embed("⚠️ Não Localizado", f"Não há diário cadastrado para {formatar_rotulo_diario(tipo.value, categoria.value)} às `{horario_fmt}`.", "Amarelo"),
                ephemeral=True
            )

        await db.execute(
            "INSERT INTO salas (guild_id, tipo, categoria, horario, sala_id, sala_senha, enviado, criado_em) VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
            (interaction.guild.id, tipo.value, categoria.value, horario_fmt, sala_id, senha, agora_brt().isoformat())
        )
        await db.commit()

    diferenca = (horario_para_datetime(horario_fmt) - agora_brt()).total_seconds()
    embed = criar_embed(
        "✅ Sala Agendada",
        f"**{formatar_rotulo_diario(tipo.value, categoria.value)}** — `{horario_fmt}`\n\n"
        f"> 🆔 **ID:** `{sala_id}`\n"
        f"> 🔑 **Senha:** `{senha}`",
        "Esmeralda"
    )

    if 0 < diferenca <= 300:
        total = await enviar_sala(interaction.guild, tipo.value, categoria.value, horario_fmt, sala_id, senha)
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute(
                "UPDATE salas SET enviado = 1 WHERE guild_id = ? AND tipo = ? AND categoria = ? AND horario = ? AND enviado = 0",
                (interaction.guild.id, tipo.value, categoria.value, horario_fmt)
            )
            await db.commit()
        embed.add_field(name="🚨 Enviado Imediatamente", value=f"Enviado para **{total}** jogadores no canal coletivo!", inline=False)
    elif diferenca > 300:
        embed.add_field(name="📩 Programado", value=f"O envio ocorrerá automaticamente **5 minutos antes** (`~{int(diferenca // 60)} min`).", inline=False)
    else:
        embed.add_field(name="⚠️ Expirado", value="Este horário já encerrou.", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="ticket", description="🎫 Mandar painel de suporte/tickets no canal")
@app_commands.default_permissions(administrator=True)
async def cmd_ticket(interaction: discord.Interaction):
    await interaction.channel.send(
        embed=criar_embed("🎫 Central de Atendimento", "Clique no botão abaixo para abrir um atendimento exclusivo com a nossa equipe.", "Fire Force"),
        view=TicketPainelView()
    )
    await interaction.response.send_message(embed=criar_embed("✅", "Painel de atendimento publicado!", "Esmeralda"), ephemeral=True)


@bot.tree.command(name="staff", description="👥 Mandar painel de status ON/OFF da equipe no canal")
@app_commands.default_permissions(administrator=True)
async def cmd_staff(interaction: discord.Interaction):
    embed = criar_embed("👥 Equipe de Atendimento", "Monitore o status dos membros da equipe em tempo real.", "Fire Force")
    embed.add_field(name="✅ Disponíveis", value="> *Nenhum*", inline=True)
    embed.add_field(name="⛔ Indisponíveis", value="> *Nenhum*", inline=True)

    await interaction.channel.send(embed=embed, view=StaffPainelView())
    await interaction.response.send_message(embed=criar_embed("✅", "Painel de status da staff publicado!", "Esmeralda"), ephemeral=True)


@bot.tree.command(name="embed", description="📝 Criar e personalizar uma embed")
@app_commands.default_permissions(manage_messages=True)
async def cmd_embed(interaction: discord.Interaction):
    await interaction.response.send_message(
        embed=criar_embed("📝 Construtor de Embeds", f"Selecione uma cor e monte seu texto customizado. ({len(CORES_DICCIONARIO)} cores disponíveis)", "Fire Force"),
        view=EmbedBuilderView(),
        ephemeral=True
    )


def _embed_jogador_ff(dados: dict, local: Optional[dict] = None) -> discord.Embed:
    """Monta a ficha do jogador consultado na API."""
    origem = "cache local" if dados.get("cache") else f"consulta ao vivo ({dados.get('provedor', '—')})"
    descricao = f"> 📡 Fonte: `{origem}`"
    if dados.get("cache") and dados.get("atualizado"):
        try:
            quando = datetime.datetime.fromisoformat(dados["atualizado"]).astimezone(TZ_BRASILIA)
            descricao += f" • `{quando.strftime('%d/%m às %H:%M')}`"
        except Exception:
            pass
    if dados.get("aviso"):
        descricao += f"\n> ⚠️ {dados['aviso']}"

    embed = criar_embed("🎮 Jogador Encontrado", descricao, "Esmeralda")
    embed.add_field(name="👤 Nick", value=f"`{dados.get('nome') or '—'}`", inline=True)
    embed.add_field(name="📊 Level", value=f"`{dados.get('nivel') or '—'}`", inline=True)
    embed.add_field(name="🌎 Região", value=f"`{dados.get('regiao') or '—'}`", inline=True)

    linha_extra = []
    if dados.get("rank"):
        linha_extra.append(f"> 🏅 **Rank:** `{dados['rank']}`")
    if dados.get("prime"):
        linha_extra.append(f"> 💠 **Passe Prime:** `Nível {dados['prime']}`")
    if dados.get("cla"):
        linha_extra.append(f"> 🛡️ **Clã:** `{dados['cla']}`")
    linha_extra.append(f"> 🆔 **ID:** `{dados.get('uid', '—')}`")
    if linha_extra:
        embed.add_field(name="🔎 Detalhes", value="\n".join(linha_extra), inline=False)

    if local and local.get("ok"):
        embed.add_field(
            name="🏠 Aqui no servidor",
            value=f"> Já jogou **{local['partidas']}** diário(s)\n> Última: {local['ultimo']}",
            inline=False
        )
    else:
        embed.add_field(name="🏠 Aqui no servidor", value="> Nenhuma inscrição registrada com esse nick.", inline=False)

    return embed


class VerificarAtualizarView(discord.ui.View):
    """Botão para forçar uma nova consulta (ignora o cache)."""

    def __init__(self, uid: str):
        super().__init__(timeout=180)
        self.uid = uid

    @discord.ui.button(label="Consultar de novo", emoji="🔄", style=discord.ButtonStyle.secondary)
    async def atualizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        dados = await verificar_ff(self.uid, forcar=True)
        if not dados.get("ok"):
            await interaction.followup.send(
                embed=criar_embed("⚠️ Consulta falhou", dados.get("mensagem", "Tente novamente."), "Amarelo"),
                ephemeral=True
            )
            return
        dados["uid"] = self.uid
        local = await consultar_jogador_local(dados["nome"])
        await interaction.edit_original_response(embed=_embed_jogador_ff(dados, local), view=self)
        button.disabled = False


@bot.tree.command(name="verificar", description="🔍 Consultar um ID do Free Fire (nick, level, rank, clã, região)")
@app_commands.describe(busca="ID numérico do Free Fire (5 a 15 dígitos) ou o nick usado nas inscrições")
async def cmd_verificar(interaction: discord.Interaction, busca: str):
    await interaction.response.defer(ephemeral=True)
    busca = (busca or "").strip()

    # ---------- ID numérico -> API do Free Fire ----------
    if busca.isdigit():
        dados = await verificar_ff(busca)
        if dados.get("ok"):
            dados["uid"] = busca
            local = await consultar_jogador_local(dados["nome"])
            await interaction.followup.send(
                embed=_embed_jogador_ff(dados, local),
                view=VerificarAtualizarView(busca),
                ephemeral=True
            )
        else:
            titulo = {
                "formato": "❌ ID inválido",
                "nao_encontrado": "🔎 ID não encontrado",
                "offline": "⚠️ Consulta indisponível",
            }.get(dados.get("motivo"), "⚠️ Consulta indisponível")
            embed = criar_embed(titulo, dados.get("mensagem", "Tente novamente."), "Vermelho" if dados.get("motivo") != "offline" else "Amarelo")
            embed.add_field(name="🆔 ID consultado", value=f"`{busca}`", inline=True)
            await interaction.followup.send(
                embed=embed,
                view=VerificarAtualizarView(busca) if dados.get("motivo") == "offline" else None,
                ephemeral=True
            )
        return

    # ---------- texto -> base local do bot ----------
    local = await consultar_jogador_local(busca)
    if local.get("ok"):
        embed = criar_embed("✅ Jogador Encontrado", "> 📡 Fonte: `base local do bot`", "Esmeralda")
        embed.add_field(name="👤 Nick", value=f"`{local['nome']}`", inline=True)
        embed.add_field(name="🎮 Diários jogados", value=f"`{local['partidas']}`", inline=True)
        embed.add_field(name="🕒 Última inscrição", value=f"> {local['ultimo']}", inline=False)
        embed.add_field(
            name="💡 Quer os dados do jogo?",
            value="> Use `/verificar` com o **ID numérico** para ver nick, level, rank e clã direto do Free Fire.",
            inline=False
        )
    else:
        embed = criar_embed(
            "🔎 Não encontrado",
            f"Não achei **`{busca}`** nas inscrições do bot.\n\n"
            f"> • Se for um **ID numérico**, mande ele completo (5 a 15 dígitos) que eu consulto no Free Fire.\n"
            f"> • Se for o **nick**, confira a escrita — uso exatamente o que foi digitado na inscrição.",
            "Amarelo"
        )

    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="help", description="❓ Exibir todos os comandos disponíveis")
async def cmd_help(interaction: discord.Interaction):
    embed = criar_embed(
        "🔥 Fire Force — Manual de Comandos",
        "📝 **Inscrição:** informe apenas o **nick** do jogo (ex: `FF⚡REI`).\n"
        "🔒 A vaga, o número do lote e o acesso ao canal do diário só são liberados "
        "**depois que a equipe confirmar o pagamento**.",
        "Fire Force"
    )
    embed.add_field(name="⚙️ Configuração", value="> `/setup` — Configurar cargos e categorias\n> `/reset` — Limpar todos os painéis e diários", inline=False)
    embed.add_field(name="🔥 Diários", value="> `/diario` — Publicar painel fixo de diário\n> `/painel` — Gerenciar horários, preços e premiações\n> `/ish` — Definir ID e senha da sala", inline=False)
    embed.add_field(name="🎟️ Cupons", value="> `/painelcupom` — Gerenciar cupons promocionais\n> `/cupom` — Aplicar desconto no seu pagamento", inline=False)
    embed.add_field(name="🎫 Atendimento & Staff", value="> `/ticket` — Publicar painel de atendimento\n> `/staff` — Publicar painel de status ON/OFF", inline=False)
    embed.add_field(
        name="💰 Carteira & Pagamentos",
        value="> `/carteira` — Ver saldo e movimentações\n"
              "> `/deposito` — Depositar via **PIX (LivePix)** e virar saldo\n"
              "> `/saque` — Sacar seu saldo via **PIX**\n"
              "> `/transferir` — Mandar saldo pra outro jogador\n"
              "> `/extrato` — Extrato completo da carteira",
        inline=False
    )
    embed.add_field(
        name="🎧 Atendimento",
        value="> `/ticket` — Abrir atendimento com o **suporte** 🎧\n"
              "> 🙋 Quem clica em **Assumir** primeiro fica com o atendimento\n"
              "> 🔒 Quem fecha é o **cliente** — e a nota (0 a 5 estrelas) é o que paga o atendente\n"
              "> `/deposito` — abre um **atendimento só seu + equipe**",
        inline=False
    )
    embed.add_field(
        name="🎉 Eventos & 🏆 Rankings",
        value="> `/evento` — Criar/encerrar eventos com bônus por kills ou top (gerência)\n"
              "> `/painelranking` — Publicar o painel de rankings\n"
              "> `/vitoria` — Registrar vitória (top 1) de um jogador\n"
              "> `/trabalho` — Carteira de trabalho da equipe (fechamento semanal)",
        inline=False
    )
    embed.add_field(
        name="🛠️ Gestão (equipe)",
        value="> `/addsaldo` — Adicionar ou remover saldo\n"
              "> `/financeiro` — Caixa, reserva, fila de saques e comissões\n"
              "> `/payout` — 💸 Fila de pagamento: quanto tirar da LivePix e quem pagar\n"
              "> `/logs` — Configurar e ver os registros\n"
              "> `/config` — LivePix, canais (cupons/eventos/rankings/logs), reserva, comissão\n"
              "> `/backup` • `/restaurar` • `/dados` — ☁️ Supabase (sobrevive ao restart)",
        inline=False
    )
    embed.add_field(name="🧰 Úteis", value="> `/embed` — Criar embeds personalizadas\n> `/verificar` — Consultar ID no Free Fire (nick, level, rank) ou nick na base", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="info", description="ℹ️ Exibir informações técnicas do bot")
async def cmd_info(interaction: discord.Interaction):
    embed = criar_embed("🔥 Fire Force Bot", f"Gerenciador de Ligas de Free Fire\n**Versão {VERSAO_BOT}**", "Fire Force")
    embed.add_field(name="🧩 Versão", value=f"`v{VERSAO_BOT}`", inline=True)
    embed.add_field(name="📊 Servidores", value=f"`{len(bot.guilds)}`", inline=True)
    try:
        latencia_txt = f"{round(bot.latency * 1000)}ms"
    except (ValueError, TypeError, OverflowError):
        latencia_txt = "medindo..."          # bot.latency pode vir NaN logo após ligar/reconectar
    embed.add_field(name="🏓 Latência", value=f"`{latencia_txt}`", inline=True)

    async with aiosqlite.connect(DATABASE_FILE) as db:
        horarios_cnt = await (await db.execute("SELECT COUNT(*) FROM horarios WHERE guild_id = ? AND ativo = 1", (interaction.guild.id,))).fetchone()
        slots_cnt = await (await db.execute("SELECT COUNT(*) FROM slots WHERE guild_id = ? AND confirmado = 1", (interaction.guild.id,))).fetchone()

    embed.add_field(name="🔥 Horários Ativos", value=f"`{horarios_cnt[0]}`", inline=True)
    embed.add_field(name="🎫 Inscrições Ativas", value=f"`{slots_cnt[0]}`", inline=True)

    async with aiosqlite.connect(DATABASE_FILE) as db:
        cache_cnt = await (await db.execute("SELECT COUNT(*) FROM ff_cache")).fetchone()

    embed.add_field(name="📡 Consulta FF (provedores)", value=ff_status_provedores(), inline=False)
    embed.add_field(name="🗂️ IDs em cache", value=f"`{cache_cnt[0]}`", inline=True)

    await interaction.response.send_message(embed=embed)


# ==================== INICIALIZAÇÃO ====================

# ══════════════════════════════════════════════════════════════
#  💰 SISTEMA FINANCEIRO — CARTEIRA VIRTUAL • LIVEPIX • LOGS
#  • Depósito (PIX via LivePix) → vira SALDO na carteira
#  • Saldo paga diário na hora (vaga liberada sem esperar staff)
#  • Saque → PIX via LivePix (automático sempre que o caixa permitir)
#  • Comissão de ADM: R$ 2,50 a cada R$ 10,00 aprovados (25%)
#  • Reserva de R$ 200,00 livres protegida pelo sistema
#  • Logs completos no canal escolhido + fireforce.log
# ══════════════════════════════════════════════════════════════

# ---------- LOG (canal + arquivo) ----------

def _log_arquivo(texto: str):
    """Grava no fireforce.log e rotaciona quando passa de LOG_TAMANHO_MAX."""
    try:
        with open(ARQUIVO_LOG, "a", encoding="utf-8") as arquivo:
            arquivo.write(f"[{agora_brt().strftime('%d/%m/%Y %H:%M:%S')}] {texto}\n")
        if os.path.getsize(ARQUIVO_LOG) > LOG_TAMANHO_MAX:
            os.replace(ARQUIVO_LOG, ARQUIVO_LOG + ".1")
    except Exception:
        pass


async def canal_de_logs(guild_id: int):
    """ID do canal de logs configurado (com cache curto pra economizar consulta)."""
    cache = _CACHE_LOGS.get(guild_id)
    if cache and (time.time() - cache[1]) < 60:
        return cache[0]
    cfg = await obter_config(guild_id)
    canal_id = cfg.get("canal_logs")
    _CACHE_LOGS[guild_id] = (canal_id, time.time())
    return canal_id


CANAIS_PUBLICOS = (
    ("deposito", "canal_log_deposito", "💰 DEPÓSITO"),
    ("saque", "canal_log_saque", "💸 SAQUE"),
    ("pagamento", "canal_log_pagamento", "✅ PAGAMENTO"),
)


def mascarar_chave(chave) -> str:
    """Esconde a chave PIX pro canal público: jo***@x.com • ***8900 • 1199...8888"""
    texto = str(chave or "").strip()
    if not texto:
        return "-"
    if "@" in texto:
        nome, _, dominio = texto.partition("@")
        return (nome[:2] + "***@" + dominio) if len(nome) > 2 else ("***@" + dominio)
    digitos = re.sub(r"\D", "", texto)
    if len(digitos) >= 10 and re.fullmatch(r"[\d.\-/()\s+]+", texto):
        return f"***{digitos[-4:]}"
    if len(texto) > 8:
        return f"{texto[:4]}...{texto[-4:]}"
    return "***"


def mascarar_chaves(texto) -> str:
    """Mascara qualquer chave PIX que apareça entre crases (ex.: `joao@pix.com`)."""
    def _troca(match):
        return match.group(1) + mascarar_chave(match.group(2)) + "`"
    return re.sub(r"(🏦[^`\n]{0,40}[Cc]have[^`\n]{0,40}`)([^`]+)`", _troca, str(texto or ""))


async def canal_anuncio(guild, tipo: str):
    """Canal do anúncio: o PÚBLICO configurado pro tipo ou, sem config, o de logs.

    Devolve (canal, publico)."""
    if not guild:
        return None, False
    chave_cfg = {chave: coluna for chave, coluna, _ in CANAIS_PUBLICOS}.get(tipo, "")
    if chave_cfg:
        cfg = await obter_config(guild.id)
        canal_id = cfg.get(chave_cfg)
        if canal_id:
            canal = guild.get_channel(int(canal_id))
            if canal:
                return canal, True
    canal_id = await canal_de_logs(guild.id)
    canal = guild.get_channel(int(canal_id)) if canal_id else None
    return canal, False


async def anunciar(guild, tipo: str, titulo: str, descricao: str, cor: str = "Esmeralda",
                   marcar: Optional[int] = None) -> bool:
    """Anúncio no canal PÚBLICO do tipo (depósito/saque/pagamento).

    Só manda se a equipe tiver configurado um canal separado — assim ninguém
    recebe mensagem repetida sem querer. A chave PIX sai mascarada."""
    canal, publico = await canal_anuncio(guild, tipo)
    if not canal or not publico:
        return False
    texto = mascarar_chaves(descricao) if publico else descricao
    try:
        await canal.send(content=(mencao(marcar) if marcar else None),
                         embed=criar_embed(titulo, texto, cor))
    except Exception as erro:
        _log_arquivo(f"[ANÚNCIO] {tipo}: {erro}")
        return False
    return True


async def registrar_log(guild, tipo: str, titulo: str, descricao: str,
                        cor: str = "Fire Force", campos: Optional[list] = None):
    """Registra o evento no arquivo e no canal de logs (se configurado)."""
    limpo = descricao.replace("**", "").replace("> ", "")
    _log_arquivo(f"[{tipo}] {titulo} — {limpo}")
    marcar_sujo()

    if not guild:
        return
    try:
        canal_id = await canal_de_logs(guild.id)
    except Exception:
        canal_id = None
    if not canal_id:
        return
    canal = guild.get_channel(int(canal_id))
    if not canal:
        return
    try:
        embed = criar_embed(titulo, descricao, cor, footer=f"🔥 Fire Force • {tipo}")
        for campo in (campos or []):
            embed.add_field(name=campo[0], value=campo[1], inline=(len(campo) < 3 or campo[2]))
        await canal.send(embed=embed)
    except Exception:
        pass


# ---------- CLIENTE LIVEPIX (API OFICIAL) ----------

class LivePix:
    """Cliente da API oficial do LivePix (OAuth2 client_credentials).

    Endpoints usados:
      • GET  /v2/wallet                    → saldo real da conta (regra dos R$200)
      • GET  /v2/payments                  → pagamentos recebidos (valor + comprovante)
      • GET  /v2/messages                  → mensagens recebidas (traz o NOME do pagador)
      • POST /v2/payments                  → cria checkout com o valor exato
      • GET  /v2/wallet/BRL/transactions   → extrato (detecta saque pago)

    Atenção: a API pública NÃO tem endpoint de transferência/saque; o saque é
    enviado pelo painel da LivePix (o bot prepara tudo e detecta quando saiu).
    """

    def __init__(self):
        self._sessao = None
        self._token = None
        self._expira = 0.0
        self.ultimo_erro = ""
        self.ultima_referencia = ""

    @property
    def configurado(self) -> bool:
        return bool(LIVEPIX_CLIENT_ID and LIVEPIX_CLIENT_SECRET)

    async def sessao(self):
        if self._sessao is None or self._sessao.closed:
            self._sessao = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        return self._sessao

    async def fechar(self):
        try:
            if self._sessao and not self._sessao.closed:
                await self._sessao.close()
        except Exception:
            pass

    async def autenticar(self) -> Optional[str]:
        """Pega (e reaproveita) o token OAuth2 — a LivePix monitora emissões."""
        if self._token and time.time() < self._expira - 60:
            return self._token
        if not self.configurado:
            return None
        try:
            sessao = await self.sessao()
            async with sessao.post(LIVEPIX_OAUTH_URL, data={
                "grant_type": "client_credentials",
                "client_id": LIVEPIX_CLIENT_ID,
                "client_secret": LIVEPIX_CLIENT_SECRET,
                "scope": LIVEPIX_SCOPES,
            }) as resp:
                corpo = await resp.json(content_type=None)
                if resp.status != 200 or "access_token" not in corpo:
                    self.ultimo_erro = f"login {resp.status}: {str(corpo)[:180]}"
                    return None
                self._token = corpo["access_token"]
                self._expira = time.time() + float(corpo.get("expires_in", 3600))
                self.ultimo_erro = ""
                return self._token
        except Exception as erro:
            self.ultimo_erro = f"login: {erro}"
            return None

    async def req(self, metodo: str, rota: str, json_body: dict = None,
                  params: dict = None) -> tuple:
        """Faz a chamada. Devolve (ok, dados_ou_erro)."""
        token = await self.autenticar()
        if not token:
            return False, self.ultimo_erro or "LivePix não configurada"
        for tentativa in (1, 2):
            try:
                sessao = await self.sessao()
                async with sessao.request(
                    metodo, f"{LIVEPIX_API}{rota}",
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                    json=json_body, params=params
                ) as resp:
                    corpo = await resp.json(content_type=None)
                    if resp.status == 401 and tentativa == 1:
                        self._token = None          # token vencido → renova uma vez
                        token = await self.autenticar()
                        if not token:
                            return False, "autenticação recusada"
                        continue
                    if resp.status == 429:
                        return False, "limite de consultas da LivePix atingido (aguarde 1 minuto)"
                    if resp.status == 403 or resp.status == 401:
                        self.ultimo_erro = f"sem permissão ({resp.status})"
                        return False, self.ultimo_erro
                    if resp.status >= 400:
                        self.ultimo_erro = f"erro {resp.status}: {str(corpo)[:180]}"
                        return False, self.ultimo_erro
                    return True, corpo
            except Exception as erro:
                self.ultimo_erro = f"{metodo} {rota}: {erro}"
        return False, self.ultimo_erro

    # ---- consultas ----

    async def saldo(self) -> Optional[float]:
        ok, dados = await self.req("GET", "/wallet")
        if not ok:
            return None
        try:
            for moeda in dados.get("data", []):
                if moeda.get("currency") == "BRL":
                    return arredondar(float(moeda.get("balance", 0)) / 100.0)
        except Exception:
            return None
        return None

    async def pagamentos(self, limite: int = 25) -> list:
        ok, dados = await self.req("GET", "/payments", params={"limit": limite})
        if not ok:
            return []
        return (dados or {}).get("data") or []

    async def mensagens(self, limite: int = 25) -> list:
        ok, dados = await self.req("GET", "/messages", params={"limit": limite})
        if not ok:
            return []
        return (dados or {}).get("data") or []

    async def transacoes(self, limite: int = 25) -> list:
        ok, dados = await self.req("GET", "/wallet/BRL/transactions", params={"limit": limite})
        if not ok:
            return []
        return (dados or {}).get("data") or []

    async def criar_checkout(self, valor: float, referencia: str = "",
                             redirect: str = "https://livepix.gg") -> Optional[str]:
        """Cria um pagamento com o valor exato e devolve o link do checkout."""
        corpo = {"amount": int(round(float(valor) * 100)), "currency": "BRL", "redirectUrl": redirect}
        if referencia:
            corpo["reference"] = referencia
        ok, dados = await self.req("POST", "/payments", json_body=corpo)
        if not ok:
            return None
        try:
            dados = dados.get("data") or {}
            self.ultima_referencia = str(dados.get("reference") or referencia or "")
            return dados.get("redirectUrl")
        except Exception:
            self.ultima_referencia = referencia or ""
            return None


livepix = LivePix()


async def link_pagamento(guild_id: int, valor: float, referencia: str = "", tipo: str = "",
                         alvo_id: int = 0, user_id: int = 0, nick: str = "",
                         horario_id: int = 0, canal_id: int = 0) -> Optional[str]:
    """Link de pagamento COM referência única: é o que faz o bot confirmar sozinho.

    Quando a LivePix está configurada, cada link nasce com um código nosso
    (ex.: `FF-D12-A7K2`). O pagamento volta com esse código e o bot sabe
    exatamente de quem é — sem depender do nome digitado nem de ninguém clicar.
    """
    if livepix.configurado:
        if not referencia:
            referencia = nova_referencia(tipo or "diario", alvo_id)
        link = await livepix.criar_checkout(valor, referencia=referencia)
        if link:
            usada = getattr(livepix, "ultima_referencia", "") or referencia
            await registrar_checkout(usada, guild_id, tipo or "deposito", alvo_id, valor, link,
                                     user_id=user_id, nick=nick, horario_id=horario_id, canal_id=canal_id)
            if usada != referencia:
                await registrar_checkout(referencia, guild_id, tipo or "deposito", alvo_id, valor, link,
                                         user_id=user_id, nick=nick, horario_id=horario_id, canal_id=canal_id)
            return link
    cfg = await obter_config(guild_id)
    return cfg.get("livepix_link") or None


def gerar_qr_url(url: str):
    """QR Code (PNG) que aponta pro link de pagamento."""
    qr = qrcode.QRCode(version=None, box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    imagem = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


# ---------- NOMES E VALORES (casamento automático) ----------

def normalizar_nome(texto: str) -> str:
    """minúsculas, sem acento e sem símbolos — pra comparar nomes."""
    texto = str(texto or "").strip().lower()
    trocas = str.maketrans("áàâãäéèêëíìîïóòôõöúùûüçñ", "aaaaaeeeeiiiiooooouuuucn")
    texto = texto.translate(trocas)
    texto = re.sub(r"[^a-z0-9 ]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


RE_CODIGO_FF = re.compile(r"\bFF[\s\-_.]*([DPSX])[\s\-_.]*(\d{1,6})[\s\-_.]*([A-Z0-9]{3,8})\b",
                          re.IGNORECASE)


def codigos_no_texto(texto) -> list:
    """Acha o código do checkout (FF-D1-U8CD) ESCRITO na mensagem do pagamento.

    Muita gente paga pelo link fixo e digita o código na mensagem — assim o
    bot reconhece do mesmo jeito que se o código viesse no campo certo."""
    achados = []
    for letra, alvo, sufixo in RE_CODIGO_FF.findall(str(texto or "").upper()):
        codigo = f"FF-{letra}{int(alvo)}-{sufixo}"
        if codigo not in achados:
            achados.append(codigo)
    return achados


def apelidos_do_usuario(usuario) -> str:
    """Apelidos do jogador no Discord (nome de usuário e nome de exibição).

    Ficam guardados no depósito/reserva pra casar com o que a pessoa escrever
    no LivePix — tem gente que escreve só o @ do Discord."""
    partes = []
    for campo in ("name", "global_name", "display_name"):
        valor = str(getattr(usuario, campo, "") or "").strip()
        if valor and valor not in partes:
            partes.append(valor)
    return "|".join(partes)[:200]


def nomes_candidatos(registro, principal) -> list:
    """Todos os nomes que podem aparecer no pagamento deste registro."""
    candidatos = [str(principal or "")]
    try:
        extra = str(registro["apelidos"] or "")
    except Exception:
        extra = ""
    for parte in extra.split("|"):
        parte = parte.strip()
        if parte and parte not in candidatos:
            candidatos.append(parte)
    return [c for c in candidatos if c]


def nome_do_pagamento_bate(evento: dict, esperado) -> bool:
    """Aceita o NOME digitado no LivePix **ou** o que a pessoa escreveu na MENSAGEM.

    Ex.: Nome = "@73u3738" e Mensagem = "Daniel Souza" → casou com o depósito
    de "Daniel Souza". Sem nome e sem mensagem (só o pagamento), também aceita:
    aí o valor e a janela de tempo é que decidem."""
    nome = str((evento or {}).get("nome") or "").strip()
    texto = str((evento or {}).get("texto") or "").strip()
    if not nome and not texto:
        return True
    return nomes_parecidos(nome, esperado) or nomes_parecidos(texto, esperado)


def nomes_parecidos(a: str, b: str) -> bool:
    """Compara o nome do pagamento com o nome do jogador (tolerante, mas seguro)."""
    na, nb = normalizar_nome(a), normalizar_nome(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    tokens_a = {t for t in na.split() if len(t) >= 3}
    tokens_b = {t for t in nb.split() if len(t) >= 3}
    if not tokens_a or not tokens_b:
        return False
    comum = tokens_a & tokens_b
    return len(comum) >= min(2, len(tokens_a), len(tokens_b))


def valor_bate(centavos, valor: float) -> bool:
    """Valor pago x valor cobrado (aceita a diferença de taxa da LivePix)."""
    try:
        pago = float(centavos) / 100.0
    except Exception:
        return False
    if abs(pago - valor) <= 0.02:
        return True
    return valor * 0.90 <= pago <= valor * 1.02


async def _ja_visto(pix_id: str, tipo: str = "pagamento") -> bool:
    """Dedupe: cada pagamento/mensagem da LivePix só conta uma vez."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        linha = await (await db.execute("SELECT 1 FROM livepix_vistos WHERE id = ?", (str(pix_id),))).fetchone()
        if linha:
            return True
        await db.execute("INSERT OR IGNORE INTO livepix_vistos (id, tipo, criado_em) VALUES (?, ?, ?)",
                         (str(pix_id), tipo, agora_brt().isoformat()))
        await db.commit()
    return False


# ---------- CARTEIRA (saldo virtual) ----------

async def _garantir_carteira(db, user_id: int, guild_id: int):
    await db.execute(
        "INSERT OR IGNORE INTO carteira (user_id, guild_id, saldo, atualizado_em) VALUES (?, ?, 0, ?)",
        (user_id, guild_id, agora_brt().isoformat())
    )


async def saldo_carteira(user_id: int, guild_id: int) -> float:
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        linha = await (await db.execute(
            "SELECT saldo FROM carteira WHERE user_id = ? AND guild_id = ?", (user_id, guild_id)
        )).fetchone()
    return arredondar(linha["saldo"] if linha else 0)


async def movimentar_saldo(user_id: int, guild_id: int, valor: float, tipo: str,
                           descricao: str, ref: str = "", permitir_negativo: bool = False):
    """Credita (valor > 0) ou debita (valor < 0). Nunca deixa saldo negativo.
    Devolve o novo saldo, ou None se faltou saldo."""
    valor = arredondar(valor)
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        await _garantir_carteira(db, user_id, guild_id)
        linha = await (await db.execute(
            "SELECT saldo FROM carteira WHERE user_id = ? AND guild_id = ?", (user_id, guild_id)
        )).fetchone()
        atual = arredondar(linha["saldo"] if linha else 0)
        novo = arredondar(atual + valor)
        if novo < 0 and not permitir_negativo:
            return None
        await db.execute(
            "UPDATE carteira SET saldo = ?, atualizado_em = ? WHERE user_id = ? AND guild_id = ?",
            (novo, agora_brt().isoformat(), user_id, guild_id)
        )
        await db.execute(
            "INSERT INTO transacoes (guild_id, user_id, tipo, valor, saldo_apos, descricao, ref, criado_em) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (guild_id, user_id, tipo, valor, novo, descricao, ref, agora_brt().isoformat())
        )
        await db.commit()
    marcar_sujo()
    return novo


async def creditar_saldo(user_id: int, guild_id: int, valor: float, tipo: str,
                         descricao: str, ref: str = "") -> float:
    return await movimentar_saldo(user_id, guild_id, abs(valor), tipo, descricao, ref)


async def debitar_saldo(user_id: int, guild_id: int, valor: float, tipo: str,
                        descricao: str, ref: str = ""):
    return await movimentar_saldo(user_id, guild_id, -abs(valor), tipo, descricao, ref)


# ---------- CAIXA DA ORG (livro interno + saldo real) ----------

async def registrar_caixa(guild_id: int, tipo: str, valor: float, descricao: str, ref: str = ""):
    """tipo: 'receita' (entrou) ou 'despesa' (saiu)."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute(
            "INSERT INTO livro_caixa (guild_id, tipo, valor, descricao, ref, criado_em) VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, tipo, arredondar(valor), descricao, ref, agora_brt().isoformat())
        )
        await db.commit()
    marcar_sujo()


async def resumo_caixa(guild_id: int, dia: Optional[str] = None) -> dict:
    """Totais do livro-caixa (geral e do dia, se informado)."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        async def _soma(tipo, filtro="", params=()):
            sql = f"SELECT COALESCE(SUM(valor), 0) FROM livro_caixa WHERE guild_id = ? AND tipo = ? {filtro}"
            return arredondar((await (await db.execute(sql, (guild_id, tipo) + params)).fetchone())[0])
        receitas = await _soma("receita")
        despesas = await _soma("despesa")
        dia_receitas = dia_receitas_qtd = 0.0
        if dia:
            dia_receitas = await _soma("receita", "AND criado_em LIKE ?", (f"{dia}%",))
            dia_despesas = await _soma("despesa", "AND criado_em LIKE ?", (f"{dia}%",))
            dia_receitas_qtd = (await (await db.execute(
                "SELECT COUNT(*) FROM livro_caixa WHERE guild_id = ? AND tipo = 'receita' AND criado_em LIKE ?",
                (guild_id, f"{dia}%")
            )).fetchone())[0]
        else:
            dia_despesas = 0.0
    return {
        "receitas": receitas, "despesas": despesas, "saldo": arredondar(receitas - despesas),
        "dia_receitas": dia_receitas, "dia_despesas": dia_despesas, "dia_movimentos": dia_receitas_qtd,
    }


async def saldo_org(guild_id: int):
    """Saldo da org: prefere o saldo REAL da LivePix; senão, o livro interno.
    Devolve (valor, fonte)."""
    if livepix.configurado:
        real = await livepix.saldo()
        if real is not None:
            return real, "LivePix"
    resumo = await resumo_caixa(guild_id)
    return resumo["saldo"], "livro interno"


async def fila_saques(guild_id: int) -> dict:
    """Saques em aberto (na fila + liberados aguardando o PIX sair)."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        linhas = await (await db.execute(
            "SELECT * FROM saques WHERE guild_id = ? AND status IN ('na_fila', 'liberado') ORDER BY id",
            (guild_id,)
        )).fetchall()
    total = arredondar(sum(arredondar(l["valor"]) for l in linhas))
    return {"saques": [dict(l) for l in linhas], "total": total, "quantidade": len(linhas)}


async def disponibilidade_saque(guild_id: int) -> dict:
    """Quanto a org pode pagar AGORA sem furar a reserva mínima."""
    cfg = await obter_config(guild_id)
    reserva = arredondar(cfg.get("reserva") if cfg.get("reserva") is not None else CARTEIRA_RESERVA)
    valor_org, fonte = await saldo_org(guild_id)
    fila = await fila_saques(guild_id)
    livre = arredondar(valor_org - reserva - fila["total"])
    return {"saldo": valor_org, "fonte": fonte, "reserva": reserva,
            "fila": fila["total"], "fila_qtd": fila["quantidade"], "livre": livre}


# ---------- APROVAÇÃO (usada pelo staff, pela carteira e pela LivePix) ----------

async def pos_aprovacao(guild, slot, horario, staff_id: Optional[int] = None, origem: str = "staff"):
    """Receita no caixa + comissão do ADM + logs. Chamado depois da vaga criada."""
    valor = arredondar(slot.get("valor_cobrado") if isinstance(slot, dict) else slot["valor_cobrado"])
    comprador = slot.get("comprador_id") if isinstance(slot, dict) else slot["comprador_id"]
    numero = slot.get("numero") if isinstance(slot, dict) else slot["numero"]
    tipo = horario.get("tipo") if isinstance(horario, dict) else horario["tipo"]
    categoria = horario.get("categoria") if isinstance(horario, dict) else horario["categoria"]
    hora = horario.get("horario") if isinstance(horario, dict) else horario["horario"]
    horario_id = horario.get("id") if isinstance(horario, dict) else horario["id"]

    await registrar_caixa(guild.id, "receita", valor,
                          f"Diário {texto_slot(tipo)} {categoria} {hora} — vaga #{numero}",
                          ref=f"slot:{slot.get('id') if isinstance(slot, dict) else slot['id']}") \
        if origem in ("staff", "livepix") else None
    # Obs.: no pagamento com SALDO o dinheiro real já entrou no depósito —
    # registrar receita de novo contaria duas vezes.

    if origem == "staff" and staff_id:
        pct = await cfgv(guild.id, "comissao_pct", CARTEIRA_COMISSAO_PCT)
        comissao = arredondar(valor * float(pct) / 100.0)
        if comissao > 0:
            # 💼 comissão do ADM cai na CARTEIRA DE TRABALHO (fechada no domingo)
            await creditar_trabalho(staff_id, guild.id, comissao, "comissao",
                                    f"Comissão {pct:.0f}% — vaga #{numero} {texto_slot(tipo)} {hora}",
                                    ref=f"slot:{slot.get('id') if isinstance(slot, dict) else slot['id']}")
            async with aiosqlite.connect(DATABASE_FILE) as db:
                await db.execute(
                    "INSERT INTO comissoes (guild_id, staff_id, slot_id, horario_id, valor_base, comissao, dia, criado_em) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (guild.id, staff_id, slot.get("id") if isinstance(slot, dict) else slot["id"], horario_id,
                     valor, comissao, agora_brt().strftime("%Y-%m-%d"), agora_brt().isoformat())
                )
                await db.commit()
            await registrar_log(
                guild, "💰 COMISSÃO", "💸 Comissão de ADM creditada (carteira de trabalho)",
                f"**{mencao(staff_id)} recebeu {formatar_moeda(comissao)}** pelo pagamento de {mencao(comprador)}.\n"
                f"> 🎮 Modo: `{texto_slot(tipo)}` • Categoria: `{categoria.title()}`\n"
                f"> ⏰ Diário: `{hora}` • Vaga: `#{numero}`\n"
                f"> 💰 Valor pago: `{formatar_moeda(valor)}` • {pct:.0f}% de comissão",
                "Verde"
            )

    titulo_origem = {"staff": "Aprovação manual", "carteira": "Pagamento com saldo",
                     "livepix": "Confirmação automática (LivePix)"}.get(origem, origem)
    await anunciar(
        guild, "pagamento", "🎮 Vaga liberada — pagamento confirmado",
        f"{mencao(comprador)} garantiu a vaga **#{numero}** no diário `{hora}`.\n"
        f"> 🎮 Modo: `{texto_slot(tipo)}` • Categoria: `{categoria.title()}`\n"
        f"> 💰 Valor: `{formatar_moeda(valor)}` • ✅ confirmado ({titulo_origem})\n"
        f"> 🧑‍⚖️ Fale com a equipe no ticket se precisar de algo.",
        "Esmeralda", marcar=comprador)

    await registrar_log(
        guild, "✅ PAGAMENTO", "✅ Pagamento aprovado",
        f"**{titulo_origem}** — {mencao(comprador)}\n"
        f"> 🎮 Modo: `{texto_slot(tipo)}` • Categoria: `{categoria.title()}`\n"
        f"> ⏰ Diário: `{hora}` • Vaga: `#{numero}`\n"
        f"> 💰 Valor: `{formatar_moeda(valor)}`",
        "Esmeralda"
    )


async def aprovar_pagamento(guild, slot_id: int, staff_id: Optional[int] = None,
                            origem: str = "carteira"):
    """Cria a vaga de verdade (número, canal do diário, acesso, tabela).
    Usado pelo pagamento com saldo e pela confirmação automática da LivePix."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        slot = await (await db.execute("SELECT * FROM slots WHERE id = ?", (slot_id,))).fetchone()
        if not slot or slot["confirmado"]:
            return None
        horario = await (await db.execute("SELECT * FROM horarios WHERE id = ?", (slot["horario_id"],))).fetchone()
        if not horario:
            return None

        total_vagas = LOTES_POR_MODO[horario["tipo"]]
        ocupadas = (await (await db.execute(
            "SELECT COUNT(*) FROM slots WHERE horario_id = ? AND confirmado = 1", (slot["horario_id"],)
        )).fetchone())[0]
        if ocupadas >= total_vagas:
            return None

        numero_final = ocupadas + 1
        await db.execute("UPDATE slots SET confirmado = 1, numero = ? WHERE id = ?", (numero_final, slot["id"]))
        await db.execute("UPDATE horarios SET lotes_usados = ? WHERE id = ?", (numero_final, slot["horario_id"]))
        await db.commit()
        slot = dict(slot)
        slot["numero"] = numero_final
        horario = dict(horario)

    try:
        canal_tabela_id = await criar_canal_tabela(guild, slot["horario_id"])
    except Exception as erro:
        canal_tabela_id = None
        print("Erro ao criar canal do diário:", erro)

    comprador = await membro_do_guild(guild, slot["comprador_id"])
    if comprador:
        try:
            await add_jogador_canal_tabela(guild, slot["horario_id"], comprador)
        except Exception:
            pass
    try:
        await atualizar_tabela(guild, slot["horario_id"])
    except Exception:
        pass
    await rebuild_painel(guild, horario["painel_id"])

    await pos_aprovacao(guild, slot, horario, staff_id=staff_id, origem=origem)

    # avisa o comprador no canal de pagamento (menção por ID: zero intent)
    try:
        canal_pag = guild.get_channel(slot["canal_pag"]) if slot.get("canal_pag") else None
        if canal_pag:
            embed = criar_embed(
                "✅ Pagamento Aprovado!",
                f"{mencao(slot['comprador_id'])} — **vaga #{numero_final}** liberada!\n"
                f"> 🎮 `{texto_slot(horario['tipo'])}` • `{horario['horario']}`\n"
                f"> 📊 Acompanhe a tabela no canal do diário.\n"
                f"> 📩 ID e senha chegam **5 minutos antes** do início.",
                "Esmeralda"
            )
            await canal_pag.send(content=mencao(slot["comprador_id"]), embed=embed)
            try:
                async for msg in canal_pag.history(limit=8):
                    if msg.author == guild.me and msg.components:
                        await msg.edit(view=None)
                        break
            except Exception:
                pass
    except Exception:
        pass

    return numero_final, horario


async def pagar_com_saldo(guild, slot_id: int, user_id: int):
    """Paga a reserva com o saldo da carteira. Devolve (ok, mensagem, numero)."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        slot = await (await db.execute("SELECT * FROM slots WHERE id = ?", (slot_id,))).fetchone()
    if not slot or slot["confirmado"]:
        return False, "Esta reserva não está mais aberta.", None
    if int(slot["comprador_id"]) != int(user_id):
        return False, "Só o dono desta reserva pode pagar com saldo.", None

    valor = arredondar(slot["valor_cobrado"])
    novo = await debitar_saldo(user_id, guild.id, valor, "compra",
                               f"Diário — vaga reservada (slot {slot_id})", ref=f"slot:{slot_id}")
    if novo is None:
        return False, f"Saldo insuficiente. Você tem {formatar_moeda(await saldo_carteira(user_id, guild.id))} e a vaga custa {formatar_moeda(valor)}.", None

    resultado = await aprovar_pagamento(guild, slot_id, staff_id=None, origem="carteira")
    if not resultado:
        await creditar_saldo(user_id, guild.id, valor, "estorno", "Estorno — vaga indisponível", ref=f"slot:{slot_id}")
        return False, "A sala estava lotada — o saldo foi devolvido.", None

    numero, horario = resultado
    await registrar_log(
        guild, "💰 CARTEIRA", "💰 Vaga paga com saldo da carteira",
        f"{mencao(user_id)} pagou **{formatar_moeda(valor)}** com saldo.\n"
        f"> 🎮 Modo: `{texto_slot(horario['tipo'])}` • Categoria: `{horario['categoria'].title()}`\n"
        f"> ⏰ Diário: `{horario['horario']}` • Vaga: `#{numero}` • Saldo agora: `{formatar_moeda(novo)}`",
        "Verde"
    )
    return True, f"Pagamento com saldo aprovado! Vaga **#{numero}** liberada.", numero


# ---------- DEPÓSITO (LivePix) ----------

class DepositoModal(discord.ui.Modal, title="💰 Depositar — PIX via LivePix"):
    campo_valor = discord.ui.TextInput(
        label="Valor do depósito (R$)", placeholder="Ex: 10,00", required=True, max_length=12)
    campo_nome = discord.ui.TextInput(
        label="Nome que vai usar no pagamento",
        placeholder="Escreva EXATAMENTE o nome que você vai digitar no LivePix",
        required=True, max_length=60)

    def __init__(self, deposito_id: int = 0, canal_id: int = 0):
        super().__init__()
        self.deposito_id = deposito_id
        self.canal_id = canal_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        valor = parse_valor(self.campo_valor.value)
        minimo = float(await cfgv(interaction.guild.id, "deposito_min", CARTEIRA_DEPOSITO_MIN))
        if valor is None or valor < minimo:
            return await interaction.followup.send(
                embed=criar_embed("❌ Valor inválido", f"O depósito mínimo é **{formatar_moeda(minimo)}**.", "Vermelho"),
                ephemeral=True)

        nome = self.campo_nome.value.strip()
        janela = int(await cfgv(interaction.guild.id, "janela_min", CARTEIRA_JANELA_MIN))
        expira = (agora_brt() + datetime.timedelta(minutes=janela)).isoformat()

        if self.deposito_id:
            async with aiosqlite.connect(DATABASE_FILE) as db:
                await db.execute("UPDATE depositos SET valor = ?, nome_pagador = ?, status = 'na_janela', "
                                 "criado_em = ?, expira_em = ? WHERE id = ?",
                                 (valor, nome, agora_brt().isoformat(), expira, self.deposito_id))
                await db.commit()
            deposito_id = self.deposito_id
        else:
            async with aiosqlite.connect(DATABASE_FILE) as db:
                cursor = await db.execute(
                    "INSERT INTO depositos (guild_id, user_id, valor, nome_pagador, apelidos, status, "
                    "criado_em, expira_em) VALUES (?, ?, ?, ?, ?, 'na_janela', ?, ?)",
                    (interaction.guild.id, interaction.user.id, valor, nome,
                     apelidos_do_usuario(interaction.user), agora_brt().isoformat(), expira))
                deposito_id = cursor.lastrowid
                await db.commit()
        marcar_sujo()

        link = await link_pagamento(interaction.guild.id, valor, tipo="deposito", alvo_id=deposito_id,
                                    user_id=interaction.user.id, nick=nome,
                                    canal_id=self.canal_id or interaction.channel.id)
        embed = criar_embed(
            "💰 PIX do depósito",
            f"**{interaction.user.mention}** vai depositar **{formatar_moeda(valor)}**.\n\n"
            f"> 🧾 **Valor exato:** `{formatar_moeda(valor)}`\n"
            f"> 👤 **Nome no pagamento:** `{nome}`\n"
            f"> ⏱️ **Confirmação automática:** até {janela} min depois de pagar\n"
            f"> 🤝 Passou disso? A equipe confirma manualmente pra você. 💛",
            "Esmeralda", footer=f"Fire Force • Depósito #{deposito_id}")
        if link:
            embed.add_field(name="🔗 Link (PIX)", value=f"> {link}", inline=False)
            embed.add_field(
                name="📌 Passo a passo",
                value="> 1️⃣ Abra o link e pague o valor exato\n"
                      "> 2️⃣ **Nome:** escreva o **seu nick** (o mesmo que você usa aqui)\n"
                      "> 💬 **Mensagem:** se quiser, escreva o seu **@ do Discord** — o bot lê os dois 👍\n"
                      "> 3️⃣ O saldo cai sozinho na sua carteira ✅",
                inline=False)
        arquivo = None
        if link:
            try:
                arquivo = discord.File(gerar_qr_url(link), "deposito.png")
                embed.set_image(url="attachment://deposito.png")
            except Exception:
                arquivo = None

        destino = interaction.channel
        try:
            if self.canal_id:
                destino = interaction.guild.get_channel(self.canal_id) or interaction.channel
        except Exception:
            destino = interaction.channel
        enviar = {"embed": embed}
        if arquivo:
            enviar["file"] = arquivo
        try:
            await destino.send(**enviar)
            await interaction.followup.send(
                embed=criar_embed("✅ Depósito aberto", "Confira a mensagem com o PIX aqui no canal. 💰",
                                  "Esmeralda"), ephemeral=True)
        except Exception:
            if arquivo:
                await interaction.followup.send(embed=embed, ephemeral=True, file=arquivo)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)

        await registrar_log(
            interaction.guild, "💰 DEPÓSITO", "💰 Depósito aberto",
            f"{mencao(interaction.user.id)} abriu depósito de **{formatar_moeda(valor)}** "
            f"(nome no pagamento: `{nome}`).", "Azul")


class SaqueModal(discord.ui.Modal, title="💸 Sacar — PIX"):
    campo_valor = discord.ui.TextInput(label="Valor do saque (R$)", placeholder="Ex: 25,00", required=True,
                                       max_length=12)
    campo_chave = discord.ui.TextInput(label="Sua chave PIX", placeholder="CPF, celular, e-mail ou aleatória",
                                       required=True, max_length=120)
    campo_titular = discord.ui.TextInput(
        label="Nome do titular da chave", required=False, max_length=80,
        placeholder="Use o mesmo nome do depósito — agiliza o pagamento")

    def __init__(self, tipo_chave: str = "aleatoria", tipo_carteira: str = "jogador",
                 chave_salva: str = "", titular_salvo: str = ""):
        super().__init__()
        self.tipo_chave = tipo_chave or "aleatoria"
        self.tipo_carteira = tipo_carteira or "jogador"
        if chave_salva:
            self.campo_chave.default = chave_salva
        if titular_salvo:
            self.campo_titular.default = titular_salvo

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        valor = parse_valor(self.campo_valor.value)
        minimo = float(await cfgv(interaction.guild.id, "saque_min", CARTEIRA_SAQUE_MIN))
        chave = self.campo_chave.value.strip()
        titular = self.campo_titular.value.strip()
        de_trabalho = (self.tipo_carteira == "trabalho")

        saldo = (await saldo_trabalho(interaction.user.id, interaction.guild.id) if de_trabalho
                 else await saldo_carteira(interaction.user.id, interaction.guild.id))
        if valor is None or valor < minimo:
            return await interaction.followup.send(
                embed=criar_embed("❌ Valor inválido", f"O saque mínimo é **{formatar_moeda(minimo)}**.", "Vermelho"),
                ephemeral=True)
        if valor > saldo:
            onde = "na sua **carteira de trabalho** (o salário da equipe)" if de_trabalho else "na sua carteira"
            return await interaction.followup.send(
                embed=criar_embed("❌ Saldo insuficiente",
                                  f"Você tem **{formatar_moeda(saldo)}** {onde} e pediu "
                                  f"**{formatar_moeda(valor)}**.\n\n"
                                  + ("> 💼 O saque da equipe sai sempre da **carteira de trabalho** "
                                     "(as comissões e o pagamento dos atendimentos)." if de_trabalho else
                                     "> 💰 Use `/deposito` ou `/transferir` pra completar o valor."),
                                  "Vermelho"), ephemeral=True)

        # salva a chave: o próximo saque vira 1 clique
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute(
                "INSERT OR REPLACE INTO chaves_salvas (user_id, guild_id, tipo, chave, titular, atualizado_em) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (interaction.user.id, interaction.guild.id, self.tipo_chave, chave, titular,
                 agora_brt().isoformat()))
            await db.commit()
        marcar_sujo()

        if de_trabalho:
            novo = await movimentar_trabalho(interaction.user.id, interaction.guild.id, -valor, "saque",
                                             f"Saque da carteira de trabalho ({self.tipo_chave})")
        else:
            novo = await debitar_saldo(interaction.user.id, interaction.guild.id, valor, "saque",
                                       f"Saque solicitado — chave {self.tipo_chave}")
        if novo is None:
            return await interaction.followup.send(
                embed=criar_embed("❌ Saldo insuficiente", "Tente novamente.", "Vermelho"), ephemeral=True)

        disp = await disponibilidade_saque(interaction.guild.id)
        liberado = disp["livre"] >= valor
        status = "liberado" if liberado else "na_fila"

        async with aiosqlite.connect(DATABASE_FILE) as db:
            cursor = await db.execute(
                "INSERT INTO saques (guild_id, user_id, valor, chave_pix, titular, status, tipo, criado_em, "
                "saldo_antes, saldo_apos) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (interaction.guild.id, interaction.user.id, valor, chave, titular, status,
                 "trabalho" if de_trabalho else "jogador", agora_brt().isoformat(),
                 arredondar(saldo), arredondar(novo)))
            saque_id = cursor.lastrowid
            await db.commit()
        marcar_sujo()

        embed = criar_embed(
            "💸 Saque solicitado",
            f"**{interaction.user.mention}**, seu saque de **{formatar_moeda(valor)}** foi registrado.\n\n"
            f"> 🏦 **Chave ({self.tipo_chave}):** `{chave}`\n"
            f"> 👤 **Titular:** `{titular or 'não informado'}`\n"
            f"> 💼 **{'Carteira de trabalho agora' if de_trabalho else 'Saldo agora'}:** "
            f"`{formatar_moeda(novo)}`\n"
            f"> 🔖 **Protocolo:** `#{saque_id}`\n\n"
            f"⏳ **Pagamento:** de **1 minuto a 24 horas (ou mais)** — quem paga é o **dono/gerente**, "
            f"que são os únicos com acesso à conta. Você não precisa fazer nada: quando o PIX sair, "
            f"a confirmação chega aqui. 💛",
            "Esmeralda")
        embed.add_field(
            name=("⚡ Prioridade" if liberado else "🤝 Fila de pagamento"),
            value=("> Seu saque já entrou na **fila de pagamento de agora** — a equipe foi avisada e o PIX sai "
                   "em instantes." if liberado else
                   "> O caixa está no limite de segurança agora, então seu saque entrou na fila. Assim que entrar "
                   "saldo, ele é **pago automaticamente** — sem você pedir de novo."),
            inline=False)
        embed.add_field(
            name="⏱️ Quanto tempo demora?",
            value=("> O PIX sai **na mão**, pelo **dono ou gerente** (só eles entram na conta).\n"
                   "> O normal é cair em **minutos** — mas pode levar **até 24 horas ou mais** se "
                   "nenhum deles estiver online.\n"
                   "> **Seu saque não se perde:** ele fica na fila, o bot cobra a equipe sozinho "
                   "e o status é sempre atualizado com o seu protocolo. 💛"), inline=False)
        embed.add_field(name="⭐ Próxima vez",
                        value="> Sua chave ficou **salva**: no próximo saque é só clicar em "
                              "**Usar minha chave salva**. ⚡", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

        await anunciar(
            interaction.guild, "saque", "💸 Novo pedido de saque",
            f"{mencao(interaction.user.id)} pediu **{formatar_moeda(valor)}** e já reservou o valor da "
            f"carteira.\n> 🔖 Protocolo: `#{saque_id}`\n"
            f"> 📋 Status: **{'liberado para pagar ✅' if liberado else 'na fila de pagamento 🤝'}**\n"
            f"> 🏦 Chave: `{chave}`"
            + (f"\n> ⏱️ O pagamento sai pelo **dono/gerente** — de minutos até 24h ou mais."
               if liberado else "\n> ⏳ Entra na fila de pagamento assim que o caixa liberar."),
            "Amarelo", marcar=None)
        await notificar_saque(interaction.guild, saque_id)
        await registrar_log(
            interaction.guild, "💸 SAQUE", "💸 Novo pedido de saque",
            f"{mencao(interaction.user.id)} pediu saque de **{formatar_moeda(valor)}**"
            f"{' — descontado da **carteira de trabalho** (salário)' if de_trabalho else ''}.\n"
            f"> 🔖 Protocolo: `#{saque_id}` • Status: `{'liberado para pagar' if liberado else 'na fila'}`\n"
            f"> 🏦 Chave ({self.tipo_chave}): `{chave}` • Titular: `{titular or '-'}`\n"
            + (f"> 💼 Carteira de trabalho: `{formatar_moeda(saldo)}` − `{formatar_moeda(valor)}` = "
               f"**total atualizado `{formatar_moeda(novo)}`**"
               if de_trabalho else
               f"> 💰 Carteira: `{formatar_moeda(saldo)}` − `{formatar_moeda(valor)}` = "
               f"**total atualizado `{formatar_moeda(novo)}`**"),
            "Amarelo")


class SaqueAcaoView(discord.ui.View):
    """Botões do staff no aviso de saque (persistente após restart)."""

    def __init__(self, saque_id: int):
        super().__init__(timeout=None)
        self.saque_id = saque_id
        self.marcar.custom_id = f"ff_saque_pago:{saque_id}"
        self.estornar.custom_id = f"ff_saque_estorno:{saque_id}"
        self.marcar_auto.custom_id = f"ff_saque_auto:{saque_id}"

    async def _buscar(self):
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            return await (await db.execute("SELECT * FROM saques WHERE id = ?", (self.saque_id,))).fetchone()

    @discord.ui.button(label="PIX enviado ✅", style=discord.ButtonStyle.green)
    async def marcar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await e_staff(interaction.user):
            return await interaction.response.send_message(
                embed=criar_embed("❌ Sem Permissão", "Apenas a equipe financeira.", "Vermelho"), ephemeral=True
            )
        saque = await self._buscar()
        if not saque or saque["status"] == "pago":
            return await interaction.response.send_message(
                embed=criar_embed("ℹ️ Já resolvido", "Este saque já foi pago ou cancelado.", "Amarelo"), ephemeral=True
            )
        await concluir_saque(saque["id"], interaction.user.id, "pagamento marcado pela equipe")
        await interaction.response.send_message(
            embed=criar_embed("✅ Saque pago", f"Protocolo `#{saque['id']}` marcado como pago.", "Esmeralda"), ephemeral=True
        )

    @discord.ui.button(label="Estornar (devolver saldo)", style=discord.ButtonStyle.gray)
    async def estornar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await e_staff(interaction.user):
            return await interaction.response.send_message(
                embed=criar_embed("❌ Sem Permissão", "Apenas a equipe financeira.", "Vermelho"), ephemeral=True
            )
        saque = await self._buscar()
        if not saque or saque["status"] in ("pago", "estornado"):
            return await interaction.response.send_message(
                embed=criar_embed("ℹ️ Já resolvido", "Este saque já foi pago ou estornado.", "Amarelo"), ephemeral=True
            )
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute("UPDATE saques SET status = 'estornado' WHERE id = ?", (saque["id"],))
            await db.commit()
        await creditar_saldo(saque["user_id"], saque["guild_id"], saque["valor"], "estorno",
                             f"Estorno do saque #{saque['id']}", ref=f"saque:{saque['id']}")
        await registrar_log(
            interaction.guild, "💸 SAQUE", "↩️ Saque estornado",
            f"Protocolo `#{saque['id']}` foi estornado por {interaction.user.mention}.\n"
            f"> {mencao(saque['user_id'])} recebeu **{formatar_moeda(saque['valor'])}** de volta na carteira.",
            "Amarelo"
        )
        try:
            await interaction.message.edit(view=None)
        except Exception:
            pass
        await interaction.response.send_message(
            embed=criar_embed("↩️ Estornado", "O saldo voltou pra carteira do jogador.", "Amarelo"), ephemeral=True
        )

    @discord.ui.button(label="Tentar novamente", style=discord.ButtonStyle.blurple)
    async def marcar_auto(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await e_staff(interaction.user):
            return await interaction.response.send_message(
                embed=criar_embed("❌ Sem Permissão", "Apenas a equipe financeira.", "Vermelho"), ephemeral=True
            )
        await notificar_saque(interaction.guild, self.saque_id, forcar=True)
        await interaction.response.send_message(
            embed=criar_embed("🔁 Reenviado", "Dados do saque reenviados.", "Azul"), ephemeral=True
        )


async def notificar_saque(guild, saque_id: int, forcar: bool = False):
    """Manda pro canal de logs/financeiro os dados prontos pra pagar no painel da LivePix."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        saque = await (await db.execute("SELECT * FROM saques WHERE id = ?", (saque_id,))).fetchone()
    if not saque or saque["status"] in ("pago", "estornado"):
        return
    if saque["status"] == "na_fila" and not forcar:
        return

    disp = await disponibilidade_saque(guild.id)
    embed = criar_embed(
        "💸 PIX PARA ENVIAR — LivePix",
        f"**Protocolo:** `#{saque['id']}`\n"
        f"**Jogador:** {mencao(saque['user_id'])}\n\n"
        f"> 💰 **Valor:** `{formatar_moeda(saque['valor'])}`\n"
        f"> 🏦 **Chave PIX:** `{saque['chave_pix']}`\n"
        f"> 👤 **Titular:** `{saque['titular'] or 'não informado'}`\n\n"
        f"> 🖱️ Pague no painel da LivePix: {LIVEPIX_PAINEL}\n"
        f"> ✅ Depois clique em **PIX enviado** aqui embaixo (ou deixe o bot detectar sozinho).",
        "Amarelo"
    )
    embed.add_field(name="📊 Caixa agora", value=f"> Saldo: `{formatar_moeda(disp['saldo'])}` (fonte: {disp['fonte']})\n"
                                                f"> Reserva protegida: `{formatar_moeda(disp['reserva'])}`\n"
                                                f"> Fila total: `{formatar_moeda(disp['fila'])}`", inline=False)
    # 💼 de onde saiu o dinheiro + o total atualizado depois do desconto
    de_trabalho = (saque["tipo"] or "jogador") == "trabalho"
    atual = (await saldo_trabalho(saque["user_id"], saque["guild_id"]) if de_trabalho
             else await saldo_carteira(saque["user_id"], saque["guild_id"]))
    detalhe = ("> Fonte: **carteira de trabalho** (salário da equipe)\n" if de_trabalho
               else "> Fonte: carteira do jogador\n")
    if saque["saldo_antes"] is not None:
        detalhe += (f"> ⏮️ Antes do saque: `{formatar_moeda(saque['saldo_antes'])}`\n"
                    f"> 📉 Descontado: `{formatar_moeda(saque['valor'])}`\n")
    detalhe += f"> ✅ **Total atualizado: `{formatar_moeda(atual)}`**"
    embed.add_field(name="💼 Carteira depois deste saque", value=detalhe, inline=False)
    embed.add_field(
        name="👑 Quem paga agora",
        value=("> **Dono e gerente** — só quem tem acesso à conta da LivePix.\n"
               "> 🖱️ Retire o valor da LivePix pro seu PIX e mande pros jogadores no app do banco.\n"
               "> ⏱️ O jogador **já foi avisado**: de **1 minuto a 24h ou mais**, conforme a sua\n"
               "> disponibilidade — mas o bot cobra a equipe automaticamente até sair.\n"
               "> ✅ Depois marque em **✅ Marcar pagos** no painel da fila (ou no botão aqui)."),
        inline=False)
    canal_id = await canal_de_logs(guild.id)
    canal = guild.get_channel(int(canal_id)) if canal_id else None
    if canal:
        try:
            await canal.send(embed=embed, view=SaqueAcaoView(saque_id))
        except Exception:
            pass


async def concluir_saque(saque_id: int, staff_id: Optional[int] = None, motivo: str = ""):
    """Fecha o saque como PAGO: caixa, log e aviso pro jogador."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        saque = await (await db.execute("SELECT * FROM saques WHERE id = ?", (saque_id,))).fetchone()
        if not saque or saque["status"] in ("pago", "estornado"):
            return False
        await db.execute(
            "UPDATE saques SET status = 'pago', processado_em = ?, processado_por = ? WHERE id = ?",
            (agora_brt().isoformat(), staff_id, saque_id)
        )
        await db.commit()

    await registrar_caixa(saque["guild_id"], "despesa", saque["valor"],
                          f"Saque pago #{saque_id} (PIX via LivePix)", ref=f"saque:{saque_id}")

    guild = bot.get_guild(saque["guild_id"])
    if guild:
        try:
            canal, publico = await canal_anuncio(guild, "saque")
            if canal:
                chave_mostrada = mascarar_chave(saque["chave_pix"]) if publico else saque["chave_pix"]
                embed = criar_embed(
                    "✅ Saque pago",
                    f"{mencao(saque['user_id'])} — seu saque foi **enviado**!\n\n"
                    f"> 🔖 Protocolo: `#{saque_id}`\n"
                    f"> 💰 Valor: `{formatar_moeda(saque['valor'])}`\n"
                    f"> 🏦 Chave: `{chave_mostrada}`\n\n"
                    f"Obrigado por jogar na 🔥 Fire Force! Qualquer coisa, chama no ticket.",
                    "Esmeralda"
                )
                await canal.send(content=mencao(saque["user_id"]), embed=embed)
        except Exception:
            pass
        quem = f" por {mencao(staff_id)}" if staff_id else ""
        de_trabalho = (saque["tipo"] or "jogador") == "trabalho"
        atual = (await saldo_trabalho(saque["user_id"], guild.id) if de_trabalho
                 else await saldo_carteira(saque["user_id"], guild.id))
        await registrar_log(
            guild, "💸 SAQUE", "✅ Saque pago",
            f"Protocolo `#{saque_id}` — {formatar_moeda(saque['valor'])} para {mencao(saque['user_id'])}{quem}.\n"
            f"> {motivo or 'pagamento enviado'}\n> 🏦 Chave: `{saque['chave_pix']}`\n"
            + (f"> 💼 Carteira de trabalho: `{formatar_moeda(saque['saldo_antes'])}` − "
               f"`{formatar_moeda(saque['valor'])}` = **total atualizado `{formatar_moeda(atual)}`**"
               if (de_trabalho and saque["saldo_antes"] is not None)
               else f"> 💰 Carteira agora: **`{formatar_moeda(atual)}`**"),
            "Esmeralda"
        )
        # se liberou espaço, tenta pagar o próximo da fila
        await processar_fila_saques(guild.id)
    return True


# ---------- FILA: paga sozinho quando o caixa permite ----------

async def processar_fila_saques(guild_id: int) -> list:
    """Sempre que entra dinheiro, olha a fila e libera o que couber na reserva."""
    liberados = []
    disp = await disponibilidade_saque(guild_id)
    if disp["livre"] <= 0:
        return liberados

    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        fila = await (await db.execute(
            "SELECT * FROM saques WHERE guild_id = ? AND status = 'na_fila' ORDER BY id", (guild_id,)
        )).fetchall()

    livre = disp["livre"]
    for saque in fila:
        if arredondar(saque["valor"]) > livre:
            continue
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute("UPDATE saques SET status = 'liberado' WHERE id = ?", (saque["id"],))
            await db.commit()
        livre = arredondar(livre - saque["valor"])
        liberados.append(dict(saque))

    guild = bot.get_guild(guild_id)
    for saque in liberados:
        if guild:
            await notificar_saque(guild, saque["id"])
            await registrar_log(
                guild, "💸 SAQUE", "⚡ Saque liberado para pagamento",
                f"Protocolo `#{saque['id']}` de {mencao(saque['user_id'])} "
                f"(**{formatar_moeda(saque['valor'])}**) entrou na fila de pagamento de agora.",
                "Verde"
            )
    return liberados


# ---------- CASAMENTO AUTOMÁTICO (o coração da confirmação em 5 min) ----------

def _ler_tempo_pix(registro: dict) -> Optional[datetime.datetime]:
    for chave in ("createdAt", "criadoEm", "timestamp", "created_at"):
        valor = registro.get(chave)
        if not valor:
            continue
        try:
            if isinstance(valor, (int, float)):
                return datetime.datetime.fromtimestamp(float(valor), TZ_BRASILIA)
            texto = str(valor).replace("Z", "+00:00")
            dt = datetime.datetime.fromisoformat(texto)
            return dt.astimezone(TZ_BRASILIA) if dt.tzinfo else dt.replace(tzinfo=TZ_BRASILIA)
        except Exception:
            continue
    return None


async def casar_pagamentos_livepix(guild_id: int, limite: int = LIVEPIX_PAGAMENTOS_LIMITE,
                                   folga_min: int = 0) -> dict:
    """⚡ Confirma pagamento SOZINHO, nesta ordem:

      1) pela REFERÊNCIA do checkout  → certeiro, sem depender de nome nem de janela
      2) pelo nome do pagador + valor → plano B (quem pagou por fora, escrevendo o nome)
      3) valor exato com UMA única reserva aberta → plano C (link fixo/chave)
      4) saques que já saíram da conta → detecta o débito no extrato da LivePix

    `folga_min` = minutos que o bot ficou FORA DO AR: a janela de conferência é
    esticada por esse tempo (até 24h), então pagamento que caiu com o bot
    desligado é reconhecido na volta — sem depender da equipe.
    """
    resultado = {"depositos": 0, "reservas": 0, "saques": 0, "ref": 0, "erro": ""}
    if not livepix.configurado:
        resultado["erro"] = "LivePix não configurada"
        return resultado

    pagamentos = await livepix.pagamentos(limite)
    mensagens = await livepix.mensagens(limite)
    if not mensagens and not pagamentos:
        # Pode ser só "ninguém pagou nada ainda": a checagem da RETIRADA da
        # carteira (item 5) continua valendo, então não saímos daqui.
        resultado["erro"] = livepix.ultimo_erro or "sem resposta da LivePix"

    # junta tudo num formato único: (id, nome, centavos, quando, referência)
    eventos = []
    for msg in mensagens:
        nome_pago = str(msg.get("username") or "")
        recado = str(msg.get("message") or "")
        eventos.append({
            "id": f"msg:{msg.get('id')}", "nome": nome_pago,
            "texto": f"{nome_pago} {recado}".strip(),
            "centavos": msg.get("amount") or 0, "quando": _ler_tempo_pix(msg),
            "reference": str(msg.get("reference") or ""),
        })
    for pag in pagamentos:
        eventos.append({
            "id": f"pag:{pag.get('id')}", "nome": "", "texto": "",
            "centavos": pag.get("amount") or 0,
            "quando": _ler_tempo_pix(pag), "reference": str(pag.get("reference") or ""),
        })

    guild = bot.get_guild(guild_id)

    # ---------- 1) REFERÊNCIA DO CHECKOUT (o caminho 100% automático) ----------
    com_ref = [{"id": e["id"].split(":", 1)[1], "amount": e["centavos"], "reference": e["reference"]}
               for e in eventos if e["reference"]]
    # ...e quem digitou o código na MENSAGEM do LivePix conta do mesmo jeito
    ja_listados = {c["reference"] for c in com_ref}
    for evento in eventos:
        for codigo in codigos_no_texto(evento.get("texto", "")):
            if codigo not in ja_listados:
                com_ref.append({"id": evento["id"].split(":", 1)[1], "amount": evento["centavos"],
                                "reference": codigo})
                ja_listados.add(codigo)
    if com_ref:
        resultado["ref"] = await reconciliar_referencias(guild_id, com_ref, resultado)

    janela = int(await cfgv(guild_id, "janela_min", CARTEIRA_JANELA_MIN))
    # 🩺 folga_min = tempo que o bot ficou fora do ar (0 no dia a dia)
    janela_nome = max(30, janela) + max(0, int(folga_min or 0))

    # ---------- 2) DEPÓSITOS (nome + valor) ----------
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        abertos = await (await db.execute(
            "SELECT * FROM depositos WHERE guild_id = ? AND status = 'na_janela'", (guild_id,)
        )).fetchall()

    for deposito in abertos:
        criado = None
        try:
            criado = datetime.datetime.fromisoformat(deposito["criado_em"])
        except Exception:
            pass
        if criado and (agora_brt() - criado).total_seconds() > janela_nome * 60:
            continue

        for evento in eventos:
            if not valor_bate(evento["centavos"], arredondar(deposito["valor"])):
                continue
            # nome: vale o NOME digitado, a MENSAGEM escrita e os apelidos do jogador
            candidatos = nomes_candidatos(deposito, deposito["nome_pagador"])
            if not any(nome_do_pagamento_bate(evento, alvo) for alvo in candidatos):
                continue
            # 🩺 na reconferência, o PIX tem que ter caído depois do pedido
            if not pagamento_depois_do_pedido(evento, criado, folga_min):
                continue
            if await _ja_visto(evento["id"]):
                continue

            await creditar_deposito(guild, dict(deposito),
                                    f"PIX automático no LivePix (janela de {janela_nome} min)", evento["id"])
            resultado["depositos"] += 1
            if guild and deposito["assumido_por"]:
                await registrar_log_suporte(
                    guild, "💰 DEPÓSITO", "✅ Depósito confirmado (atendimento)",
                    f"{mencao(deposito['user_id'])} depositou **{formatar_moeda(deposito['valor'])}** "
                    f"(assumido por {mencao(deposito['assumido_por'])}).", "Esmeralda")
            break

    # ---------- 3) RESERVAS DE DIÁRIO (nome + valor) ----------
    limite_sql = (agora_brt() - datetime.timedelta(minutes=janela_nome)).isoformat()
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        reservas = await (await db.execute(
            "SELECT * FROM slots WHERE guild_id = ? AND confirmado = 0 AND criado_em >= ?", (guild_id, limite_sql)
        )).fetchall()

    for reserva in reservas:
        valor = arredondar(reserva["valor_cobrado"])
        try:
            criado_reserva = datetime.datetime.fromisoformat(reserva["criado_em"])
        except Exception:
            criado_reserva = None
        for evento in eventos:
            if not valor_bate(evento["centavos"], valor):
                continue
            candidatos = nomes_candidatos(reserva, reserva["comprador_nome"])
            if not any(nome_do_pagamento_bate(evento, alvo) for alvo in candidatos):
                continue
            # 🩺 na reconferência, o PIX tem que ter caído depois da reserva
            if not pagamento_depois_do_pedido(evento, criado_reserva, folga_min):
                continue
            if await _ja_visto(evento["id"]):
                continue
            if guild:
                aprovado = await aprovar_pagamento(guild, reserva["id"], staff_id=None, origem="livepix")
                if aprovado:
                    resultado["reservas"] += 1
                    await registrar_log(
                        guild, "✅ PAGAMENTO", "⚡ Pagamento detectado na LivePix",
                        f"PIX de **{formatar_moeda(valor)}** ({evento['nome'] or 'pagador'}) "
                        f"casou com a reserva de {mencao(reserva['comprador_id'])}.\n"
                        f"> Vaga `#{aprovado[0]}` liberada automaticamente.", "Esmeralda")
            break

    # ---------- 4) VALOR EXATO COM UMA ÚNICA RESERVA ABERTA ----------
    if guild:
        await casar_por_valor_unico(guild_id, eventos, resultado)

    # ---------- 5) RETIRADA DA LIVEPIX (dinheiro saiu da conta) ----------
    try:
        resultado["saques"] = await detectar_retirada_livepix(guild_id)
    except Exception as erro:
        _log_arquivo(f"[FILA] retirada: {erro}")

    return resultado


# ---------- UTILITÁRIOS DO SISTEMA FINANCEIRO ----------

def parse_valor(texto) -> Optional[float]:
    """Aceita '10', '10,00', '10.00', 'R$ 10,00'."""
    try:
        limpo = str(texto or "").strip().lower().replace("r$", "").replace(" ", "")
        if "," in limpo and "." in limpo:
            limpo = limpo.replace(".", "").replace(",", ".")
        else:
            limpo = limpo.replace(",", ".")
        valor = round(float(limpo), 2)
        return valor if valor > 0 else None
    except Exception:
        return None


async def cfgv(guild_id: int, chave: str, padrao=None):
    """Valor de configuração do servidor com fallback pro padrão."""
    cfg = await obter_config(guild_id)
    valor = cfg.get(chave)
    return padrao if valor in (None, "", 0) else valor


async def extrato_texto(user_id: int, guild_id: int, quantidade: int = 10) -> str:
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        linhas = await (await db.execute(
            "SELECT * FROM transacoes WHERE guild_id = ? AND user_id = ? ORDER BY id DESC LIMIT ?",
            (guild_id, user_id, quantidade)
        )).fetchall()
    if not linhas:
        return "> *Nenhuma movimentação ainda.*"

    icones = {
        "deposito": "⬆️", "saque": "⬇️", "compra": "🎮", "comissao": "💸",
        "transferencia_enviada": "📤", "transferencia_recebida": "📥",
        "ajuste": "🛠️", "estorno": "↩️", "premio": "🏆",
    }
    texto = []
    for linha in linhas:
        valor = arredondar(linha["valor"])
        sinal = "+" if valor >= 0 else "−"
        icone = icones.get(linha["tipo"], "•")
        quando = (linha["criado_em"] or "")[8:16].replace("-", "/")
        descricao = (linha["descricao"] or "")[:48]
        texto.append(f"> {icone} `{sinal}{formatar_moeda(abs(valor))}` — {descricao} `{quando}`")
    return "\n".join(texto)


async def resumo_comissoes_dia(guild_id: int, dia: str) -> dict:
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        linhas = await (await db.execute(
            "SELECT staff_id, COUNT(*) AS qtd, COALESCE(SUM(valor_base), 0) AS base, "
            "COALESCE(SUM(comissao), 0) AS total FROM comissoes "
            "WHERE guild_id = ? AND dia = ? GROUP BY staff_id ORDER BY total DESC",
            (guild_id, dia)
        )).fetchall()
    return {
        "por_adm": [dict(l) for l in linhas],
        "total": arredondar(sum(arredondar(l["total"]) for l in linhas)),
        "base": arredondar(sum(arredondar(l["base"]) for l in linhas)),
        "vendas": sum(int(l["qtd"]) for l in linhas),
    }


# ==================== COMANDOS DA CARTEIRA ====================

@bot.tree.command(name="carteira", description="💰 Ver seu saldo e o extrato da carteira")
@app_commands.describe(usuario="Ver a carteira de outra pessoa (equipe)")
async def cmd_carteira(interaction: discord.Interaction, usuario: Optional[discord.Member] = None):
    alvo = usuario or interaction.user
    if usuario and usuario.id != interaction.user.id and not await e_staff(interaction.user):
        return await interaction.response.send_message(
            embed=criar_embed("❌ Sem Permissão", "Você só pode ver a sua própria carteira.", "Vermelho"), ephemeral=True
        )

    saldo = await saldo_carteira(alvo.id, interaction.guild.id)
    extrato = await extrato_texto(alvo.id, interaction.guild.id, 8)

    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        saques = await (await db.execute(
            "SELECT COUNT(*) AS qtd, COALESCE(SUM(valor), 0) AS total FROM saques "
            "WHERE guild_id = ? AND user_id = ? AND status IN ('na_fila', 'liberado')",
            (interaction.guild.id, alvo.id)
        )).fetchone()

    embed = criar_embed(
        f"💰 Carteira — {alvo.display_name}",
        f"**Saldo disponível:** `{formatar_moeda(saldo)}`\n"
        f"**Saques em andamento:** `{formatar_moeda(saques['total'])}` ({saques['qtd']}x)\n\n"
        f"**Últimas movimentações:**\n{extrato}",
        "Esmeralda",
        thumb=(alvo.display_avatar.url if getattr(alvo, "display_avatar", None) else None)
    )
    embed.add_field(
        name="💡 Como usar",
        value="> 💰 `/deposito` — deposita via PIX (LivePix) e vira saldo\n"
              "> 🎮 Pague o diário na hora com o saldo (botão no canal de pagamento)\n"
              "> 💸 `/saque` — saca seu saldo via PIX\n"
              "> 📤 `/transferir` — manda saldo pra outro jogador",
        inline=False
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="addsaldo", description="🛠️ Adicionar ou remover saldo de um jogador (equipe)")
@app_commands.describe(usuario="Quem vai receber (ou perder) o saldo",
                       valor="Valor (use negativo pra remover, ex: -10)",
                       motivo="Motivo (aparece no extrato e no log)")
async def cmd_addsaldo(interaction: discord.Interaction, usuario: discord.Member, valor: str,
                       motivo: Optional[str] = None):
    if not await e_staff(interaction.user):
        return await interaction.response.send_message(
            embed=criar_embed("❌ Sem Permissão", "Apenas ADM, Gerente e Dono.", "Vermelho"), ephemeral=True
        )

    quantidade = parse_valor(valor.replace("-", "") if valor else "")
    negativo = str(valor or "").strip().startswith("-")
    if quantidade is None:
        return await interaction.response.send_message(
            embed=criar_embed("❌ Valor inválido", "Use algo como `50`, `50,00` ou `-25`.", "Vermelho"), ephemeral=True
        )
    quantidade = -quantidade if negativo else quantidade
    texto_motivo = motivo or ("Ajuste manual da equipe" if not negativo else "Remoção manual da equipe")

    novo = await movimentar_saldo(usuario.id, interaction.guild.id, quantidade, "ajuste",
                                  f"{texto_motivo} — por {interaction.user.display_name}")
    if novo is None:
        return await interaction.response.send_message(
            embed=criar_embed("❌ Saldo insuficiente",
                              f"{usuario.mention} tem apenas **{formatar_moeda(await saldo_carteira(usuario.id, interaction.guild.id))}**.",
                              "Vermelho"),
            ephemeral=True
        )

    await interaction.response.send_message(
        embed=criar_embed(
            "✅ Saldo ajustado" if not negativo else "✅ Saldo removido",
            f"{usuario.mention}: `{'+' if not negativo else '−'}{formatar_moeda(abs(quantidade))}`\n"
            f"> 💼 Novo saldo: `{formatar_moeda(novo)}`\n> 📝 Motivo: {texto_motivo}",
            "Esmeralda"
        )
    )
    await registrar_log(
        interaction.guild, "💰 AJUSTE", ("💰 Saldo adicionado" if not negativo else "💰 Saldo removido"),
        f"{interaction.user.mention} {'adicionou' if not negativo else 'removeu'} "
        f"**{formatar_moeda(abs(quantidade))}** de/para {usuario.mention}.\n"
        f"> 📝 Motivo: {texto_motivo}\n> 💼 Novo saldo: `{formatar_moeda(novo)}`",
        "Verde" if not negativo else "Amarelo"
    )


@bot.tree.command(name="transferir", description="📤 Transferir saldo pra outro jogador")
@app_commands.describe(usuario="Quem vai receber", valor="Quanto transferir (ex: 10,00)")
async def cmd_transferir(interaction: discord.Interaction, usuario: discord.Member, valor: str):
    await interaction.response.defer(ephemeral=True, thinking=True)

    if usuario.id == interaction.user.id:
        return await interaction.followup.send(
            embed=criar_embed("❌ Ops", "Você não pode transferir pra você mesmo.", "Vermelho"), ephemeral=True)
    if usuario.bot:
        return await interaction.followup.send(
            embed=criar_embed("❌ Ops", "Não dá pra transferir pra um bot.", "Vermelho"), ephemeral=True)

    quantidade = parse_valor(valor)
    if quantidade is None:
        return await interaction.followup.send(
            embed=criar_embed("❌ Valor inválido", "Use algo como `10`, `10,00`.", "Vermelho"), ephemeral=True)

    sem_taxa = await debitar_saldo(interaction.user.id, interaction.guild.id, quantidade, "transferencia_enviada",
                                   f"Transferência para {usuario.display_name}")
    if sem_taxa is None:
        saldo = await saldo_carteira(interaction.user.id, interaction.guild.id)
        return await interaction.followup.send(
            embed=criar_embed("❌ Saldo insuficiente",
                              f"Você tem **{formatar_moeda(saldo)}** e tentou enviar **{formatar_moeda(quantidade)}**.",
                              "Vermelho"), ephemeral=True)

    await creditar_saldo(usuario.id, interaction.guild.id, quantidade, "transferencia_recebida",
                         f"Transferência de {interaction.user.display_name}")

    await interaction.followup.send(
        embed=criar_embed(
            "📤 Transferência feita",
            f"Você enviou **{formatar_moeda(quantidade)}** para {usuario.mention}.\n"
            f"> 💼 Seu saldo agora: `{formatar_moeda(sem_taxa)}`",
            "Esmeralda"
        ), ephemeral=True
    )
    await registrar_log(
        interaction.guild, "💸 TRANSFERÊNCIA", "📤 Transferência entre jogadores",
        f"{interaction.user.mention} → {usuario.mention}\n> 💰 Valor: `{formatar_moeda(quantidade)}`",
        "Azul"
    )


@bot.tree.command(name="deposito", description="💰 Depositar via PIX (LivePix) e virar saldo na carteira")
async def cmd_deposito(interaction: discord.Interaction):
    """Abre um ATENDIMENTO privado de depósito (jogador + suporte/gerência)."""
    if not interaction.guild:
        return await interaction.response.send_message(
            embed=criar_embed("❌ Só no servidor", "Use este comando dentro do servidor.", "Vermelho"), ephemeral=True)

    cfg = await obter_config(interaction.guild.id)
    if not livepix.configurado and not cfg.get("livepix_link") and not await e_staff(interaction.user):
        pass          # mesmo sem LivePix o atendimento abre (a equipe resolve na mão)

    try:
        await abrir_atendimento_deposito(interaction)
    except discord.Forbidden:
        await interaction.response.send_message(
            embed=criar_embed("❌ Sem permissão no servidor",
                              "Não consegui criar o canal do depósito. Avise a equipe (preciso de "
                              "**Gerenciar Canais**).", "Vermelho"), ephemeral=True)
    except Exception as erro:
        _log_arquivo(f"[DEPÓSITO] erro: {erro}")
        if not interaction.response.is_done():
            await interaction.response.send_message(
                embed=criar_embed("❌ Deu ruim", f"Não consegui abrir o atendimento: `{erro}`", "Vermelho"),
                ephemeral=True)


@bot.tree.command(name="saque", description="💸 Sacar seu saldo via PIX")
async def cmd_saque(interaction: discord.Interaction):
    if not interaction.guild:
        return await interaction.response.send_message(
            embed=criar_embed("❌ Só no servidor", "Use este comando dentro do servidor.", "Vermelho"), ephemeral=True)

    # 💼 quem tem cargo da equipe saca a CARTEIRA DE TRABALHO, e só no domingo
    cfg = await obter_config(interaction.guild.id)
    cargos_equipe = [cfg.get("cargo_dono"), cfg.get("cargo_gerente"), cfg.get("cargo_mediador"), cfg.get("cargo_suporte")]
    eh_equipe = interaction.user.guild_permissions.administrator or any(
        r.id in cargos_equipe for r in getattr(interaction.user, "roles", []) if r.id)

    tipo_carteira = "jogador"
    if eh_equipe and await saldo_trabalho(interaction.user.id, interaction.guild.id) > 0:
        tipo_carteira = "trabalho"
        dia_fechamento = int(await cfgv(interaction.guild.id, "dia_fechamento", 0))
        # domingo permitido sempre; no dia de fechamento, só depois do fechamento (00h)
        if agora_brt().weekday() != 6 and not (agora_brt().weekday() == dia_fechamento and agora_brt().hour >= 0 and dia_fechamento == 6):
            return await interaction.response.send_message(
                embed=criar_embed(
                    "💼 Carteira de trabalho",
                    f"Seu salário entra na **carteira de trabalho** e o saque é liberado **no domingo** "
                    f"(fechamento na virada da meia-noite).\n\n"
                    f"> 💰 A receber: `{formatar_moeda(await saldo_trabalho(interaction.user.id, interaction.guild.id))}`\n"
                    f"> 📅 Hoje é {['segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo'][agora_brt().weekday()]} — "
                    f"volte no domingo pra sacar! 💛",
                    "Amarelo"), ephemeral=True)

    saldo = (await saldo_trabalho(interaction.user.id, interaction.guild.id) if tipo_carteira == "trabalho"
             else await saldo_carteira(interaction.user.id, interaction.guild.id))
    minimo = float(await cfgv(interaction.guild.id, "saque_min", CARTEIRA_SAQUE_MIN))
    if saldo < minimo:
        return await interaction.response.send_message(
            embed=criar_embed(
                "💸 Saque",
                f"Seu saldo é **{formatar_moeda(saldo)}** — o saque mínimo é **{formatar_moeda(minimo)}**.\n\n"
                f"> 💰 Deposite com `/deposito`, jogue os diários ou ganhe saldo da equipe.",
                "Amarelo"), ephemeral=True)

    embed = criar_embed(
        "💸 Saque — PIX",
        f"**Disponível:** `{formatar_moeda(saldo)}`"
        + (f" *(carteira de trabalho)*" if tipo_carteira == "trabalho" else "") + "\n\n"
        f"> 🏦 Escolha o **tipo da sua chave** PIX abaixo.\n"
        f"> ⭐ Se já sacou antes, clique em **Usar minha chave salva** e é 1 toque.",
        "Esmeralda")
    await interaction.response.send_message(embed=embed, view=SaqueTipoView(saldo, tipo_carteira), ephemeral=True)


@bot.tree.command(name="extrato", description="📜 Ver o extrato completo da carteira")
@app_commands.describe(usuario="Ver o extrato de outra pessoa (equipe)", quantidade="Quantas linhas (padrão 15)")
async def cmd_extrato(interaction: discord.Interaction, usuario: Optional[discord.Member] = None,
                      quantidade: Optional[int] = 15):
    alvo = usuario or interaction.user
    if usuario and usuario.id != interaction.user.id and not await e_staff(interaction.user):
        return await interaction.response.send_message(
            embed=criar_embed("❌ Sem Permissão", "Você só pode ver o seu próprio extrato.", "Vermelho"), ephemeral=True)

    quantidade = max(1, min(int(quantidade or 15), 40))
    extrato = await extrato_texto(alvo.id, interaction.guild.id, quantidade)
    saldo = await saldo_carteira(alvo.id, interaction.guild.id)
    embed = criar_embed(f"📜 Extrato — {alvo.display_name}",
                        f"**Saldo atual:** `{formatar_moeda(saldo)}`\n\n{extrato}", "Azul")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="financeiro", description="📊 Painel financeiro da org (equipe)")
async def cmd_financeiro(interaction: discord.Interaction):
    if not await e_staff(interaction.user):
        return await interaction.response.send_message(
            embed=criar_embed("❌ Sem Permissão", "Apenas a equipe.", "Vermelho"), ephemeral=True)

    await interaction.response.defer(ephemeral=True, thinking=True)
    hoje = agora_brt().strftime("%Y-%m-%d")
    disp = await disponibilidade_saque(interaction.guild.id)
    resumo = await resumo_caixa(interaction.guild.id, hoje)
    comissoes = await resumo_comissoes_dia(interaction.guild.id, hoje)

    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        depositos_dia = await (await db.execute(
            "SELECT COUNT(*) AS qtd, COALESCE(SUM(valor), 0) AS total FROM depositos "
            "WHERE guild_id = ? AND status = 'creditado' AND criado_em LIKE ?",
            (interaction.guild.id, f"{hoje}%")
        )).fetchone()
        saques_dia = await (await db.execute(
            "SELECT COUNT(*) AS qtd, COALESCE(SUM(valor), 0) AS total FROM saques "
            "WHERE guild_id = ? AND status = 'pago' AND criado_em LIKE ?",
            (interaction.guild.id, f"{hoje}%")
        )).fetchone()
        carteiras = await (await db.execute(
            "SELECT COALESCE(SUM(saldo), 0) AS total, COUNT(*) AS qtd FROM carteira WHERE guild_id = ?",
            (interaction.guild.id,)
        )).fetchone()

    linhas_adm = "> *Nenhuma comissão hoje.*"
    if comissoes["por_adm"]:
        linhas_adm = "\n".join(
            f"> {mencao(l['staff_id'])} — `{formatar_moeda(l['total'])}` ({l['qtd']} venda(s), base `{formatar_moeda(l['base'])}`)"
            for l in comissoes["por_adm"]
        )

    embed = criar_embed(
        "📊 Financeiro da Org",
        f"**Fonte do saldo:** `{disp['fonte']}`\n"
        f"**Saldo da org:** `{formatar_moeda(disp['saldo'])}`\n"
        f"**Reserva protegida:** `{formatar_moeda(disp['reserva'])}`\n"
        f"**Livre para pagar agora:** `{formatar_moeda(disp['livre'])}`\n"
        f"**Fila de saques:** `{formatar_moeda(disp['fila'])}` ({disp['fila_qtd']}x)",
        "Dourado"
    )
    embed.add_field(
        name="📅 Hoje",
        value=f"> 🎮 Receita dos diários: `{formatar_moeda(resumo['dia_receitas'])}` ({resumo['dia_movimentos']} vaga(s))\n"
              f"> ⬆️ Depósitos: `{formatar_moeda(depositos_dia['total'])}` ({depositos_dia['qtd']}x)\n"
              f"> ⬇️ Saques pagos: `{formatar_moeda(saques_dia['total'])}` ({saques_dia['qtd']}x)\n"
              f"> 💸 Comissões: `{formatar_moeda(comissoes['total'])}` ({comissoes['vendas']} venda(s))",
        inline=False
    )
    embed.add_field(name="🏅 Comissões de hoje por ADM", value=linhas_adm, inline=False)
    embed.add_field(
        name="👛 Carteiras",
        value=f"> Saldo total dos jogadores: `{formatar_moeda(carteiras['total'])}`\n"
              f"> Jogadores com carteira: `{carteiras['qtd']}`",
        inline=False
    )
    embed.add_field(
        name="🧾 Caixa interno (histórico)",
        value=f"> Receitas: `{formatar_moeda(resumo['receitas'])}`\n"
              f"> Despesas: `{formatar_moeda(resumo['despesas'])}`\n"
              f"> Saldo: `{formatar_moeda(resumo['saldo'])}`",
        inline=False
    )
    embed.add_field(
        name="⚡ Confirmação automática",
        value="> O bot confirma PIX sozinho pela **referência do checkout** — o link do diário/depósito "
              "já nasce identificado.\n"
              "> 🔎 Use o botão abaixo só quando o pagamento veio por fora (chave/link fixo/dinheiro).",
        inline=False)
    if livepix.ultimo_erro:
        embed.add_field(name="⚠️ LivePix", value=f"> `{livepix.ultimo_erro[:180]}`", inline=False)
    await interaction.followup.send(embed=embed, ephemeral=True, view=FinanceiroAcaoView())


@bot.tree.command(name="logs", description="🧾 Configurar e ver os logs do bot (equipe)")
@app_commands.describe(acao="O que fazer", canal="Canal de logs (pra configurar)")
@app_commands.choices(acao=[
    app_commands.Choice(name="Configurar canal", value="canal"),
    app_commands.Choice(name="Canal de DEPÓSITOS (público)", value="canal_deposito"),
    app_commands.Choice(name="Canal de SAQUES (público)", value="canal_saque"),
    app_commands.Choice(name="Canal de PAGAMENTOS/vagas (público)", value="canal_pagamento"),
    app_commands.Choice(name="Ver canais configurados", value="ver_canais"),
    app_commands.Choice(name="Ver últimos eventos", value="ver"),
    app_commands.Choice(name="Testar", value="testar"),
    app_commands.Choice(name="Desligar logs", value="desligar"),
])
async def cmd_logs(interaction: discord.Interaction, acao: app_commands.Choice[str],
                   canal: Optional[discord.TextChannel] = None):
    if not await e_staff(interaction.user):
        return await interaction.response.send_message(
            embed=criar_embed("❌ Sem Permissão", "Apenas a equipe.", "Vermelho"), ephemeral=True)

    if acao.value == "canal":
        if not canal:
            return await interaction.response.send_message(
                embed=criar_embed("❌ Falta o canal", "Use `/logs acao:Configurar canal canal:#logs`.", "Vermelho"),
                ephemeral=True)
        await salvar_config(interaction.guild.id, canal_logs=canal.id)
        _CACHE_LOGS.pop(interaction.guild.id, None)
        await interaction.response.send_message(
            embed=criar_embed("✅ Logs ativados", f"Todos os eventos vão aparecer em {canal.mention}.", "Esmeralda"),
            ephemeral=True)
        await registrar_log(interaction.guild, "⚙️ CONFIG", "🧾 Canal de logs configurado",
                            f"Os registros passam a sair em {canal.mention}.\n"
                            f"> Comandos: aprovações, comissões, depósitos, saques, transferências, ajustes.",
                            "Azul")
        return

    if acao.value in ("canal_deposito", "canal_saque", "canal_pagamento"):
        if not canal:
            return await interaction.response.send_message(
                embed=criar_embed("❌ Falta o canal",
                                  f"Use `/logs acao:{acao.name} canal:#seu-canal`.", "Vermelho"), ephemeral=True)
        chave = {"canal_deposito": "canal_log_deposito", "canal_saque": "canal_log_saque",
                 "canal_pagamento": "canal_log_pagamento"}[acao.value]
        await salvar_config(interaction.guild.id, **{chave: canal.id})
        await interaction.response.send_message(
            embed=criar_embed("✅ Canal configurado",
                              f"Os anúncios de **{acao.name.split(' ')[2].strip('()').lower()}** vão sair em "
                              f"{canal.mention}.\n\n"
                              f"> 🔒 A chave PIX sai **mascarada** aqui (ex.: `jo***@pix.com`) — "
                              f"o canal de logs da equipe continua com os dados completos.\n"
                              f"> 💛 Use `/logs acao:Testar` pra ver como fica.", "Esmeralda"), ephemeral=True)
        await registrar_log(interaction.guild, "⚙️ CONFIG", "📢 Canal público configurado",
                            f"{acao.name} → {canal.mention}", "Azul")
        return

    if acao.value == "ver_canais":
        cfg = await obter_config(interaction.guild.id)
        def _mostrar(canal_id):
            return f"<#{int(canal_id)}>" if canal_id else "*(não configurado)*"
        return await interaction.response.send_message(
            embed=criar_embed(
                "🧾 Canais de log",
                f"> 🧾 **Geral (equipe):** {_mostrar(cfg.get('canal_logs'))}\n"
                f"> 🎧 **Atendimento:** {_mostrar(cfg.get('canal_logs_suporte'))}\n"
                f"> 💰 **Depósitos (público):** {_mostrar(cfg.get('canal_log_deposito'))}\n"
                f"> 💸 **Saques (público):** {_mostrar(cfg.get('canal_log_saque'))}\n"
                f"> 🎮 **Pagamentos/vagas (público):** {_mostrar(cfg.get('canal_log_pagamento'))}\n\n"
                f"> 💡 Os públicos mostram os anúncios **com a chave mascarada**; o geral guarda tudo.\n"
                f"> Sem canal público configurado, os avisos continuam só no geral.",
                "Azul"), ephemeral=True)

    if acao.value == "desligar":
        await salvar_config(interaction.guild.id, canal_logs=None)
        _CACHE_LOGS.pop(interaction.guild.id, None)
        return await interaction.response.send_message(
            embed=criar_embed("🔕 Logs desligados", "Os eventos continuam sendo gravados em `fireforce.log`.", "Amarelo"),
            ephemeral=True)

    if acao.value == "testar":
        await registrar_log(interaction.guild, "🧪 TESTE", "🧪 Teste de log",
                            f"Se você está vendo isso, os logs estão funcionando! ({interaction.user.mention})", "Azul")
        return await interaction.response.send_message(
            embed=criar_embed("🧪 Enviado", "Mandei um evento de teste no canal de logs.", "Azul"), ephemeral=True)

    # ver: mostra as últimas linhas do arquivo
    try:
        with open(ARQUIVO_LOG, "r", encoding="utf-8") as arquivo:
            linhas = arquivo.readlines()[-12:]
        texto = "".join(linhas).strip() or "Nada registrado ainda."
    except Exception:
        texto = "Nada registrado ainda."
    trecho = texto[-1800:]
    await interaction.response.send_message(
        embed=criar_embed("🧾 Últimos eventos", f"```\n{trecho}\n```", "Cinza Escuro"), ephemeral=True)


@bot.tree.command(name="saude", description="🩺 Como está o bot agora: no ar, LivePix, Supabase e pendências")
async def cmd_saude(interaction: discord.Interaction):
    if not interaction.guild:
        return await interaction.response.send_message(
            embed=criar_embed("❌ Só no servidor", "Use este comando dentro do servidor.", "Vermelho"),
            ephemeral=True)
    if not await e_staff(interaction.user):
        return await interaction.response.send_message(
            embed=criar_embed("❌ Sem Permissão", "Apenas a equipe.", "Vermelho"), ephemeral=True)

    await interaction.response.defer(ephemeral=True, thinking=True)
    gid = interaction.guild.id
    fora = await tempo_fora()
    pend = await _pendencias(gid)
    disp = await disponibilidade_saque(gid)

    def _ha(quando: float) -> str:
        return f"há {int(time.time() - quando)}s" if quando else "ainda não"

    embed = criar_embed("🩺 Bot em forma?", "", "Esmeralda" if not fora else "Amarelo")
    embed.add_field(
        name="🟢 No ar",
        value=f"> Ligado {_ha_iso(INICIADO_EM.isoformat())} "
              f"({_tempo_texto(int((agora_brt() - INICIADO_EM).total_seconds() // 60))} rodando)\n"
              f"> Último pulso (prova de vida): {await _ha_iso(await _meta_ler('ultimo_pulso'))}",
        inline=False)
    embed.add_field(
        name="⚡ LivePix",
        value=(f"> {'✅ configurada' if livepix.configurado else '❌ não configurada'}\n"
               f"> Última varredura de pagamentos: {await _ha_iso(await _meta_ler('ultima_varredura'))}"
               + (f"\n> ⚠️ Último aviso: `{str(livepix.ultimo_erro)[:110]}`"
                  if getattr(livepix, "ultimo_erro", "") else "")),
        inline=False)
    embed.add_field(
        name="☁️ Supabase",
        value=(f"> {'✅ configurado' if supabase_configurado() else '❌ não configurado'}\n"
               f"> Backup completo: {_ha(_sync_ultimo)}\n"
               f"> Tempo real (config/rankings): {_ha(_sql_ultimo)}"
               + (f"\n> ⚠️ Último erro: `{str(_sync_erro or _sql_erro)[:110]}`"
                  if (_sync_erro or _sql_erro) else "")),
        inline=False)
    embed.add_field(
        name="📋 Esperando alguém",
        value=(f"> 💰 Depósitos na janela: `{pend['depositos']}` "
               f"({formatar_moeda(pend['depositos_valor'])})\n"
               f"> 🎮 Reservas sem pagamento: `{pend['reservas']}`\n"
               f"> 💸 Saques aguardando (fila/liberado): `{pend['saques']}` "
               f"({formatar_moeda(pend['saques_valor'])})\n"
               f"> 🎧 Tickets abertos: `{pend['tickets']}`"),
        inline=False)
    embed.add_field(
        name="💼 Caixa e fila de pagamento",
        value=(f"> Saldo (fonte: {disp['fonte']}): `{formatar_moeda(disp['saldo'])}`\n"
               f"> Reserva protegida: `{formatar_moeda(disp['reserva'])}`\n"
               f"> Livre pra pagar agora: `{formatar_moeda(disp['livre'])}` • "
               f"Fila: `{formatar_moeda(disp['fila'])}` ({disp['fila_qtd']})"),
        inline=False)
    embed.set_footer(text="🔥 Fire Force • Se algo parecer travado, reinicie: na volta o bot "
                          "reconfere a LivePix sozinho (janela esticada pelo tempo que ficou fora)")
    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="config", description="⚙️ Ajustes financeiros, canais de log e rodízio da equipe")
@app_commands.describe(link_livepix="Link fixo de pagamento da LivePix",
                       reserva="Reserva mínima protegida (padrão 200)",
                       comissao="% de comissão do ADM (padrão 25)",
                       saque_min="Saque mínimo (padrão 5)",
                       deposito_min="Depósito mínimo (padrão 1)",
                       janela="Minutos da confirmação automática (padrão 5)",
                       canal_logs="Canal de logs geral (pagamentos, depósitos, saques)",
                       canal_logs_suporte="Canal de logs do atendimento (tickets e avaliações)",
                       canal_cupons="Canal que anuncia os cupons automaticamente",
                       canal_eventos="Canal que anuncia os eventos",
                       canal_rankings="Canal do painel de rankings",
                       dia_fechamento="Dia do fechamento semanal da equipe")
@app_commands.choices(dia_fechamento=[
    app_commands.Choice(name="Domingo (recomendado)", value=6),
    app_commands.Choice(name="Segunda", value=0),
    app_commands.Choice(name="Sexta", value=4),
])
async def cmd_config(interaction: discord.Interaction,
                     link_livepix: Optional[str] = None, reserva: Optional[str] = None,
                     comissao: Optional[str] = None, saque_min: Optional[str] = None,
                     deposito_min: Optional[str] = None, janela: Optional[int] = None,
                     canal_logs: Optional[discord.TextChannel] = None,
                     canal_logs_suporte: Optional[discord.TextChannel] = None,
                     canal_cupons: Optional[discord.TextChannel] = None,
                     canal_eventos: Optional[discord.TextChannel] = None,
                     canal_rankings: Optional[discord.TextChannel] = None,
                     dia_fechamento: Optional[app_commands.Choice[int]] = None):
    if not await e_dono_ou_gerente(interaction.user):
        return await interaction.response.send_message(
            embed=criar_embed("❌ Sem Permissão", "Apenas Dono e Gerente.", "Vermelho"), ephemeral=True)

    mudancas, erros, novos = [], [], {}

    if link_livepix is not None:
        novos["livepix_link"] = link_livepix.strip()
        mudancas.append(f"> 🔗 Link LivePix: `{link_livepix.strip()[:80]}`")
    for nome_campo, valor, chave in (("Reserva", reserva, "reserva"), ("Comissão %", comissao, "comissao_pct"),
                                     ("Saque mínimo", saque_min, "saque_min"),
                                     ("Depósito mínimo", deposito_min, "deposito_min")):
        if valor is None:
            continue
        numero = parse_valor(str(valor).replace("%", ""))
        if numero is None:
            erros.append(f"> ⚠️ {nome_campo}: valor inválido")
            continue
        novos[chave] = numero
        mudancas.append(f"> {nome_campo}: `{numero}`")
    if janela is not None:
        novos["janela_min"] = max(1, min(int(janela), 60))
        mudancas.append(f"> ⏱️ Janela de confirmação: `{novos['janela_min']} min`")
    for nome_campo, canal, chave in (("Logs gerais", canal_logs, "canal_logs"),
                                     ("Logs do atendimento", canal_logs_suporte, "canal_logs_suporte"),
                                     ("Canal de cupons", canal_cupons, "canal_cupons"),
                                     ("Canal de eventos", canal_eventos, "canal_eventos"),
                                     ("Canal de rankings", canal_rankings, "canal_rankings")):
        if canal is not None:
            novos[chave] = canal.id
            _CACHE_LOGS.pop(interaction.guild.id, None)
            mudancas.append(f"> 🧾 {nome_campo}: {canal.mention}")
    if dia_fechamento is not None:
        novos["dia_fechamento"] = int(dia_fechamento.value)
        dias = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
        mudancas.append(f"> 📅 Fechamento semanal da equipe: **{dias[int(dia_fechamento.value)]}** à meia-noite")

    if not novos and not erros:
        cfg = await obter_config(interaction.guild.id)

        def _canal(valor):
            return f"<#{valor}>" if valor else "`não definido`"

        dias = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
        embed = criar_embed(
            "⚙️ Configuração atual",
            f"> 🔗 Link LivePix: `{cfg.get('livepix_link') or 'não definido'}`\n"
            f"> 🏦 Reserva: `{formatar_moeda(await cfgv(interaction.guild.id, 'reserva', CARTEIRA_RESERVA))}`\n"
            f"> 💸 Comissão: `{await cfgv(interaction.guild.id, 'comissao_pct', CARTEIRA_COMISSAO_PCT)}%`\n"
            f"> 💸 Saque mínimo: `{formatar_moeda(await cfgv(interaction.guild.id, 'saque_min', CARTEIRA_SAQUE_MIN))}`\n"
            f"> 💰 Depósito mínimo: `{formatar_moeda(await cfgv(interaction.guild.id, 'deposito_min', CARTEIRA_DEPOSITO_MIN))}`\n"
            f"> ⏱️ Janela de confirmação: `{await cfgv(interaction.guild.id, 'janela_min', CARTEIRA_JANELA_MIN)} min`\n"
            f"> 🧾 Logs gerais: {_canal(cfg.get('canal_logs'))}\n"
            f"> 🎧 Logs do atendimento: {_canal(cfg.get('canal_logs_suporte'))}\n"
            f"> 🎟️ Canal de cupons: {_canal(cfg.get('canal_cupons'))}\n"
            f"> 🎉 Canal de eventos: {_canal(cfg.get('canal_eventos'))}\n"
            f"> 🏆 Canal de rankings: {_canal(cfg.get('canal_rankings'))}\n"
            f"> 📅 Fechamento da equipe: `{dias[int(await cfgv(interaction.guild.id, 'dia_fechamento', 0))]}` à meia-noite\n"
            f"> 💳 LivePix API: `{'conectada' if livepix.configurado else 'sem credenciais (modo manual)'}`\n"
            f"> ☁️ Supabase: `{'conectado' if supabase_configurado() else 'não configurado'}`",
            "Azul")
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    if novos:
        await salvar_config(interaction.guild.id, **novos)
        marcar_sujo()
    await interaction.response.send_message(
        embed=criar_embed("⚙️ Config atualizada", "\n".join(mudancas + erros) or "> Nada mudou.", "Esmeralda"),
        ephemeral=True)
    if novos:
        await registrar_log(interaction.guild, "⚙️ CONFIG", "⚙️ Configuração alterada",
                            f"Por {interaction.user.mention}\n" + "\n".join(mudancas), "Azul")


# ══════════════════════════════════════════════════════════════
#  💸 FILA DE PAGAMENTO — o máximo de automação que a LivePix permite
#
#  A API pública da LivePix NÃO tem envio de PIX (não existe cash-out).
#  Então o bot faz TODAS as partes que dão pra fazer sozinho e deixa pro
#  humano só o que é impossível sem API: apertar o botão no banco.
#
#   1) o bot publica e MANTÉM ATUALIZADO o painel da fila no canal de
#      logs: quanto retirar da LivePix + cada PIX pronto (chave copiável);
#   2) quando a retirada da LivePix aparece no extrato, o bot reconhece
#      (inclusive quando o valor é a SOMA de vários saques) e avisa:
#      "o dinheiro já saiu da LivePix — agora é só mandar os PIX";
#   3) cada saque fecha com 1 toque, ou digitando os protocolos de uma
#      vez ("12, 14, 15") ou "todos";
#   4) saque parado não fica esquecido: a equipe é cobrada sozinha.
# ══════════════════════════════════════════════════════════════

FILA_LEMBRETE_MIN = int(os.getenv("FILA_LEMBRETE_MIN", "20"))     # cobra a equipe depois disso
FILA_ESPERA_MIN = int(os.getenv("FILA_ESPERA_MIN", "60"))         # lembrete da fila sem caixa
FILA_MAXIMO_LISTA = 24
FILA_SALDO_TTL = 60

_fila_assinatura = {}
_fila_lembrete = {}
_fila_espera_aviso = 0.0
_saldo_livepix_cache = {"quando": 0.0, "valor": None}


async def _meta_ler(chave: str) -> str:
    try:
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            linha = await (await db.execute("SELECT valor FROM sync_meta WHERE chave = ?",
                                            (str(chave),))).fetchone()
        return (linha["valor"] if linha else "") or ""
    except Exception:
        return ""


async def _meta_gravar(chave: str, valor: str):
    try:
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute("INSERT OR REPLACE INTO sync_meta (chave, valor) VALUES (?, ?)",
                             (str(chave), str(valor)))
            await db.commit()
    except Exception:
        pass


async def saldo_livepix_cache(ttl: float = FILA_SALDO_TTL) -> Optional[float]:
    """Saldo da carteira LivePix com cache curto (a API tem limite de consultas)."""
    agora = time.time()
    if _saldo_livepix_cache["valor"] is not None and (agora - _saldo_livepix_cache["quando"]) < ttl:
        return _saldo_livepix_cache["valor"]
    if not livepix.configurado:
        return None
    valor = await livepix.saldo()
    if valor is not None:
        _saldo_livepix_cache["quando"] = agora
        _saldo_livepix_cache["valor"] = valor
    return valor


async def saques_disponiveis(guild_id: int) -> dict:
    """Saques prontos pra pagar (liberado) e os que esperam o caixa (na_fila)."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        linhas = await (await db.execute(
            "SELECT * FROM saques WHERE guild_id = ? AND status IN ('liberado', 'na_fila') "
            "ORDER BY CASE status WHEN 'liberado' THEN 0 ELSE 1 END, id",
            (guild_id,))).fetchall()
    prontos = [dict(l) for l in linhas if l["status"] == "liberado"]
    espera = [dict(l) for l in linhas if l["status"] != "liberado"]
    return {
        "prontos": prontos, "espera": espera,
        "total_prontos": arredondar(sum(arredondar(s["valor"]) for s in prontos)),
        "total_espera": arredondar(sum(arredondar(s["valor"]) for s in espera)),
    }


async def resumo_abastecimento(guild_id: int) -> dict:
    """Tudo que a equipe precisa saber pra pagar: o que tirar da LivePix e o que falta."""
    cfg = await obter_config(guild_id)
    reserva = arredondar(cfg.get("reserva") if cfg.get("reserva") is not None else CARTEIRA_RESERVA)
    fila = await saques_disponiveis(guild_id)
    saldo = await saldo_livepix_cache()
    livre = None if saldo is None else arredondar(saldo - reserva)
    falta = None if livre is None else arredondar(max(0.0, fila["total_prontos"] - livre))
    return {"reserva": reserva, "saldo": saldo, "livre": livre, "falta": falta, **fila}


def texto_lote(resumo: dict, maximo: int = FILA_MAXIMO_LISTA) -> str:
    """O roteiro de pagamento: 1 linha de retirada + 1 linha por PIX."""
    prontos = resumo.get("prontos") or []
    if not prontos:
        return ("> ✅ **Nenhum saque esperando pagamento agora.**\n"
                "> 👑 Quando tiver, o bot avisa **dono e gerente** e monta o roteiro aqui — e o jogador "
                "já sabe que o prazo vai de **1 minuto a 24 horas ou mais**.")

    linhas = [
        f"**1️⃣ Retire `{formatar_moeda(resumo['total_prontos'])}` da LivePix** pro seu PIX "
        f"({LIVEPIX_PAINEL}) — 1 saque só, o valor já é o da fila inteira."
    ]
    if resumo.get("saldo") is not None:
        linhas.append(f"> 🏦 **Carteira LivePix agora:** `{formatar_moeda(resumo['saldo'])}` "
                      f"• reserva protegida `{formatar_moeda(resumo['reserva'])}`")
        if resumo.get("falta"):
            linhas.append(f"> ⚠️ Faltam `{formatar_moeda(resumo['falta'])}` de saldo pra cobrir a fila toda — "
                          f"o que já tem, dá pra pagar.")
    linhas.append("**2️⃣ Mande os PIX abaixo no app do banco** (toque no código pra copiar a chave):")
    for saque in prontos[:maximo]:
        equipe = " • 💼 equipe" if (saque.get("tipo") or "jogador") == "trabalho" else ""
        pago_no_extrato = " • 💵 já saiu da LivePix" if saque.get("retirada_em") else ""
        linhas.append(
            f"> `#{saque['id']}` • **{formatar_moeda(saque['valor'])}** • chave `{saque['chave_pix']}` "
            f"• {(saque.get('titular') or 'sem titular')[:40]}{equipe}{pago_no_extrato}")
    if len(prontos) > maximo:
        linhas.append(f"> … e mais **{len(prontos) - maximo}** saque(s) na fila.")
    linhas.append("**3️⃣ Marque como pago** no botão **✅ Marcar pagos** aqui embaixo — pode digitar vários "
                  "protocolos de uma vez (`12, 14, 15`) ou `todos`. O jogador é avisado na hora. 💛")
    linhas.append("> 👑 **Pagam: dono e gerente** (só quem tem acesso à conta). ⏱️ O jogador já sabe que "
                  "pode levar de **1 minuto a 24 horas ou mais**, conforme quem estiver disponível — "
                  "o bot cobra a equipe sozinho a cada " + str(FILA_LEMBRETE_MIN) + " min até sair.")
    return "\n".join(linhas)


def _embed_fila(resumo: dict, cor: str = "Amarelo") -> discord.Embed:
    descricao = texto_lote(resumo)
    if len(descricao) > 3900:
        descricao = descricao[:3890] + "\n> *…lista cortada, use `/payout` pra ver tudo.*"
    embed = criar_embed("💸 FILA DE PAGAMENTO — LivePix", descricao, cor)
    if resumo.get("espera"):
        embed.add_field(
            name=f"🤝 Esperando o caixa ({len(resumo['espera'])})",
            value=f"> `{formatar_moeda(resumo['total_espera'])}` em saques entram na fila de pagamento "
                  f"**sozinhos** assim que o saldo liberar — ninguém precisa pedir de novo.", inline=False)
    embed.set_footer(text="🔥 Fire Force • o bot confere o extrato da LivePix a cada 25s")
    return embed


async def publicar_painel_fila(guild, forcar: bool = False) -> Optional[int]:
    """Cria (1x) e mantém atualizado o painel da fila no canal de logs."""
    if not guild:
        return None
    canal_id = await canal_de_logs(guild.id)
    if not canal_id:
        return None
    canal = guild.get_channel(int(canal_id))
    if not canal:
        return None

    resumo = await resumo_abastecimento(guild.id)
    chave_meta = f"painel_fila:{guild.id}"
    mensagem = None
    guardado = await _meta_ler(chave_meta)
    if guardado and not forcar:
        try:
            canal_antigo, msg_id = str(guardado).split(":", 1)
            alvo = guild.get_channel(int(canal_antigo)) or canal
            mensagem = await alvo.fetch_message(int(msg_id))
        except Exception:
            mensagem = None

    embed = _embed_fila(resumo)
    try:
        if mensagem:
            await mensagem.edit(embed=embed)
            return mensagem.id
        nova = await canal.send(embed=embed, view=FilaPagamentoView())
    except Exception as erro:
        _log_arquivo(f"[FILA] painel: {erro}")
        return None
    await _meta_gravar(chave_meta, f"{canal.id}:{nova.id}")
    return nova.id


async def avisar_equipe(guild, texto: str, tipo: str = "💸 FILA") -> None:
    """Avisa quem manda no financeiro (dono + gerente + mediador) no canal de logs."""
    if not guild:
        return
    cfg = await obter_config(guild.id)
    marcas = [f"<@&{cfg.get('cargo_dono')}>" if cfg.get("cargo_dono") else "",
              f"<@&{cfg.get('cargo_gerente')}>" if cfg.get("cargo_gerente") else ""]
    marcas = [m for m in marcas if m]
    canal_id = await canal_de_logs(guild.id)
    canal = guild.get_channel(int(canal_id)) if canal_id else None
    if not canal:
        return
    try:
        await canal.send(content=" ".join(marcas)[:180], embed=criar_embed("⏰ FILA DE PAGAMENTO", texto, "Vermelho"))
    except Exception:
        pass
    await registrar_log(guild, tipo, "⏰ Cobrança automática da fila", texto, "Vermelho")


class FilaPagoModal(discord.ui.Modal, title="✅ Marcar saques como pagos"):
    campo = discord.ui.TextInput(
        label="Protocolos pagos (ex: 12, 14, 15) ou 'todos'",
        placeholder="Só os que você JÁ mandou o PIX", required=True, max_length=200)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        texto = str(self.campo.value or "").lower().strip()
        resumo = await saques_disponiveis(interaction.guild.id)
        if not resumo["prontos"]:
            return await interaction.followup.send(
                embed=criar_embed("ℹ️ Nada pra pagar", "Não tem saque liberado esperando pagamento agora.",
                                  "Amarelo"), ephemeral=True)

        if "todos" in texto or "all" in texto:
            escolhidos = list(resumo["prontos"])
        else:
            numeros = {int(parte) for parte in re.findall(r"\d{1,7}", texto)}
            escolhidos = [s for s in resumo["prontos"] if int(s["id"]) in numeros]

        if not escolhidos:
            return await interaction.followup.send(
                embed=criar_embed("❌ Nenhum protocolo encontrado",
                                  f"> Prontos pra pagar: " + ", ".join(f"`#{s['id']}`" for s in resumo["prontos"][:20])
                                  + "\n\n> Digite só os números, ex: `12, 14, 15` — ou `todos`.",
                                  "Vermelho"), ephemeral=True)

        total, fechados = 0.0, []
        for saque in escolhidos:
            if await concluir_saque(saque["id"], interaction.user.id, "pagamento marcado no painel da fila"):
                total = arredondar(total + arredondar(saque["valor"]))
                fechados.append(f"`#{saque['id']}`")
        embed = criar_embed(
            "✅ Saques pagos",
            f"**{len(fechados)}** saque(s) fechado(s) como pagos — total `{formatar_moeda(total)}`.\n\n"
            f"> {', '.join(fechados)}\n"
            f"> Os jogadores já receberam a confirmação e o log de saque pago. 💛",
            "Esmeralda")
        await interaction.followup.send(embed=embed, ephemeral=True)
        await publicar_painel_fila(interaction.guild)


class FilaPagamentoView(discord.ui.View):
    """Botões fixos do painel da fila (funcionam depois de qualquer restart)."""

    def __init__(self):
        super().__init__(timeout=None)
        self.scan.custom_id = "ff_fila_scan"
        self.atualizar.custom_id = "ff_fila_atualizar"
        self.marcar.custom_id = "ff_fila_marcar"
        self.cobrar.custom_id = "ff_fila_cobrar"

    async def _permissao(self, interaction: discord.Interaction) -> bool:
        if await e_staff(interaction.user):
            return True
        await interaction.response.send_message(
            embed=criar_embed("❌ Sem Permissão", "Apenas a equipe financeira (dono/gerente/mediador).",
                              "Vermelho"), ephemeral=True)
        return False

    @discord.ui.button(label="Procurar pagamento agora", style=discord.ButtonStyle.blurple, emoji="🎯")
    async def scan(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._permissao(interaction):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        resultado = await casar_pagamentos_livepix(interaction.guild.id)
        resumo = await resumo_abastecimento(interaction.guild.id)
        await publicar_painel_fila(interaction.guild)
        await interaction.followup.send(
            embed=criar_embed(
                "🎯 Varredura feita",
                f"> Pagamentos casados agora: **{resultado['depositos']}** depósito(s), "
                f"**{resultado['reservas']}** vaga(s), **{resultado['ref']}** por referência.\n"
                f"> Retiradas da LivePix reconhecidas: **{resultado['saques']}**.\n"
                f"> Fila pronta pra pagar: `{formatar_moeda(resumo['total_prontos'])}` "
                f"({len(resumo['prontos'])}x)"
                + (f"\n> ⚠️ {resultado['erro'][:120]}" if resultado.get("erro") else ""),
                "Azul"), ephemeral=True)

    @discord.ui.button(label="Atualizar painel", style=discord.ButtonStyle.gray, emoji="🔄")
    async def atualizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._permissao(interaction):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        resumo = await resumo_abastecimento(interaction.guild.id)
        try:
            await interaction.message.edit(embed=_embed_fila(resumo))
        except Exception:
            pass
        await publicar_painel_fila(interaction.guild)
        await interaction.followup.send(
            embed=criar_embed("🔄 Painel atualizado",
                              f"> Fila pronta: `{formatar_moeda(resumo['total_prontos'])}` "
                              f"({len(resumo['prontos'])}x) • esperando caixa: "
                              f"`{formatar_moeda(resumo['total_espera'])}` ({len(resumo['espera'])}x)",
                              "Azul"), ephemeral=True)

    @discord.ui.button(label="Marcar pagos", style=discord.ButtonStyle.green, emoji="✅")
    async def marcar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._permissao(interaction):
            return
        await interaction.response.send_modal(FilaPagoModal())

    @discord.ui.button(label="Lembrar equipe", style=discord.ButtonStyle.gray, emoji="🔔")
    async def cobrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._permissao(interaction):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        resumo = await resumo_abastecimento(interaction.guild.id)
        if not resumo["prontos"] and not resumo["espera"]:
            return await interaction.followup.send(
                embed=criar_embed("✅ Fila vazia", "Não tem saque esperando nada. Tudo em dia! 💛", "Esmeralda"),
                ephemeral=True)
        await avisar_equipe(
            interaction.guild,
            f"Fila de pagamento pedida por {mencao(interaction.user.id)}.\n\n" + texto_lote(resumo, 8))
        await interaction.followup.send(
            embed=criar_embed("🔔 Equipe avisada", "Mandei o lote no canal de logs.", "Esmeralda"), ephemeral=True)


# ---------- RETIRADA DA LIVEPIX (o que dá pra detectar sozinho) ----------

def _centavos_transacao(transacao: dict) -> int:
    try:
        return int(round(float(transacao.get("amount") or 0)))
    except Exception:
        return 0


def _subconjunto_centavos(alvo: int, saques: list, tolerancia: int = 2) -> list:
    """Acha quais saques somam exatamente o valor retirado (retirada em lote)."""
    if len(saques) > 22 or alvo <= 0:
        return []
    estado = {0: []}
    for saque in sorted(saques, key=lambda s: arredondar(s["valor"]), reverse=True):
        centavos = int(round(arredondar(saque["valor"]) * 100))
        novos = {}
        for soma, itens in list(estado.items()):
            nova = soma + centavos
            if nova > alvo + tolerancia or nova in estado or nova in novos:
                continue
            novos[nova] = itens + [saque]
        estado.update(novos)
        if len(estado) > 400000:
            return []
        for soma, itens in estado.items():
            if itens and abs(soma - alvo) <= tolerancia:
                return itens
    return []


async def detectar_retirada_livepix(guild_id: int, limite: int = LIVEPIX_PAGAMENTOS_LIMITE) -> int:
    """Olha o extrato da carteira e reconhece a RETIRADA do dinheiro da LivePix.

    • valor igual ao de 1 saque          → reconhece
    • valor igual à SOMA de vários saques → reconhece (retirada em lote)

    Importante: retirar da LivePix manda o dinheiro pro SEU PIX (mesmo CPF),
    então isto NÃO fecha o saque do jogador — marca os saques como
    "💵 já saiu da LivePix" e avisa a equipe que agora é só mandar os PIX.
    """
    if not livepix.configurado:
        return 0
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        em_aberto = [dict(l) for l in await (await db.execute(
            "SELECT * FROM saques WHERE guild_id = ? AND status = 'liberado'", (guild_id,))).fetchall()]
    if not em_aberto:
        return 0

    transacoes = await livepix.transacoes(limite)
    if not transacoes:
        return 0
    guild = bot.get_guild(guild_id)
    reconhecidas = 0
    pendentes = list(em_aberto)

    ordenadas = sorted(transacoes, key=lambda t: float(t.get("timestamp") or 0), reverse=True)
    for transacao in ordenadas:
        centavos = _centavos_transacao(transacao)
        if centavos >= 0:
            continue                     # só DÉBITO (retirada) interessa
        prova = f"tx:{transacao.get('proof') or transacao.get('timestamp')}"
        if await _ja_visto(prova, "saque"):
            continue
        quandotransacao = None
        try:
            quandotransacao = datetime.datetime.fromtimestamp(float(transacao.get("timestamp") or 0), TZ_BRASILIA)
        except Exception:
            pass

        alvos = []
        for saque in pendentes:
            if abs(centavos + int(round(arredondar(saque["valor"]) * 100))) <= 2:
                if quandotransacao is None or _transacao_depois_do_saque(quandotransacao, saque):
                    alvos = [saque]
                    break
        if not alvos:
            candidatos = [s for s in pendentes
                          if quandotransacao is None or _transacao_depois_do_saque(quandotransacao, s)]
            alvos = _subconjunto_centavos(abs(centavos), candidatos)
        if not alvos:
            continue

        agora_texto = agora_brt().isoformat()
        async with aiosqlite.connect(DATABASE_FILE) as db:
            for saque in alvos:
                await db.execute("UPDATE saques SET retirada_em = ?, retirada_prova = ? WHERE id = ?",
                                 (agora_texto, str(transacao.get("proof") or ""), saque["id"]))
                pendentes.remove(saque)
            await db.commit()
        marcar_sujo()
        reconhecidas += len(alvos)
        if guild:
            total = arredondar(sum(arredondar(s["valor"]) for s in alvos))
            lista = ", ".join(f"`#{s['id']}` ({formatar_moeda(s['valor'])})" for s in alvos)
            await registrar_log(
                guild, "💸 SAQUE", "💵 Dinheiro saiu da LivePix — pague os PIX",
                f"Retirada de **{formatar_moeda(abs(centavos) / 100.0)}** reconhecida no extrato da LivePix"
                + (f" e bate com {len(alvos)} saque(s): {lista}" if len(alvos) > 1 else f" — saque {lista}")
                + ".\n> O dinheiro está na sua conta: agora é só mandar o PIX pra cada chave abaixo e marcar "
                  "**✅ Marcar pagos** no painel da fila.",
                "Amarelo")
            await avisar_equipe(
                guild,
                f"💵 O bot viu a retirada de **{formatar_moeda(abs(centavos) / 100.0)}** no extrato da LivePix "
                f"({len(alvos)} saque(s) da fila).\n> Mande os PIX e marque como pagos no painel — "
                f"fila pronta: `{formatar_moeda(await _total_prontos(guild_id))}`.", "💵 RETIRADA")
    return reconhecidas


def _transacao_depois_do_saque(quando: datetime.datetime, saque) -> bool:
    """A retirada não pode ser anterior ao pedido de saque (com 5 min de folga)."""
    try:
        criado = datetime.datetime.fromisoformat(saque["criado_em"])
        if criado.tzinfo is None:
            criado = criado.replace(tzinfo=TZ_BRASILIA)
        return quando >= criado - datetime.timedelta(minutes=5)
    except Exception:
        return True


async def _total_prontos(guild_id: int) -> float:
    return (await saques_disponiveis(guild_id))["total_prontos"]


# ---------- LOOP DA FILA: painel sempre atualizado + cobrança automática ----------

def _assinatura_fila(resumo: dict) -> str:
    partes = [f"{s['id']}:{arredondar(s['valor'])}:{1 if s.get('retirada_em') else 0}" for s in resumo["prontos"]]
    return "|".join(partes) + f"//{len(resumo['espera'])}"


async def loop_fila_pagamento():
    """A cada 25s: mantém o painel da fila atualizado e cobra a equipe quando
    algum saque fica parado. Nada aqui precisa de clique de ninguém."""
    global _fila_espera_aviso
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            for guild in list(bot.guilds):
                try:
                    resumo = await saques_disponiveis(guild.id)
                except Exception:
                    continue
                if not resumo["prontos"] and not resumo["espera"]:
                    _fila_assinatura.pop(guild.id, None)
                    _fila_lembrete.clear()
                    continue

                assinatura = _assinatura_fila(resumo)
                if _fila_assinatura.get(guild.id) != assinatura:
                    _fila_assinatura[guild.id] = assinatura
                    await publicar_painel_fila(guild)

                # saque parado sem pagamento → cobra a equipe (1x por janela)
                agora = agora_brt()
                parados = []
                for saque in resumo["prontos"]:
                    try:
                        criado = datetime.datetime.fromisoformat(saque["criado_em"])
                        if criado.tzinfo is None:
                            criado = criado.replace(tzinfo=TZ_BRASILIA)
                        minutos = (agora - criado).total_seconds() / 60.0
                    except Exception:
                        continue
                    if minutos < FILA_LEMBRETE_MIN:
                        continue
                    ultimo = _fila_lembrete.get(saque["id"], 0.0)
                    if (time.time() - ultimo) < FILA_LEMBRETE_MIN * 60:
                        continue
                    _fila_lembrete[saque["id"]] = time.time()
                    parados.append((saque, int(minutos)))
                if parados:
                    lista = "\n".join(f"> `#{s['id']}` • **{formatar_moeda(s['valor'])}** • chave "
                                      f"`{s['chave_pix']}` • esperando há **{m} min** — {mencao(s['user_id'])}"
                                      for s, m in parados[:8])
                    await avisar_equipe(
                        guild,
                        f"**{len(parados)} saque(s)** liberado(s) e ainda não pagos.\n\n{lista}\n\n"
                        f"> Total da fila: `{formatar_moeda(resumo['total_prontos'])}` • "
                        f"use **✅ Marcar pagos** no painel da fila.\n"
                        f"> 👑 Só **dono e gerente** conseguem pagar (acesso à conta) — quem estiver "
                        f"disponível resolve; o jogador já foi avisado do prazo (1 min a 24h+).",
                        "⏰ SAQUE")

                # fila esperando caixa → lembra de quanto falta (1x por hora)
                if resumo["espera"] and (time.time() - _fila_espera_aviso) > FILA_ESPERA_MIN * 60:
                    _fila_espera_aviso = time.time()
                    await avisar_equipe(
                        guild,
                        f"Tem `{formatar_moeda(resumo['total_espera'])}` em "
                        f"**{len(resumo['espera'])} saque(s)** esperando o caixa liberar.\n"
                        f"> Eles entram na fila de pagamento sozinhos assim que o saldo permitir — "
                        f"ninguém precisa pedir de novo.",
                        "🤝 FILA")
        except Exception as erro:
            _log_arquivo(f"[FILA] erro no loop: {erro}")
        await asyncio.sleep(LIVEPIX_INTERVALO)


@bot.tree.command(name="payout", description="💸 Fila de pagamento: quem pagar agora e quanto tirar da LivePix")
async def cmd_payout(interaction: discord.Interaction):
    if not interaction.guild:
        return await interaction.response.send_message(
            embed=criar_embed("❌ Só no servidor", "Use este comando dentro do servidor.", "Vermelho"), ephemeral=True)
    if not await e_staff(interaction.user):
        return await interaction.response.send_message(
            embed=criar_embed("❌ Sem Permissão", "Apenas a equipe financeira (dono/gerente/mediador).",
                              "Vermelho"), ephemeral=True)

    await interaction.response.defer(ephemeral=True, thinking=True)
    resumo = await resumo_abastecimento(interaction.guild.id)
    publicada = await publicar_painel_fila(interaction.guild, forcar=True)
    extra = ("> 📌 Painel atualizado no canal de logs (todo mundo da equipe vê).\n\n" if publicada else
             "> ⚠️ Não consegui publicar no canal de logs — confira `/logs`.\n\n")
    embed = _embed_fila(resumo, "Esmeralda" if not resumo["prontos"] else "Amarelo")
    embed.description = extra + (embed.description or "")
    await interaction.followup.send(embed=embed, ephemeral=True)


# ==================== LOOPS (LivePix + relatório) ====================

# ══════════════════════════════════════════════════════════════════════════════
#  🩺 PULSO E RECUPERAÇÃO PÓS-QUEDA
#  O bot grava "estou vivo" a cada minuto. Quando volta (host que resetou a cada
#  6h, internet que caiu, luz que faltou), ele RECONFERE a LivePix com a janela
#  esticada pelo tempo que ficou fora — ANTES de expirar qualquer coisa — e conta
#  pra equipe o que recuperou. Nada do jogador se perde: o pagamento fica no
#  histórico da LivePix e é aplicado na volta.
# ══════════════════════════════════════════════════════════════════════════════

PULSO_SEGUNDOS = 60         # grava o pulso no máximo 1x por minuto
RECUPERAR_MIN = 3           # ficou fora mais que isso? reconferência de verdade
RECUPERAR_MAX_MIN = 1440    # teto da janela estendida (24h)
INICIADO_EM = agora_brt()   # pra mostrar "estou no ar há X"

_ultimo_pulso_gravado = 0.0
_recuperou_em = 0.0         # quando rolou a última reconferência (evita varredura dupla)


async def _pulso_periodico(forcar: bool = False):
    """Grava 'ainda estou vivo' (vai pro Supabase junto com o resto do estado)."""
    global _ultimo_pulso_gravado
    if not forcar and (time.time() - _ultimo_pulso_gravado) < PULSO_SEGUNDOS:
        return
    _ultimo_pulso_gravado = time.time()
    await _meta_gravar("ultimo_pulso", agora_brt().isoformat())


async def tempo_fora() -> int:
    """Quantos minutos o bot ficou fora do ar (0 = sem referência pra comparar)."""
    texto = await _meta_ler("ultimo_pulso")
    try:
        antes = datetime.datetime.fromisoformat(texto)
    except Exception:
        return 0
    if not antes.tzinfo:
        antes = antes.replace(tzinfo=TZ_BRASILIA)
    return max(0, int((agora_brt() - antes).total_seconds() // 60))


def _tempo_texto(minutos) -> str:
    """'12 min', '5h', '6h30' — jeito curto de falar tempo."""
    minutos = int(minutos or 0)
    if minutos < 60:
        return f"{minutos} min"
    horas, resto = divmod(minutos, 60)
    return f"{horas}h{resto:02d}" if resto else f"{horas}h"


async def _ha_iso(texto) -> str:
    """'hora do último X' em linguagem de gente."""
    try:
        quando = datetime.datetime.fromisoformat(str(texto))
        if not quando.tzinfo:
            quando = quando.replace(tzinfo=TZ_BRASILIA)
        segundos = max(0, int((agora_brt() - quando).total_seconds()))
    except Exception:
        return "sem registro ainda"
    if segundos < 90:
        return f"há {segundos}s"
    if segundos < 5400:
        return f"há {segundos // 60} min"
    return f"há {_tempo_texto(segundos // 60)}"


def pagamento_depois_do_pedido(evento: dict, criado, folga_min: int = 0) -> bool:
    """🩺 Só na reconferência: o PIX tem que ter caído DEPOIS do pedido (5 min de
    folga), pra um pagamento velho não casar com um pedido novo.

    Se a LivePix não mandar a data do evento, não bloqueia."""
    if not folga_min or criado is None or not evento.get("quando"):
        return True
    try:
        return evento["quando"] >= criado - datetime.timedelta(minutes=5)
    except Exception:
        return True


async def _pendencias(guild_id: int) -> dict:
    """Retrato do que está esperando alguém (usado na recuperação e no /saude)."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        dep = await (await db.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(valor), 0) v FROM depositos "
            "WHERE guild_id = ? AND status = 'na_janela'", (guild_id,))).fetchone()
        res = (await (await db.execute(
            "SELECT COUNT(*) FROM slots WHERE guild_id = ? AND confirmado = 0", (guild_id,))).fetchone())[0]
        saq = await (await db.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(valor), 0) v FROM saques "
            "WHERE guild_id = ? AND status IN ('na_fila', 'liberado')", (guild_id,))).fetchone()
        tik = (await (await db.execute(
            "SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND status = 'aberto'", (guild_id,))).fetchone())[0]
    return {"depositos": int(dep["n"] or 0), "depositos_valor": arredondar(dep["v"] or 0),
            "reservas": int(res or 0), "saques": int(saq["n"] or 0),
            "saques_valor": arredondar(saq["v"] or 0), "tickets": int(tik or 0)}


async def _relatorio_atrasado(guild):
    """Se o bot ficou fora na hora do relatório (23:55), manda o de ontem agora."""
    ontem = (agora_brt() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            ja = await (await db.execute(
                "SELECT 1 FROM relatorios_dia WHERE guild_id = ? AND dia = ?", (guild.id, ontem))).fetchone()
        if ja:
            return
        resumo = await resumo_caixa(guild.id, ontem)
        if not (resumo["dia_movimentos"] or resumo["dia_receitas"] or resumo["dia_despesas"]):
            return
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute("INSERT INTO relatorios_dia (guild_id, dia, enviado_em) VALUES (?, ?, ?)",
                             (guild.id, ontem, agora_brt().isoformat()))
            await db.commit()
        await enviar_relatorio_diario(guild, ontem)
        _log_arquivo(f"[RELATÓRIO] atrasado de {ontem} enviado depois da queda")
    except Exception as erro:
        _log_arquivo(f"[RELATÓRIO] atrasado: {erro}")


async def recuperar_apos_queda(fora_min: int) -> dict:
    """Reconfere TUDO que ficou pendente enquanto o bot estava fora.

    Roda no arranque ANTES do loop de expiração — senão a reserva de diário
    (30 min) seria apagada antes de o PIX do jogador ser reconhecido."""
    global _recuperou_em
    _recuperou_em = time.time()
    folga = max(0, min(int(fora_min or 0) + 10, RECUPERAR_MAX_MIN))
    total = {"depositos": 0, "reservas": 0, "saques": 0, "ref": 0}

    for leve in await guilds_para_sync():
        # conectado agora OU servidor que existe no banco (mesmo antes do cache do Discord)
        guild = leve if hasattr(leve, "get_channel") else bot.get_guild(int(getattr(leve, "id", 0)))
        if guild is None:
            continue
        detalhes = []
        try:
            if livepix.configurado:
                resumo = await casar_pagamentos_livepix(guild.id, limite=LIVEPIX_LIMITE_BOOT,
                                                       folga_min=folga)
                for chave in total:
                    total[chave] += int(resumo.get(chave) or 0)
                if resumo.get("erro"):
                    detalhes.append(f"> ⚠️ LivePix respondeu: `{str(resumo['erro'])[:120]}`")
            await processar_fila_saques(guild.id)        # a fila anda de novo conforme o caixa
            await publicar_painel_fila(guild)             # painel da fila atualizado (sem spam)

            avisos = []
            if total["ref"]:
                avisos.append(f"**{total['ref']}** pagamento(s) confirmado(s) pela referência/código")
            if total["depositos"]:
                avisos.append(f"**{total['depositos']}** depósito(s) caiu(ram) na carteira do jogador")
            if total["reservas"]:
                avisos.append(f"**{total['reservas']}** vaga(s) de diário liberada(s) sozinha(s)")
            if total["saques"]:
                avisos.append(f"**{total['saques']}** saque(s) reconhecido(s) no extrato da LivePix")

            pend = await _pendencias(guild.id)
            corpo = (
                f"O bot ficou **{_tempo_texto(fora_min)}** fora do ar e voltou **sozinho**.\n"
                f"Reconferência automática feita — **nada do jogador se perde**. 💛\n\n"
                + ("\n".join(f"> ✅ {a}" for a in avisos) if avisos else
                   "> ✅ Nenhum pagamento novo apareceu na LivePix nesse período.")
                + "\n\n"
                f"> 🕐 Janela reconferida: últimos **{_tempo_texto(folga)}**\n"
                f"> 💸 Fila de pagamento: `{pend['saques']}` saque(s) "
                f"({formatar_moeda(pend['saques_valor'])})\n"
                f"> 💰 Depósitos esperando: `{pend['depositos']}` "
                f"({formatar_moeda(pend['depositos_valor'])}) • "
                f"🎮 Reservas abertas: `{pend['reservas']}` • 🎧 Tickets: `{pend['tickets']}`\n"
                + ("\n".join(detalhes) if detalhes else "")
            )
            await registrar_log(guild, "🔄 RECUPERAÇÃO", "🔄 Bot voltou — reconferência feita",
                                corpo, "Azul")
            await _relatorio_atrasado(guild)
        except Exception as erro:
            _log_arquivo(f"[RECUPERAÇÃO] {type(erro).__name__}: {erro}")

    await _pulso_periodico(forcar=True)     # prova de vida renovada: "voltei"
    print(f"  🩺 Recuperação pós-queda ({_tempo_texto(fora_min)} fora): "
          f"{total['depositos']} depósito(s), {total['reservas']} vaga(s), "
          f"{total['saques']} saque(s), {total['ref']} por referência")
    return total


# ══════════════════════════════════════════════════════════════════════════════
#  💸 FILA DE PAGAMENTO (painel vivo + automação) — ver bloco da fila abaixo
# ══════════════════════════════════════════════════════════════════════════════


async def loop_livepix():
    """A cada 25s: casar depósitos/pagamentos, detectar saques pagos e
    liberar a fila conforme o caixa permite.

    Ao ligar, faz uma VARREDURA GRANDE: pagamentos que chegaram com o bot
    desligado (host que resetou, queda de internet) são liberados na hora."""
    await bot.wait_until_ready()
    # 🩺 se a recuperação pós-queda já rodou (e foi maior), não repete a varredura agora
    if livepix.configurado and (time.time() - _recuperou_em) > 120:
        for guild in bot.guilds:
            try:
                resumo = await casar_pagamentos_livepix(guild.id, limite=LIVEPIX_LIMITE_BOOT)
                if resumo["depositos"] or resumo["reservas"] or resumo["saques"] or resumo["ref"]:
                    print(f"  ⚡ Pagamentos achados no arranque: {resumo['depositos']} depósito(s), "
                          f"{resumo['reservas']} vaga(s), {resumo['saques']} saque(s)")
                if resumo["erro"]:
                    print(f"  ⚠️ LivePix: {resumo['erro'][:120]}")
            except Exception as erro:
                _log_arquivo(f"[LIVEPIX] varredura de arranque: {erro}")
    while not bot.is_closed():
        try:
            for guild in bot.guilds:
                if livepix.configurado:
                    resumo = await casar_pagamentos_livepix(guild.id)
                    if resumo["depositos"] or resumo["reservas"] or resumo["saques"]:
                        await processar_fila_saques(guild.id)
                    if not resumo["erro"]:
                        await _meta_gravar("ultima_varredura", agora_brt().isoformat())
                else:
                    await processar_fila_saques(guild.id)   # caixa interno
                await checar_reserva(guild)                  # avisa 1x/hora se furar a reserva
            await _pulso_periodico()                         # 🩺 "ainda estou vivo"
        except Exception as erro:
            _log_arquivo(f"[LIVEPIX] erro no loop: {erro}")
        await asyncio.sleep(LIVEPIX_INTERVALO)


async def loop_relatorio():
    """Todo dia 23:59 (BRT) manda o relatório financeiro do dia no canal de logs."""
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            agora = agora_brt()
            if agora.hour == 23 and agora.minute >= 55:
                hoje = agora.strftime("%Y-%m-%d")
                for guild in bot.guilds:
                    async with aiosqlite.connect(DATABASE_FILE) as db:
                        ja = await (await db.execute(
                            "SELECT 1 FROM relatorios_dia WHERE guild_id = ? AND dia = ?", (guild.id, hoje)
                        )).fetchone()
                        if ja:
                            continue
                        await db.execute("INSERT INTO relatorios_dia (guild_id, dia, enviado_em) VALUES (?, ?, ?)",
                                         (guild.id, hoje, agora.isoformat()))
                        await db.commit()
                    await enviar_relatorio_diario(guild, hoje)
        except Exception as erro:
            _log_arquivo(f"[RELATÓRIO] erro: {erro}")
        await asyncio.sleep(300)


async def enviar_relatorio_diario(guild, dia: str):
    resumo = await resumo_caixa(guild.id, dia)
    comissoes = await resumo_comissoes_dia(guild.id, dia)

    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        depositos = await (await db.execute(
            "SELECT COUNT(*) AS qtd, COALESCE(SUM(valor), 0) AS total FROM depositos "
            "WHERE guild_id = ? AND status = 'creditado' AND criado_em LIKE ?", (guild.id, f"{dia}%")
        )).fetchone()
        saques = await (await db.execute(
            "SELECT COUNT(*) AS qtd, COALESCE(SUM(valor), 0) AS total FROM saques "
            "WHERE guild_id = ? AND status = 'pago' AND criado_em LIKE ?", (guild.id, f"{dia}%")
        )).fetchone()

    disp = await disponibilidade_saque(guild.id)
    linhas_adm = "\n".join(
        f"> {mencao(l['staff_id'])} — `{formatar_moeda(l['total'])}` ({l['qtd']} venda(s))"
        for l in comissoes["por_adm"]
    ) or "> *Nenhuma comissão hoje.*"

    embed = criar_embed(
        f"📊 Relatório do dia — {dia[8:10]}/{dia[5:7]}",
        f"**🎮 Receita dos diários:** `{formatar_moeda(resumo['dia_receitas'])}` "
        f"({resumo['dia_movimentos']} vaga(s))\n"
        f"**⬆️ Depósitos na carteira:** `{formatar_moeda(depositos['total'])}` ({depositos['qtd']}x)\n"
        f"**⬇️ Saques pagos:** `{formatar_moeda(saques['total'])}` ({saques['qtd']}x)\n"
        f"**💰 Comissões:** `{formatar_moeda(comissoes['total'])}` ({comissoes['vendas']} venda(s))",
        "Dourado"
    )
    embed.add_field(name="🏅 Comissões por ADM", value=linhas_adm, inline=False)
    embed.add_field(
        name="🏦 Caixa",
        value=f"> Saldo da org: `{formatar_moeda(disp['saldo'])}` (fonte: {disp['fonte']})\n"
              f"> Reserva protegida: `{formatar_moeda(disp['reserva'])}`\n"
              f"> Fila de saques: `{formatar_moeda(disp['fila'])}` ({disp['fila_qtd']}x)",
        inline=False
    )
    embed.add_field(
        name="📈 Histórico interno",
        value=f"> Receitas totais: `{formatar_moeda(resumo['receitas'])}`\n"
              f"> Despesas totais: `{formatar_moeda(resumo['despesas'])}`\n"
              f"> Saldo: `{formatar_moeda(resumo['saldo'])}`",
        inline=False
    )

    canal_id = await canal_de_logs(guild.id)
    canal = guild.get_channel(int(canal_id)) if canal_id else None
    if canal:
        try:
            await canal.send(embed=embed)
        except Exception:
            pass
    _log_arquivo(f"[RELATÓRIO] {dia} enviado para o servidor {guild.id}")


# ---------- aviso de caixa baixo (1x por hora, sem spam) ----------

async def checar_reserva(guild):
    agora = time.time()
    ultimo = _ULTIMO_AVISO_RESERVA.get(guild.id, 0)
    if agora - ultimo < 3600:
        return
    disp = await disponibilidade_saque(guild.id)
    if disp["saldo"] < disp["reserva"]:
        _ULTIMO_AVISO_RESERVA[guild.id] = agora
        await registrar_log(
            guild, "⚠️ CAIXA", "⚠️ Saldo abaixo da reserva de segurança",
            f"O saldo da org (`{formatar_moeda(disp['saldo'])}`, fonte: {disp['fonte']}) está abaixo da reserva "
            f"de `{formatar_moeda(disp['reserva'])}`.\n"
            f"> 💡 Novos saques entram na fila e são pagos automaticamente quando o caixa recuperar.",
            "Vermelho"
        )



# ══════════════════════════════════════════════════════════════
#  ☁️ SINCRONIZAÇÃO SUPABASE (sobrevive a reset/restart de hospedagem)
#
#  Como funciona: o bot trabalha no banco local (rápido e leve, ~0 MB de
#  RAM extra) e envia uma FOTOGRAFIA compacta do estado para o Supabase
#  (gzip + base64 → ~dezenas de KB). Quando o host reinicia, o bot baixa a
#  fotografia e restaura tudo: config, painéis, diários, carteiras, cupons,
#  tickets, ganhos, rankings e eventos.
#
#  Só precisa de 2 variáveis de ambiente:
#     SUPABASE_URL=https://xxxxxxxx.supabase.co
#     SUPABASE_ANON_KEY=eyJhbGciOi....
#  (ou SUPABASE_KEY com a chave service_role, mais segura p/ escrita)
# ══════════════════════════════════════════════════════════════
SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY") or ""
SUPABASE_TABELA = os.getenv("SUPABASE_TABELA", "fireforce_estado")
SUPABASE_ID = os.getenv("SUPABASE_ID", "principal")   # vira o "cofre": use algo difícil de adivinhar
SYNC_SEGUNDOS = int(os.getenv("SYNC_SEGUNDOS", "60"))

# tabelas que podem crescer: guardamos só as N linhas mais recentes
SYNC_LIMITE_TABELAS = {
    "transacoes": 4000, "livro_caixa": 4000, "comissoes": 2000,
    "ganhos_trabalho": 2000, "avaliacoes": 1000, "livepix_vistos": 800,
    "ff_cache": 2000,
}
_sync_sujo = False
_sync_ultimo = 0.0
_sync_erro = ""


def supabase_configurado() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def marcar_sujo():
    """Avisa que algo mudou (o envio acontece no loop ou no /backup)."""
    global _sync_sujo
    _sync_sujo = True


async def _sb_req(metodo: str, rota: str, json_body=None, params=None, prefer=None):
    """Chamada REST no Supabase. Devolve (ok, dados)."""
    if not supabase_configurado():
        return False, "Supabase não configurado"
    cabecalho = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Accept": "application/json",
    }
    if prefer:
        cabecalho["Prefer"] = prefer
    try:
        timeout = aiohttp.ClientTimeout(total=25)
        async with aiohttp.ClientSession(timeout=timeout) as sessao:
            async with sessao.request(metodo, f"{SUPABASE_URL}{rota}",
                                      headers=cabecalho, json=json_body, params=params) as resp:
                texto = await resp.text()
                if resp.status >= 400:
                    return False, f"HTTP {resp.status}: {texto[:200]}"
                try:
                    return True, (json.loads(texto) if texto else {})
                except Exception:
                    return True, {}
    except Exception as erro:
        return False, f"{type(erro).__name__}: {erro}"


async def _tabelas_locais() -> list:
    async with aiosqlite.connect(DATABASE_FILE) as db:
        linhas = await (await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )).fetchall()
    return [l[0] for l in linhas]


async def snapshot_dump() -> dict:
    """Fotografia de todas as tabelas (limitando as que crescem)."""
    foto = {"versao": VERSAO_BOT, "quando": agora_brt().isoformat(), "tabelas": {}}
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        for tabela in await _tabelas_locais():
            colunas = [c[1] for c in await (await db.execute(f"PRAGMA table_info({tabela})")).fetchall()]
            limite = SYNC_LIMITE_TABELAS.get(tabela)
            sql = f"SELECT * FROM {tabela}"
            if limite:
                sql += f" ORDER BY rowid DESC LIMIT {limite}"
            linhas = await (await db.execute(sql)).fetchall()
            foto["tabelas"][tabela] = {"colunas": colunas, "linhas": [list(l) for l in linhas]}
    return foto


async def snapshot_aplicar(foto: dict) -> int:
    """Restaura a fotografia no banco local. Devolve quantas linhas voltaram."""
    if not isinstance(foto, dict) or "tabelas" not in foto:
        return 0
    total = 0
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        for tabela, dados in (foto.get("tabelas") or {}).items():
            colunas = dados.get("colunas") or []
            linhas = dados.get("linhas") or []
            if not colunas:
                continue
            existentes = [x[1] for x in await (await db.execute(
                f"PRAGMA table_info({tabela})")).fetchall()]
            if any(c[0] != "_" and c not in existentes for c in colunas):
                continue          # tabela local diferente: pula com segurança
            placeholders = ", ".join("?" for _ in colunas)
            sql = f"INSERT OR REPLACE INTO {tabela} ({', '.join(colunas)}) VALUES ({placeholders})"
            for linha in linhas:
                try:
                    await db.execute(sql, tuple(linha))
                    total += 1
                except Exception:
                    continue
        await db.commit()
    return total


def _pacote(foto: dict) -> str:
    cru = json.dumps(foto, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(gzip.compress(cru, 6)).decode("ascii")


def _despacotar(pacote: str) -> dict:
    return json.loads(gzip.decompress(base64.b64decode(pacote)).decode("utf-8"))


async def salvar_estado(forcar: bool = False) -> str:
    """Envia a fotografia para o Supabase. Devolve mensagem do que aconteceu."""
    global _sync_sujo, _sync_ultimo, _sync_erro
    if not supabase_configurado():
        return "Supabase não configurado (defina SUPABASE_URL e SUPABASE_ANON_KEY)."

    foto = await snapshot_dump()
    pacote = _pacote(foto)
    corpo = {"id": SUPABASE_ID, "dado": pacote,
             "atualizado_em": agora_brt().isoformat(), "versao": VERSAO_BOT}
    ok, dados = await _sb_req(
        "POST", f"/rest/v1/{SUPABASE_TABELA}",
        json_body=corpo,
        prefer="resolution=merge-duplicates,return=minimal",
        params={"on_conflict": "id"},
    )
    if not ok:
        _sync_erro = str(dados)
        return f"❌ Não consegui salvar no Supabase: {_sync_erro[:150]}"
    _sync_sujo = False
    _sync_ultimo = time.time()
    _sync_erro = ""
    kb = len(pacote) / 1024.0
    return f"✅ Salvo no Supabase ({kb:.0f} KB, {sum(len(t['linhas']) for t in foto['tabelas'].values())} linhas)"


async def carregar_estado(forcar: bool = False) -> tuple:
    """Baixa a fotografia. por_padrao só restaura se o banco local estiver vazio."""
    if not supabase_configurado():
        return False, "Supabase não configurado."

    ok, dados = await _sb_req(
        "GET", f"/rest/v1/{SUPABASE_TABELA}",
        params={"id": f"eq.{SUPABASE_ID}", "select": "dado,atualizado_em,versao"},
    )
    if not ok:
        return False, f"❌ Erro ao baixar do Supabase: {str(dados)[:150]}"
    if not dados:
        return False, "Nada salvo no Supabase ainda (primeira execução)."

    registro = dados[0]
    try:
        foto = _despacotar(registro["dado"])
    except Exception as erro:
        return False, f"❌ Pacote inválido: {erro}"

    if not forcar and not await _banco_vazio():
        return False, ("O banco local já tem dados — use `/restaurar forcar:Sim` "
                       "se quiser sobrescrever com o backup do Supabase.")

    linhas = await snapshot_aplicar(foto)
    return True, f"✅ Restaurado do Supabase: {linhas} linhas (backup de {registro.get('atualizado_em', '?')})"


# ══════════════════════════════════════════════════════════════
#  🧱 ESTRUTURAS NO SUPABASE (tempo real)
#
#  Além do backup completo (fireforce_estado), o bot escreve nas tabelas
#  "de verdade" do Supabase pra você consultar/linkar de fora:
#
#    • ff_config        → configurações do bot (as mesmas do /config)
#    • ff_cargos        → cargos (dono, gerente, mediador, suporte)
#    • ff_staff_online  → quem está ON/OFF agora (painel /staff)
#    • ff_rankings      → tops: saldo, transferências, depósitos, ganhos,
#                         vitórias, comissões e carteira de trabalho
#
#  O SQL que cria essas tabelas está no arquivo `supabase_setup.sql`.
# ══════════════════════════════════════════════════════════════

COLUNAS_FF_CONFIG = (
    "guild_id", "guild_nome",
    "cargo_dono", "cargo_gerente", "cargo_mediador", "cargo_suporte",
    "cat_premium", "cat_basico", "cat_pagamentos", "cat_tickets",
    "canal_logs", "canal_logs_suporte", "canal_cupons", "canal_eventos", "canal_rankings",
    "reserva", "comissao_pct", "saque_min", "deposito_min", "janela_min",
    "dia_fechamento", "livepix_link", "nota_valores", "cor",
)

CARGOS_DO_BOT = (("dono", "cargo_dono"), ("gerente", "cargo_gerente"),
                 ("mediador", "cargo_mediador"), ("suporte", "cargo_suporte"))

CATEGORIAS_SQL = ("saldo", "transferencias", "depositos", "ganhos", "vitórias",
                  "comissoes", "trabalho")

_sql_ultimo = 0.0
_sql_erro = ""
_sql_linhas = 0


class _GuildRef:
    """Servidor "leve" (id + nome) — deixa a sincronizar funcionar mesmo antes
    do cache de servidores do Discord ficar pronto (ex.: logo no arranque)."""

    def __init__(self, guild_id, nome: str = ""):
        self.id = int(guild_id)
        self.name = nome or ""


async def guilds_para_sync() -> list:
    """Servidores conectados + os que existem no banco local (sem repetir)."""
    vistos, lista = set(), []
    for guild in bot.guilds:
        vistos.add(int(guild.id))
        lista.append(guild)
    try:
        async with aiosqlite.connect(DATABASE_FILE) as db:
            linhas = await (await db.execute("SELECT guild_id FROM config")).fetchall()
    except Exception:
        linhas = []
    for linha in linhas or []:
        try:
            guild_id = int(linha[0])
        except Exception:
            continue
        if guild_id not in vistos:
            vistos.add(guild_id)
            lista.append(_GuildRef(guild_id))
    return lista


async def linhas_config(guild) -> list:
    """Linha de configuração do servidor no formato da tabela ff_config."""
    cfg = await obter_config(guild.id)
    linha = {"guild_id": int(guild.id),
             "guild_nome": str(getattr(guild, "name", "") or "")[:120],
             "atualizado_em": agora_brt().isoformat()}
    for coluna in COLUNAS_FF_CONFIG:
        if coluna in ("guild_id", "guild_nome"):
            continue
        valor = cfg.get(coluna)
        if coluna == "nota_valores":
            valor = str(valor or "")
        elif coluna == "cor":
            valor = str(valor or "Fire Force")
        elif isinstance(valor, (int, float)):
            valor = float(valor)
        elif valor is not None:
            valor = int(valor) if str(valor).isdigit() else str(valor)
        linha[coluna] = valor
    return [linha]


async def linhas_cargos(guild) -> list:
    """Um registro por cargo usado pelo bot (dono/gerente/mediador/suporte)."""
    cfg = await obter_config(guild.id)
    agora = agora_brt().isoformat()
    linhas = []
    for tipo, chave in CARGOS_DO_BOT:
        cargo_id = cfg.get(chave)
        if not cargo_id:
            continue
        linhas.append({"guild_id": int(guild.id), "tipo": tipo, "cargo_id": int(cargo_id),
                       "atualizado_em": agora})
    return linhas


async def linhas_staff(guild) -> list:
    """Quem está ON/OFF agora (status do painel /staff)."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        linhas = await (await db.execute(
            "SELECT * FROM staff_status WHERE guild_id = ?", (guild.id,))).fetchall()
    agora = agora_brt().isoformat()
    return [{"guild_id": int(guild.id), "user_id": int(l["user_id"]),
             "online": bool(l["online"]), "desde": agora, "atualizado_em": agora}
            for l in linhas]


async def linhas_rankings(guild, limite: int = 25) -> list:
    """Tops de todas as categorias (mesma conta que aparece no /painelranking)."""
    agora = agora_brt().isoformat()
    linhas = []
    for categoria in CATEGORIAS_SQL:
        try:
            dados = await ranking_dados(guild.id, categoria, limite)
        except Exception:
            continue
        for posicao, (user_id, valor) in enumerate(dados, 1):
            linhas.append({"guild_id": int(guild.id), "categoria": categoria,
                           "user_id": int(user_id), "valor": float(valor),
                           "posicao": posicao, "atualizado_em": agora})
    return linhas


async def _upsert_supabase(tabela: str, linhas: list, conflito: str) -> tuple:
    """Grava (insere ou atualiza) linhas numa tabela do Supabase."""
    if not linhas:
        return True, ""
    ok, dados = await _sb_req(
        "POST", f"/rest/v1/{tabela}",
        json_body=linhas,
        prefer="resolution=merge-duplicates,return=minimal",
        params={"on_conflict": conflito},
    )
    return ok, ("" if ok else str(dados)[:160])


async def _apagar_rows(tabela: str, filtros: dict) -> tuple:
    """Apaga linhas de uma tabela do Supabase (usado nos rankings, que são reescritos)."""
    params = {chave: f"eq.{valor}" for chave, valor in filtros.items()}
    ok, dados = await _sb_req("DELETE", f"/rest/v1/{tabela}", params=params,
                              prefer="return=minimal")
    return ok, ("" if ok else str(dados)[:160])


async def sincronizar_estruturado(silencioso: bool = False) -> str:
    """Escreve config, cargos, online/offline e rankings no Supabase.

    Chamado: no arranque, a cada mudança (loop de 60s), no /backup e no /dados.
    """
    global _sql_ultimo, _sql_erro, _sql_linhas
    if not supabase_configurado():
        return "❌ Supabase não configurado (defina `SUPABASE_URL` e `SUPABASE_ANON_KEY`)."

    total, erros = 0, []
    for guild in await guilds_para_sync():
        try:
            config_linhas = await linhas_config(guild)
            cargos_linhas = await linhas_cargos(guild)
            staff_linhas = await linhas_staff(guild)
            ranking_linhas = await linhas_rankings(guild)

            for tabela, linhas, conflito in (
                ("ff_config", config_linhas, "guild_id"),
                ("ff_cargos", cargos_linhas, "guild_id,tipo"),
                ("ff_staff_online", staff_linhas, "guild_id,user_id"),
            ):
                ok, erro = await _upsert_supabase(tabela, linhas, conflito)
                if ok:
                    total += len(linhas)
                else:
                    erros.append(f"{tabela}: {erro}")

            # rankings: reescreve o topo do servidor (some quem saiu da lista)
            if ranking_linhas:
                ok, erro = await _apagar_rows("ff_rankings", {"guild_id": int(guild.id)})
                if not ok:
                    erros.append(f"ff_rankings (limpeza): {erro}")
                ok, erro = await _upsert_supabase("ff_rankings", ranking_linhas,
                                                  "guild_id,categoria,user_id")
                if ok:
                    total += len(ranking_linhas)
                else:
                    erros.append(f"ff_rankings: {erro}")
        except Exception as erro:
            erros.append(f"{type(erro).__name__}: {erro}")

    _sql_linhas = total
    if erros:
        _sql_erro = " | ".join(erros)[:240]
        return f"❌ Estruturas: {_sql_erro[:150]}"
    _sql_erro = ""
    _sql_ultimo = time.time()
    if not silencioso:
        _log_arquivo(f"[SUPABASE] estruturas sincronizadas ({total} linhas)")
    return (f"✅ Supabase em tempo real: {total} linhas "
            f"(config, cargos, online/offline e rankings)")


async def _banco_vazio() -> bool:
    """True quando é uma hospedagem nova (sem config/painéis/vagas)."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        for tabela in ("config", "paineis", "horarios", "slots", "carteira", "cupons", "tickets"):
            try:
                n = (await (await db.execute(f"SELECT COUNT(*) FROM {tabela}")).fetchone())[0]
            except Exception:
                continue
            if n:
                return False
    return True


async def loop_sync():
    """Envia sozinho: a cada SYNC_SEGUNDOS quando algo mudou."""
    await bot.wait_until_ready()
    if supabase_configurado():
        try:
            ok, mensagem = await carregar_estado()
            print(f"  ☁️ Supabase: {mensagem}")
        except Exception as erro:
            print(f"  ☁️ Supabase: falha ao restaurar ({erro})")
        try:
            print(f"  🧱 {await sincronizar_estruturado(silencioso=True)}")
        except Exception as erro:
            print(f"  🧱 Supabase: falha ao criar as estruturas ({erro})")
    while not bot.is_closed():
        try:
            if supabase_configurado() and _sync_sujo:
                resultado = await salvar_estado()
                if resultado.startswith("❌"):
                    _log_arquivo(f"[SYNC] {resultado}")
                estruturas = await sincronizar_estruturado(silencioso=True)
                if estruturas.startswith("❌"):
                    _log_arquivo(f"[SYNC] {estruturas}")
        except Exception as erro:
            _log_arquivo(f"[SYNC] erro: {erro}")
        await asyncio.sleep(SYNC_SEGUNDOS)


# ══════════════════════════════════════════════════════════════
#  🎧 ATENDIMENTO v2 — 2 FILAS • ASSUMIR • AVALIAÇÃO • CARTEIRA DE TRABALHO
# ══════════════════════════════════════════════════════════════

NOTA_VALORES_PADRAO = {0.0: 0.0, 0.5: 0.05, 1.0: 0.50, 1.5: 0.75, 2.0: 1.00, 2.5: 1.25,
                       3.0: 1.50, 3.5: 1.75, 4.0: 2.00, 4.5: 2.25, 5.0: 2.50}


def _emoji_nota(nota: float) -> str:
    cheias = int(nota)
    resto = nota - cheias
    return "⭐" * cheias + ("½" if resto >= 0.5 else "") or "0️⃣"


async def nota_valores(guild_id: int) -> dict:
    """Tabela nota → valor (configurável no /config)."""
    texto = await cfgv(guild_id, "nota_valores", "")
    if texto:
        try:
            dados = json.loads(texto)
            return {float(k): float(v) for k, v in dados.items()}
        except Exception:
            pass
    return dict(NOTA_VALORES_PADRAO)


def fila_normalizada(tipo: str) -> str:
    """As 2 filas do servidor: 🎧 suporte e 🤝 mediador (ADM)."""
    return "mediador" if (tipo or "").strip().lower() in ("mediador", "adm", "financeiro") else "suporte"


def cargos_da_fila(tipo: str) -> list:
    """Quem atende cada fila: 🎧 suporte (cargo_suporte) e 🤝 mediador/ADM (cargo_mediador)."""
    if fila_normalizada(tipo) == "mediador":
        return ["cargo_mediador", "cargo_gerente", "cargo_dono"]
    return ["cargo_suporte", "cargo_gerente", "cargo_dono"]


async def atendente_autorizado(tipo: str, member) -> bool:
    if member.guild_permissions.administrator:
        return True
    cfg = await obter_config(member.guild.id)
    permitidos = [cfg.get(k) for k in cargos_da_fila(tipo)]
    return any(r.id in permitidos for r in getattr(member, "roles", []) if r.id)


async def e_gerencia(member) -> bool:
    """Dono, gerente ou administrador."""
    if member.guild_permissions.administrator:
        return True
    cfg = await obter_config(member.guild.id)
    return any(r.id in [cfg.get("cargo_dono"), cfg.get("cargo_gerente")]
               for r in getattr(member, "roles", []) if r.id)


# ---------- CARTEIRA DE TRABALHO (salários da equipe) ----------

async def saldo_trabalho(user_id: int, guild_id: int) -> float:
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        linha = await (await db.execute(
            "SELECT saldo FROM carteira_trabalho WHERE user_id = ? AND guild_id = ?", (user_id, guild_id)
        )).fetchone()
    return arredondar(linha["saldo"] if linha else 0)


async def movimentar_trabalho(user_id: int, guild_id: int, valor: float, tipo: str,
                              descricao: str, ref: str = "", permitir_negativo: bool = False):
    valor = arredondar(valor)
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("INSERT OR IGNORE INTO carteira_trabalho (user_id, guild_id, saldo, atualizado_em) "
                         "VALUES (?, ?, 0, ?)", (user_id, guild_id, agora_brt().isoformat()))
        linha = await (await db.execute(
            "SELECT saldo FROM carteira_trabalho WHERE user_id = ? AND guild_id = ?", (user_id, guild_id)
        )).fetchone()
        atual = arredondar(linha["saldo"] if linha else 0)
        novo = arredondar(atual + valor)
        if novo < 0 and not permitir_negativo:
            return None
        await db.execute("UPDATE carteira_trabalho SET saldo = ?, atualizado_em = ? WHERE user_id = ? AND guild_id = ?",
                         (novo, agora_brt().isoformat(), user_id, guild_id))
        await db.execute(
            "INSERT INTO ganhos_trabalho (guild_id, user_id, tipo, valor, saldo_apos, descricao, ref, criado_em) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (guild_id, user_id, tipo, valor, novo, descricao, ref, agora_brt().isoformat())
        )
        await db.commit()
    marcar_sujo()
    return novo


async def creditar_trabalho(user_id: int, guild_id: int, valor: float, tipo: str,
                            descricao: str, ref: str = ""):
    return await movimentar_trabalho(user_id, guild_id, abs(valor), tipo, descricao, ref)


async def extrato_trabalho(user_id: int, guild_id: int, quantidade: int = 8) -> str:
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        linhas = await (await db.execute(
            "SELECT * FROM ganhos_trabalho WHERE guild_id = ? AND user_id = ? ORDER BY id DESC LIMIT ?",
            (guild_id, user_id, quantidade)
        )).fetchall()
    if not linhas:
        return "> *Nenhum ganho registrado.*"
    icones = {"comissao": "💸", "avaliacao": "⭐", "saque": "🏦", "reset": "🔄", "ajuste": "🛠️", "premio": "🏆"}
    return "\n".join(
        f"> {icones.get(l['tipo'], '•')} `{'+' if l['valor'] >= 0 else '−'}{formatar_moeda(abs(l['valor']))}`"
        f" — {(l['descricao'] or '')[:44]} `{(l['criado_em'] or '')[8:16].replace('-', '/')}`"
        for l in linhas
    )


async def pagar_comissao(guild, staff_id: int, valor: float, descricao: str, ref: str = ""):
    """Comissão do ADM/mediador vai pra CARTEIRA DE TRABALHO (fecha no domingo)."""
    if not staff_id or valor <= 0:
        return 0.0
    await creditar_trabalho(staff_id, guild.id, valor, "comissao", descricao, ref=ref)
    await registrar_log(
        guild, "💰 COMISSÃO", "💸 Comissão creditada",
        f"{mencao(staff_id)} recebeu **{formatar_moeda(valor)}** de comissão.\n> {descricao}",
        "Verde"
    )
    return valor


async def reset_semanal_trabalho(guild) -> dict:
    """Zera as carteiras de trabalho (pagamento da semana fechou)."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        contas = await (await db.execute(
            "SELECT * FROM carteira_trabalho WHERE guild_id = ? AND saldo > 0", (guild.id,)
        )).fetchall()

    total = 0.0
    linhas = []
    for conta in contas:
        await movimentar_trabalho(conta["user_id"], guild.id, -conta["saldo"], "reset",
                                  "Fechamento semanal — carteira de trabalho zerada (pague no domingo!)",
                                  ref=f"reset:{agora_brt().strftime('%Y-%m-%d')}")
        total = arredondar(total + conta["saldo"])
        linhas.append(f"> {mencao(conta['user_id'])}: `{formatar_moeda(conta['saldo'])}`")

    if linhas:
        await registrar_log(
            guild, "🔄 FECHAMENTO", "🔄 Fechamento semanal das carteiras de trabalho",
            f"Total que deveria ter sido pago: **{formatar_moeda(total)}**\n" + "\n".join(linhas) +
            "\n> As carteiras voltaram a zero para a nova semana.",
            "Dourado"
        )
        await registrar_log(
            guild, "🔄 FECHAMENTO", "🔄 Fechamento semanal das carteiras de trabalho",
            f"Total: **{formatar_moeda(total)}** — carteiras zeradas.", "Dourado"
        )
    return {"total": total, "contas": len(linhas)}


async def loop_fechamento_semanal():
    """Domingo (configurável) na virada da meia-noite: fecha a semana da equipe."""
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            agora = agora_brt()
            dia = int(await cfgv(None, "dia_fechamento", 0))   # 0 = segunda (fim do domingo)
            hoje = agora.weekday()
            if hoje == dia and agora.hour == 0:
                marca = f"fechamento:{agora.strftime('%Y-%m-%d')}"
                async with aiosqlite.connect(DATABASE_FILE) as db:
                    ja = await (await db.execute("SELECT 1 FROM sync_meta WHERE chave = ?", (marca,))).fetchone()
                    if ja:
                        await asyncio.sleep(600)
                        continue
                    await db.execute("INSERT OR REPLACE INTO sync_meta (chave, valor) VALUES (?, ?)",
                                     (marca, agora.isoformat()))
                    await db.commit()
                for guild in bot.guilds:
                    try:
                        await reset_semanal_trabalho(guild)
                    except Exception as erro:
                        _log_arquivo(f"[FECHAMENTO] erro: {erro}")
                    try:
                        await pagar_fila_trabalho(guild)
                    except Exception:
                        pass
        except Exception as erro:
            _log_arquivo(f"[FECHAMENTO] erro no loop: {erro}")
        await asyncio.sleep(300)


async def pagar_fila_trabalho(guild) -> int:
    """Libera os saques de trabalho que já podem ser pagos (reserva respeitada)."""
    disp = await disponibilidade_saque(guild.id)
    livre = disp["livre"]
    if livre <= 0:
        return 0
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        fila = await (await db.execute(
            "SELECT * FROM saques WHERE guild_id = ? AND status = 'na_fila' AND tipo = 'trabalho' ORDER BY id",
            (guild.id,)
        )).fetchall()
    liberados = 0
    for saque in fila:
        if arredondar(saque["valor"]) > livre:
            continue
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute("UPDATE saques SET status = 'liberado' WHERE id = ?", (saque["id"],))
            await db.commit()
        livre = arredondar(livre - saque["valor"])
        liberados += 1
        await notificar_saque(guild, saque["id"])
    return liberados


# ══════════════════════════════════════════════════════════════
#  ⚡ MODO 100% AUTOMÁTICO — o bot confirma o pagamento SOZINHO
#
#  Como funciona (na prática, sem ninguém clicar em nada):
#   1) o bot gera o checkout da LivePix com uma REFERÊNCIA única
#      (é um código nosso, tipo "FF-A7K2") e guarda na tabela `checkouts`;
#   2) o jogador paga o link (não precisa digitar nome, nada);
#   3) a LivePix devolve os pagamentos com a mesma referência → o bot
#      identifica QUE PAGAMENTO É, de quem e de qual diário/depósito,
#      e libera a vaga na hora;
#   4) se o pagamento chegar com o bot desligado, no próximo arranque o
#      bot varre o histórico da LivePix e libera tudo retroativamente;
#   5) se a reserva tinha expirado (ou o canal já tinha fechado), o bot
#      recria a vaga e libera igual; se a sala já lotou, o valor vira
#      SALDO na carteira do jogador (dinheiro nunca some).
#
#  O mediador/equipe entra só como PLANO B: quando a LivePix não responde
#  ou o PIX veio de outro jeito (link fixo, chave do painel, dinheiro).
# ══════════════════════════════════════════════════════════════

def _referencia_curta(tamanho: int = 4) -> str:
    """Código curto e único pra identificar um checkout (sem precisar do nome)."""
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(alfabeto[b % len(alfabeto)] for b in os.urandom(tamanho))


def nova_referencia(tipo: str, alvo_id: int) -> str:
    """Ex.: tipo 'diario' + alvo 12 → 'FF-D12-A7K2' (fácil de achar no extrato)."""
    letra = {"diario": "D", "deposito": "P", "saque": "S"}.get(tipo, "X")
    return f"FF-{letra}{alvo_id}-{_referencia_curta()}"


async def registrar_checkout(referencia: str, guild_id: int, tipo: str, alvo_id: int, valor: float,
                             link: str = "", user_id: int = 0, nick: str = "",
                             horario_id: int = 0, canal_id: int = 0):
    """Guarda o checkout: é isso que permite confirmar o pagamento sozinho."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute(
            "INSERT INTO checkouts (referencia, guild_id, tipo, alvo_id, valor, link, user_id, nick, "
            "horario_id, canal_id, criado_em, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'aberto') "
            "ON CONFLICT(referencia) DO UPDATE SET valor = excluded.valor, link = excluded.link, "
            "user_id = excluded.user_id, nick = excluded.nick, horario_id = excluded.horario_id, "
            "canal_id = excluded.canal_id, criado_em = excluded.criado_em",
            (referencia, guild_id, tipo, alvo_id, arredondar(valor), link, user_id, nick,
             horario_id, canal_id, agora_brt().isoformat()))
        await db.commit()
    marcar_sujo()


async def _visto(prova: str) -> bool:
    async with aiosqlite.connect(DATABASE_FILE) as db:
        linha = await (await db.execute("SELECT 1 FROM livepix_vistos WHERE id = ?", (str(prova),))).fetchone()
    return bool(linha)


async def _marcar_visto(prova: str, tipo: str = "pagamento"):
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute("INSERT OR IGNORE INTO livepix_vistos (id, tipo, criado_em) VALUES (?, ?, ?)",
                         (str(prova), tipo, agora_brt().isoformat()))
        await db.commit()


async def checkout_aberto(referencia: str):
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        return await (await db.execute(
            "SELECT * FROM checkouts WHERE referencia = ?", (referencia,))).fetchone()


async def fechar_checkout(referencia: str, valor_pago: float = 0.0, prova: str = "",
                          status: str = "pago"):
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute(
            "UPDATE checkouts SET status = ?, valor_pago = ?, prova = ?, pago_em = ? WHERE referencia = ?",
            (status, arredondar(valor_pago), prova, agora_brt().isoformat(), referencia))
        await db.commit()
    marcar_sujo()


async def avisar_jogador(guild, user_id: int, titulo: str, texto: str, cor: str = "Esmeralda"):
    """Manda um aviso na DM do jogador (se não der, o log cobre)."""
    try:
        membro = await membro_do_guild(guild, user_id)
        if membro:
            await membro.send(embed=criar_embed(titulo, texto, cor))
            return True
    except Exception:
        pass
    return False


async def _recriar_reserva(co, horario):
    """A reserva tinha expirado mas o jogador pagou: recria a vaga na hora."""
    total = LOTES_POR_MODO[horario["tipo"]]
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        ocupadas = (await (await db.execute(
            "SELECT COUNT(*) FROM slots WHERE horario_id = ? AND confirmado = 1", (horario["id"],)
        )).fetchone())[0]
        if ocupadas >= total:
            return None
        cursor = await db.execute(
            "INSERT INTO slots (horario_id, guild_id, comprador_id, comprador_nome, apelidos, numero, "
            "confirmado, canal_pag, criado_em, valor_cobrado) VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?, ?)",
            (horario["id"], co["guild_id"], co["user_id"] or 0, co["nick"] or "Jogador",
             str(co["nick"] or ""), co["canal_id"] or 0, agora_brt().isoformat(), arredondar(co["valor"])))
        slot_id = cursor.lastrowid
        if co["nick"]:
            await db.execute(
                "INSERT INTO slot_jogadores (slot_id, posicao, ff_uid, ff_nome, ff_nivel, discord_nome) "
                "VALUES (?, 1, '', ?, 0, ?)", (slot_id, co["nick"], co["nick"]))
        await db.commit()
    marcar_sujo()
    return slot_id


async def _saldo_em_vez_de_vaga(guild, co, valor_pago: float, motivo: str, prova: str):
    """Não tem mais vaga (ou o diário já começou): o dinheiro vira SALDO. Nunca some."""
    if not co["user_id"]:
        return None
    valor = arredondar(valor_pago or co["valor"])
    novo = await creditar_saldo(co["user_id"], co["guild_id"], valor, "estorno",
                                f"Pagamento do diário sem vaga ({motivo}) — virou saldo",
                                ref=prova)
    if guild:
        await registrar_log(
            guild, "↩️ ESTORNO", "↩️ Pagamento virou saldo automaticamente",
            f"{mencao(co['user_id'])} pagou **{formatar_moeda(valor)}** e não tinha mais vaga ({motivo}).\n"
            f"> 💰 O valor entrou como **saldo na carteira** (saldo agora: `{formatar_moeda(novo)}`).\n"
            f"> 🎟️ Referência do PIX: `{co['referencia']}`", "Dourado")
        await avisar_jogador(
            guild, co["user_id"], "↩️ Seu pagamento virou saldo",
            f"Recebemos seu PIX de **{formatar_moeda(valor)}**, mas a vaga não estava mais disponível "
            f"({motivo}).\n\n> 💰 O valor já está na sua **carteira** — use quando quiser ou peça o saque.\n"
            f"> 🎟️ Referência: `{co['referencia']}`\n\nQualquer coisa, chama o **suporte** aqui no servidor. 💛",
            "Dourado")
    return novo


async def confirmar_diario_por_referencia(guild, co, valor_pago: float, prova: str, resultado: dict) -> bool:
    """O PIX de um diário, identificado pela REFERÊNCIA do checkout."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        slot = await (await db.execute("SELECT * FROM slots WHERE id = ?", (co["alvo_id"],))).fetchone()
        horario_id = (slot["horario_id"] if slot else 0) or co["horario_id"] or 0
        horario = await (await db.execute("SELECT * FROM horarios WHERE id = ?", (horario_id,))).fetchone()

    # 1) reserva viva → libera a vaga sozinho (caminho normal)
    if slot and not slot["confirmado"]:
        aprovado = await aprovar_pagamento(guild, slot["id"], staff_id=None, origem="livepix")
        if aprovado:
            resultado["reservas"] += 1
            await registrar_log(
                guild, "✅ PAGAMENTO", "⚡ Vaga liberada sozinha (PIX identificado)",
                f"{mencao(slot['comprador_id'])} pagou **{formatar_moeda(valor_pago or slot['valor_cobrado'])}**.\n"
                f"> 🎟️ Referência: `{co['referencia']}` • Vaga `#{aprovado[0]}` liberada **sem equipe**.\n"
                f"> 🎮 `{texto_slot(horario['tipo'])}` • `{horario['horario']}`", "Esmeralda")
            await avisar_jogador(
                guild, slot["comprador_id"], "✅ Pagamento confirmado automaticamente!",
                f"Sua vaga **#{aprovado[0]}** está liberada! 🎮\n"
                f"> ⏰ Diário `{horario['horario']}` — entre no canal do diário pra ver a tabela.\n"
                f"> 📩 ID e senha chegam **5 minutos antes**. Bom jogo! 🔥")
            return True
        # tinha reserva mas a sala lotou entre o pagamento e a confirmação
        if horario:
            await _saldo_em_vez_de_vaga(guild, co, valor_pago, "a sala lotou", prova)
        return False

    # 2) a reserva já tinha sido confirmada: pagamento repetido no mesmo link → vira saldo
    if slot and slot["confirmado"]:
        await _saldo_em_vez_de_vaga(guild, co, valor_pago, "pagamento repetido", prova)
        return False

    # 3) a reserva expirou e foi apagada, mas o jogador pagou: recria a vaga e libera
    if horario and horario["ativo"]:
        try:
            if (horario_para_datetime(horario["horario"]) - agora_brt()).total_seconds() < 0:
                horario = None       # o diário já começou
        except Exception:
            pass
    if horario and horario["ativo"]:
        novo_slot = await _recriar_reserva(co, horario)
        if novo_slot:
            aprovado = await aprovar_pagamento(guild, novo_slot, staff_id=None, origem="livepix")
            if aprovado:
                resultado["reservas"] += 1
                await registrar_log(
                    guild, "✅ PAGAMENTO", "⚡ Pagamento achado depois da reserva expirar",
                    f"{mencao(co['user_id'])} pagou **{formatar_moeda(valor_pago or co['valor'])}** e a reserva "
                    f"dele já tinha expirado.\n"
                    f"> ✅ O bot **recriou a vaga** (`#{aprovado[0]}`) e liberou tudo sozinho.\n"
                    f"> 🎟️ Referência: `{co['referencia']}`", "Esmeralda")
                await avisar_jogador(
                    guild, co["user_id"], "✅ Pagou e a vaga está garantida!",
                    f"Seu PIX chegou depois da reserva expirar, mas eu **recriei sua vaga (#{aprovado[0]})** "
                    f"automaticamente. 🎉\n> ⏰ Diário `{horario['horario']}` — bom jogo! 🔥")
                return True

    # 4) não tem mais como dar vaga (sala lotada ou diário já começou) → vira saldo
    motivo = "o diário já começou" if (horario and not horario["ativo"]) else "a sala lotou"
    if horario is None and co["horario_id"]:
        motivo = "o diário não está mais aberto"
    await _saldo_em_vez_de_vaga(guild, co, valor_pago, motivo, prova)
    return False


async def reconciliar_referencias(guild_id: int, pagamentos: list, resultado: dict) -> int:
    """Identifica os pagamentos pela REFERÊNCIA do checkout e resolve tudo sozinho."""
    por_ref = {}
    for pag in pagamentos:
        ref = str(pag.get("reference") or "").strip()
        if ref:
            por_ref[ref] = pag
    if not por_ref:
        return 0

    guild = bot.get_guild(guild_id)
    confirmados = 0
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        abertos = await (await db.execute(
            "SELECT * FROM checkouts WHERE guild_id = ? AND status = 'aberto'", (guild_id,))).fetchall()

    for co in abertos:
        pag = por_ref.get(co["referencia"])
        if not pag:
            continue
        prova = f"pag:{pag.get('id') or pag.get('proof') or co['referencia']}"
        if await _visto(prova):
            await fechar_checkout(co["referencia"], 0.0, prova)
            continue
        valor_pago = arredondar(float(pag.get("amount") or 0) / 100.0)
        co = dict(co)

        try:
            if co["tipo"] == "deposito":
                async with aiosqlite.connect(DATABASE_FILE) as db:
                    db.row_factory = aiosqlite.Row
                    dep = await (await db.execute(
                        "SELECT * FROM depositos WHERE id = ?", (co["alvo_id"],))).fetchone()
                if dep and dep["status"] != "creditado":
                    await creditar_deposito(guild, dict(dep), f"PIX automático LivePix (ref {co['referencia']})",
                                            prova)
                    resultado["depositos"] += 1
                elif co["user_id"]:
                    # depósito cancelado/sem registro: o dinheiro é do jogador → vira saldo
                    novo = await creditar_saldo(co["user_id"], co["guild_id"], valor_pago or co["valor"],
                                                "deposito", f"Depósito PIX (ref {co['referencia']}) — direto",
                                                ref=prova)
                    if guild:
                        await registrar_log(
                            guild, "💰 DEPÓSITO", "✅ Depósito creditado sozinho",
                            f"{mencao(co['user_id'])} depositou **{formatar_moeda(valor_pago or co['valor'])}** "
                            f"(referência `{co['referencia']}`).\n> 💰 Saldo agora: `{formatar_moeda(novo)}`",
                            "Esmeralda")
                confirmados += 1
            elif co["tipo"] == "diario":
                if await confirmar_diario_por_referencia(guild, co, valor_pago, prova, resultado):
                    confirmados += 1
                else:
                    confirmados += 1
            elif co["tipo"] == "saque":
                pass
        except Exception as erro:
            _log_arquivo(f"[AUTO] erro ao confirmar ref {co['referencia']}: {erro}")
            continue

        await _marcar_visto(prova, f"ref_{co['tipo']}")
        await fechar_checkout(co["referencia"], valor_pago, prova)

    return confirmados


async def casar_por_valor_unico(guild_id: int, eventos: list, resultado: dict) -> int:
    """Plano C: só existe UMA reserva aberta com aquele valor e UM pagamento com aquele
    valor → é dele. Serve pra quem pagou pela chave/link fixo (sem checkout nosso)."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        reservas = await (await db.execute(
            "SELECT * FROM slots WHERE guild_id = ? AND confirmado = 0 ORDER BY id", (guild_id,))).fetchall()
    if not reservas:
        return 0

    guild = bot.get_guild(guild_id)
    confirmados = 0
    for reserva in reservas:
        valor = arredondar(reserva["valor_cobrado"])
        candidatas = [r for r in reservas if arredondar(r["valor_cobrado"]) == valor and not r["confirmado"]]
        if len(candidatas) != 1:
            continue
        iguais = [e for e in eventos if valor_bate(e["centavos"], valor)]
        if len(iguais) != 1:
            continue
        evento = iguais[0]
        if await _ja_visto(evento["id"], "valor"):
            continue
        if guild:
            aprovado = await aprovar_pagamento(guild, reserva["id"], staff_id=None, origem="livepix")
            if aprovado:
                resultado["reservas"] += 1
                confirmados += 1
                await registrar_log(
                    guild, "✅ PAGAMENTO", "⚡ Vaga liberada sozinha (valor exato do PIX)",
                    f"PIX de **{formatar_moeda(valor)}** tinha uma única reserva aberta com esse valor — "
                    f"vaga `#{aprovado[0]}` liberada automaticamente pra {mencao(reserva['comprador_id'])}.\n"
                    f"> ⚠️ Se esse PIX não for dele, use `/financeiro` → **Depósitos** pra acertar.", "Amarelo")
                await avisar_jogador(
                    guild, reserva["comprador_id"], "✅ Pagamento confirmado automaticamente!",
                    f"Seu PIX de **{formatar_moeda(valor)}** bateu com a sua reserva — vaga **#{aprovado[0]}** "
                    f"liberada! 🎮\n> 📩 ID e senha chegam **5 minutos antes**. 🔥")
    return confirmados


async def buscar_pagamentos_agora(guild_id: int, limite: int = LIVEPIX_PAGAMENTOS_LIMITE,
                                 silencioso: bool = False) -> dict:
    """Botão/plano B da equipe: força uma varredura da LivePix agora."""
    resumo = await casar_pagamentos_livepix(guild_id, limite=limite)
    if not silencioso:
        _log_arquivo(
            f"[AUTO] varredura manual: {resumo['depositos']} depósito(s), {resumo['reservas']} vaga(s), "
            f"{resumo['saques']} saque(s){(' — ' + resumo['erro']) if resumo['erro'] else ''}")
    return resumo


class FinanceiroAcaoView(discord.ui.View):
    """Plano B da equipe: procura pagamentos na LivePix na hora (ou explica que é automático)."""

    def __init__(self):
        super().__init__(timeout=600)

    @discord.ui.button(label="Procurar pagamentos agora", style=discord.ButtonStyle.green,
                       emoji="🔎", custom_id="ff_fin_buscar")
    async def buscar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await e_staff(interaction.user):
            return await interaction.response.send_message(
                embed=criar_embed("❌ Sem Permissão", "Apenas a equipe.", "Vermelho"), ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not livepix.configurado:
            return await interaction.followup.send(
                embed=criar_embed("ℹ️ Modo manual",
                                  "A LivePix não está configurada, então o bot usa o **link fixo** e a equipe "
                                  "confirma os pagamentos nos botões.\n\n"
                                  "> 💡 Com as credenciais da LivePix (`LIVEPIX_CLIENT_ID` e "
                                  "`LIVEPIX_CLIENT_SECRET`), isso passa a ser **100% automático**.",
                                  "Amarelo"), ephemeral=True)
        resumo = await buscar_pagamentos_agora(interaction.guild.id, limite=LIVEPIX_LIMITE_BOOT)
        embed = criar_embed(
            "🔎 Varredura da LivePix",
            f"> ⬆️ Depósitos confirmados: `{resumo['depositos']}`\n"
            f"> 🎮 Vagas liberadas: `{resumo['reservas']}`\n"
            f"> ⬇️ Saques detectados como pagos: `{resumo['saques']}`\n"
            + (f"\n⚠️ `{resumo['erro'][:160]}`" if resumo["erro"] else
               "\n✅ Nada pendente — o bot já confirma tudo sozinho a cada "
               f"`{LIVEPIX_INTERVALO}s`."),
            "Esmeralda" if not resumo["erro"] else "Amarelo")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Como é automático?", style=discord.ButtonStyle.blurple, emoji="⚡",
                       custom_id="ff_fin_auto")
    async def explicar(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            abertos = (await (await db.execute(
                "SELECT COUNT(*) FROM checkouts WHERE guild_id = ? AND status = 'aberto'",
                (interaction.guild.id,))).fetchone())[0]
            pagos = (await (await db.execute(
                "SELECT COUNT(*) FROM checkouts WHERE guild_id = ? AND status = 'pago'",
                (interaction.guild.id,))).fetchone())[0]
        await interaction.response.send_message(
            embed=criar_embed(
                "⚡ Modo 100% automático",
                f"Cada checkout gerado leva uma **referência única** (ex.: `FF-D12-A7K2`). Quando o PIX cai, "
                f"a LivePix devolve essa referência e o bot **libera a vaga/depósito na hora** — sem ninguém "
                f"clicar.\n\n"
                f"> ⏱️ Varredura automática a cada `{LIVEPIX_INTERVALO}s`\n"
                f"> 🎟️ Checkouts monitorando agora: `{abertos}`\n"
                f"> ✅ Já confirmados sozinhos: `{pagos}`\n\n"
                f"**Quando a equipe precisa entrar:** só se o PIX veio por fora (chave/link fixo/dinheiro) ou "
                f"se a LivePix estiver fora do ar — aí é o botão *Confirmar Pagamento* no canal do jogador.",
                "Esmeralda"), ephemeral=True)


# ---------- ATENDIMENTO (suporte) ----------

class TicketPainelView(discord.ui.View):
    """Painel público: o jogador abre atendimento com o SUPORTE."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Suporte", style=discord.ButtonStyle.green, emoji="🎧", custom_id="ff_tk_sup")
    async def fila_suporte(self, interaction: discord.Interaction, button: discord.ui.Button):
        await abrir_ticket(interaction, "suporte")

    @discord.ui.button(label="Dúvida de pagamento", style=discord.ButtonStyle.blurple, emoji="💰",
                       custom_id="ff_tk_fin")
    async def fila_pagamento(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Atalho pra quem está com dúvida no pagamento — cai no MESMO suporte."""
        await abrir_ticket(interaction, "suporte")


async def abrir_ticket(interaction: discord.Interaction, tipo: str = "suporte"):
    tipo = "suporte"          # atendimento com jogador = SEMPRE suporte
    cfg = await obter_config(interaction.guild.id)
    if not any(cfg.get(k) for k in cargos_da_fila(tipo)):
        return await interaction.response.send_message(
            embed=criar_embed("⚙️ Em configuração", "Esse atendimento ainda está sendo configurado. Tente o outro botão.", "Amarelo"),
            ephemeral=True
        )

    async with aiosqlite.connect(DATABASE_FILE) as db:
        existente = await (await db.execute(
            "SELECT 1 FROM tickets WHERE guild_id = ? AND user_id = ? AND status = 'aberto'",
            (interaction.guild.id, interaction.user.id)
        )).fetchone()
    if existente:
        return await interaction.response.send_message(
            embed=criar_embed("⚠️ Você já tem um atendimento aberto",
                              "Finalize o atendimento atual antes de abrir outro.", "Amarelo"), ephemeral=True)

    categoria = interaction.guild.get_channel(cfg.get("cat_tickets"))
    rotulo = "🎧" if tipo == "suporte" else "🤝"
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True,
                                                      read_message_history=True),
        interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
    }
    for chave in cargos_da_fila(tipo):
        if cfg.get(chave):
            cargo = interaction.guild.get_role(cfg[chave])
            if cargo:
                overwrites[cargo] = discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                                               manage_messages=True, read_message_history=True)

    canal = await interaction.guild.create_text_channel(
        f"{rotulo}│{interaction.user.display_name}"[:100], category=categoria, overwrites=overwrites)

    async with aiosqlite.connect(DATABASE_FILE) as db:
        cursor = await db.execute(
            "INSERT INTO tickets (guild_id, channel_id, user_id, status, tipo, criado_em) VALUES (?, ?, ?, 'aberto', ?, ?)",
            (interaction.guild.id, canal.id, interaction.user.id, tipo, agora_brt().isoformat()))
        ticket_id = cursor.lastrowid
        await db.commit()
    marcar_sujo()

    nomes = {"suporte": "Suporte 🎧"}
    dica = ("Quem assume aqui é o **suporte** — dúvidas, problemas no bot, diário e cupom. 🎧\n"
            "> 💰 Pagamento do diário/depósito é **automático**: o bot confirma o PIX sozinho.")
    embed = criar_embed(
        f"🎫 Atendimento — {nomes.get(tipo, 'Suporte 🎧')}",
        f"Olá {interaction.user.mention}! Descreva o que você precisa que a equipe já responde.\n"
        f"> {dica}\n\n"
        f"> 🙋 **Assumir:** o primeiro atendente da fila que clicar assume o atendimento.\n"
        f"> 🔒 **Fechar:** só **você** fecha o atendimento — aí o atendente recebe sua avaliação.\n"
        f"> 👥 Precisa chamar alguém? Use os botões abaixo.",
        "Fire Force", footer=f"Fire Force • Atendimento #{ticket_id}"
    )
    await canal.send(content=mencao(interaction.user.id), embed=embed, view=TicketView(ticket_id))
    await interaction.response.send_message(
        embed=criar_embed("✅ Atendimento aberto", f"Fale com a equipe em {canal.mention}", "Esmeralda"),
        ephemeral=True)

    await registrar_log_suporte(
        interaction.guild, "🎫 TICKET", "🎫 Novo atendimento aberto",
        f"{mencao(interaction.user.id)} abriu atendimento **{nomes.get(tipo, 'Atendimento')}**.\n"
        f"> 🔖 Protocolo: `#{ticket_id}` • Fila: `{tipo}`\n> Ninguém assumiu ainda.",
        "Azul")


class TicketView(discord.ui.View):
    """Botões do atendimento (persistentes: funcionam após restart)."""

    def __init__(self, ticket_id: int = 0):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id
        if ticket_id:
            self.assumir.custom_id = f"ff_tk_assumir:{ticket_id}"
            self.add.custom_id = f"ff_tk_add:{ticket_id}"
            self.rem.custom_id = f"ff_tk_rem:{ticket_id}"
            self.renomear.custom_id = f"ff_tk_ren:{ticket_id}"
            self.fechar.custom_id = f"ff_tk_fechar:{ticket_id}"

    async def _ticket(self, channel_id: int):
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            return await (await db.execute(
                "SELECT * FROM tickets WHERE channel_id = ? ORDER BY id DESC LIMIT 1", (channel_id,)
            )).fetchone()

    @discord.ui.button(label="Assumir", style=discord.ButtonStyle.green, emoji="🙋")
    async def assumir(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = await self._ticket(interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message(
                embed=criar_embed("❌ Atendimento não encontrado", "Use o painel de novo.", "Vermelho"), ephemeral=True)
        if not await atendente_autorizado(fila_normalizada(ticket["tipo"]), interaction.user):
            return await interaction.response.send_message(
                embed=criar_embed("❌ Sem Permissão",
                                  "Esse atendimento é de outra fila. Só quem é da fila (ou gerência) assume.", "Vermelho"),
                ephemeral=True)
        if ticket["assumido_por"] and ticket["assumido_por"] != interaction.user.id:
            return await interaction.response.send_message(
                embed=criar_embed("🙋 Já foi assumido",
                                  f"Este atendimento já é de {mencao(ticket['assumido_por'])}.", "Amarelo"), ephemeral=True)

        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute("UPDATE tickets SET assumido_por = ?, assumido_em = ? WHERE id = ?",
                             (interaction.user.id, agora_brt().isoformat(), ticket["id"]))
            await db.commit()
        marcar_sujo()

        # a partir daqui só o atendente + gerência enxergam o canal
        cfg = await obter_config(interaction.guild.id)
        for chave in cargos_da_fila(fila_normalizada(ticket["tipo"])):
            if chave in ("cargo_dono", "cargo_gerente"):
                continue
            cargo = interaction.guild.get_role(cfg.get(chave)) if cfg.get(chave) else None
            if cargo:
                try:
                    await interaction.channel.set_permissions(cargo, overwrite=None)
                except Exception:
                    pass

        embed = criar_embed(
            "🙋 Atendimento assumido",
            f"{interaction.user.mention} assumiu este atendimento.\n"
            f"> A partir de agora só ele (e a gerência) acompanha aqui.\n"
            f"> 🔒 Quem fecha é **{mencao(ticket['user_id'])}** — e ele dá a nota no final.",
            "Esmeralda")
        await interaction.response.send_message(content=mencao(ticket["user_id"]), embed=embed)
        await registrar_log_suporte(
            interaction.guild, "🎫 TICKET", "🙋 Atendimento assumido",
            f"{mencao(interaction.user.id)} assumiu o protocolo `#{ticket['id']}` "
            f"(fila `{ticket['tipo']}`) de {mencao(ticket['user_id'])}.", "Verde")

    @discord.ui.button(label="Adicionar", style=discord.ButtonStyle.blurple, emoji="➕")
    async def add(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._pode_gerenciar(interaction):
            return
        await interaction.response.send_message("Selecione quem adicionar:", view=TicketAddView(), ephemeral=True)

    @discord.ui.button(label="Remover", style=discord.ButtonStyle.gray, emoji="➖")
    async def rem(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._pode_gerenciar(interaction):
            return
        await interaction.response.send_message("Selecione quem remover:", view=TicketRemView(), ephemeral=True)

    @discord.ui.button(label="Renomear", style=discord.ButtonStyle.gray, emoji="✏️")
    async def renomear(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._pode_gerenciar(interaction):
            return
        await interaction.response.send_modal(TicketRenomearModal())

    @discord.ui.button(label="Fechar atendimento", style=discord.ButtonStyle.red, emoji="🔒")
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = await self._ticket(interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message(
                embed=criar_embed("❌ Atendimento não encontrado", "", "Vermelho"), ephemeral=True)
        if interaction.user.id != ticket["user_id"]:
            return await interaction.response.send_message(
                embed=criar_embed("🔒 Só o cliente fecha",
                                  f"Quem fecha o atendimento é {mencao(ticket['user_id'])} — "
                                  f"é ele que avalia o atendente no final.", "Amarelo"), ephemeral=True)
        if not ticket["assumido_por"]:
            return await interaction.response.send_message(
                embed=criar_embed("⏳ Ninguém assumiu ainda",
                                  "Espere um atendente assumir para poder avaliar e fechar. 💛", "Amarelo"),
                ephemeral=True)
        await interaction.response.send_message(
            embed=criar_embed("⭐ Avaliação do atendimento",
                              "Antes de fechar, dê uma **nota ao atendimento**.\n"
                              "A descrição é **opcional** (mas ajuda muito a equipe!).",
                              "Dourado"),
            view=TicketNotaView(ticket["id"], ticket["assumido_por"]), ephemeral=True)

    async def _pode_gerenciar(self, interaction) -> bool:
        ticket = await self._ticket(interaction.channel.id)
        if not ticket:
            return False
        if interaction.user.id == ticket["assumido_por"] or await e_gerencia(interaction.user):
            return True
        await interaction.response.send_message(
            embed=criar_embed("❌ Só quem assumiu", "Assuma o atendimento (ou seja gerência) para usar isso.", "Vermelho"),
            ephemeral=True)
        return False


class TicketNotaView(discord.ui.View):
    """0 a 5 estrelas, com meia estrela — é isso que paga o atendente."""

    def __init__(self, ticket_id: int, atendente_id: int):
        super().__init__(timeout=300)
        self.ticket_id = ticket_id
        self.atendente_id = atendente_id
        opcoes = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
        self.selecionar.options = [
            discord.SelectOption(
                label=("0 (sem estrela)" if n == 0 else f"{_emoji_nota(n)}  ({n:g} estrela{'s' if n != 1 else ''})"),
                value=str(n), description=("Nota zero — o atendente não recebe nada" if n == 0
                                           else f"Vale {formatar_moeda(NOTA_VALORES_PADRAO[n])} para o atendente"))
            for n in opcoes
        ]

    @discord.ui.select(placeholder="Escolha a nota do atendimento (0 a 5 estrelas)...", min_values=1, max_values=1)
    async def selecionar(self, interaction: discord.Interaction, select: discord.ui.Select):
        nota = float(select.values[0])
        await interaction.response.send_modal(TicketNotaDescModal(self.ticket_id, self.atendente_id, nota))


class TicketNotaDescModal(discord.ui.Modal, title="⭐ Finalizar atendimento"):
    descricao = discord.ui.TextInput(label="Descrição (opcional)", style=discord.TextStyle.paragraph,
                                     required=False, max_length=500,
                                     placeholder="Conte como foi o atendimento (opcional)")

    def __init__(self, ticket_id: int, atendente_id: int, nota: float):
        super().__init__()
        self.ticket_id = ticket_id
        self.atendente_id = atendente_id
        self.nota = nota

    async def on_submit(self, interaction: discord.Interaction):
        await finalizar_ticket(interaction, self.ticket_id, self.atendente_id, self.nota, self.descricao.value)


async def finalizar_ticket(interaction, ticket_id: int, atendente_id: int, nota: float, descricao: str):
    valores = await nota_valores(interaction.guild.id)
    valor = arredondar(valores.get(nota, 0.0))
    descricao = (descricao or "").strip()

    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        ticket = await (await db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))).fetchone()
        if not ticket or ticket["status"] != "aberto":
            return await interaction.response.send_message(
                embed=criar_embed("ℹ️ Já finalizado", "Este atendimento já foi fechado.", "Amarelo"), ephemeral=True)
        await db.execute(
            "UPDATE tickets SET status = 'fechado', nota = ?, nota_desc = ?, pago_nota = ?, "
            "fechado_em = ?, fechado_por = ? WHERE id = ?",
            (nota, descricao, valor, agora_brt().isoformat(), interaction.user.id, ticket_id))
        await db.commit()
        await db.execute(
            "INSERT INTO avaliacoes (guild_id, ticket_id, avaliador_id, atendente_id, nota, descricao, valor_pago, criado_em) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (interaction.guild.id, ticket_id, interaction.user.id, atendente_id, nota, descricao,
             valor, agora_brt().isoformat()))
        await db.commit()
    marcar_sujo()

    if valor > 0:
        await creditar_trabalho(atendente_id, interaction.guild.id, valor, "avaliacao",
                                f"Avaliação {_emoji_nota(nota)} do atendimento #{ticket_id}",
                                ref=f"ticket:{ticket_id}")
        await registrar_caixa(interaction.guild.id, "despesa", valor,
                              f"Pagamento de atendimento #{ticket_id} (nota {nota:g})", ref=f"ticket:{ticket_id}")

    saldo_atendente = await saldo_trabalho(atendente_id, interaction.guild.id)
    embed = criar_embed(
        "✅ Atendimento finalizado",
        f"**{mencao(interaction.user.id)}** avaliou com {_emoji_nota(nota)} **({nota:g} estrela{'s' if nota != 1 else ''})**.\n"
        f"> 💰 Valor para o atendente: `{formatar_moeda(valor)}`\n"
        f"> 💼 Carteira de trabalho dele agora: `{formatar_moeda(saldo_atendente)}`\n"
        + (f"> 📝 *{descricao[:200]}*" if descricao else "> 📝 *(sem descrição)*"),
        "Esmeralda")
    await interaction.response.send_message(embed=embed)

    await registrar_log_suporte(
        interaction.guild, "⭐ AVALIAÇÃO", "⭐ Atendimento avaliado",
        f"Protocolo `#{ticket_id}` — fila `{ticket['tipo']}`\n"
        f"> 👤 Cliente: {mencao(interaction.user.id)}\n"
        f"> 🙋 Atendente: {mencao(atendente_id)}\n"
        f"> ⭐ Nota: **{nota:g}** ({_emoji_nota(nota)})\n"
        f"> 💰 Pago ao atendente: `{formatar_moeda(valor)}`\n"
        f"> 💼 Saldo de trabalho agora: `{formatar_moeda(saldo_atendente)}`\n"
        + (f"> 📝 Descrição: {descricao[:300]}" if descricao else "> 📝 Sem descrição"),
        "Dourado")

    try:
        await interaction.channel.send(embed=criar_embed(
            "🔒 Atendimento encerrado",
            f"Obrigado pelo contato! Este canal será fechado em {TICKET_FECHAR_SEGUNDOS} segundos.", "Cinza Escuro"))
    except Exception:
        pass
    await asyncio.sleep(TICKET_FECHAR_SEGUNDOS)
    try:
        await interaction.channel.delete()
    except Exception:
        pass


async def registrar_log_suporte(guild, tipo: str, titulo: str, descricao: str, cor: str = "Azul"):
    """Log da equipe de atendimento (canal próprio)."""
    limpo = descricao.replace("**", "").replace("> ", "")
    _log_arquivo(f"[{tipo}] {titulo} — {limpo}")
    if not guild:
        return
    try:
        canal_id = await cfgv(guild.id, "canal_logs_suporte", None)
    except Exception:
        canal_id = None
    if not canal_id:
        return
    canal = guild.get_channel(int(canal_id))
    if not canal:
        return
    try:
        await canal.send(embed=criar_embed(titulo, descricao, cor, footer=f"🔥 Fire Force • atendimento"))
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
#  💰 DEPÓSITO-ATENDIMENTO • 🎟️ CUPONS • 🎉 EVENTOS • 🏆 RANKINGS • 💸 SAQUE v2
# ══════════════════════════════════════════════════════════════

# ---------- DEPÓSITO COMO ATENDIMENTO PRIVADO ----------

async def abrir_atendimento_deposito(interaction: discord.Interaction):
    """Cria o canal privado do depósito: jogador + suporte/gerente/dono (sem mediador)."""
    cfg = await obter_config(interaction.guild.id)
    async with aiosqlite.connect(DATABASE_FILE) as db:
        aberto = await (await db.execute(
            "SELECT 1 FROM depositos WHERE guild_id = ? AND user_id = ? AND status IN ('na_janela','aguardando')",
            (interaction.guild.id, interaction.user.id)
        )).fetchone()
    if aberto:
        return await interaction.response.send_message(
            embed=criar_embed("⚠️ Você já tem um depósito aberto",
                              "Finalize o depósito atual (ou fale com a equipe) antes de abrir outro. 💛",
                              "Amarelo"), ephemeral=True)

    categoria = interaction.guild.get_channel(cfg.get("cat_tickets")) or interaction.guild.get_channel(cfg.get("cat_pagamentos"))
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True,
                                                      read_message_history=True),
        interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
    }
    for chave in ("cargo_suporte", "cargo_gerente", "cargo_dono"):     # mediador NÃO vê o depósito
        if cfg.get(chave):
            cargo = interaction.guild.get_role(cfg[chave])
            if cargo:
                overwrites[cargo] = discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                                               manage_messages=True, read_message_history=True)

    canal = await interaction.guild.create_text_channel(
        f"💰│deposito-{interaction.user.display_name}"[:100], category=categoria, overwrites=overwrites)

    async with aiosqlite.connect(DATABASE_FILE) as db:
        cursor = await db.execute(
            "INSERT INTO depositos (guild_id, user_id, valor, nome_pagador, apelidos, status, canal_id, "
            "criado_em) VALUES (?, ?, 0, '', ?, 'aguardando', ?, ?)",
            (interaction.guild.id, interaction.user.id, apelidos_do_usuario(interaction.user), canal.id,
             agora_brt().isoformat()))
        deposito_id = cursor.lastrowid
        await db.commit()
    marcar_sujo()

    embed = criar_embed(
        "💰 Depósito na carteira",
        f"Olá {interaction.user.mention}! Este é o seu atendimento de **depósito**.\n\n"
        f"> 1️⃣ Clique em **Abrir depósito** e informe o valor\n"
        f"> 2️⃣ No LivePix: **Nome** = o **seu nick** • **Mensagem** = o **seu @ do Discord** (ou nada)\n"
        f"> 3️⃣ O saldo entra **sozinho** na sua carteira (ou a equipe confirma pra você)\n\n"
        f"🙋 **Equipe:** quem chegar primeiro clica em **Assumir** para mediar este depósito.\n"
        f"💛 Dúvida? Escreva aqui mesmo que a equipe responde.",
        "Esmeralda", footer=f"Fire Force • Depósito #{deposito_id}")
    await canal.send(content=mencao(interaction.user.id), embed=embed, view=DepositoCanalView(deposito_id))
    await interaction.response.send_message(
        embed=criar_embed("✅ Atendimento criado", f"Continue em {canal.mention} 💰", "Esmeralda"), ephemeral=True)

    await registrar_log_suporte(
        interaction.guild, "💰 DEPÓSITO", "💰 Atendimento de depósito aberto",
        f"{mencao(interaction.user.id)} abriu um atendimento de depósito.\n"
        f"> 🔖 Protocolo: `#{deposito_id}` • Canal: {canal.mention}", "Azul")


class DepositoCanalView(discord.ui.View):
    def __init__(self, deposito_id: int = 0):
        super().__init__(timeout=None)
        if deposito_id:
            self.abrir.custom_id = f"ff_dep_abrir:{deposito_id}"
            self.assumir.custom_id = f"ff_dep_assumir:{deposito_id}"
            self.manual.custom_id = f"ff_dep_manual:{deposito_id}"
            self.fechar.custom_id = f"ff_dep_fechar:{deposito_id}"

    async def _deposito(self, channel_id: int):
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            return await (await db.execute(
                "SELECT * FROM depositos WHERE canal_id = ? ORDER BY id DESC LIMIT 1", (channel_id,)
            )).fetchone()

    @discord.ui.button(label="Abrir depósito", style=discord.ButtonStyle.green, emoji="💳")
    async def abrir(self, interaction: discord.Interaction, button: discord.ui.Button):
        deposito = await self._deposito(interaction.channel.id)
        if not deposito:
            return await interaction.response.send_message(
                embed=criar_embed("❌ Não encontrado", "Abra um novo com `/deposito`.", "Vermelho"), ephemeral=True)
        if interaction.user.id != deposito["user_id"]:
            return await interaction.response.send_message(
                embed=criar_embed("🙋 É o atendimento de outra pessoa",
                                  f"Quem abre o depósito é {mencao(deposito['user_id'])}.", "Amarelo"), ephemeral=True)
        await interaction.response.send_modal(DepositoModal(deposito["id"], interaction.channel.id))

    @discord.ui.button(label="Assumir", style=discord.ButtonStyle.blurple, emoji="🙋")
    async def assumir(self, interaction: discord.Interaction, button: discord.ui.Button):
        deposito = await self._deposito(interaction.channel.id)
        if not deposito or not await atendente_autorizado("suporte", interaction.user):
            return await interaction.response.send_message(
                embed=criar_embed("❌ Sem Permissão", "Só a equipe de suporte/gerência assume depósitos.", "Vermelho"),
                ephemeral=True)
        if deposito["assumido_por"] and deposito["assumido_por"] != interaction.user.id:
            return await interaction.response.send_message(
                embed=criar_embed("🙋 Já assumido", f"Já é de {mencao(deposito['assumido_por'])}.", "Amarelo"),
                ephemeral=True)
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute("UPDATE depositos SET assumido_por = ? WHERE id = ?",
                             (interaction.user.id, deposito["id"]))
            await db.commit()
        marcar_sujo()
        await interaction.response.send_message(
            content=mencao(deposito["user_id"]),
            embed=criar_embed("🙋 Depósito assumido",
                              f"{interaction.user.mention} está acompanhando este depósito.\n"
                              f"> Qualquer coisa, é só falar aqui. 💛", "Esmeralda"))
        await registrar_log_suporte(interaction.guild, "💰 DEPÓSITO", "🙋 Depósito assumido",
                                    f"{mencao(interaction.user.id)} assumiu o depósito `#{deposito['id']}`.", "Verde")

    @discord.ui.button(label="Confirmar manualmente", style=discord.ButtonStyle.gray, emoji="🛠️")
    async def manual(self, interaction: discord.Interaction, button: discord.ui.Button):
        deposito = await self._deposito(interaction.channel.id)
        if not deposito or not await atendente_autorizado("suporte", interaction.user):
            return await interaction.response.send_message(
                embed=criar_embed("❌ Sem Permissão", "Só a equipe confirma manualmente.", "Vermelho"), ephemeral=True)
        if deposito["status"] == "creditado":
            return await interaction.response.send_message(
                embed=criar_embed("ℹ️ Já creditado", "Esse depósito já caiu na carteira.", "Amarelo"), ephemeral=True)
        await interaction.response.send_message(
            embed=criar_embed("🛠️ Confirmação manual",
                              "Use `/financeiro` → **Depósitos** ou confirme pelo valor pago no LivePix.\n"
                              "Assim que confirmar, o saldo cai na carteira na hora.", "Amarelo"), ephemeral=True)

    @discord.ui.button(label="Fechar atendimento", style=discord.ButtonStyle.red, emoji="🔒")
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await atendente_autorizado("suporte", interaction.user):
            return await interaction.response.send_message(
                embed=criar_embed("❌ Sem Permissão", "Só a equipe fecha o atendimento de depósito.", "Vermelho"),
                ephemeral=True)
        deposito = await self._deposito(interaction.channel.id)
        if deposito and deposito["status"] != "creditado":
            async with aiosqlite.connect(DATABASE_FILE) as db:
                await db.execute("UPDATE depositos SET status = 'cancelado' WHERE id = ?", (deposito["id"],))
                await db.commit()
        await interaction.response.send_message(
            embed=criar_embed("🔒 Atendimento encerrado", "Este canal será fechado em 10 segundos.", "Cinza Escuro"))
        await asyncio.sleep(10)
        try:
            await interaction.channel.delete()
        except Exception:
            pass


async def creditar_deposito(guild, deposito, origem: str, livepix_id: str = ""):
    """Credita o depósito na carteira + fecha o atendimento."""
    novo = await creditar_saldo(deposito["user_id"], deposito["guild_id"], arredondar(deposito["valor"]),
                                "deposito", f"Depósito PIX — {deposito['nome_pagador'] or origem}", ref=livepix_id or "")
    await registrar_caixa(deposito["guild_id"], "receita", arredondar(deposito["valor"]),
                          f"Depósito da carteira — #{deposito['id']}", ref=livepix_id or "")
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute("UPDATE depositos SET status = 'creditado', livepix_id = ?, creditado_em = ? WHERE id = ?",
                         (livepix_id, agora_brt().isoformat(), deposito["id"]))
        await db.commit()
    marcar_sujo()

    if not guild:
        return novo
    await registrar_log(guild, "💰 DEPÓSITO", "✅ Depósito creditado",
                        f"{mencao(deposito['user_id'])} depositou **{formatar_moeda(deposito['valor'])}**.\n"
                        f"> 💰 Saldo agora: `{formatar_moeda(novo)}`\n> ⚡ Origem: {origem}", "Esmeralda")
    # 📢 canal público de depósitos (se a equipe configurar um): todo mundo vê o PIX cair
    await anunciar(guild, "deposito", "✅ Depósito confirmado (PIX)",
                   f"{mencao(deposito['user_id'])} depositou **{formatar_moeda(deposito['valor'])}** "
                   f"e o saldo já caiu na carteira dele 💰\n"
                   f"> ⚡ Confirmação automática pela LivePix — sem ninguém clicar\n"
                   f"> 🎮 Já pode usar pra pagar o diário na hora!", "Esmeralda",
                   marcar=deposito["user_id"])
    canal = guild.get_channel(int(deposito["canal_id"])) if deposito.get("canal_id") else None
    if canal:
        try:
            await canal.send(
                content=mencao(deposito["user_id"]),
                embed=criar_embed("✅ Depósito confirmado!",
                                  f"Seu saldo de **{formatar_moeda(deposito['valor'])}** caiu na carteira.\n"
                                  f"> 💰 Saldo agora: `{formatar_moeda(novo)}`\n"
                                  f"> 🎮 Já pode usar pra pagar o diário! Este canal fecha em {DEPOSITO_FECHAR_SEGUNDOS}s.",
                                  "Esmeralda"))
            await asyncio.sleep(DEPOSITO_FECHAR_SEGUNDOS)
            await canal.delete()
        except Exception:
            pass
    return novo


# ---------- CUPONS: ANÚNCIO + ESGOTADO ----------

def _dados_cupom(cupom) -> str:
    if (cupom["tipo_desconto"] or "pct") == "pct":
        desconto = f"{cupom['valor']:g}% de desconto"
    else:
        desconto = f"{formatar_moeda(cupom['valor'])} de desconto"
    limites = []
    if cupom["usos_max"]:
        limites.append(f"{cupom['usos_max']} usos no total")
    if cupom["usos_por_user"]:
        limites.append(f"{cupom['usos_por_user']}x por pessoa")
    if cupom["expira_em"]:
        limites.append(f"válido até {str(cupom['expira_em'])[:16].replace('T', ' às ')}")
    return (f"**{desconto}** em qualquer diário\n"
            f"> 🎟️ **Como usar:** `/cupom {cupom['codigo']}` no seu canal de pagamento\n"
            f"> 📊 Limites: {', '.join(limites) if limites else 'sem limite'}")


async def anunciar_cupom(guild, cupom_id: int):
    """Manda o anúncio do cupom no canal configurado (marcando todo mundo)."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        cupom = await (await db.execute("SELECT * FROM cupons WHERE id = ?", (cupom_id,))).fetchone()
    if not cupom or not guild:
        return
    canal_id = await cfgv(guild.id, "canal_cupons", None)
    canal = guild.get_channel(int(canal_id)) if canal_id else None
    if not canal:
        return
    embed = criar_embed(
        f"🎟️ CUPOM NOVO — {cupom['codigo']}",
        f"{_dados_cupom(cupom)}\n\n"
        f"> ⚠️ Quando os usos acabarem, este cupom é **encerrado automaticamente**.\n"
        f"> 🏁 Corra e garanta sua vaga!",
        "Dourado", footer="🔥 Fire Force • Cupons")
    try:
        mensagem = await canal.send(content="@everyone", embed=embed)
        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute("UPDATE cupons SET msg_id = ?, canal_id = ? WHERE id = ?",
                             (mensagem.id, canal.id, cupom_id))
            await db.commit()
        marcar_sujo()
    except Exception as erro:
        _log_arquivo(f"[CUPOM] erro ao anunciar: {erro}")


async def encerrar_cupom(guild, cupom, motivo: str):
    """Fecha o cupom: edita o anúncio + avisa todo mundo uma única vez."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute("UPDATE cupons SET esgotado_avisado = 1, ativo = 0 WHERE id = ?", (cupom["id"],))
        await db.commit()
    marcar_sujo()

    canal_id = cupom["canal_id"] or await cfgv(guild.id, "canal_cupons", None)
    canal = guild.get_channel(int(canal_id)) if canal_id else None
    if canal:
        texto = ("🎟️ **CUPOM ESGOTADO** — não é mais válido. Fique ligado nos próximos! 🔥"
                 if motivo == "esgotado" else
                 "⌛ **CUPOM EXPIRADO** — não é mais válido. Fique ligado nos próximos! 🔥")
        try:
            if cupom["msg_id"]:
                mensagem = await canal.fetch_message(int(cupom["msg_id"]))
                embed = criar_embed(f"❌ {texto}", f"O cupom `{cupom['codigo']}` foi encerrado.", "Vermelho",
                                    footer="🔥 Fire Force • Cupons")
                await mensagem.edit(content="@everyone", embed=embed)
            else:
                await canal.send(content="@everyone", embed=criar_embed(f"❌ {texto}",
                                                                        f"O cupom `{cupom['codigo']}` foi encerrado.",
                                                                        "Vermelho"))
        except Exception:
            pass
    await registrar_log(guild, "🎟️ CUPOM", f"🎟️ Cupom {motivo}",
                        f"O cupom `{cupom['codigo']}` foi **{motivo}** e não pode mais ser usado.\n"
                        f"> 👥 Usos: `{cupom['usos_atuais']}`"
                        + (f"/{cupom['usos_max']}" if cupom["usos_max"] else ""),
                        "Vermelho")


async def loop_cupons():
    """Verifica cupons esgotados/expirados e encerra sozinho (edita o anúncio)."""
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            async with aiosqlite.connect(DATABASE_FILE) as db:
                db.row_factory = aiosqlite.Row
                cupons = await (await db.execute(
                    "SELECT * FROM cupons WHERE COALESCE(esgotado_avisado, 0) = 0"
                )).fetchall()
            for cupom in cupons:
                guild = bot.get_guild(cupom["guild_id"])
                if not guild:
                    continue
                esgotado = cupom["usos_max"] and cupom["usos_atuais"] >= cupom["usos_max"]
                expirado = False
                if cupom["expira_em"]:
                    try:
                        expirado = agora_brt() > datetime.datetime.fromisoformat(str(cupom["expira_em"]))
                    except Exception:
                        expirado = False
                if esgotado:
                    await encerrar_cupom(guild, cupom, "esgotado")
                elif expirado:
                    await encerrar_cupom(guild, cupom, "expirado")
        except Exception as erro:
            _log_arquivo(f"[CUPOM] erro no loop: {erro}")
        await asyncio.sleep(120)


# ---------- EVENTOS ----------

async def evento_ativo(guild_id: int, valor: float = None, tipo: str = None, categoria: str = None):
    """Evento rolando agora (e compatível com o diário, se informado)."""
    agora = agora_brt().isoformat()
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        eventos = await (await db.execute(
            "SELECT * FROM eventos WHERE guild_id = ? AND ativo = 1", (guild_id,)
        )).fetchall()
    for evento in eventos:
        if evento["fim_em"]:
            try:
                if agora_brt() > datetime.datetime.fromisoformat(str(evento["fim_em"])):
                    continue
            except Exception:
                pass
        if valor is not None and arredondar(evento["aposta_min"] or 0) > arredondar(valor):
            continue
        if tipo and evento["modos"] and str(evento["modos"]).lower() not in ("todos", "todas"):
            if tipo.lower() not in [m.strip().lower() for m in str(evento["modos"]).split(",") if m.strip()]:
                continue
        if categoria and evento["categorias"] and str(evento["categorias"]).lower() not in ("todas", "todos"):
            if categoria.lower() not in [c.strip().lower() for c in str(evento["categorias"]).split(",") if c.strip()]:
                continue
        return evento
    return None


async def registrar_participante(evento, slot_id: int, user_id: int, valor: float):
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute(
            "INSERT OR IGNORE INTO evento_participantes (evento_id, user_id, slot_id, valor, criado_em) "
            "VALUES (?, ?, ?, ?, ?)",
            (evento["id"], user_id, slot_id, arredondar(valor), agora_brt().isoformat()))
        await db.commit()
    marcar_sujo()


async def embed_evento(evento, guild) -> discord.Embed:
    premio = []
    if evento["kills_min"]:
        premio.append(f"{evento['kills_min']} kills")
    if evento["top_min"]:
        premio.append(f"top {evento['top_min']} na partida")
    embed = criar_embed(
        f"🎉 {evento['nome']}",
        f"{evento['descricao'] or ''}\n\n"
        f"> 💰 **Aposta mínima:** `{formatar_moeda(evento['aposta_min'])}`\n"
        f"> 🎯 **Conquiste:** {' ou '.join(premio) if premio else 'participar'}\n"
        f"> 🎁 **Bônus:** `{formatar_moeda(evento['bonus'])}` na carteira\n"
        f"> 🎮 **Modos:** `{evento['modos'] or 'todos'}` • **Categorias:** `{evento['categorias'] or 'todas'}`\n"
        + (f"> ⏳ **Termina:** `{str(evento['fim_em'])[:16].replace('T', ' às ')}`\n" if evento["fim_em"] else ""),
        "Dourado", footer="🔥 Fire Force • Evento")
    embed.add_field(
        name="📌 Como participar",
        value="> É automático! Se você comprar um diário dentro do valor mínimo, "
              "o bot já te coloca no evento e avisa aqui.", inline=False)
    if evento["msg_id"] and evento["canal_id"] and guild:
        embed.set_footer(text=f"🔥 Fire Force • Evento #{evento['id']}")
    return embed


async def avisar_eventos_nos_pagamentos():
    """Publica o card do evento no canal de pagamento de quem se inscreveu."""
    return True


# ---------- RANKINGS ----------

async def ranking_dados(guild_id: int, categoria: str, limite: int = 10) -> list:
    """Devolve [(user_id, valor)] para o ranking pedido."""
    categoria = {"vitorias": "vitórias", "victorias": "vitórias",
                 "transferências": "transferencias", "depósitos": "depositos"}.get(categoria, categoria)
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        if categoria == "saldo":
            linhas = await (await db.execute(
                "SELECT user_id, saldo AS valor FROM carteira WHERE guild_id = ? AND saldo > 0 "
                "ORDER BY saldo DESC LIMIT ?", (guild_id, limite))).fetchall()
        elif categoria == "transferencias":
            linhas = await (await db.execute(
                "SELECT user_id, COALESCE(SUM(valor), 0) AS valor FROM transacoes "
                "WHERE guild_id = ? AND tipo = 'transferencia_enviada' "
                "GROUP BY user_id ORDER BY valor DESC LIMIT ?", (guild_id, limite))).fetchall()
        elif categoria == "depositos":
            linhas = await (await db.execute(
                "SELECT user_id, COALESCE(SUM(valor), 0) AS valor FROM transacoes "
                "WHERE guild_id = ? AND tipo = 'deposito' "
                "GROUP BY user_id ORDER BY valor DESC LIMIT ?", (guild_id, limite))).fetchall()
        elif categoria == "ganhos":
            linhas = await (await db.execute(
                "SELECT user_id, COALESCE(SUM(valor), 0) AS valor FROM transacoes "
                "WHERE guild_id = ? AND tipo = 'ajuste' AND valor > 0 "
                "GROUP BY user_id ORDER BY valor DESC LIMIT ?", (guild_id, limite))).fetchall()
        elif categoria == "vitórias":
            linhas = await (await db.execute(
                "SELECT user_id, qtd AS valor FROM vitorias WHERE guild_id = ? AND qtd > 0 "
                "ORDER BY qtd DESC LIMIT ?", (guild_id, limite))).fetchall()
        elif categoria == "trabalho":
            linhas = await (await db.execute(
                "SELECT user_id, saldo AS valor FROM carteira_trabalho WHERE guild_id = ? AND saldo > 0 "
                "ORDER BY saldo DESC LIMIT ?", (guild_id, limite))).fetchall()
        else:
            linhas = []
    return [(l["user_id"], arredondar(l["valor"])) for l in linhas]


RANKING_TITULOS = {
    "saldo": ("💰 Mais saldo na carteira", "valor em R$", "saldo"),
    "transferencias": ("📤 Quem mais transferiu", "total transferido", "transferencias"),
    "depositos": ("⬆️ Quem mais depositou", "total depositado", "depositos"),
    "ganhos": ("🎁 Quem mais ganhou (equipe dando saldo)", "total ganho", "ganhos"),
    "vitórias": ("🏆 Quem mais venceu (top 1)", "vitórias", "vitorias"),
    "trabalho": ("💼 Carteira de trabalho (equipe)", "a receber no domingo", "trabalho"),
}


async def montar_embed_ranking(guild, categoria: str, limite: int = 10) -> discord.Embed:
    titulo, unidade, chave_busca = RANKING_TITULOS.get(categoria, ("📊 Ranking", "valor", "saldo"))
    dados = await ranking_dados(guild.id, chave_busca, limite)
    medalhas = ["🥇", "🥈", "🥉"]
    linhas = []
    for posicao, (uid, valor) in enumerate(dados, 1):
        icone = medalhas[posicao - 1] if posicao <= 3 else f"`{posicao}.`"
        if categoria in ("vitórias",):
            valor_txt = f"{int(valor)} vitória{'s' if int(valor) != 1 else ''}"
        else:
            valor_txt = formatar_moeda(valor)
        linhas.append(f"{icone} {mencao(uid)} — **{valor_txt}**")
    embed = criar_embed(titulo, "\n".join(linhas) or "> *Nada por aqui ainda. Bora jogar? 🔥*", "Dourado",
                        footer=f"🔥 Fire Force • {unidade} • atualizado agora")
    return embed


class RankingView(discord.ui.View):
    def __init__(self, categoria: str = "saldo"):
        super().__init__(timeout=None)
        self.categoria = categoria
        # 🔑 custom_id fixo = a view sobrevive a restart (bot.add_view exige isso)
        self.selecionar.custom_id = "ff_ranking_categoria"
        self.atualizar.custom_id = "ff_ranking_atualizar"
        for opcao in self.selecionar.options:
            opcao.default = (opcao.value == categoria)

    @discord.ui.select(placeholder="Escolha um ranking...", options=[
        discord.SelectOption(label="Mais saldo", value="saldo", emoji="💰"),
        discord.SelectOption(label="Mais transferências enviadas", value="transferencias", emoji="📤"),
        discord.SelectOption(label="Mais depósitos", value="depositos", emoji="⬆️"),
        discord.SelectOption(label="Mais ganhos (saldo dado)", value="ganhos", emoji="🎁"),
        discord.SelectOption(label="Mais vitórias (top 1)", value="vitórias", emoji="🏆"),
        discord.SelectOption(label="Carteira de trabalho (equipe)", value="trabalho", emoji="💼"),
    ])
    async def selecionar(self, interaction: discord.Interaction, select: discord.ui.Select):
        embed = await montar_embed_ranking(interaction.guild, select.values[0], 10)
        await interaction.response.edit_message(embed=embed, view=RankingView(select.values[0]))

    @discord.ui.button(label="Atualizar", style=discord.ButtonStyle.gray, emoji="🔄", row=1)
    async def atualizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = await montar_embed_ranking(interaction.guild, self.categoria, 10)
        await interaction.response.edit_message(embed=embed, view=RankingView(self.categoria))


# ---------- SAQUE v2 (tipo de chave + nome) ----------

class SaqueTipoView(discord.ui.View):
    def __init__(self, saldo: float, tipo_carteira: str):
        super().__init__(timeout=180)
        self.saldo = saldo
        self.tipo_carteira = tipo_carteira

    @discord.ui.select(placeholder="Escolha o tipo da sua chave PIX...", options=[
        discord.SelectOption(label="CPF/CNPJ", value="cpf", emoji="🪪"),
        discord.SelectOption(label="Celular", value="telefone", emoji="📱"),
        discord.SelectOption(label="E-mail", value="email", emoji="✉️"),
        discord.SelectOption(label="Chave aleatória", value="aleatoria", emoji="🔑"),
    ])
    async def tipo(self, interaction: discord.Interaction, select: discord.ui.Select):
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            salva = await (await db.execute(
                "SELECT * FROM chaves_salvas WHERE user_id = ? AND guild_id = ?",
                (interaction.user.id, interaction.guild.id))).fetchone()
        await interaction.response.send_modal(SaqueModal(
            tipo_chave=select.values[0], tipo_carteira=self.tipo_carteira,
            chave_salva=(salva["chave"] if salva and salva["tipo"] == select.values[0] else ""),
            titular_salvo=(salva["titular"] if salva else "")))

    @discord.ui.button(label="Usar minha chave salva", style=discord.ButtonStyle.green, emoji="⭐", row=1)
    async def usar_salva(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            salva = await (await db.execute(
                "SELECT * FROM chaves_salvas WHERE user_id = ? AND guild_id = ?",
                (interaction.user.id, interaction.guild.id))).fetchone()
        if not salva:
            return await interaction.response.send_message(
                embed=criar_embed("⭐ Sem chave salva", "Escolha o tipo e cadastre a sua chave uma vez.", "Amarelo"),
                ephemeral=True)
        await interaction.response.send_modal(SaqueModal(
            tipo_chave=salva["tipo"], tipo_carteira=self.tipo_carteira,
            chave_salva=salva["chave"], titular_salvo=salva["titular"] or ""))


async def _resolver_nome_pix(user_id: int, guild_id: int) -> str:
    """Sugere o nome usado no último depósito (pra ficar igual no PIX)."""
    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        linha = await (await db.execute(
            "SELECT nome_pagador FROM depositos WHERE guild_id = ? AND user_id = ? AND status = 'creditado' "
            "ORDER BY id DESC LIMIT 1", (guild_id, user_id))).fetchone()
    return (linha["nome_pagador"] if linha else "") or ""


# ==================== COMANDOS v10.1 (Supabase • Evento • Ranking • Equipe) ====================

@bot.tree.command(name="backup", description="☁️ Salvar o estado do bot no Supabase agora")
async def cmd_backup(interaction: discord.Interaction):
    if not await e_gerencia(interaction.user):
        return await interaction.response.send_message(
            embed=criar_embed("❌ Sem Permissão", "Apenas Dono, Gerente ou ADM.", "Vermelho"), ephemeral=True)
    await interaction.response.defer(ephemeral=True, thinking=True)
    mensagem = await salvar_estado(forcar=True)
    estruturas = await sincronizar_estruturado()
    embed = criar_embed("☁️ Backup", f"{mensagem}\n{estruturas}",
                        "Esmeralda" if mensagem.startswith("✅") else "Vermelho")
    embed.add_field(name="⚙️ Supabase", value=("> Configurado ✅" if supabase_configurado()
                                               else "> ❌ Não configurado (defina `SUPABASE_URL` e `SUPABASE_ANON_KEY`)"),
                    inline=False)
    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="restaurar", description="☁️ Restaurar o estado salvo no Supabase")
@app_commands.describe(forcar="Sobrescrever os dados atuais com o backup (sim/nao)")
@app_commands.choices(forcar=[app_commands.Choice(name="Sim, sobrescrever", value="sim"),
                              app_commands.Choice(name="Não, só se estiver vazio", value="nao")])
async def cmd_restaurar(interaction: discord.Interaction, forcar: Optional[app_commands.Choice[str]] = None):
    if not await e_gerencia(interaction.user):
        return await interaction.response.send_message(
            embed=criar_embed("❌ Sem Permissão", "Apenas Dono, Gerente ou ADM.", "Vermelho"), ephemeral=True)
    await interaction.response.defer(ephemeral=True, thinking=True)
    ok, mensagem = await carregar_estado(forcar=bool(forcar and forcar.value == "sim"))
    await interaction.followup.send(
        embed=criar_embed("☁️ Restauração", mensagem, "Esmeralda" if ok else "Amarelo"), ephemeral=True)


@bot.tree.command(name="dados", description="☁️ Ver o status da sincronização (Supabase, linhas, último envio)")
async def cmd_dados(interaction: discord.Interaction):
    if not await e_staff(interaction.user):
        return await interaction.response.send_message(
            embed=criar_embed("❌ Sem Permissão", "Apenas a equipe.", "Vermelho"), ephemeral=True)
    await interaction.response.defer(ephemeral=True, thinking=True)
    foto = await snapshot_dump()
    total = sum(len(t["linhas"]) for t in foto["tabelas"].values())
    pacote = len(_pacote(foto)) / 1024.0
    embed = criar_embed("☁️ Status dos dados", "", "Azul")
    embed.add_field(name="🗄️ Banco local", value=f"> `{DATABASE_FILE}`\n> {total} linhas em {len(foto['tabelas'])} tabelas",
                    inline=False)
    embed.add_field(name="📦 Tamanho do backup", value=f"> `{pacote:.0f} KB` (compactado)", inline=True)
    embed.add_field(name="☁️ Supabase", value=("> ✅ Configurado" if supabase_configurado() else "> ❌ Não configurado"),
                    inline=True)
    embed.add_field(name="🔄 Último envio", value=(f"> {int(time.time() - _sync_ultimo)}s atrás"
                                                   if _sync_ultimo else "> ainda não enviado"), inline=True)
    if _sync_erro:
        embed.add_field(name="⚠️ Último erro", value=f"> `{_sync_erro[:180]}`", inline=False)
    embed.add_field(
        name="🧱 Tabelas em tempo real (consulta no Supabase)",
        value="> `ff_config` — configurações do bot\n"
              "> `ff_cargos` — cargos (dono/gerente/mediador/suporte)\n"
              "> `ff_staff_online` — quem está ON agora\n"
              "> `ff_rankings` — tops (saldo, depósitos, ganhos, vitórias, comissões...)\n"
              + (f"> ✅ {_sql_linhas} linhas • enviado "
                 f"{int(time.time() - _sql_ultimo)}s atrás" if _sql_ultimo
                 else "> ⏳ ainda não enviadas (use `/backup`)")
              + (f"\n> ⚠️ `{_sql_erro[:150]}`" if _sql_erro else ""), inline=False)
    embed.add_field(name="💡 Como funciona",
                    value="> O bot salva sozinho a cada mudança (a cada ~60s) o **backup completo** "
                          "(`fireforce_estado`) e as **tabelas de leitura** (config, cargos, online, rankings). "
                          "Se a hospedagem reiniciar, ele **restaura tudo automaticamente** ao ligar. 🚀",
                    inline=False)
    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="evento", description="🎉 Criar e gerenciar eventos (bônus por kills/top)")
@app_commands.describe(acao="O que fazer", nome="Nome do evento (ex: Mega Evento Dia das Crianças)",
                       descricao="Descrição que aparece no anúncio", aposta_min="Valor mínimo do diário pra participar",
                       kills="Kills necessárias pra ganhar o bônus", bonus="Valor do bônus",
                       top="Bônus também pra quem ficar no top X (0 = desligado)",
                       modos="Modos (ex: solo,duo ou 'todos')", categorias="Categorias (premium,basico ou 'todas')",
                       horas="Duração em horas (ex: 24)", usuario="Jogador (pro resultado)",
                       posicao="Posição final dele na partida (1 = vitória)")
@app_commands.choices(acao=[app_commands.Choice(name="Criar evento", value="criar"),
                            app_commands.Choice(name="Encerrar evento", value="encerrar"),
                            app_commands.Choice(name="Listar participantes", value="lista"),
                            app_commands.Choice(name="Registrar resultado", value="resultado")])
async def cmd_evento(interaction: discord.Interaction, acao: app_commands.Choice[str],
                     nome: Optional[str] = None, descricao: Optional[str] = None,
                     aposta_min: Optional[str] = None, kills: Optional[int] = None,
                     bonus: Optional[str] = None, top: Optional[int] = None,
                     modos: Optional[str] = None, categorias: Optional[str] = None,
                     horas: Optional[int] = None, usuario: Optional[discord.Member] = None,
                     posicao: Optional[int] = None):
    if not await e_gerencia(interaction.user):
        return await interaction.response.send_message(
            embed=criar_embed("❌ Sem Permissão", "Só Dono, Gerente ou ADM mexe em evento.", "Vermelho"), ephemeral=True)

    # ---------- ENCERRAR ----------
    if acao.value == "encerrar":
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            evento = await (await db.execute(
                "SELECT * FROM eventos WHERE guild_id = ? AND ativo = 1 ORDER BY id DESC LIMIT 1",
                (interaction.guild.id,))).fetchone()
            if not evento:
                return await interaction.response.send_message(
                    embed=criar_embed("ℹ️ Nada rolando", "Não tem evento ativo agora.", "Amarelo"), ephemeral=True)
            await db.execute("UPDATE eventos SET ativo = 0 WHERE id = ?", (evento["id"],))
            await db.commit()
        marcar_sujo()
        canal = interaction.guild.get_channel(evento["canal_id"]) if evento["canal_id"] else None
        if canal:
            try:
                if evento["msg_id"]:
                    msg = await canal.fetch_message(int(evento["msg_id"]))
                    await msg.edit(embed=criar_embed(f"🏁 {evento['nome']} — ENCERRADO",
                                                     "Esse evento chegou ao fim. Obrigado a todos que participaram! 🔥",
                                                     "Cinza Escuro"))
                else:
                    await canal.send(embed=criar_embed(f"🏁 {evento['nome']} — ENCERRADO",
                                                       "Obrigado a todos que participaram! 🔥", "Cinza Escuro"))
            except Exception:
                pass
        return await interaction.response.send_message(
            embed=criar_embed("🏁 Evento encerrado", f"**{evento['nome']}** foi finalizado.", "Amarelo"),
            ephemeral=True)

    # ---------- LISTA ----------
    if acao.value == "lista":
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            evento = await (await db.execute(
                "SELECT * FROM eventos WHERE guild_id = ? ORDER BY id DESC LIMIT 1", (interaction.guild.id,))).fetchone()
            if not evento:
                return await interaction.response.send_message(
                    embed=criar_embed("ℹ️ Nenhum evento", "Crie um com `/evento acao:Criar evento`.", "Amarelo"),
                    ephemeral=True)
            participantes = await (await db.execute(
                "SELECT * FROM evento_participantes WHERE evento_id = ? ORDER BY id", (evento["id"],))).fetchall()
        linhas = "\n".join(
            f"> {mencao(p['user_id'])} — `{formatar_moeda(p['valor'])}`"
            + (f" • {p['kills']} kills" if p["kills"] else "")
            + (f" • top {p['posicao']}" if p["posicao"] else "")
            + (f" • bônus `{formatar_moeda(p['bonus_pago'])}`" if p["bonus_pago"] else "")
            for p in participantes[:30]) or "> *Ninguém participou ainda.*"
        return await interaction.response.send_message(
            embed=criar_embed(f"🎉 {evento['nome']} — participantes ({len(participantes)})",
                              f"{linhas}\n\n> 💰 Aposta mínima `{formatar_moeda(evento['aposta_min'])}` • "
                              f"🎯 {evento['kills_min']} kills • 🎁 bônus `{formatar_moeda(evento['bonus'])}`",
                              "Dourado", footer="🔥 Fire Force • Evento"), ephemeral=True)

    # ---------- RESULTADO ----------
    if acao.value == "resultado":
        if not usuario:
            return await interaction.response.send_message(
                embed=criar_embed("❌ Falta o jogador", "Use `/evento acao:Registrar resultado usuario:@jogador kills:3 posicao:1`.",
                                  "Vermelho"), ephemeral=True)
        async with aiosqlite.connect(DATABASE_FILE) as db:
            db.row_factory = aiosqlite.Row
            evento = await (await db.execute(
                "SELECT * FROM eventos WHERE guild_id = ? ORDER BY id DESC LIMIT 1", (interaction.guild.id,))).fetchone()
            if not evento:
                return await interaction.response.send_message(
                    embed=criar_embed("ℹ️ Nenhum evento", "Crie um evento primeiro.", "Amarelo"), ephemeral=True)
            participante = await (await db.execute(
                "SELECT * FROM evento_participantes WHERE evento_id = ? AND user_id = ?",
                (evento["id"], usuario.id))).fetchone()
            if not participante:
                return await interaction.response.send_message(
                    embed=criar_embed("⚠️ Fora do evento",
                                      f"{usuario.mention} não entrou no evento (não comprou diário dentro do mínimo).",
                                      "Amarelo"), ephemeral=True)

        kills_j = int(kills or 0)
        posicao_j = int(posicao or 0)
        ganhou = (kills_j >= int(evento["kills_min"] or 0)) or \
                 (int(evento["top_min"] or 0) > 0 and 0 < posicao_j <= int(evento["top_min"]))
        valor_bonus = arredondar(evento["bonus"]) if ganhou else 0.0

        async with aiosqlite.connect(DATABASE_FILE) as db:
            await db.execute(
                "UPDATE evento_participantes SET kills = ?, posicao = ?, bonus_pago = ? "
                "WHERE evento_id = ? AND slot_id = ?",
                (kills_j, posicao_j, valor_bonus, evento["id"], participante["slot_id"]))
            await db.commit()
        marcar_sujo()

        if valor_bonus > 0:
            await creditar_saldo(usuario.id, interaction.guild.id, valor_bonus, "premio",
                                 f"Bônus do evento {evento['nome']} ({kills_j} kills"
                                 + (f", top {posicao_j}" if posicao_j else "") + ")",
                                 ref=f"evento:{evento['id']}")
            await registrar_caixa(interaction.guild.id, "despesa", valor_bonus,
                                  f"Bônus de evento — {evento['nome']}", ref=f"evento:{evento['id']}")
        if posicao_j == 1:
            async with aiosqlite.connect(DATABASE_FILE) as db:
                await db.execute("INSERT INTO vitorias (user_id, guild_id, qtd) VALUES (?, ?, 1) "
                                 "ON CONFLICT(user_id, guild_id) DO UPDATE SET qtd = qtd + 1",
                                 (usuario.id, interaction.guild.id))
                await db.commit()
            marcar_sujo()

        embed = criar_embed(
            "🎉 Resultado do evento",
            f"**{usuario.mention}** — `{kills_j}` kills" + (f" • `top {posicao_j}`" if posicao_j else "") + "\n\n"
            + (f"> 🎁 **Bônus pago: `{formatar_moeda(valor_bonus)}`** na carteira!" if valor_bonus > 0
               else "> 😕 Não atingiu o requisito — dessa vez não teve bônus."),
            "Esmeralda" if valor_bonus > 0 else "Amarelo")
        if posicao_j == 1:
            embed.add_field(name="🏆 Vitória registrada", value="> +1 no ranking de vitórias!", inline=False)
        await interaction.response.send_message(embed=embed)
        await registrar_log(
            interaction.guild, "🎉 EVENTO", f"🎉 Resultado — {evento['nome']}",
            f"{mencao(usuario.id)}: `{kills_j}` kills"
            + (f" • top `{posicao_j}`" if posicao_j else "") + "\n"
            f"> 🎁 Bônus pago: `{formatar_moeda(valor_bonus)}`", "Dourado")
        return

    # ---------- CRIAR ----------
    if not nome:
        return await interaction.response.send_message(
            embed=criar_embed("❌ Falta o nome", "Use `/evento acao:Criar evento nome:Mega Evento ...`.", "Vermelho"),
            ephemeral=True)

    valor_min = parse_valor(aposta_min or "10") or 10.0
    valor_bonus = parse_valor(bonus or "5") or 5.0
    kills_min = int(kills if kills is not None else 3)
    top_min = int(top or 0)
    modos_txt = (modos or "todos").strip()
    categorias_txt = (categorias or "todas").strip()
    fim = (agora_brt() + datetime.timedelta(hours=int(horas or 24))).isoformat() if (horas or 24) > 0 else None

    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute("UPDATE eventos SET ativo = 0 WHERE guild_id = ? AND ativo = 1", (interaction.guild.id,))
        cursor = await db.execute(
            "INSERT INTO eventos (guild_id, nome, descricao, aposta_min, kills_min, bonus, top_min, modos, "
            "categorias, ativo, criado_em, fim_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (interaction.guild.id, nome, descricao or "", valor_min, kills_min, valor_bonus, top_min,
             modos_txt, categorias_txt, agora_brt().isoformat(), fim))
        evento_id = cursor.lastrowid
        await db.commit()
        db.row_factory = aiosqlite.Row
        evento = await (await db.execute("SELECT * FROM eventos WHERE id = ?", (evento_id,))).fetchone()
    marcar_sujo()

    canal_id = await cfgv(interaction.guild.id, "canal_eventos", None)
    canal = interaction.guild.get_channel(int(canal_id)) if canal_id else None
    anuncio = None
    if canal:
        embed_anuncio = await embed_evento(evento, interaction.guild)
        try:
            anuncio = await canal.send(content="@everyone", embed=embed_anuncio)
            async with aiosqlite.connect(DATABASE_FILE) as db:
                await db.execute("UPDATE eventos SET canal_id = ?, msg_id = ? WHERE id = ?",
                                 (canal.id, anuncio.id, evento_id))
                await db.commit()
        except Exception:
            anuncio = None
    elif not canal_id:
        pass

    resumo = criar_embed(
        "🎉 Evento criado!",
        f"**{nome}** está rolando!\n\n"
        f"> 💰 Aposta mínima: `{formatar_moeda(valor_min)}`\n"
        f"> 🎯 Conquista: `{kills_min}` kills"
        + (f" ou `top {top_min}`" if top_min else "") + "\n"
        f"> 🎁 Bônus: `{formatar_moeda(valor_bonus)}`\n"
        f"> 🎮 Modos: `{modos_txt}` • Categorias: `{categorias_txt}`\n"
        f"> ⏳ Duração: `{int(horas or 24)}h`\n\n"
        + (f"> 📣 Anunciado em {canal.mention} marcando todo mundo!" if anuncio
           else "> 💡 Configure o canal de eventos com `/config canal_eventos:#canal` pra anunciar sozinho."),
        "Dourado", footer=f"Fire Force • Evento #{evento_id}")
    await interaction.response.send_message(embed=resumo)
    await registrar_log(
        interaction.guild, "🎉 EVENTO", f"🎉 Evento criado — {nome}",
        f"Por {interaction.user.mention}\n> 💰 mín `{formatar_moeda(valor_min)}` • 🎯 `{kills_min}` kills"
        f" • 🎁 `{formatar_moeda(valor_bonus)}` • 🎮 `{modos_txt}`", "Dourado")


@bot.tree.command(name="painelranking", description="🏆 Publicar o painel de rankings no canal")
async def cmd_painelranking(interaction: discord.Interaction):
    if not await e_gerencia(interaction.user):
        return await interaction.response.send_message(
            embed=criar_embed("❌ Sem Permissão", "Só Dono, Gerente ou ADM.", "Vermelho"), ephemeral=True)
    embed = await montar_embed_ranking(interaction.guild, "saldo", 10)
    embed.description = (embed.description or "") + \
        "\n\n> 🎛️ **Escolha o ranking no menu abaixo** e clique em 🔄 pra atualizar."
    await interaction.response.send_message(embed=embed, view=RankingView("saldo"))
    await registrar_log(interaction.guild, "🏆 RANKING", "🏆 Painel de rankings publicado",
                        f"Por {interaction.user.mention} em {interaction.channel.mention}.", "Azul")


@bot.tree.command(name="vitoria", description="🏆 Registrar uma vitória (top 1) no ranking de um jogador")
@app_commands.describe(usuario="Quem venceu", quantidade="Quantas vitórias registrar (padrão 1)")
async def cmd_vitoria(interaction: discord.Interaction, usuario: discord.Member, quantidade: Optional[int] = 1):
    if not await e_staff(interaction.user):
        return await interaction.response.send_message(
            embed=criar_embed("❌ Sem Permissão", "Apenas a equipe registra vitórias.", "Vermelho"), ephemeral=True)
    quantidade = max(1, int(quantidade or 1))
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute("INSERT INTO vitorias (user_id, guild_id, qtd) VALUES (?, ?, ?) "
                         "ON CONFLICT(user_id, guild_id) DO UPDATE SET qtd = qtd + ?",
                         (usuario.id, interaction.guild.id, quantidade, quantidade))
        await db.commit()
        total = (await (await db.execute("SELECT qtd FROM vitorias WHERE user_id = ? AND guild_id = ?",
                                         (usuario.id, interaction.guild.id))).fetchone())[0]
    marcar_sujo()
    await interaction.response.send_message(
        embed=criar_embed("🏆 Vitória registrada!",
                          f"{usuario.mention} agora tem **{total}** vitória{'s' if total != 1 else ''} "
                          f"(+{quantidade}). 🔥", "Dourado"))
    await registrar_log(interaction.guild, "🏆 RANKING", "🏆 Vitória registrada",
                        f"{usuario.mention} +{quantidade} vitória(s) — total `{total}` (por {interaction.user.mention}).",
                        "Dourado")


@bot.tree.command(name="trabalho", description="💼 Ver sua carteira de trabalho (equipe) e quando o dinheiro é pago")
@app_commands.describe(usuario="Ver a de outra pessoa (gerência)")
async def cmd_trabalho(interaction: discord.Interaction, usuario: Optional[discord.Member] = None):
    alvo = usuario or interaction.user
    if usuario and usuario.id != interaction.user.id and not await e_gerencia(interaction.user):
        return await interaction.response.send_message(
            embed=criar_embed("❌ Sem Permissão", "Você só pode ver a sua.", "Vermelho"), ephemeral=True)

    saldo = await saldo_trabalho(alvo.id, interaction.guild.id)
    extrato = await extrato_trabalho(alvo.id, interaction.guild.id, 10)
    dia = int(await cfgv(interaction.guild.id, "dia_fechamento", 0))
    dias = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
    embed = criar_embed(
        f"💼 Carteira de trabalho — {alvo.display_name}",
        f"**A receber:** `{formatar_moeda(saldo)}`\n"
        f"**Fechamento:** toda **{dias[dia]}** à meia-noite (o saldo é zerado e você saca no domingo)\n\n"
        f"**Últimos ganhos:**\n{extrato}",
        "Dourado")
    embed.add_field(name="🧾 Como você ganha",
                    value="> 💸 **Comissão 25%** por pagamento que você aprova/assume\n"
                          "> ⭐ **Avaliação do atendimento** (0★ = R$ 0,00 até 5★ = R$ 2,50)\n"
                          "> 💸 Saque com `/saque` — liberado no domingo (quantas vezes quiser)", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.event
async def on_ready():
    await init_db()

    bot.add_view(TicketPainelView())
    # (os botões de controle DENTRO de cada ticket são restaurados logo abaixo,
    #  um por ticket aberto, com TicketView(id) — não existe view sem id pra eles)
    bot.add_view(StaffPainelView())

    async with aiosqlite.connect(DATABASE_FILE) as db:
        db.row_factory = aiosqlite.Row
        
        paineis = await (await db.execute("SELECT DISTINCT painel_id FROM horarios WHERE ativo = 1")).fetchall()
        for p in paineis:
            for guild in bot.guilds:
                try:
                    await rebuild_painel(guild, p["painel_id"])
                except Exception:
                    pass

        slots_pendentes = await (await db.execute("SELECT * FROM slots WHERE confirmado = 0")).fetchall()
        for s in slots_pendentes:
            bot.add_view(PagamentoAcaoView())

        saques_abertos = await (await db.execute(
            "SELECT id FROM saques WHERE status IN ('na_fila', 'liberado')")).fetchall()
        for linha_saque in saques_abertos:
            bot.add_view(SaqueAcaoView(linha_saque["id"]))

        # 🎧 atendimentos abertos voltam funcionando depois de qualquer restart
        tickets_abertos = await (await db.execute(
            "SELECT id FROM tickets WHERE status = 'aberto'")).fetchall()
        for linha_ticket in tickets_abertos:
            bot.add_view(TicketView(linha_ticket["id"]))

        depositos_abertos = await (await db.execute(
            "SELECT id FROM depositos WHERE status IN ('aguardando', 'na_janela')")).fetchall()
        for linha_deposito in depositos_abertos:
            bot.add_view(DepositoCanalView(linha_deposito["id"]))

        bot.add_view(RankingView("saldo"))
    bot.add_view(FilaPagamentoView())          # 💸 painel da fila de pagamento

    try:
        sincronizados = await bot.tree.sync()
        print(f"  ✅ {len(sincronizados)} comandos Slash sincronizados com sucesso!")
    except Exception as e:
        print("Erro ao sincronizar comandos:", e)

    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name="🔥 Liga de Diário FF (BRT)"),
        status=discord.Status.online
    )

    # 🩺 ficou fora? reconfere TUDO antes de o loop de expiração apagar reserva antiga
    fora = await tempo_fora()
    if fora >= RECUPERAR_MIN:
        try:
            await recuperar_apos_queda(fora)
        except Exception as erro:
            _log_arquivo(f"[RECUPERAÇÃO] geral: {erro}")
    await _pulso_periodico(forcar=True)

    bot.loop.create_task(loop_expirar())
    bot.loop.create_task(loop_salas())
    bot.loop.create_task(loop_tabelas())
    bot.loop.create_task(loop_livepix())
    bot.loop.create_task(loop_fila_pagamento())
    bot.loop.create_task(loop_relatorio())
    bot.loop.create_task(loop_sync())
    bot.loop.create_task(loop_cupons())
    bot.loop.create_task(loop_fechamento_semanal())

    print(f"""
  ╔══════════════════════════════════════════╗
  ║     🔥  F I R E   F O R C E  🔥          ║
  ║            v 1 0 . 0  P R O              ║
  ╠══════════════════════════════════════════╣
  ║  Bot conectado como: {bot.user}
  ║  Servidores conectados: {len(bot.guilds)}
  ║  Fuso Horário: Brasília (UTC-3)
  ║  Status: ONLINE E PRONTO! ✅
  ╚══════════════════════════════════════════╝
    """)


@bot.event
async def on_guild_join(guild: discord.Guild):
    for canal in guild.text_channels:
        if canal.permissions_for(guild.me).send_messages:
            embed = criar_embed(
                "🔥 Fire Force Conectado!",
                "Obrigado por me adicionar ao servidor!\n\n"
                "**Primeiros Passos:**\n"
                "> 1️⃣ Execute `/setup` para configurar os cargos e categorias\n"
                "> 2️⃣ Use `/help` para ver o manual completo de comandos",
                "Fire Force"
            )
            await canal.send(embed=embed)
            break


def _token_do_ambiente():
    """Token do arquivo ou das variáveis de ambiente do host (DISCORD_TOKEN/TOKEN)."""
    token = (TOKEN or "").strip()
    if token and token.upper() not in ("SEU_TOKEN_AQUI", "TOKEN", "COLE_SEU_TOKEN_AQUI"):
        return token
    return (os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN") or "").strip()


def _problema_no_token(token: str) -> Optional[str]:
    """Explica o que está errado ANTES de tentar conectar (sem traceback feio)."""
    if not token:
        return 'O TOKEN ainda não foi configurado — o arquivo está com "SEU_TOKEN_AQUI".'
    if token.count(".") != 2 or len(token) < 50:
        return ("O TOKEN parece incompleto ou colado errado. Ele tem 3 partes "
                "separadas por ponto e costuma ter 70+ caracteres.")
    return None


def _run():
    print(f"\n  🔥 Iniciando Fire Force Pro v{VERSAO_BOT}...")
    print("  📦 Dependências: pip install discord.py qrcode[pil] aiosqlite Pillow aiohttp")

    token = _token_do_ambiente()
    problema = _problema_no_token(token)
    if problema:
        print("\n  ❌ NÃO DEU PRA LIGAR O BOT")
        print(f"  ➜ {problema}")
        print("\n  COMO RESOLVER (2 minutinhos):")
        print("   1️⃣  Abra discord.com/developers/applications → escolha seu app")
        print('   2️⃣  Menu lateral: Bot → botão "Reset Token" → copie o token')
        print('   3️⃣  Cole no fireforce_bot.py na linha:  TOKEN = "cole_aqui"')
        print("       (ou crie a variável de ambiente DISCORD_TOKEN no host)")
        print("   4️⃣  Salve e rode de novo:  python fireforce_bot.py\n")
        return

    try:
        bot.run(token)
    except discord.LoginFailure:
        print("\n  ❌ TOKEN INVÁLIDO — o Discord recusou o login.")
        print("  ➜ O token foi resetado, expirou ou foi copiado errado.")
        print("  ➜ Gere outro em discord.com/developers → seu app → Bot → Reset Token")
        print("    e cole de novo no fireforce_bot.py (linha do TOKEN).\n")
    except discord.PrivilegedIntentsRequired:
        print("\n  ❌ O portal do bot está com intents privilegiadas LIGADAS.")
        print("  ➜ O Fire Force não usa nenhuma. Em discord.com/developers → seu app →")
        print("    Bot → Privileged Gateway Intents, desligue as TRÊS opções.\n")
    except Exception as erro:
        print(f"\n  ❌ Erro ao ligar o bot: {type(erro).__name__}: {erro}")
        print("  ➜ Confira a internet do host/PC e rode de novo.\n")
    finally:
        try:
            _loop_final = asyncio.new_event_loop()
            if supabase_configurado():
                try:
                    print("  ☁️ Salvando os dados no Supabase antes de sair...")
                    _loop_final.run_until_complete(salvar_estado(forcar=True))
                except Exception as erro:
                    print(f"  ☁️ Não deu pra salvar agora: {erro}")
            _loop_final.run_until_complete(_ff_fechar_sessao())
            _loop_final.close()
        except Exception:
            pass


if __name__ == "__main__":
    # emojis nunca quebram o console do Windows
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    _run()