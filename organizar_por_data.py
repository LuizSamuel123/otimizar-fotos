import json
import os
import re
import shutil
import subprocess
import time
from collections import defaultdict
from datetime import datetime

from otimizar_fotos import *
from auditar_anos import extrair_anos, pasta_e_ano, anos_citados_no_caminho, anos_citados_no_nome


# =============================================================================
# Organizar midias por data real
# =============================================================================
DATAS_TIRADAS_WINDOWS_CACHE = {}


def obter_tipo_midia(nome_arquivo):
    ext = os.path.splitext(nome_arquivo)[1].lower()
    if ext in EXTENSOES_IMAGEM:
        return "foto"
    if ext in EXTENSOES_VIDEO:
        return "video"
    return None


def converter_texto_data(valor):
    if isinstance(valor, bytes):
        valor = valor.decode("utf-8", errors="ignore")
    valor = str(valor).strip().replace("\x00", "")
    formatos = (
        "%Y:%m:%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
    )
    for formato in formatos:
        try:
            return datetime.strptime(valor, formato)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def converter_texto_data_windows(valor):
    texto = re.sub(r"[^\d/: -]+", "", str(valor or "")).strip()
    texto = re.sub(r"\s+", " ", texto)
    formatos = (
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
    )
    for formato in formatos:
        try:
            return datetime.strptime(texto, formato)
        except ValueError:
            pass
    return None


def caminho_powershell_literal(caminho):
    return "'" + str(caminho).replace("'", "''") + "'"


def datas_tiradas_windows_da_pasta(pasta):
    pasta_abs = os.path.abspath(pasta)
    chave = caminho_normalizado(pasta_abs)
    if chave in DATAS_TIRADAS_WINDOWS_CACHE:
        return DATAS_TIRADAS_WINDOWS_CACHE[chave]

    DATAS_TIRADAS_WINDOWS_CACHE[chave] = {}
    if os.name != "nt":
        return DATAS_TIRADAS_WINDOWS_CACHE[chave]

    script = f"""
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$path = {caminho_powershell_literal(pasta_abs)}
$shell = New-Object -ComObject Shell.Application
$folder = $shell.Namespace($path)
$rows = @()
if ($folder -ne $null) {{
    foreach ($file in Get-ChildItem -LiteralPath $path -File) {{
        $item = $folder.ParseName($file.Name)
        if ($item -ne $null) {{
            $dateTaken = $folder.GetDetailsOf($item, 12)
            if ($dateTaken) {{
                $rows += [PSCustomObject]@{{ Name = $file.Name; DateTaken = $dateTaken }}
            }}
        }}
    }}
}}
$rows | ConvertTo-Json -Compress
"""
    try:
        resultado = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            timeout=30,
        )
    except Exception as erro:
        log(f"[DATA WINDOWS] Nao consegui ler Data tirada em {caminho_curto(pasta_abs)} ({erro})")
        return DATAS_TIRADAS_WINDOWS_CACHE[chave]

    if resultado.returncode != 0 or not resultado.stdout.strip():
        return DATAS_TIRADAS_WINDOWS_CACHE[chave]

    try:
        dados = json.loads(resultado.stdout)
    except json.JSONDecodeError:
        return DATAS_TIRADAS_WINDOWS_CACHE[chave]

    if isinstance(dados, dict):
        dados = [dados]
    if not isinstance(dados, list):
        return DATAS_TIRADAS_WINDOWS_CACHE[chave]

    datas = {}
    for item in dados:
        if not isinstance(item, dict):
            continue
        nome = item.get("Name")
        data = converter_texto_data_windows(item.get("DateTaken"))
        if nome and data:
            datas[nome] = data
    DATAS_TIRADAS_WINDOWS_CACHE[chave] = datas
    return datas


def obter_data_tirada_windows(caminho):
    datas = datas_tiradas_windows_da_pasta(os.path.dirname(caminho))
    data = datas.get(os.path.basename(caminho))
    if data:
        log(f"[DATA WINDOWS] {caminho_curto(caminho)} -> {data:%Y-%m-%d %H:%M:%S}")
    return data


def obter_data_exif_imagem(caminho):
    try:
        from PIL import Image
    except ImportError:
        data_piexif = obter_data_exif_piexif(caminho)
        return data_piexif or obter_data_exif_bruta_imagem(caminho)
    try:
        with Image.open(caminho) as imagem:
            exif = imagem.getexif()
            for tag in (36867, 36868, 306):
                valor = exif.get(tag)
                if valor:
                    data = converter_texto_data(valor)
                    if data:
                        return data
    except Exception:
        pass
    data_piexif = obter_data_exif_piexif(caminho)
    return data_piexif or obter_data_exif_bruta_imagem(caminho)


def obter_data_exif_piexif(caminho):
    try:
        import piexif
    except ImportError:
        return None
    try:
        exif = piexif.load(caminho)
    except Exception:
        return None

    candidatos = (
        ("Exif", getattr(piexif.ExifIFD, "DateTimeOriginal", None)),
        ("Exif", getattr(piexif.ExifIFD, "DateTimeDigitized", None)),
        ("0th", getattr(piexif.ImageIFD, "DateTime", None)),
    )
    for grupo, tag in candidatos:
        if tag is None:
            continue
        valor = exif.get(grupo, {}).get(tag)
        if valor:
            data = converter_texto_data(valor)
            if data:
                return data
    return None


def obter_data_exif_bruta_imagem(caminho):
    try:
        with open(caminho, "rb") as arquivo:
            dados = arquivo.read(2 * 1024 * 1024)
    except OSError:
        return None

    if b"Exif" not in dados[:65536]:
        return None

    for padrao in (
        rb"(?:19|20)\d{2}:\d{2}:\d{2} \d{2}:\d{2}:\d{2}",
        rb"(?:19|20)\d{2}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}",
    ):
        for encontrado in re.finditer(padrao, dados):
            data = converter_texto_data(encontrado.group(0))
            if data:
                return data
    return None


def obter_data_metadados_video(caminho):
    try:
        resultado = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_entries",
                "format_tags=creation_time:stream_tags=creation_time",
                caminho,
            ],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            timeout=10,
        )
    except Exception:
        return None
    if resultado.returncode != 0 or not resultado.stdout:
        return None
    try:
        metadados = json.loads(resultado.stdout)
    except json.JSONDecodeError:
        return None
    valores = [metadados.get("format", {}).get("tags", {}).get("creation_time")]
    for stream in metadados.get("streams", []):
        valores.append(stream.get("tags", {}).get("creation_time"))
    for valor in valores:
        if valor:
            data = converter_texto_data(valor)
            if data:
                return data
    return None


def obter_data_arquivo(caminho, tipo_midia):
    if tipo_midia == "foto":
        data = obter_data_exif_imagem(caminho)
        if data:
            return data
        data = obter_data_tirada_windows(caminho)
        if data:
            return data
    if tipo_midia == "video":
        data = obter_data_metadados_video(caminho)
        if data:
            return data
    return None


def caminho_em_fotos_antigas(caminho):
    partes = os.path.abspath(caminho).split(os.sep)
    return any(normalizar_nome(parte) == "fotos antigas" for parte in partes)


def pista_data_pelo_nome(arquivo):
    try:
        from resolver_nao_sei import ano_pelo_nome, data_pelo_nome, mes_pelo_nome
    except ImportError:
        return None, None

    ano_nome, mes_nome = data_pelo_nome(arquivo)
    if ano_nome:
        return ano_nome, mes_nome

    ano_nome = ano_pelo_nome(arquivo)
    mes_nome = mes_pelo_nome(arquivo)
    return ano_nome, mes_nome


def partes_album(raiz, pasta_atual, ano, mes):
    rel = os.path.relpath(pasta_atual, raiz)
    if rel == ".":
        return []
    partes = []
    nomes_meses = {normalizar_nome(limpar_nome_pasta(nome_mes)) for nome_mes in MESES.values()}
    for parte in rel.split(os.sep):
        chave = remover_acentos(parte).casefold()
        chave_mes = normalizar_nome(limpar_nome_pasta(parte))
        if (
            parte == ano
            or parte == mes
            or pasta_e_ano(parte) is not None
            or chave_mes in nomes_meses
            or chave in {"fotos", "imagens", "videos", "fotos_imagens", "sem_album"}
        ):
            continue
        partes.append(limpar_nome_pasta(parte))
    return partes


def destino_sem_data_preservando_contexto(raiz, pasta_atual, arquivo):
    rel = os.path.relpath(pasta_atual, raiz)
    if rel == ".":
        partes = []
    else:
        partes = [limpar_nome_pasta(parte) for parte in rel.split(os.sep)]
    return os.path.join(raiz, NOME_SEM_DATA, *partes, arquivo)


def destino_ano_conflitante_preservando_contexto(raiz, pasta_atual, arquivo):
    rel = os.path.relpath(pasta_atual, raiz)
    if rel == ".":
        partes = []
    else:
        partes = [limpar_nome_pasta(parte) for parte in rel.split(os.sep)]
    return os.path.join(raiz, NOME_ANO_CONFLITANTE, *partes, arquivo)


def destino_ano_solto(raiz, arquivo, ano):
    raiz_abs = os.path.abspath(raiz)
    ano_base = pasta_e_ano(os.path.basename(raiz_abs))
    if ano_base is None:
        return os.path.join(raiz_abs, str(ano), arquivo)
    return os.path.join(os.path.dirname(raiz_abs), str(ano), arquivo)


def ano_citado_principal_no_caminho(raiz, pasta_atual, arquivo):
    ano_base = pasta_e_ano(os.path.basename(os.path.abspath(raiz)))
    if ano_base is None:
        return None

    anos_no_nome = anos_citados_no_nome(arquivo, ano_base)
    if len(anos_no_nome) == 1:
        return anos_no_nome[0]

    rel_pasta = os.path.relpath(pasta_atual, raiz)
    rel = arquivo if rel_pasta == "." else os.path.join(rel_pasta, arquivo)
    anos_no_caminho = anos_citados_no_caminho(rel, arquivo, ano_base)
    if len(anos_no_caminho) == 1:
        return anos_no_caminho[0]
    return None


def destino_ano_citado_preservando_contexto(raiz, pasta_atual, arquivo, ano_citado):
    raiz_abs = os.path.abspath(raiz)
    ano_base = pasta_e_ano(os.path.basename(raiz_abs))
    if ano_base is None:
        destino_raiz = os.path.join(raiz_abs, str(ano_citado))
    else:
        destino_raiz = os.path.join(os.path.dirname(raiz_abs), str(ano_citado))

    rel = os.path.relpath(pasta_atual, raiz_abs)
    if rel == ".":
        partes = []
    else:
        partes = [
            parte
            for parte in rel.split(os.sep)
            if normalizar_nome(parte) != normalizar_nome(NOME_ANO_CONFLITANTE)
        ]
    meses = {normalizar_nome(limpar_nome_pasta(nome_mes)): numero_mes for numero_mes, nome_mes in MESES.items()}
    mes_contexto = next(
        (meses[normalizar_nome(limpar_nome_pasta(parte))] for parte in partes if normalizar_nome(limpar_nome_pasta(parte)) in meses),
        None,
    )
    if mes_contexto:
        partes = [
            parte
            for parte in partes
            if normalizar_nome(limpar_nome_pasta(parte)) not in meses
        ]
        partes.insert(0, MESES[mes_contexto])
    try:
        from resolver_nao_sei import data_pelo_nome
    except ImportError:
        data_pelo_nome = None
    if data_pelo_nome:
        ano_nome, mes_nome = data_pelo_nome(arquivo)
        if ano_nome == ano_citado and mes_nome:
            partes = [
                parte
                for parte in partes
                if normalizar_nome(limpar_nome_pasta(parte)) not in meses
            ]
            partes.insert(0, MESES[mes_nome])
    return os.path.join(destino_raiz, *partes, arquivo)


def anos_conflitantes_no_caminho(raiz, pasta_atual, arquivo):
    ano_base = pasta_e_ano(os.path.basename(os.path.abspath(raiz)))
    if ano_base is None:
        return []

    rel_pasta = os.path.relpath(pasta_atual, raiz)
    rel = arquivo if rel_pasta == "." else os.path.join(rel_pasta, arquivo)
    return anos_citados_no_caminho(rel, arquivo, ano_base)


def organizar_album(args):
    if bloquear_pasta_ampla_se_preciso(args):
        return

    raiz = os.path.abspath(args.pasta)
    inicio = time.time()
    midias = []
    sem_data = []
    ano_solto_pelo_nome = []
    ano_corrigido_pelo_nome = []
    ano_conflitante = []
    destinos_sem_data = set()
    destinos_ano_solto = set()
    destinos_ano_corrigido = set()
    destinos_ano_conflitante = set()
    fotos_antigas_preservadas = 0
    total_pastas = 0
    total_arquivos = 0

    log("=== ORGANIZADOR DE ALBUM ===")
    log(f"Alvo: {raiz}")
    log("=== MAPEANDO MIDIAS ===")
    for pasta_atual, _, arquivos in iterar_arvore(raiz):
        total_pastas += 1
        for arquivo in arquivos:
            total_arquivos += 1
            tipo = obter_tipo_midia(arquivo)
            if not tipo:
                continue
            caminho = os.path.join(pasta_atual, arquivo)
            if caminho_esta_dentro(caminho, os.path.join(raiz, NOME_QUARENTENA)):
                continue
            try:
                anos_conflitantes = anos_conflitantes_no_caminho(raiz, pasta_atual, arquivo)
                if anos_conflitantes:
                    ano_citado = ano_citado_principal_no_caminho(raiz, pasta_atual, arquivo)
                    if ano_citado is not None:
                        destino_base = destino_ano_citado_preservando_contexto(raiz, pasta_atual, arquivo, ano_citado)
                        destinos_usados = destinos_ano_corrigido
                        lista_destino = ano_corrigido_pelo_nome
                        log_prefixo = "[ANO DO NOME]"
                        dados_destino = ano_citado
                    else:
                        destino_base = destino_ano_conflitante_preservando_contexto(raiz, pasta_atual, arquivo)
                        destinos_usados = destinos_ano_conflitante
                        lista_destino = ano_conflitante
                        log_prefixo = "[ANO CONFLITANTE]"
                        dados_destino = anos_conflitantes

                    destino = gerar_caminho_unico(destino_base)
                    pasta_destino, nome_destino = os.path.split(destino_base)
                    nome_base, ext = os.path.splitext(nome_destino)
                    contador_conflito = 1
                    while caminho_normalizado(destino) in destinos_usados:
                        destino = gerar_caminho_unico(os.path.join(pasta_destino, f"{nome_base}_{contador_conflito}{ext}"))
                        contador_conflito += 1
                    destinos_usados.add(caminho_normalizado(destino))
                    lista_destino.append((caminho, destino, dados_destino))
                    log(f"{log_prefixo} {caminho_curto(caminho)} -> {caminho_curto(destino)}")
                    continue

                fotos_antigas = caminho_em_fotos_antigas(caminho)
                if not fotos_antigas:
                    data = obter_data_arquivo(caminho, tipo)
                    if data:
                        ano = str(data.year)
                        mes = MESES[data.month]
                        midias.append((os.path.getmtime(caminho), caminho, ano, mes, partes_album(raiz, pasta_atual, ano, mes), tipo))
                        continue

                ano_nome, mes_nome = pista_data_pelo_nome(arquivo)
                if ano_nome and mes_nome:
                    ano = str(ano_nome)
                    mes = MESES[mes_nome]
                    midias.append((os.path.getmtime(caminho), caminho, ano, mes, partes_album(raiz, pasta_atual, ano, mes), tipo))
                    log(f"[DATA NO NOME] {caminho_curto(caminho)} -> {ano}\\{mes}")
                    continue
                if ano_nome:
                    destino_base = destino_ano_solto(raiz, arquivo, ano_nome)
                    destino = gerar_caminho_unico(destino_base)
                    pasta_destino, nome_destino = os.path.split(destino_base)
                    nome_base, ext = os.path.splitext(nome_destino)
                    contador_ano_solto = 1
                    while caminho_normalizado(destino) in destinos_ano_solto:
                        destino = gerar_caminho_unico(os.path.join(pasta_destino, f"{nome_base}_{contador_ano_solto}{ext}"))
                        contador_ano_solto += 1
                    destinos_ano_solto.add(caminho_normalizado(destino))
                    ano_solto_pelo_nome.append((caminho, destino, ano_nome))
                    log(f"[ANO SOLTO PELO NOME] {caminho_curto(caminho)} -> {caminho_curto(destino)}")
                    continue

                if fotos_antigas:
                    fotos_antigas_preservadas += 1
                    log(f"[FOTOS ANTIGAS PRESERVADA] {caminho_curto(caminho)}")
                    continue

                destino_base = destino_sem_data_preservando_contexto(raiz, pasta_atual, arquivo)
                destino = gerar_caminho_unico(destino_base)
                pasta_destino, nome_destino = os.path.split(destino_base)
                nome_base, ext = os.path.splitext(nome_destino)
                contador_sem_data = 1
                while caminho_normalizado(destino) in destinos_sem_data:
                    destino = gerar_caminho_unico(os.path.join(pasta_destino, f"{nome_base}_{contador_sem_data}{ext}"))
                    contador_sem_data += 1
                destinos_sem_data.add(caminho_normalizado(destino))
                sem_data.append((caminho, destino))
                log(f"[SEM DATA] {caminho_curto(caminho)} -> {caminho_curto(destino)}")
                continue
            except OSError:
                continue
        if total_pastas % 200 == 0:
            log(f"Mapeando {total_pastas} pastas, {len(midias)} midias | {caminho_curto(pasta_atual)}")

    log(f"Midias com data confiavel: {len(midias)}")
    log(f"Midias sem data confiavel: {len(sem_data)}")
    log(f"Midias soltas no ano pelo nome: {len(ano_solto_pelo_nome)}")
    log(f"Midias movidas pelo ano do nome: {len(ano_corrigido_pelo_nome)}")
    log(f"Midias com ano conflitante: {len(ano_conflitante)}")
    log(f"Fotos Antigas preservadas sem pista clara no nome: {fotos_antigas_preservadas}")
    if not args.executar:
        log("Modo simulacao: nada sera movido. Use --executar para aplicar.")

    por_tamanho = defaultdict(list)
    for item in midias:
        try:
            por_tamanho[os.path.getsize(item[1])].append(item)
        except OSError:
            pass
    suspeitos = [(tamanho, itens) for tamanho, itens in por_tamanho.items() if len(itens) > 1]
    total_hash = sum(len(itens) for _, itens in suspeitos)
    total_bytes_hash = sum(tamanho * len(itens) for tamanho, itens in suspeitos)
    fator = fator_disco(raiz)
    segundos_total = (
        estimar_segundos(total_pastas + total_arquivos, 1200 * fator)
        + estimar_segundos(total_bytes_hash, 55 * 1024 * 1024 * fator)
        + estimar_segundos(len(midias), 14 * fator)
    )
    log("\n=== ESTIMATIVA ===")
    log(f"Pastas: {total_pastas} | Arquivos lidos: {total_arquivos} | Midias com data: {len(midias)} | Sem data: {len(sem_data)}")
    log(f"Comparacao/hash de duplicatas: {estimar_hash_bytes(total_bytes_hash, raiz)}")
    log(f"Organizacao final: {formatar_tempo(estimar_segundos(len(midias), 14 * fator))}")
    log(f"Tempo total aproximado: {formatar_tempo(segundos_total)}")

    if args.executar and not confirmar("Organizar album e mover duplicatas para quarentena?", args.sim):
        relatorio("Cancelado.")
        return

    removidas_norm = set()
    inicio_etapas = time.time()
    ano_solto_movidas = 0
    ano_corrigido_movidas = 0
    ano_conflitante_movidas = 0
    sem_data_movidas = 0
    duplicatas_quarentena = 0
    duplicatas_ausentes = 0
    duplicatas_erros = 0

    feitos = 0
    ultimo_hash = 0
    ultimo_movimento = 0
    for _, itens in suspeitos:
        hashes_grupo = defaultdict(list)
        for item in itens:
            feitos += 1
            mostrar, ultimo_hash = deve_mostrar_progresso(feitos, ultimo_hash, lote=100, total=total_hash)
            if mostrar and total_hash:
                relatorio(texto_progresso("Hash/comparacao de midias", feitos, total_hash, inicio))
            hash_arquivo = gerar_hash(item[1])
            if hash_arquivo:
                hashes_grupo[hash_arquivo].append(item)

        for duplicatas in hashes_grupo.values():
            if len(duplicatas) <= 1:
                continue
            duplicatas = [item for item in duplicatas if os.path.exists(item[1])]
            if len(duplicatas) <= 1:
                continue
            duplicatas.sort(key=lambda item: (pontuar_nome_para_manter(item[1]), item[0], item[1].lower()))
            log(f"[MANTIDO] {duplicatas[0][1]}")
            for item in duplicatas[1:]:
                _, caminho, ano, mes, _, _ = item
                caminho_norm = caminho_normalizado(caminho)
                if caminho_norm in removidas_norm:
                    continue
                try:
                    destino, _ = mover_para_quarentena(caminho, os.path.join(raiz, NOME_QUARENTENA), inicio_etapas, [ano, mes], args.executar)
                except OSError as erro:
                    duplicatas_erros += 1
                    log(f"[ERRO] Nao movi para quarentena: {caminho_curto(caminho)} ({erro})")
                    continue
                if args.executar and destino is None:
                    duplicatas_ausentes += 1
                    continue
                removidas_norm.add(caminho_norm)
                duplicatas_quarentena += 1
                mostrar, ultimo_movimento = deve_mostrar_progresso(duplicatas_quarentena, ultimo_movimento, lote=100)
                if mostrar:
                    relatorio(texto_progresso("Duplicatas ja enviadas/listadas para quarentena", duplicatas_quarentena, None, inicio_etapas))
    total_ano_solto = len(ano_solto_pelo_nome)
    ultimo_progresso = time.time()
    for indice, (caminho, destino, _) in enumerate(ano_solto_pelo_nome, start=1):
        mostrar, ultimo_progresso = deve_mostrar_progresso(indice, ultimo_progresso, lote=100, total=total_ano_solto)
        if mostrar and total_ano_solto:
            relatorio(texto_progresso("Movendo para o ano sem mes", indice, total_ano_solto, inicio))
        if caminho_normalizado(caminho) == caminho_normalizado(destino):
            continue
        log(f"[ANO SOLTO PELO NOME] {caminho_curto(caminho)} -> {caminho_curto(destino)}")
        if args.executar:
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            mover_com_historico(caminho, destino, executar=True)
        ano_solto_movidas += 1

    total_corrigidas = len(ano_corrigido_pelo_nome)
    ultimo_progresso = time.time()
    for indice, (caminho, destino, _) in enumerate(ano_corrigido_pelo_nome, start=1):
        mostrar, ultimo_progresso = deve_mostrar_progresso(indice, ultimo_progresso, lote=100, total=total_corrigidas)
        if mostrar and total_corrigidas:
            relatorio(texto_progresso("Movendo pelo ano do nome", indice, total_corrigidas, inicio))
        if caminho_normalizado(caminho) == caminho_normalizado(destino):
            continue
        log(f"[ANO DO NOME] {caminho_curto(caminho)} -> {caminho_curto(destino)}")
        if args.executar:
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            mover_com_historico(caminho, destino, executar=True)
        ano_corrigido_movidas += 1

    total_conflitantes = len(ano_conflitante)
    ultimo_progresso = time.time()
    for indice, (caminho, destino, _) in enumerate(ano_conflitante, start=1):
        mostrar, ultimo_progresso = deve_mostrar_progresso(indice, ultimo_progresso, lote=100, total=total_conflitantes)
        if mostrar and total_conflitantes:
            relatorio(texto_progresso("Separando ano conflitante", indice, total_conflitantes, inicio))
        if caminho_normalizado(caminho) == caminho_normalizado(destino):
            continue
        log(f"[ANO CONFLITANTE] {caminho_curto(caminho)} -> {caminho_curto(destino)}")
        if args.executar:
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            mover_com_historico(caminho, destino, executar=True)
        ano_conflitante_movidas += 1

    total_sem_data = len(sem_data)
    ultimo_progresso = time.time()
    for indice, (caminho, destino) in enumerate(sem_data, start=1):
        mostrar, ultimo_progresso = deve_mostrar_progresso(indice, ultimo_progresso, lote=100, total=total_sem_data)
        if mostrar and total_sem_data:
            relatorio(texto_progresso("Movendo sem data", indice, total_sem_data, inicio))
        if caminho_normalizado(caminho) == caminho_normalizado(destino):
            continue
        log(f"[SEM DATA] {caminho_curto(caminho)} -> {caminho_curto(destino)}")
        if args.executar:
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            mover_com_historico(caminho, destino, executar=True)
        sem_data_movidas += 1

    restantes = [item for item in midias if caminho_normalizado(item[1]) not in removidas_norm]
    restantes.sort(key=lambda item: (item[2], item[3], "/".join(item[4]).lower(), item[0], item[1].lower()))

    movidos = 0
    total_restantes = len(restantes)
    ultimo_progresso = 0
    for indice, (_, caminho, ano, mes, partes, _) in enumerate(restantes, start=1):
        mostrar, ultimo_progresso = deve_mostrar_progresso(indice, ultimo_progresso, lote=100, total=total_restantes)
        if mostrar and total_restantes:
            relatorio(texto_progresso("Organizando por data", indice, total_restantes, inicio_etapas))
        destino_dir = os.path.join(raiz, ano, mes, *partes)
        destino = gerar_caminho_unico(os.path.join(destino_dir, os.path.basename(caminho)))
        if caminho_normalizado(caminho) == caminho_normalizado(destino):
            continue
        log(f"[ORGANIZAR] {caminho_curto(caminho)} -> {caminho_curto(destino)}")
        if args.executar:
            os.makedirs(destino_dir, exist_ok=True)
            mover_com_historico(caminho, destino, executar=True)
        movidos += 1

    acao_arquivos = "enviados" if args.executar else "que iriam"
    acao_duplicatas = "enviadas" if args.executar else "que iriam"
    relatorio(f"RELATORIO - album organizar | {nome_alvo(raiz)}", respiro=True)
    relatorio(f"Pasta: {raiz}")
    relatorio(f"Midias analisadas: {len(midias) + len(sem_data) + len(ano_solto_pelo_nome) + len(ano_corrigido_pelo_nome) + len(ano_conflitante) + fotos_antigas_preservadas}")
    relatorio(f"Arquivos {acao_arquivos} soltos no ano pelo nome: {ano_solto_movidas}")
    relatorio(f"Arquivos {acao_arquivos} pelo ano do nome/caminho: {ano_corrigido_movidas}")
    relatorio(f"Arquivos {acao_arquivos} para {NOME_ANO_CONFLITANTE}: {ano_conflitante_movidas}")
    relatorio(f"Arquivos {acao_arquivos} para {NOME_SEM_DATA}: {sem_data_movidas}")
    relatorio(f"Fotos Antigas preservadas sem pista clara no nome: {fotos_antigas_preservadas}")
    relatorio(f"Duplicatas {acao_duplicatas} para {NOME_QUARENTENA}: {duplicatas_quarentena}")
    if duplicatas_ausentes:
        relatorio(f"Duplicatas que sumiram antes de mover: {duplicatas_ausentes}")
    if duplicatas_erros:
        relatorio(f"Erros ao mover duplicatas para quarentena: {duplicatas_erros}")
    relatorio(f"Arquivos organizados/listados por data: {movidos}")

    relatorio(f"Tempo: {formatar_tempo(time.time() - inicio)}")

