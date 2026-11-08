import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import unicodedata
from datetime import datetime


MEDIA_EXTS = {
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".heic", ".heif",
    ".mp4", ".mov", ".avi", ".mkv", ".wmv", ".m4v", ".webm", ".3gp", ".mpeg", ".mpg",
}

IMAGE_EXTS = {
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".heic", ".heif",
}

MESES = {
    1: "1) Janeiro",
    2: "2) Fevereiro",
    3: "3) Marco",
    4: "4) Abril",
    5: "5) Maio",
    6: "6) Junho",
    7: "7) Julho",
    8: "8) Agosto",
    9: "9) Setembro",
    10: "10) Outubro",
    11: "11) Novembro",
    12: "12) Dezembro",
}

SEM_DATA = "nao_sei(verificar)"
ANO_CONFLITANTE = "ano_conflitante(verificar)"
QUARENTENA = "1-QUARENTENA"

PADRAO_ANO = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")
PADROES_DATA_NOME = (
    re.compile(r"(?<!\d)(?P<ano>19\d{2}|20\d{2})[-_.\s](?P<mes>0?[1-9]|1[0-2])[-_.\s](?P<dia>0?[1-9]|[12]\d|3[01])(?!\d)"),
    re.compile(r"(?<!\d)(?P<dia>0?[1-9]|[12]\d|3[01])[-_.\s](?P<mes>0?[1-9]|1[0-2])[-_.\s](?P<ano>19\d{2}|20\d{2})(?!\d)"),
    re.compile(r"(?<!\d)(?P<ano>19\d{2}|20\d{2})(?P<mes>0[1-9]|1[0-2])(?P<dia>0[1-9]|[12]\d|3[01])(?!\d)"),
)

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


def sem_acentos(texto):
    normal = unicodedata.normalize("NFKD", str(texto))
    return "".join(ch for ch in normal if not unicodedata.combining(ch))


def normalizar(texto):
    return sem_acentos(str(texto).strip().casefold())


def limpar_nome_pasta(nome):
    original = str(nome).strip()
    nome_limpo = original
    while True:
        novo = re.sub(r"^\s*(?:[\(\[\{]\d{1,3}[\)\]\}]|\d{1,3}[\)\]\}]|\d{1,3}\s*[-_.])\s*", "", nome_limpo).strip()
        if novo == nome_limpo:
            break
        nome_limpo = novo
    nome_limpo = re.sub(r"\s*[\(\[\{]\d{1,3}[\)\]\}]\s*$", "", nome_limpo).strip()
    return nome_limpo or original


def texto_busca(texto):
    texto = normalizar(texto)
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return f" {texto.strip()} "


def contem_termo(texto, termo):
    return f" {texto_busca(termo).strip()} " in texto


def mes_por_nome(nome):
    texto = texto_busca(os.path.splitext(str(nome))[0])
    for mes, termos in PALAVRAS_MES.items():
        if any(contem_termo(texto, termo) for termo in termos):
            return mes
    for mes, termos in PALAVRAS_EVENTO_MES.items():
        if any(contem_termo(texto, termo) for termo in termos):
            return mes
    return None


def mes_por_parte(parte):
    chave = normalizar(limpar_nome_pasta(parte))
    for numero, nome_mes in MESES.items():
        if chave == normalizar(limpar_nome_pasta(nome_mes)):
            return numero
    return None


def ano_pasta(parte):
    texto = str(parte).strip()
    return int(texto) if re.fullmatch(r"(?:19|20)\d{2}", texto) else None


def parse_data_texto(valor):
    if isinstance(valor, bytes):
        valor = valor.decode("utf-8", errors="ignore")
    valor = str(valor or "").strip().replace("\x00", "")
    if not valor:
        return None
    formatos = (
        "%Y:%m:%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
    )
    for formato in formatos:
        try:
            return datetime.strptime(valor, formato)
        except ValueError:
            pass
    return None


def parse_data_windows(valor):
    texto = re.sub(r"[^\d/: -]+", "", str(valor or "")).strip()
    texto = re.sub(r"\s+", " ", texto)
    return parse_data_texto(texto)


def data_nome(nome):
    texto = os.path.splitext(str(nome))[0]
    for padrao in PADROES_DATA_NOME:
        achou = padrao.search(texto)
        if not achou:
            continue
        ano = int(achou.group("ano"))
        mes = int(achou.group("mes"))
        dia = int(achou.group("dia"))
        if 1900 <= ano <= 2099 and 1 <= mes <= 12 and 1 <= dia <= 31:
            return datetime(ano, mes, dia)
    return None


def anos_nome(nome):
    anos = {int(ano) for ano in PADRAO_ANO.findall(str(nome))}
    data = data_nome(nome)
    if data:
        anos.add(data.year)
    return sorted(anos)


def data_exif_imagem(caminho):
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(caminho) as imagem:
            exif = imagem.getexif()
            for tag in (36867, 36868, 306):
                data = parse_data_texto(exif.get(tag))
                if data:
                    return data
    except Exception:
        return None
    return None


def data_bruta_imagem(caminho):
    try:
        with open(caminho, "rb") as arquivo:
            dados = arquivo.read(2 * 1024 * 1024)
    except OSError:
        return None
    for padrao in (
        rb"(?:19|20)\d{2}:\d{2}:\d{2} \d{2}:\d{2}:\d{2}",
        rb"(?:19|20)\d{2}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}",
    ):
        for achou in re.finditer(padrao, dados):
            data = parse_data_texto(achou.group(0))
            if data:
                return data
    return None


def data_video_ffprobe(caminho):
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
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except Exception:
        return None
    if resultado.returncode != 0 or not resultado.stdout:
        return None
    try:
        dados = json.loads(resultado.stdout)
    except json.JSONDecodeError:
        return None
    valores = [dados.get("format", {}).get("tags", {}).get("creation_time")]
    for stream in dados.get("streams", []):
        valores.append(stream.get("tags", {}).get("creation_time"))
    for valor in valores:
        data = parse_data_texto(valor)
        if data:
            return data
    return None


def ps_literal(texto):
    return "'" + str(texto).replace("'", "''") + "'"


def datas_windows(root):
    if os.name != "nt":
        return {}
    script = f"""
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$root = {ps_literal(os.path.abspath(root))}
$shell = New-Object -ComObject Shell.Application
$cache = @{{}}
$rows = @()
foreach ($file in Get-ChildItem -LiteralPath $root -Recurse -File) {{
    $dir = $file.DirectoryName
    if (-not $cache.ContainsKey($dir)) {{
        $cache[$dir] = $shell.Namespace($dir)
    }}
    $folder = $cache[$dir]
    if ($folder -eq $null) {{ continue }}
    $item = $folder.ParseName($file.Name)
    if ($item -eq $null) {{ continue }}
    $dateTaken = $folder.GetDetailsOf($item, 12)
    if ($dateTaken) {{
        $rows += [PSCustomObject]@{{ FullName = $file.FullName; DateTaken = $dateTaken }}
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
            timeout=180,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except Exception:
        return {}
    if resultado.returncode != 0 or not resultado.stdout.strip():
        return {}
    try:
        dados = json.loads(resultado.stdout)
    except json.JSONDecodeError:
        return {}
    if isinstance(dados, dict):
        dados = [dados]
    saida = {}
    for item in dados if isinstance(dados, list) else []:
        caminho = item.get("FullName")
        data = parse_data_windows(item.get("DateTaken"))
        if caminho and data:
            saida[os.path.normcase(os.path.abspath(caminho))] = data
    return saida


def hash_arquivo(caminho):
    hasher = hashlib.sha256()
    with open(caminho, "rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            hasher.update(bloco)
    return hasher.hexdigest()


def partes_contexto(root, caminho):
    rel_dir = os.path.relpath(os.path.dirname(caminho), root)
    if rel_dir == ".":
        return []
    partes = []
    ignorar = {
        normalizar(SEM_DATA),
        normalizar(ANO_CONFLITANTE),
        normalizar(QUARENTENA),
        "fotos",
        "imagens",
        "videos",
        "fotos_imagens",
        "sem_album",
    }
    for parte in rel_dir.split(os.sep):
        chave = normalizar(parte)
        if chave in ignorar:
            continue
        if ano_pasta(parte) is not None:
            continue
        if mes_por_parte(parte) is not None:
            continue
        partes.append(limpar_nome_pasta(parte))
    return partes


def ano_mes_do_caminho(root, caminho):
    rel_dir = os.path.relpath(os.path.dirname(caminho), root)
    if rel_dir == ".":
        return None, None
    ano = None
    mes = None
    for parte in rel_dir.split(os.sep):
        if ano is None:
            ano = ano_pasta(parte)
        if mes is None:
            mes = mes_por_parte(parte)
    return ano, mes


def gerar_destino_unico(destino, ocupados, origem=None):
    destino_norm = os.path.normcase(os.path.abspath(destino))
    origem_norm = os.path.normcase(os.path.abspath(origem)) if origem else None
    if origem_norm and destino_norm == origem_norm:
        ocupados.add(destino_norm)
        return destino

    pasta, nome = os.path.split(destino)
    base, ext = os.path.splitext(nome)
    candidato = destino
    contador = 1
    while os.path.normcase(os.path.abspath(candidato)) in ocupados or os.path.exists(candidato):
        candidato = os.path.join(pasta, f"{base}__codex_{contador}{ext}")
        contador += 1
    ocupados.add(os.path.normcase(os.path.abspath(candidato)))
    return candidato


def classificar(root, caminho, windows_map):
    nome = os.path.basename(caminho)
    ext = os.path.splitext(nome)[1].lower()
    path_ano, path_mes = ano_mes_do_caminho(root, caminho)
    contexto = partes_contexto(root, caminho)

    data = None
    fonte = None
    if ext in IMAGE_EXTS:
        data = data_exif_imagem(caminho) or data_bruta_imagem(caminho)
        if data:
            fonte = "metadado_imagem"
    else:
        data = data_video_ffprobe(caminho)
        if data:
            fonte = "metadado_video"

    if not data:
        data = data_nome(nome)
        if data:
            fonte = "data_no_nome"

    if data:
        return data.year, data.month, fonte, contexto

    anos = anos_nome(nome)
    if len(anos) == 1:
        mes = mes_por_nome(nome) or path_mes
        if mes:
            return anos[0], mes, "ano_no_nome_mes_do_contexto", contexto
        return anos[0], None, "ano_no_nome_sem_mes", contexto

    data = windows_map.get(os.path.normcase(os.path.abspath(caminho)))
    if data:
        return data.year, data.month, "data_tirada_windows_ultima_instancia", contexto

    mes_nome = mes_por_nome(nome)
    if path_ano and (mes_nome or path_mes):
        return path_ano, mes_nome or path_mes, "ano_mes_do_caminho", contexto

    if path_ano:
        return path_ano, None, "ano_do_caminho_sem_mes", contexto

    return None, None, "sem_data_confiavel", contexto


def montar_plano(root):
    root = os.path.abspath(root)
    windows_map = datas_windows(root)
    midias = []
    for pasta_atual, subpastas, arquivos in os.walk(root):
        subpastas[:] = [p for p in subpastas if normalizar(p) not in {".git", ".maestro_historico", "__pycache__"}]
        for nome in arquivos:
            ext = os.path.splitext(nome)[1].lower()
            if ext not in MEDIA_EXTS:
                continue
            origem = os.path.join(pasta_atual, nome)
            ano, mes, fonte, contexto = classificar(root, origem, windows_map)
            if ano and mes:
                destino_dir = os.path.join(root, str(ano), MESES[mes], *contexto)
            elif ano:
                destino_dir = os.path.join(root, str(ano), SEM_DATA, *contexto)
            else:
                destino_dir = os.path.join(root, SEM_DATA, *contexto)
            destino = os.path.join(destino_dir, nome)
            midias.append({
                "origem": origem,
                "destino_base": destino,
                "ano": ano,
                "mes": mes,
                "fonte": fonte,
                "contexto": os.path.join(*contexto) if contexto else "",
            })
    ocupados = set()
    for item in midias:
        item["destino"] = gerar_destino_unico(item["destino_base"], ocupados, origem=item["origem"])
        item["mover"] = os.path.normcase(os.path.abspath(item["origem"])) != os.path.normcase(os.path.abspath(item["destino"]))
    return midias


def salvar_relatorio(plano, caminho_csv):
    os.makedirs(os.path.dirname(os.path.abspath(caminho_csv)), exist_ok=True)
    with open(caminho_csv, "w", newline="", encoding="utf-8-sig") as arquivo:
        campos = ["mover", "fonte", "ano", "mes", "origem", "destino"]
        writer = csv.DictWriter(arquivo, fieldnames=campos)
        writer.writeheader()
        for item in plano:
            writer.writerow({campo: item.get(campo, "") for campo in campos})


def mover(plano):
    movidos = 0
    erros = 0
    for item in sorted((p for p in plano if p["mover"]), key=lambda x: x["origem"].count(os.sep), reverse=True):
        origem = item["origem"]
        destino = item["destino"]
        if not os.path.exists(origem):
            continue
        try:
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            shutil.move(origem, destino)
            movidos += 1
        except OSError as erro:
            erros += 1
            print(f"[ERRO] {origem} -> {destino}: {erro}", flush=True)
    return movidos, erros


def remover_vazias(root):
    removidas = 0
    for pasta_atual, subpastas, arquivos in os.walk(root, topdown=False):
        if os.path.normcase(os.path.abspath(pasta_atual)) == os.path.normcase(os.path.abspath(root)):
            continue
        try:
            if not os.listdir(pasta_atual):
                os.rmdir(pasta_atual)
                removidas += 1
        except OSError:
            pass
    return removidas


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("--executar", action="store_true")
    parser.add_argument("--relatorio", required=True)
    args = parser.parse_args()

    plano = montar_plano(args.root)
    salvar_relatorio(plano, args.relatorio)

    por_fonte = {}
    for item in plano:
        por_fonte[item["fonte"]] = por_fonte.get(item["fonte"], 0) + 1

    print(f"Midias analisadas: {len(plano)}")
    print(f"Arquivos a mover: {sum(1 for item in plano if item['mover'])}")
    print("Fontes de data:")
    for fonte, total in sorted(por_fonte.items(), key=lambda x: (-x[1], x[0])):
        print(f"- {fonte}: {total}")
    print(f"Relatorio: {args.relatorio}")

    if not args.executar:
        print("Modo teste: nada foi movido.")
        return

    movidos, erros = mover(plano)
    vazias = remover_vazias(args.root)
    print(f"Movidos: {movidos}")
    print(f"Erros: {erros}")
    print(f"Pastas vazias removidas: {vazias}")


if __name__ == "__main__":
    main()
