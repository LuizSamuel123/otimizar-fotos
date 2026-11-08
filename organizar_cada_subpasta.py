import argparse
import os
import time

from otimizar_fotos import *
from organizar_por_data import organizar_album
from quarentena import quarentena_album


# =============================================================================
# Organizar album em lote por subpasta
# =============================================================================


def subpastas_de_trabalho(raiz):
    subpastas = []
    try:
        nomes = os.listdir(raiz)
    except OSError:
        return subpastas

    for nome in nomes:
        caminho = os.path.join(raiz, nome)
        if not os.path.isdir(caminho):
            continue
        if ignorar_dir(nome):
            continue
        subpastas.append(caminho)
    return sorted(subpastas, key=lambda caminho: os.path.basename(caminho).casefold())


def criar_args_etapa(args, pasta):
    valores = vars(args).copy()
    valores.update({
        "pasta": pasta,
        "sim": True if args.executar else getattr(args, "sim", False),
        "permitir_pasta_grande": True,
    })
    return argparse.Namespace(**valores)


def comando_album_subpastas(args):
    if bloquear_pasta_ampla_se_preciso(args, "album subpastas"):
        return

    inicio = time.time()
    raiz = os.path.abspath(args.pasta)
    subpastas = subpastas_de_trabalho(raiz)

    relatorio(f"RELATORIO - album subpastas | {nome_alvo(raiz)}", respiro=True)
    relatorio(f"Pasta pai: {raiz}")
    relatorio(f"Subpastas selecionadas: {len(subpastas)}")

    if not subpastas:
        relatorio("Nada para processar.")
        return

    if args.executar and not confirmar(
        f"Rodar organizar e quarentena em {len(subpastas)} subpasta(s)?",
        args.sim,
    ):
        relatorio("Cancelado.")
        return

    for indice, subpasta in enumerate(subpastas, start=1):
        relatorio(
            f"RELATORIO - album subpastas etapa {indice}/{len(subpastas)} | {nome_alvo(subpasta)}",
            respiro=True,
        )
        relatorio(f"Pasta: {subpasta}")
        etapa_args = criar_args_etapa(args, subpasta)
        organizar_album(etapa_args)
        quarentena_album(etapa_args)

    relatorio(f"RELATORIO - album subpastas final | {nome_alvo(raiz)}", respiro=True)
    relatorio(f"Pasta pai: {raiz}")
    relatorio(f"Subpastas processadas/listadas: {len(subpastas)}")
    relatorio(f"Tempo total: {formatar_tempo(time.time() - inicio)}")

