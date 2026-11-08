import os
import time
from collections import defaultdict

from otimizar_fotos import *
from organizar_por_data import obter_tipo_midia


# =============================================================================
# Quarentena de duplicatas de midia
# =============================================================================


def mover_duplicatas_de_midia_do_grupo(por_hash, pasta_quarentena, inicio_etapas, executar, movidas, ausentes, erros, ultimo_progresso):
    for caminhos in por_hash.values():
        if len(caminhos) <= 1:
            continue
        caminhos = [caminho for caminho in caminhos if os.path.exists(caminho)]
        if len(caminhos) <= 1:
            continue
        caminhos.sort(key=pontuar_nome_para_manter)
        mantido = caminhos[0]
        log(f"[MANTIDO] {mantido}")
        for copia in caminhos[1:]:
            subpasta_origem = os.path.basename(os.path.dirname(copia)) or "origem"
            try:
                destino, _ = mover_para_quarentena(copia, pasta_quarentena, inicio_etapas, [subpasta_origem], executar)
            except OSError as erro:
                erros += 1
                log(f"[ERRO] Nao movi para quarentena: {caminho_curto(copia)} ({erro})")
                continue
            if executar and destino is None:
                ausentes += 1
                continue
            movidas += 1
            mostrar, ultimo_progresso = deve_mostrar_progresso(movidas, ultimo_progresso, lote=100)
            if mostrar:
                relatorio(texto_progresso("Duplicatas de midia ja enviadas/listadas", movidas, None, inicio_etapas))
    return movidas, ausentes, erros, ultimo_progresso


def quarentena_album(args):

    if bloquear_pasta_ampla_se_preciso(args, "album quarentena"):
        return

    raiz = os.path.abspath(args.pasta)
    pasta_quarentena = os.path.join(raiz, NOME_QUARENTENA)
    inicio = time.time()
    por_tamanho = defaultdict(list)
    total_pastas = 0
    total_midias = 0

    log("=== ALBUM: QUARENTENA DE DUPLICATAS ===")
    log(f"Alvo: {raiz}")
    for pasta_atual, _, arquivos in iterar_arvore(raiz):
        total_pastas += 1
        for arquivo in arquivos:
            if not obter_tipo_midia(arquivo):
                continue
            caminho = os.path.abspath(os.path.join(pasta_atual, arquivo))
            if caminho_esta_dentro(caminho, pasta_quarentena):
                continue
            try:
                por_tamanho[os.path.getsize(caminho)].append(caminho)
            except OSError:
                continue
            total_midias += 1
        if total_pastas % 500 == 0:
            log(f"Mapeadas {total_pastas} pastas, {total_midias} midias | {caminho_curto(pasta_atual)}")

    suspeitos = [(tamanho, caminhos) for tamanho, caminhos in por_tamanho.items() if len(caminhos) > 1]
    total_hash = sum(len(caminhos) for _, caminhos in suspeitos)
    total_bytes_hash = sum(tamanho * len(caminhos) for tamanho, caminhos in suspeitos)

    log("\n=== ESTIMATIVA ===")
    log(f"Pastas: {total_pastas} | Midias: {total_midias} | Suspeitas para hash: {total_hash}")
    log(f"Hash/comparacao: {estimar_hash_bytes(total_bytes_hash, raiz)}")

    if not total_hash:
        relatorio(f"RELATORIO - album quarentena | {nome_alvo(raiz)}", respiro=True)
        relatorio(f"Pasta: {raiz}")
        relatorio(f"Midias analisadas: {total_midias}")
        relatorio("Duplicatas de midia enviadas/listadas para 1-QUARENTENA: 0")
        relatorio(f"Tempo: {formatar_tempo(time.time() - inicio)}")
        return

    relatorio(f"RELATORIO - album quarentena | {nome_alvo(raiz)}", respiro=True)
    relatorio(f"Pasta: {raiz}")
    relatorio(f"Midias analisadas: {total_midias}")
    relatorio(f"Midias candidatas para comparacao/hash: {total_hash}")
    relatorio(f"Tamanho a ler para comparar: {formatar_bytes(total_bytes_hash)}")
    relatorio("Duplicatas serao movidas conforme cada bloco de tamanho for confirmado.")

    if args.executar and not confirmar("Comparar e mover duplicatas de midia conforme forem encontradas?", args.sim):
        relatorio("Cancelado.")
        return
    if not args.executar:
        log("Modo simulacao: duplicatas serao listadas, mas nada sera movido. Use --executar para mover.")

    inicio_etapas = time.time()
    feitos = 0
    movidas = 0
    ausentes = 0
    erros_movimento = 0
    ultimo_hash = 0
    ultimo_movimento = 0

    for _, caminhos in suspeitos:
        por_hash = defaultdict(list)
        for caminho in caminhos:
            feitos += 1
            mostrar, ultimo_hash = deve_mostrar_progresso(feitos, ultimo_hash, lote=100, total=total_hash)
            if mostrar:
                relatorio(texto_progresso("Hash/comparacao de midias", feitos, total_hash, inicio))
            hash_arquivo = gerar_hash(caminho)
            if hash_arquivo:
                por_hash[hash_arquivo].append(caminho)
        movidas, ausentes, erros_movimento, ultimo_movimento = mover_duplicatas_de_midia_do_grupo(
            por_hash,
            pasta_quarentena,
            inicio_etapas,
            args.executar,
            movidas,
            ausentes,
            erros_movimento,
            ultimo_movimento,
        )

    acao = "enviadas" if args.executar else "que iriam"
    relatorio(f"RELATORIO - album quarentena | {nome_alvo(raiz)}", respiro=True)
    relatorio(f"Pasta: {raiz}")
    relatorio(f"Midias analisadas: {total_midias}")
    relatorio(f"Duplicatas de midia {acao} para {NOME_QUARENTENA}: {movidas}")
    if ausentes:
        relatorio(f"Arquivos que sumiram antes de mover: {ausentes}")
    if erros_movimento:
        relatorio(f"Erros ao mover para quarentena: {erros_movimento}")
    relatorio(f"Tempo: {formatar_tempo(time.time() - inicio)}")
