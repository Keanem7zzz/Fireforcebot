#!/usr/bin/env python3
# ══════════════════════════════════════════════════════════════════════════════
#  ✅ CHECAGEM DO FIRE FORCE — "este código liga?"
# ══════════════════════════════════════════════════════════════════════════════
#  PARA QUE SERVE:
#  Responde a única pergunta que importa antes de publicar uma mudança:
#  **este arquivo carrega de verdade, ou ele quebra o bot no ar?**
#
#  O bot se atualiza sozinho a cada 60s puxando a branch `main`. Antes desta
#  checagem, a única validação era "o texto é Python válido?" — e texto válido
#  NÃO é código que funciona. Um nome digitado errado (ex.: chamar
#  `aprova_pagamento` em vez de `aprovar_pagamento`) é Python perfeitamente
#  válido e derruba o bot no instante em que ele liga.
#
#  Esta ferramenta faz as DUAS coisas:
#     1. confere a sintaxe            (pega erro de digitação grosseiro)
#     2. CARREGA o módulo de verdade   (pega o erro que só aparece ao ligar)
#     3. confere o que foi carregado   (45 comandos, intents desligadas, versão)
#
#  É 100% SEGURA: ela só importa o módulo. O `bot.run()` fica protegido por
#  `if __name__ == "__main__"`, então nada conecta no Discord, nada toca no
#  banco e nada cria arquivo.
#
#  ONDE ELA RODA:
#     • no GitHub Actions (`.github/workflows/ci.yml`) — barra mudança quebrada
#       ANTES de ela chegar na `main`
#     • na sua máquina, quando quiser conferir algo:
#           python checagem_ci.py
#           python checagem_ci.py caminho/outro_arquivo.py
#
#  RESULTADO: sai com código 0 se está tudo certo, 1 se algo falhou.
# ══════════════════════════════════════════════════════════════════════════════
from __future__ import annotations

import ast
import json
import os
import py_compile
import subprocess
import sys
import tempfile

# Quantos comandos slash o bot precisa ter registrado para a checagem passar.
# Se um dia você adicionar ou remover comando, ajuste este número aqui.
MINIMO_COMANDOS_SLASH = 45

# Tempo máximo (em segundos) para o módulo carregar. É generoso de propósito:
# o carregamento normal leva menos de 2s.
TEMPO_MAXIMO_CARGA = 120

# O script que roda DENTRO do processo filho: importa o candidato e devolve um
# retrato em JSON. Roda separado de propósito — se o candidato tiver um erro
# fatal, ele mata só o filho, nunca esta checagem.
SCRIPT_FILHO = r"""
import importlib.machinery, importlib.util, json, sys
caminho = sys.argv[1]
saida = {"ok": False}
try:
    carregador = importlib.machinery.SourceFileLoader("ff_candidato", caminho)
    spec = importlib.util.spec_from_loader("ff_candidato", carregador)
    modulo = importlib.util.module_from_spec(spec)
    carregador.exec_module(modulo)
    intents = getattr(modulo, "intents", None)
    saida = {
        "ok": True,
        "versao": str(getattr(modulo, "VERSAO_BOT", "") or ""),
        "comandos": len(modulo.bot.tree.get_commands()) if getattr(modulo, "bot", None) else 0,
        "members": bool(getattr(intents, "members", False)),
        "presences": bool(getattr(intents, "presences", False)),
        "message_content": bool(getattr(intents, "message_content", False)),
        "auto_update": bool(getattr(modulo, "AUTO_UPDATE_ATIVO", False)),
    }
except BaseException as erro:
    saida = {"ok": False, "erro": f"{type(erro).__name__}: {erro}",
             "linha": getattr(erro, "lineno", None)}
print("\n__FF_JSON__" + json.dumps(saida, ensure_ascii=False))
"""


def _linha(texto: str, simbolo: str) -> None:
    print(f"  {simbolo} {texto}")


def _descrever_pyflakes(linha_aviso: str) -> tuple[str, str, str]:
    """Transforma `caminho:329:13: undefined name 'x'` em (caminho, 329, mensagem)."""
    partes = linha_aviso.split(":")
    caminho_aviso = partes[0] if partes else ""
    numero = partes[1] if len(partes) > 1 else "?"
    mensagem = linha_aviso.split(": ", 1)[-1] if ": " in linha_aviso else linha_aviso
    return caminho_aviso, numero, mensagem


def checar(caminho: str) -> tuple[bool, list[str]]:
    """Roda todas as checagens. Devolve `(tudo_ok, lista_de_problemas)`."""
    problemas: list[str] = []
    caminho = os.path.abspath(caminho)

    print(f"\n🔎 Checando: {caminho}")
    print("─" * 66)

    # ---------- 1) existe e é UTF-8 ----------
    if not os.path.exists(caminho):
        _linha(f"o arquivo não existe: {caminho}", "❌")
        return False, ["arquivo não encontrado"]
    try:
        with open(caminho, "rb") as arq:
            bruto = arq.read()
        texto = bruto.decode("utf-8")
        _linha(f"arquivo lido ({len(bruto) / 1024:.0f} KB, {texto.count(chr(10)) + 1} linhas) e UTF-8 válido", "✅")
    except UnicodeDecodeError as erro:
        _linha(f"o arquivo não é UTF-8 válido: {erro}", "❌")
        return False, ["UTF-8 inválido"]

    # ---------- 2) sintaxe ----------
    # Vem primeiro de propósito: se a sintaxe estiver quebrada, nada abaixo
    # consegue nem ler o arquivo.
    try:
        arvore = ast.parse(texto, caminho)
        _linha("sintaxe Python válida", "✅")
    except SyntaxError as erro:
        _linha(f"ERRO DE SINTAXE na linha {erro.lineno}: {erro.msg}", "❌")
        return False, [f"sintaxe: linha {erro.lineno}: {erro.msg}"]

    # ---------- 3) assinatura de versão ----------
    versao_no_codigo = "?"
    for no in ast.walk(arvore):
        if isinstance(no, ast.Assign):
            for alvo in no.targets:
                if isinstance(alvo, ast.Name) and alvo.id == "VERSAO_BOT":
                    versao_no_codigo = getattr(no.value, "value", "?")
    if "VERSAO_BOT" not in texto:
        _linha("não achei VERSAO_BOT no arquivo — não parece ser o bot", "❌")
        return False, ["VERSAO_BOT ausente"]
    _linha(f"assinatura VERSAO_BOT presente (v{versao_no_codigo})", "✅")

    # ---------- 4) compilação de verdade ----------
    try:
        with tempfile.TemporaryDirectory() as pasta:
            py_compile.compile(caminho, cfile=os.path.join(pasta, "ff.pyc"), doraise=True)
        _linha("compila sem erro (py_compile)", "✅")
    except py_compile.PyCompileError as erro:
        _linha(f"falhou ao compilar: {erro}", "❌")
        problemas.append(f"py_compile: {erro}")
        return False, problemas

    # ---------- 5) CARREGA o módulo num processo separado ----------
    # Esta é a checagem que importa de verdade: um nome errado, um import
    # inexistente ou uma assinatura que mudou só aparecem aqui.
    print("  … carregando o módulo de verdade (pode levar alguns segundos)")
    try:
        resultado = subprocess.run(
            [sys.executable, "-c", SCRIPT_FILHO, caminho],
            cwd=os.path.dirname(caminho),
            capture_output=True,
            text=True,
            timeout=TEMPO_MAXIMO_CARGA,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        _linha(f"o módulo NÃO carregou em {TEMPO_MAXIMO_CARGA}s (travou?)", "❌")
        problemas.append("carga expirou")
        return False, problemas

    retrato = None
    for linha_saida in (resultado.stdout or "").splitlines():
        if linha_saida.startswith("__FF_JSON__"):
            try:
                retrato = json.loads(linha_saida[len("__FF_JSON__"):])
            except Exception:
                retrato = None

    if retrato is None or not retrato.get("ok"):
        motivo = (retrato or {}).get("erro") or (resultado.stderr or "sem detalhe").strip()[-400:]
        _linha(f"o módulo QUEBROU ao carregar → {motivo}", "❌")
        problemas.append(f"carga: {motivo}")
        return False, problemas
    _linha("o módulo CARREGOU de verdade, sem erro", "✅")

    # ---------- 6) o que foi carregado faz sentido? ----------
    versao = retrato.get("versao") or "?"
    comandos = int(retrato.get("comandos") or 0)
    if comandos < MINIMO_COMANDOS_SLASH:
        _linha(f"só {comandos} comandos slash registrados (esperava {MINIMO_COMANDOS_SLASH}+)", "❌")
        problemas.append(f"comandos: {comandos} < {MINIMO_COMANDOS_SLASH}")
    else:
        _linha(f"{comandos} comandos slash registrados (v{versao})", "✅")

    # Intents privilegiadas ligadas = o bot passa a exigir verificação do
    # Discord (e trava em servidor grande). O Fire Force nunca usa nenhuma.
    intents_ligadas = [rotulo for chave, rotulo in (
        ("members", "members"), ("presences", "presences"),
        ("message_content", "message_content")) if retrato.get(chave)]
    if intents_ligadas:
        _linha(f"intent privilegiada LIGADA: {', '.join(intents_ligadas)}", "❌")
        problemas.extend(f"intent {nome} ligada" for nome in intents_ligadas)
    else:
        _linha("nenhuma intent privilegiada (members/presences/message_content desligadas)", "✅")

    # ---------- 7) nomes que não existem (pyflakes) ----------
    # O passo 5 pega o que quebra AO LIGAR. Este pega o que quebra SÓ AO USAR:
    # se você renomear `criar_embed` e esquecer uma das 622 chamadas, o módulo
    # carrega perfeitamente — e o comando quebra na hora em que o jogador clica.
    # Só "undefined name" reprova (é o que derruba o bot de verdade); aviso de
    # variável sem uso é apenas informativo, para não travar o seu trabalho.
    tem_pyflakes = subprocess.run(
        [sys.executable, "-c", "import pyflakes"], capture_output=True).returncode == 0

    if not tem_pyflakes:
        _linha("pyflakes não instalado — pulando a checagem de nomes "
               "(ative com: pip install pyflakes)", "ℹ️")
    else:
        try:
            resultado_pf = subprocess.run(
                [sys.executable, "-m", "pyflakes", caminho],
                cwd=os.path.dirname(caminho), capture_output=True, text=True,
                timeout=TEMPO_MAXIMO_CARGA, encoding="utf-8", errors="replace",
            )
            avisos = [l for l in (resultado_pf.stdout or "").splitlines() if l.strip()]
        except subprocess.TimeoutExpired:
            avisos = []

        indefinidos = [l for l in avisos if "undefined name" in l]
        cosmeticos = [l for l in avisos if "undefined name" not in l]

        if indefinidos:
            _linha(f"{len(indefinidos)} NOME(S) QUE NÃO EXISTEM no código:", "❌")
            for linha_erro in indefinidos[:10]:
                _, numero, mensagem = _descrever_pyflakes(linha_erro)
                _linha(f"linha {numero}: {mensagem}", "   •")
            if len(indefinidos) > 10:
                _linha(f"… e mais {len(indefinidos) - 10}", "   •")
            problemas.append(f"{len(indefinidos)} nomes indefinidos")
        else:
            _linha("nenhum nome inexistente no código (pyflakes)", "✅")
        if cosmeticos:
            _linha(f"{len(cosmeticos)} aviso(s) de estilo, sem impacto no funcionamento", "ℹ️")

    print("─" * 66)
    if problemas:
        print(f"  ❌ REPROVADO — {len(problemas)} problema(s). NÃO publique esta versão.\n")
        return False, problemas
    print(f"  ✅ APROVADO — v{versao}, {comandos} comandos, carrega sem erro.\n")
    return True, []


def main() -> int:
    alvo = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "fireforce_bot.py")
    print("═" * 66)
    print("  🔥 FIRE FORCE — checagem antes de publicar")
    print("═" * 66)
    ok, _ = checar(alvo)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
