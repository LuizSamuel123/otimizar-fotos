import os
import re
import time
from collections import Counter

from otimizar_fotos import *


# =============================================================================
# Auditoria de anos conflitantes
# =============================================================================


PADRAO_ANO = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")


def extrair_anos(texto):
    return {int(ano) for ano in PADRAO_ANO.findall(str(texto))}


def data_extraida_do_nome(nome):
    try:
        from resolver_nao_sei import data_pelo_nome
    except ImportError:
        return None, None
    return data_pelo_nome(nome)


def anos_citados_no_nome(nome, ano_base):
    anos = set(extrair_anos(nome))
    ano_nome, _ = data_extraida_do_nome(nome)
    if ano_nome:
        anos.add(ano_nome)
    return sorted(ano for ano in anos if ano != ano_base)


def anos_citados_no_caminho(rel, nome, ano_base):
    anos = set(extrair_anos(rel))
    ano_nome, _ = data_extraida_do_nome(nome)
    if ano_nome:
        anos.add(ano_nome)
    return sorted(ano for ano in anos if ano != ano_base)


def pasta_e_ano(nome):
    anos = extrair_anos(nome)
    if len(anos) != 1:
        return None
    ano = next(iter(anos))
    return ano if str(ano) == nome.strip() else None


def ignorar_dir_auditoria(nome):
    nome_norm = normalizar_nome(nome)
    if nome_norm in DIRETORIOS_TECNICOS_IGNORADOS:
        return True
    if nome_norm in NOMES_QUARENTENA:
        return True
    return nome_norm == normalizar_nome(NOME_ANO_CONFLITANTE)


def iterar_arvore_para_auditoria(raiz):
    inicio = time.time()
    ultimo_progresso = 0
    analisadas = 0
    for pasta_atual, subpastas, arquivos in os.walk(raiz, topdown=True):
        analisadas += 1
        mostrar, ultimo_progresso = deve_mostrar_progresso(analisadas, ultimo_progresso, lote=500)
        if mostrar:
            relatorio(texto_progresso("Auditando pastas", analisadas, None, inicio))
        subpastas[:] = [
            subpasta
            for subpasta in subpastas
            if not ignorar_dir_auditoria(subpasta)
        ]
        yield pasta_atual, subpastas, arquivos


def auditar_conflitos_de_ano(raiz):
    conflitos = []
    subpastas_ano = []

    try:
        nomes = os.listdir(raiz)
    except OSError:
        return subpastas_ano, conflitos

    for nome in sorted(nomes, key=lambda valor: valor.casefold()):
        caminho = os.path.join(raiz, nome)
        if not os.path.isdir(caminho):
            continue
        ano_base = pasta_e_ano(nome)
        if ano_base is None:
            continue
        subpastas_ano.append((ano_base, caminho))

    inicio = time.time()
    ultimo_progresso = 0
    total_anos = len(subpastas_ano)
    for indice_ano, (ano_base, pasta_ano) in enumerate(subpastas_ano, start=1):
        mostrar, ultimo_progresso = deve_mostrar_progresso(indice_ano, ultimo_progresso, lote=1, total=total_anos)
        if mostrar:
            relatorio(texto_progresso("Auditando anos", indice_ano, total_anos, inicio))
        for pasta_atual, subpastas, arquivos in iterar_arvore_para_auditoria(pasta_ano):
            rel_pasta = os.path.relpath(pasta_atual, pasta_ano)
            itens = [(subpasta, "pasta") for subpasta in subpastas]
            itens.extend((arquivo, "arquivo") for arquivo in arquivos)
            for nome, tipo in itens:
                caminho = os.path.join(pasta_atual, nome)
                rel = os.path.join(rel_pasta, nome) if rel_pasta != "." else nome
                anos = anos_citados_no_caminho(rel, nome, ano_base)
                anos_no_nome = anos_citados_no_nome(nome, ano_base)
                if anos:
                    conflitos.append({
                        "ano_base": ano_base,
                        "anos_citados": anos,
                        "anos_no_nome": anos_no_nome,
                        "tipo": tipo,
                        "caminho": caminho,
                    })

    return subpastas_ano, conflitos


def encontrar_pasta_ano_conflitante(pasta_ano):
    try:
        nomes = os.listdir(pasta_ano)
    except OSError:
        return None

    alvo = normalizar_nome(NOME_ANO_CONFLITANTE)
    for nome in nomes:
        caminho = os.path.join(pasta_ano, nome)
        if os.path.isdir(caminho) and normalizar_nome(nome) == alvo:
            return caminho
    return None


def conflitos_ja_separados(subpastas_ano):
    conflitos = []
    for ano_base, pasta_ano in subpastas_ano:
        pasta_revisao = encontrar_pasta_ano_conflitante(pasta_ano)
        if not pasta_revisao:
            continue

        for pasta_atual, subpastas, arquivos in os.walk(pasta_revisao, topdown=True):
            subpastas[:] = [
                subpasta
                for subpasta in subpastas
                if normalizar_nome(subpasta) not in DIRETORIOS_TECNICOS_IGNORADOS
            ]
            for arquivo in arquivos:
                if os.path.splitext(arquivo)[1].lower() not in EXTENSOES_IMAGEM + EXTENSOES_VIDEO:
                    continue
                anos_no_nome = anos_citados_no_nome(arquivo, ano_base)
                if len(anos_no_nome) != 1:
                    continue
                caminho = os.path.join(pasta_atual, arquivo)
                conflitos.append({
                    "ano_base": ano_base,
                    "anos_citados": anos_no_nome,
                    "anos_no_nome": anos_no_nome,
                    "tipo": "arquivo",
                    "caminho": caminho,
                    "ja_separado": True,
                })
    return conflitos


def linhas_relatorio_conflitos(raiz, subpastas_ano, conflitos, limite):
    por_par = Counter()
    for conflito in conflitos:
        for ano_citado in conflito["anos_citados"]:
            por_par[(conflito["ano_base"], ano_citado)] += 1

    linhas = [
        f"RELATORIO - album auditar anos | {nome_alvo(raiz)}",
        f"Pasta pai: {raiz}",
        f"Subpastas de ano analisadas: {len(subpastas_ano)}",
        f"Conflitos encontrados: {len(conflitos)}",
    ]

    if por_par:
        linhas.append("Resumo por conflito:")
        for (ano_base, ano_citado), total in por_par.most_common(20):
            linhas.append(f"- dentro de {ano_base}, cita {ano_citado}: {total}")

    if conflitos:
        linhas.append("")
        linhas.append(f"Primeiros caminhos conflitantes (limite {limite}):")
        for conflito in conflitos[:limite]:
            anos = ", ".join(str(ano) for ano in conflito["anos_citados"])
            linhas.append(f"- [{conflito['tipo']}] dentro de {conflito['ano_base']}, cita {anos}: {conflito['caminho']}")
        if len(conflitos) > limite:
            linhas.append(f"... mais {len(conflitos) - limite} conflito(s).")

    return linhas


def comando_auditar_anos(args):
    inicio = time.time()
    raiz = os.path.abspath(args.pasta)
    subpastas_ano, conflitos = auditar_conflitos_de_ano(raiz)
    separados_resoluveis = conflitos_ja_separados(subpastas_ano)
    linhas = linhas_relatorio_conflitos(raiz, subpastas_ano, conflitos, max(1, args.limite))

    relatorio(linhas[0], respiro=True)
    for linha in linhas[1:]:
        relatorio(linha)
    relatorio(f"Arquivos em {NOME_ANO_CONFLITANTE} com ano claro no nome: {len(separados_resoluveis)}")
    if separados_resoluveis:
        relatorio(f"Primeiros ja separados que podem ir para o ano correto (limite {max(1, args.limite)}):")
        for conflito in separados_resoluveis[:max(1, args.limite)]:
            ano_destino = ano_citado_principal(conflito)
            relatorio(f"- dentro de {conflito['ano_base']}, nome cita {ano_destino}: {conflito['caminho']}")
    relatorio(f"Tempo: {formatar_tempo(time.time() - inicio)}")


def filtrar_conflitos(conflitos, ano_base=None, ano_citado=None):
    filtrados = []
    for conflito in conflitos:
        if ano_base is not None and conflito["ano_base"] != ano_base:
            continue
        if ano_citado is not None and ano_citado not in conflito["anos_citados"]:
            continue
        filtrados.append(conflito)
    return filtrados


def selecionar_conflitos_raiz(conflitos):
    selecionados = []
    pastas_selecionadas = []

    def chave(conflito):
        caminho = conflito["caminho"]
        tipo_ordem = 0 if conflito["tipo"] == "pasta" else 1
        return (caminho.count(os.sep), tipo_ordem, caminho.casefold())

    for conflito in sorted(conflitos, key=chave):
        caminho_norm = caminho_normalizado(conflito["caminho"])
        if any(caminho_norm == pasta or caminho_norm.startswith(pasta + os.sep) for pasta in pastas_selecionadas):
            continue
        selecionados.append(conflito)
        if conflito["tipo"] == "pasta":
            pastas_selecionadas.append(caminho_norm)

    return selecionados


def destino_conflito(raiz, conflito):
    pasta_ano = os.path.join(os.path.abspath(raiz), str(conflito["ano_base"]))
    rel = os.path.relpath(conflito["caminho"], pasta_ano)
    return os.path.join(pasta_ano, NOME_ANO_CONFLITANTE, rel)


def ano_citado_principal(conflito):
    anos_no_nome = conflito.get("anos_no_nome") or []
    if len(anos_no_nome) == 1:
        return anos_no_nome[0]
    anos_citados = conflito.get("anos_citados") or []
    if len(anos_citados) == 1:
        return anos_citados[0]
    return None


def mes_da_parte(parte):
    chave = normalizar_nome(limpar_nome_pasta(parte))
    for numero_mes, nome_mes in MESES.items():
        if chave == normalizar_nome(limpar_nome_pasta(nome_mes)):
            return numero_mes
    return None


def parte_e_pasta_mes(parte):
    return mes_da_parte(parte) is not None


def destino_pelo_ano_citado(raiz, conflito):
    ano_citado = ano_citado_principal(conflito)
    if ano_citado is None:
        return None

    raiz_abs = os.path.abspath(raiz)
    pasta_ano = os.path.join(raiz_abs, str(conflito["ano_base"]))
    rel = os.path.relpath(conflito["caminho"], pasta_ano)
    partes = [
        parte
        for parte in rel.split(os.sep)
        if normalizar_nome(parte) != normalizar_nome(NOME_ANO_CONFLITANTE)
    ]
    mes_contexto = next((mes_da_parte(parte) for parte in partes if mes_da_parte(parte)), None)
    if mes_contexto:
        partes = [parte for parte in partes if not parte_e_pasta_mes(parte)]
        partes.insert(0, MESES[mes_contexto])
    try:
        from resolver_nao_sei import data_pelo_nome
    except ImportError:
        data_pelo_nome = None
    if data_pelo_nome:
        ano_nome, mes_nome = data_pelo_nome(os.path.basename(conflito["caminho"]))
        if ano_nome == ano_citado and mes_nome:
            partes = [parte for parte in partes if not parte_e_pasta_mes(parte)]
            partes.insert(0, MESES[mes_nome])
    return os.path.join(raiz_abs, str(ano_citado), *partes)


def comando_separar_conflitos(args):
    inicio = time.time()
    raiz = os.path.abspath(args.pasta)
    subpastas_ano, conflitos = auditar_conflitos_de_ano(raiz)
    conflitos.extend(conflitos_ja_separados(subpastas_ano))
    ano_base = getattr(args, "ano_base", None)
    ano_citado = getattr(args, "ano_citado", None)
    conflitos_filtrados = filtrar_conflitos(conflitos, ano_base=ano_base, ano_citado=ano_citado)
    selecionados = selecionar_conflitos_raiz(conflitos_filtrados)
    limite = max(1, args.limite)

    relatorio(f"RELATORIO - album separar conflitos | {nome_alvo(raiz)}", respiro=True)
    relatorio(f"Pasta pai: {raiz}")
    if ano_base is not None:
        relatorio(f"Filtro ano base: {ano_base}")
    if ano_citado is not None:
        relatorio(f"Filtro ano citado: {ano_citado}")
    relatorio(f"Conflitos encontrados no filtro: {len(conflitos_filtrados)}")
    destinos_por_ano = sum(1 for conflito in selecionados if ano_citado_principal(conflito) is not None)
    relatorio(f"Itens raiz a mover: {len(selecionados)}")
    relatorio(f"Itens com ano claro no nome/caminho: {destinos_por_ano}")

    if selecionados:
        relatorio(f"Primeiros itens selecionados (limite {limite}):")
        for conflito in selecionados[:limite]:
            anos = ", ".join(str(ano) for ano in conflito["anos_citados"])
            ano_destino = ano_citado_principal(conflito)
            destino_texto = f" -> ano {ano_destino}" if ano_destino is not None else f" -> {NOME_ANO_CONFLITANTE}"
            relatorio(f"- [{conflito['tipo']}] dentro de {conflito['ano_base']}, cita {anos}{destino_texto}: {conflito['caminho']}")
        if len(selecionados) > limite:
            relatorio(f"... mais {len(selecionados) - limite} item(ns).")

    if not selecionados:
        relatorio(f"Tempo: {formatar_tempo(time.time() - inicio)}")
        return

    if not args.executar:
        relatorio("Nada foi movido. Use --executar --sim para aplicar a organizacao dos conflitos.")
        relatorio(f"Tempo: {formatar_tempo(time.time() - inicio)}")
        return

    if not confirmar(f"Mover {len(selecionados)} item(ns), usando o ano do nome quando ele estiver claro?", args.sim):
        relatorio("Cancelado.")
        return

    movidos = 0
    movidos_por_ano = 0
    movidos_para_verificar = 0
    ausentes = 0
    erros = 0
    total_selecionados = len(selecionados)
    ultimo_progresso = 0
    for indice, conflito in enumerate(selecionados, start=1):
        mostrar, ultimo_progresso = deve_mostrar_progresso(indice, ultimo_progresso, lote=100, total=total_selecionados)
        if mostrar:
            relatorio(texto_progresso("Separando conflitos", indice, total_selecionados, inicio))
        origem = conflito["caminho"]
        if not os.path.exists(origem):
            ausentes += 1
            continue
        destino_pelo_nome = destino_pelo_ano_citado(raiz, conflito)
        destino = gerar_caminho_unico(destino_pelo_nome or destino_conflito(raiz, conflito))
        try:
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            mover_com_historico(origem, destino, executar=True)
            movidos += 1
            if destino_pelo_nome:
                movidos_por_ano += 1
                log(f"[ANO DO NOME] {caminho_curto(origem)} -> {caminho_curto(destino)}")
            else:
                movidos_para_verificar += 1
                log(f"[ANO CONFLITANTE] {caminho_curto(origem)} -> {caminho_curto(destino)}")
        except OSError as erro:
            erros += 1
            log(f"[ERRO] {origem} ({erro})")

    relatorio(f"Itens movidos pelo ano do nome/caminho: {movidos_por_ano}")
    relatorio(f"Itens separados em {NOME_ANO_CONFLITANTE}: {movidos_para_verificar}")
    relatorio(f"Itens movidos no total: {movidos}")
    relatorio(f"Itens ausentes: {ausentes}")
    relatorio(f"Erros/ignorados: {erros}")
    relatorio(f"Tempo: {formatar_tempo(time.time() - inicio)}")

