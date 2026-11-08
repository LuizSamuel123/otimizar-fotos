import argparse
import os
import shutil
import time


IGNORAR_PASTAS = {
    ".agents",
    ".git",
    ".hg",
    ".maestro_historico",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".venv",
    "env",
    "node_modules",
    "venv",
}


def formatar_tempo(segundos):
    segundos = max(0, int(segundos))
    minutos, segundos = divmod(segundos, 60)
    horas, minutos = divmod(minutos, 60)
    if horas:
        return f"{horas}h {minutos}m {segundos}s"
    return f"{minutos}m {segundos}s"


def encontrar_pycache(raiz):
    encontrados = []
    inicio = time.time()
    ultimo_progresso = time.time()
    analisadas = 0
    for pasta_atual, subpastas, _ in os.walk(raiz, topdown=True):
        analisadas += 1
        agora = time.time()
        if analisadas % 500 == 0 or agora - ultimo_progresso >= 15:
            print(f"Procurando pycache: {analisadas} pastas | decorrido: {formatar_tempo(agora - inicio)}", flush=True)
            ultimo_progresso = agora
        manter = []
        for subpasta in subpastas:
            if subpasta == "__pycache__":
                encontrados.append(os.path.join(pasta_atual, subpasta))
            elif subpasta.casefold() not in IGNORAR_PASTAS:
                manter.append(subpasta)
        subpastas[:] = manter
    return sorted(encontrados, key=lambda caminho: caminho.casefold())


def limpar_pycache(raiz, executar=False, detalhado=False):
    inicio = time.time()
    raiz = os.path.abspath(raiz)
    encontrados = encontrar_pycache(raiz)
    removidos = 0
    erros = 0

    if executar:
        total_encontrados = len(encontrados)
        ultimo_progresso = time.time()
        for indice, pasta in enumerate(encontrados, start=1):
            agora = time.time()
            if indice == 1 or indice == total_encontrados or indice % 100 == 0 or agora - ultimo_progresso >= 15:
                percentual = indice / total_encontrados * 100 if total_encontrados else 100
                print(f"Removendo pycache: {indice}/{total_encontrados} ({percentual:.1f}%)", flush=True)
                ultimo_progresso = agora
            try:
                if os.path.isdir(pasta):
                    shutil.rmtree(pasta)
                    removidos += 1
                    if detalhado:
                        print(f"[REMOVIDO] {pasta}", flush=True)
            except OSError as erro:
                erros += 1
                if detalhado:
                    print(f"[ERRO] {pasta} ({erro})", flush=True)
    elif detalhado:
        for pasta in encontrados:
            print(f"[PYCACHE] {pasta}", flush=True)

    print("RELATORIO - limpar pycache", flush=True)
    print(f"Pasta: {raiz}", flush=True)
    print(f"Pycache encontrados: {len(encontrados)}", flush=True)
    if executar:
        print(f"Pycache removidos: {removidos}", flush=True)
        print(f"Erros/ignorados: {erros}", flush=True)
    else:
        print(f"Pycache que seriam removidos: {len(encontrados)}", flush=True)
        print("Nada foi removido. Use --executar para limpar de verdade.", flush=True)
    print(f"Tempo: {formatar_tempo(time.time() - inicio)}", flush=True)
    return len(encontrados), removidos, erros


def criar_parser():
    parser = argparse.ArgumentParser(
        description="Remove pastas __pycache__ de uma arvore de codigo.",
    )
    parser.add_argument("pasta", nargs="?", default=".", help="Pasta alvo. Padrao: pasta atual.")
    parser.add_argument("--executar", action="store_true", help="Remove de verdade. Sem isso, apenas simula.")
    parser.add_argument("--vigiar", action="store_true", help="Fica rodando e limpando em intervalo.")
    parser.add_argument("--intervalo", type=int, default=30, help="Segundos entre limpezas no modo --vigiar.")
    parser.add_argument("--detalhado", action="store_true", help="Mostra cada pasta __pycache__ encontrada/removida.")
    return parser


def main(argv=None):
    args = criar_parser().parse_args(argv)
    intervalo = max(2, args.intervalo)

    while True:
        limpar_pycache(args.pasta, executar=args.executar, detalhado=args.detalhado)
        if not args.vigiar:
            break
        print(f"\nVigiando. Proxima limpeza em {intervalo}s. Use Ctrl+C para parar.\n", flush=True)
        try:
            time.sleep(intervalo)
        except KeyboardInterrupt:
            print("Vigia encerrada.", flush=True)
            break


if __name__ == "__main__":
    main()

