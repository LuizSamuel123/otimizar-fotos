import os
import re
import time

from otimizar_fotos import *


# =============================================================================
# Tirar itens de nao_sei(verificar) quando o nome indica data ou mes
# =============================================================================


PALAVRAS_MES = {
    1: ("janeiro",),
    2: ("fevereiro",),
    3: ("marco", "março"),
    4: ("abril",),
    5: ("maio",),
    6: ("junho",),
    7: ("julho",),
    8: ("agosto",),
    9: ("setembro",),
    10: ("outubro",),
    11: ("novembro",),
    12: ("dezembro",),
}

PALAVRAS_EVENTO_MES = {
    5: ("dia das maes", "dia das mães"),
    6: ("festa junina", "sao joao", "são joão"),
    8: ("dia dos pais",),
    10: ("halloween",),
    12: ("natal", "reveillon", "réveillon", "ano novo"),
}


PADROES_DATA = (
    # 2020-08-15, 2020_08_15, 2020.08.15, 2020 08 15
    re.compile(r"(?<!\d)(?P<ano>19\d{2}|20\d{2})[-_.\s](?P<mes>0?[1-9]|1[0-2])[-_.\s](?P<dia>0?[1-9]|[12]\d|3[01])(?!\d)"),
    # 15-08-2020, 15_08_2020, 15.08.2020, 15 08 2020
    re.compile(r"(?<!\d)(?P<dia>0?[1-9]|[12]\d|3[01])[-_.\s](?P<mes>0?[1-9]|1[0-2])[-_.\s](?P<ano>19\d{2}|20\d{2})(?!\d)"),
    # IMG_20200815, VID-20200815, Screenshot_20200815
    re.compile(r"(?<!\d)(?P<ano>19\d{2}|20\d{2})(?P<mes>0[1-9]|1[0-2])(?P<dia>0[1-9]|[12]\d|3[01])(?!\d)"),
)


def texto_para_busca(texto):
    texto = remover_acentos(str(texto).casefold())
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return f" {texto.strip()} "


def contem_termo(texto_busca, termo):
    termo_busca = texto_para_busca(termo).strip()
    return f" {termo_busca} " in texto_busca


def mes_pelo_nome(nome):
    texto_busca = texto_para_busca(nome)
    for mes, termos in PALAVRAS_MES.items():
        if any(contem_termo(texto_busca, termo) for termo in termos):
            return mes
    for mes, termos in PALAVRAS_EVENTO_MES.items():
        if any(contem_termo(texto_busca, termo) for termo in termos):
            return mes
    return None


def data_pelo_nome(nome):
    texto = os.path.splitext(str(nome))[0]
    for padrao in PADROES_DATA:
        achou = padrao.search(texto)
        if not achou:
            continue
        ano = int(achou.group("ano"))
        mes = int(achou.group("mes"))
        dia = int(achou.group("dia"))
        if 1900 <= ano <= 2099 and 1 <= mes <= 12 and 1 <= dia <= 31:
            return ano, mes

    ano = ano_pelo_nome(texto)
    mes = mes_pelo_nome(texto)
    if ano and mes:
        return ano, mes
    return None, None


def ano_pelo_nome(nome):
    achou = re.search(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)", str(nome))
    if not achou:
        return None
    ano = int(achou.group(1))
    if 1900 <= ano <= 2099:
        return ano
    return None


def nome_e_apenas_mes(nome, mes):
    nome_limpo = texto_para_busca(limpar_nome_pasta(nome)).strip()
    return any(nome_limpo == texto_para_busca(termo).strip() for termo in PALAVRAS_MES[mes])


def nome_e_nao_sei(nome):
    return remover_acentos(normalizar_nome(nome)) == remover_acentos(normalizar_nome(NOME_SEM_DATA))


def nome_e_ano(nome):
    return len(nome) == 4 and nome.isdigit() and 1900 <= int(nome) <= 2099


def pastas_de_ano(raiz):
    try:
        nomes = sorted(os.listdir(raiz), key=str.casefold)
    except OSError:
        return []
    anos = []
    for nome in nomes:
        caminho = os.path.join(raiz, nome)
        if os.path.isdir(caminho) and nome_e_ano(nome):
            anos.append(caminho)
    return anos


def encontrar_nao_sei_do_ano(pasta_ano):
    try:
        nomes = sorted(os.listdir(pasta_ano), key=str.casefold)
    except OSError:
        return None
    for nome in nomes:
        caminho = os.path.join(pasta_ano, nome)
        if os.path.isdir(caminho) and nome_e_nao_sei(nome):
            return caminho
    return None


def encontrar_nao_sei_direta(raiz):
    try:
        nomes = sorted(os.listdir(raiz), key=str.casefold)
    except OSError:
        return None
    for nome in nomes:
        caminho = os.path.join(raiz, nome)
        if os.path.isdir(caminho) and nome_e_nao_sei(nome):
            return caminho
    return None


def listar_itens_diretos(pasta):
    try:
        nomes = sorted(os.listdir(pasta), key=str.casefold)
    except OSError:
        return []
    return [os.path.join(pasta, nome) for nome in nomes]


def montar_alvos_nao_sei(raiz):
    raiz = os.path.abspath(raiz)
    nome_raiz = os.path.basename(raiz)
    pasta_pai = os.path.dirname(raiz)
    nome_pai = os.path.basename(pasta_pai)

    if nome_e_nao_sei(nome_raiz):
        if nome_e_ano(nome_pai):
            return [(raiz, pasta_pai, int(nome_pai), "pasta nao_sei escolhida dentro de um ano")]
        return [(raiz, pasta_pai, None, "pasta nao_sei escolhida diretamente")]

    alvos = []
    nao_sei_direta = encontrar_nao_sei_direta(raiz)
    if nao_sei_direta:
        alvos.append((nao_sei_direta, raiz, None, "nao_sei direto na pasta escolhida"))

    for pasta_ano in pastas_de_ano(raiz):
        pasta_nao_sei = encontrar_nao_sei_do_ano(pasta_ano)
        if pasta_nao_sei:
            alvos.append((pasta_nao_sei, pasta_ano, int(os.path.basename(pasta_ano)), "nao_sei dentro de ano"))
    return alvos


def mover_item_para_mes(origem, pasta_mes, executar):
    destino = gerar_caminho_unico(os.path.join(pasta_mes, os.path.basename(origem)))
    log(f"[MOVER] {caminho_curto(origem)} -> {caminho_curto(destino)}")
    if executar:
        os.makedirs(pasta_mes, exist_ok=True)
        mover_com_historico(origem, destino, executar=True)
    return destino


def mover_conteudo_da_pasta_mes(origem, pasta_mes, executar):
    movidos = 0
    erros = 0
    for item in listar_itens_diretos(origem):
        try:
            mover_item_para_mes(item, pasta_mes, executar)
            movidos += 1
        except OSError as erro:
            erros += 1
            log(f"[ERRO] {item} ({erro})")
    if executar:
        try:
            if os.path.isdir(origem) and not os.listdir(origem):
                remover_pasta_vazia_com_historico(origem, executar=True)
        except OSError as erro:
            erros += 1
            log(f"[IGNORADA] Nao removi pasta vazia: {origem} ({erro})")
    return movidos, erros


def comando_resolver_nao_sei(args):
    if bloquear_pasta_ampla_se_preciso(args, "album resolver-nao-sei"):
        return

    raiz = os.path.abspath(args.pasta)
    inicio = time.time()
    if not os.path.isdir(raiz):
        relatorio(f"[ERRO] Pasta nao encontrada: {raiz}")
        return

    alvos = montar_alvos_nao_sei(raiz)
    candidatos = []
    sem_pista = 0
    sem_ano = 0
    ano_sem_mes = 0

    for pasta_nao_sei, pasta_destino_base, ano_fixo, origem_alvo in alvos:
        log(f"[ANALISANDO] {origem_alvo}: {caminho_curto(pasta_nao_sei)}")
        for item in listar_itens_diretos(pasta_nao_sei):
            nome = os.path.basename(item)
            if ignorar_dir(nome):
                continue

            ano_nome, mes_nome = data_pelo_nome(nome)
            if not ano_nome:
                ano_nome = ano_pelo_nome(nome)
            ano_final = ano_fixo or ano_nome
            mes_final = mes_nome or mes_pelo_nome(nome)

            if not mes_final:
                if ano_final:
                    pasta_ano = pasta_destino_base if ano_fixo else os.path.join(pasta_destino_base, str(ano_final))
                    candidatos.append((item, pasta_ano, None, False, ano_final))
                    ano_sem_mes += 1
                    log(f"[ANO SEM MES] {caminho_curto(item)}")
                    continue
                sem_pista += 1
                log(f"[SEM PISTA DE MES] {caminho_curto(item)}")
                continue
            if not ano_final:
                sem_ano += 1
                log(f"[SEM ANO] {caminho_curto(item)}")
                continue

            pasta_ano = pasta_destino_base if ano_fixo else os.path.join(pasta_destino_base, str(ano_final))
            pasta_mes = os.path.join(pasta_ano, MESES[mes_final])
            mover_conteudo_pasta_mes = nome_e_apenas_mes(nome, mes_final) and os.path.isdir(item)
            candidatos.append((item, pasta_mes, mes_final, mover_conteudo_pasta_mes, ano_final))

    acao = "selecionados para mover" if args.executar else "que seriam movidos"
    meses = sorted({MESES[mes] for _, _, mes, _, _ in candidatos if mes})
    anos = sorted({str(ano) for _, _, _, _, ano in candidatos})
    relatorio(f"RELATORIO - tentar organizar arquivos sem data pelo nome | {nome_alvo(raiz)}", respiro=True)
    relatorio(f"Pasta: {raiz}")
    relatorio("Regra: usa datas no nome, meses e eventos como Natal. Se souber so o ano, deixa solto no ano.")
    relatorio("Exemplos: IMG_20201224 -> 2020/Dezembro; EUROPA 2009 sem mes -> 2009.")
    relatorio(f"Pastas nao_sei analisadas: {len(alvos)}")
    relatorio(f"Itens {acao}: {len(candidatos)}")
    relatorio(f"Itens com ano, mas sem mes: {ano_sem_mes}")
    relatorio(f"Itens sem pista de mes: {sem_pista}")
    relatorio(f"Itens com mes, mas sem ano claro: {sem_ano}")
    relatorio(f"Anos envolvidos: {', '.join(anos) if anos else 'nenhum'}")
    relatorio(f"Meses envolvidos: {', '.join(meses) if meses else 'nenhum'}")

    if not alvos:
        relatorio("Nao encontrei nenhuma pasta nao_sei(verificar) para analisar.")
        relatorio("Dica: escolha a pasta que contem nao_sei(verificar), ou escolha a propria nao_sei(verificar).")
        relatorio(f"Tempo: {formatar_tempo(time.time() - inicio)}")
        return

    if not candidatos:
        relatorio(f"Tempo: {formatar_tempo(time.time() - inicio)}")
        return

    if not args.executar:
        relatorio("Nada foi movido nesta analise. Clique em Efetuar para aplicar.")
        relatorio(f"Tempo: {formatar_tempo(time.time() - inicio)}")
        return

    if not confirmar(f"Mover {len(candidatos)} item(ns) de nao_sei para ano/mes quando houver pista?", args.sim):
        relatorio("Cancelado.")
        return

    movidos = 0
    erros = 0
    for item, pasta_mes, _, mover_conteudo_pasta_mes, _ in candidatos:
        try:
            if mover_conteudo_pasta_mes:
                feitos, falhas = mover_conteudo_da_pasta_mes(item, pasta_mes, executar=True)
                movidos += feitos
                erros += falhas
            else:
                mover_item_para_mes(item, pasta_mes, executar=True)
                movidos += 1
        except OSError as erro:
            erros += 1
            log(f"[ERRO] {item} ({erro})")

    relatorio(f"Itens movidos: {movidos}")
    relatorio(f"Erros/ignorados: {erros}")
    relatorio(f"Tempo: {formatar_tempo(time.time() - inicio)}")


