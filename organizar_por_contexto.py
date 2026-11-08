import os
import re
import time
from datetime import datetime

from otimizar_fotos import *
from organizar_por_data import obter_tipo_midia


# =============================================================================
# Organizar album por data do Windows preservando contexto/evento
# =============================================================================


PADRAO_ANO = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")


def ano_pasta(nome):
    texto = str(nome).strip()
    if len(texto) != 4 or not texto.isdigit():
        return None
    ano = int(texto)
    return ano if 1900 <= ano <= 2099 else None


def anos_no_nome(nome):
    return sorted({int(ano) for ano in PADRAO_ANO.findall(str(nome))})


def mes_pasta(nome):
    nome_norm = remover_acentos(normalizar_nome(nome))
    for numero, nome_mes in MESES.items():
        if remover_acentos(normalizar_nome(nome_mes)) == nome_norm:
            return numero
    return None


def data_windows(caminho):
    try:
        return datetime.fromtimestamp(os.path.getmtime(caminho))
    except OSError:
        return None


def partes_evento(raiz, pasta_atual):
    rel = os.path.relpath(pasta_atual, raiz)
    if rel == ".":
        return []

    partes = [limpar_nome_pasta(parte) for parte in rel.split(os.sep)]
    if partes and ano_pasta(partes[0]) is not None:
        partes = partes[1:]
    if partes and mes_pasta(partes[0]) is not None:
        partes = partes[1:]
    return partes


def destino_por_contexto(raiz, pasta_atual, arquivo, data, anos_validos):
    ano = data.year
    mes = MESES[data.month]
    evento = partes_evento(raiz, pasta_atual)
    if anos_validos and ano not in anos_validos:
        destino_dir = os.path.join(raiz, NOME_ANO_CONFLITANTE, str(ano), mes, *evento)
        return os.path.join(destino_dir, arquivo), True
    destino_dir = os.path.join(raiz, str(ano), mes, *evento)
    return os.path.join(destino_dir, arquivo), False


def reservar_destino(destino_base, destinos_previstos):
    pasta_destino, nome_destino = os.path.split(destino_base)
    nome_base, ext = os.path.splitext(nome_destino)
    destino = gerar_caminho_unico(destino_base)
    contador = 1
    while caminho_normalizado(destino) in destinos_previstos:
        destino = gerar_caminho_unico(os.path.join(pasta_destino, f"{nome_base}_{contador}{ext}"))
        contador += 1
    destinos_previstos.add(caminho_normalizado(destino))
    return destino


def adicionar_pastas_origem(pastas, pasta_atual, raiz):
    pasta = os.path.abspath(pasta_atual)
    raiz_norm = caminho_normalizado(raiz)
    while caminho_esta_dentro(pasta, raiz) and caminho_normalizado(pasta) != raiz_norm:
        pastas.add(pasta)
        pasta = os.path.dirname(pasta)


def remover_pastas_origem_vazias(pastas, raiz, executar):
    removidas = 0
    erros = 0
    raiz_norm = caminho_normalizado(raiz)
    for pasta in sorted(pastas, key=lambda valor: valor.count(os.sep), reverse=True):
        pasta = os.path.abspath(pasta)
        if caminho_normalizado(pasta) == raiz_norm:
            continue
        if not caminho_esta_dentro(pasta, raiz):
            continue
        try:
            if not os.path.isdir(pasta):
                continue
            for nome_sistema in ARQUIVOS_SISTEMA_IGNORADOS_PASTA_VAZIA:
                caminho_sistema = os.path.join(pasta, nome_sistema)
                if os.path.isfile(caminho_sistema):
                    apagar_arquivo_com_historico(caminho_sistema, executar)
            if not os.listdir(pasta):
                remover_pasta_vazia_com_historico(pasta, executar)
                removidas += 1
        except OSError as erro:
            erros += 1
            log(f"[IGNORADA] Nao removi pasta vazia: {pasta} ({erro})")
    return removidas, erros


def comando_organizar_contexto(args):
    if bloquear_pasta_ampla_se_preciso(args, "album organizar-contexto"):
        return

    raiz = os.path.abspath(args.pasta)
    inicio = time.time()
    if not os.path.isdir(raiz):
        relatorio(f"[ERRO] Pasta nao encontrada: {raiz}")
        return

    anos_validos = set(anos_no_nome(os.path.basename(raiz)))
    candidatos = []
    pastas_origem = set()
    destinos_previstos = set()
    midias_analisadas = 0
    sem_data = 0
    conflitos = 0
    ja_no_lugar = 0

    for pasta_atual, _, arquivos in iterar_arvore(raiz):
        for arquivo in sorted(arquivos, key=str.casefold):
            if not obter_tipo_midia(arquivo):
                continue
            caminho = os.path.abspath(os.path.join(pasta_atual, arquivo))
            midias_analisadas += 1
            data = data_windows(caminho)
            if not data:
                sem_data += 1
                continue
            destino_base, conflita = destino_por_contexto(raiz, pasta_atual, arquivo, data, anos_validos)
            destino = reservar_destino(destino_base, destinos_previstos)
            if caminho_normalizado(caminho) == caminho_normalizado(destino):
                ja_no_lugar += 1
                continue
            candidatos.append((caminho, destino, data, conflita))
            adicionar_pastas_origem(pastas_origem, pasta_atual, raiz)
            if conflita:
                conflitos += 1
            log(f"[CONTEXTO] {caminho_curto(caminho)} -> {caminho_curto(destino)}")

    anos = sorted({str(data.year) for _, _, data, _ in candidatos})
    meses = sorted({MESES[data.month] for _, _, data, _ in candidatos})
    acao = "movidas" if args.executar else "que seriam movidas"
    relatorio(f"RELATORIO - album organizar contexto | {nome_alvo(raiz)}", respiro=True)
    relatorio(f"Pasta: {raiz}")
    relatorio("Regra: usa a data de modificacao do Windows e preserva a pasta de evento.")
    if anos_validos:
        relatorio(f"Anos aceitos pelo nome da pasta: {', '.join(str(ano) for ano in sorted(anos_validos))}")
    else:
        relatorio("Anos aceitos pelo nome da pasta: todos")
    relatorio(f"Midias analisadas: {midias_analisadas}")
    relatorio(f"Midias {acao}: {len(candidatos)}")
    relatorio(f"Midias que iriam para {NOME_ANO_CONFLITANTE}: {conflitos}")
    relatorio(f"Midias ja no lugar: {ja_no_lugar}")
    relatorio(f"Midias sem data do Windows: {sem_data}")
    relatorio(f"Anos envolvidos: {', '.join(anos) if anos else 'nenhum'}")
    relatorio(f"Meses envolvidos: {', '.join(meses) if meses else 'nenhum'}")

    if not candidatos:
        relatorio(f"Tempo: {formatar_tempo(time.time() - inicio)}")
        return

    if not args.executar:
        relatorio("Nada foi movido. Use --executar --sim para aplicar.")
        relatorio(f"Tempo: {formatar_tempo(time.time() - inicio)}")
        return

    if not confirmar(f"Mover {len(candidatos)} midia(s) por data do Windows preservando eventos?", args.sim):
        relatorio("Cancelado.")
        return

    movidas = 0
    erros = 0
    ultimo_progresso = 0
    total = len(candidatos)
    for indice, (origem, destino, _, _) in enumerate(candidatos, start=1):
        mostrar, ultimo_progresso = deve_mostrar_progresso(indice, ultimo_progresso, lote=100, total=total)
        if mostrar:
            relatorio(texto_progresso("Organizando por contexto", indice, total, inicio))
        try:
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            mover_com_historico(origem, destino, executar=True)
            movidas += 1
        except OSError as erro:
            erros += 1
            log(f"[ERRO] {origem} -> {destino} ({erro})")

    pastas_removidas, erros_pastas = remover_pastas_origem_vazias(pastas_origem, raiz, executar=True)
    relatorio(f"Midias movidas: {movidas}")
    relatorio(f"Pastas de origem vazias removidas: {pastas_removidas}")
    relatorio(f"Erros/ignoradas: {erros + erros_pastas}")
    relatorio(f"Tempo: {formatar_tempo(time.time() - inicio)}")

