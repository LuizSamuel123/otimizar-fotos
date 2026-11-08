import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


PASTA_PROGRAMA = Path(__file__).resolve().parent
MAESTRO = PASTA_PROGRAMA / "otimizar_fotos.py"

TAREFAS = [
    ("album_organizar", "Separação por Datas, Meses e Eventos", "Organiza fotos e videos por ano e mês quando ha data confiavel. Se souber so o ano, deixa solto no ano; Fotos Antigas ficam preservadas sem pista clara no nome.", ["pasta", "executar", "sim"]),
    ("album_quarentena", "Removedor de Redundância", "Procura fotos e videos repetidos e separa as copias em 1-QUARENTENA. Ele nao apaga automaticamente.", ["pasta", "executar", "sim"]),
    ("album_auditar_anos", "Rever Datas Duvidosas", "Procura itens que parecem estar no ano errado, usa o ano do nome quando estiver claro e separa apenas os ambiguos para conferencia.", ["pasta", "limite", "executar", "sim"]),
]
TAREFAS_POR_ID = {item[0]: item for item in TAREFAS}
IDS_POR_NOME = {item[1]: item[0] for item in TAREFAS}


class AssistenteMaestro(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Organizar Fotos")
        self.geometry("960x700")
        self.minsize(900, 640)

        self.tarefa_var = tk.StringVar(value=TAREFAS_POR_ID["album_organizar"][1])
        self.pasta_var = tk.StringVar()
        self.ano_base_var = tk.StringVar()
        self.ano_citado_var = tk.StringVar()
        self.limite_var = tk.StringVar(value="80")

        self.campos = {}
        self.checks = {}
        self.processo_rodando = False
        self.recuperando = False
        self.ultima_pasta_executada = None
        self.ultimo_passos_recuperar = 0

        self._montar_tela()
        self._atualizar_visibilidade()

    def _montar_tela(self):
        raiz = ttk.Frame(self, padding=16)
        raiz.pack(fill="both", expand=True)
        raiz.columnconfigure(0, weight=1)
        raiz.rowconfigure(5, weight=1)

        estilo = ttk.Style(self)
        estilo.configure("Titulo.TLabel", font=("Segoe UI", 13, "bold"))
        estilo.configure("Descricao.TLabel", font=("Segoe UI", 9))
        estilo.configure("Acao.TButton", font=("Segoe UI", 10, "bold"), padding=(18, 10))

        topo = ttk.Frame(raiz)
        topo.grid(row=0, column=0, sticky="ew")
        topo.columnconfigure(0, weight=1)

        ttk.Label(topo, text="Etapa 1 - Organizar o album", style="Titulo.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            topo,
            text="Separacao por datas, remocao de redundancia e revisao de datas duvidosas.",
            style="Descricao.TLabel",
            wraplength=840,
        ).grid(row=1, column=0, sticky="w", pady=(3, 4))
        self.botoes_tarefa = {}
        for linha, tarefa_id in enumerate(("album_organizar", "album_quarentena", "album_auditar_anos"), start=2):
            _id, nome, descricao, _recursos = TAREFAS_POR_ID[tarefa_id]
            bloco = ttk.Frame(topo, padding=(0, 10, 0, 4))
            bloco.grid(row=linha, column=0, sticky="ew", pady=(0, 8))
            bloco.columnconfigure(1, weight=1)
            botao = ttk.Button(bloco, text=nome, width=38, style="Acao.TButton", command=lambda tid=tarefa_id: self._selecionar_tarefa(tid))
            botao.grid(row=0, column=0, sticky="nsew", padx=(0, 16), ipady=4)
            ttk.Label(bloco, text=descricao, wraplength=620).grid(row=0, column=1, sticky="w", pady=(0, 2))
            self.botoes_tarefa[tarefa_id] = botao

        self.nome_tarefa = ttk.Label(topo, text="", style="Descricao.TLabel", wraplength=840)
        self.nome_tarefa.grid(row=6, column=0, sticky="w", pady=(4, 0))
        self.descricao = ttk.Label(topo, text="", wraplength=840, style="Descricao.TLabel")
        self.descricao.grid_remove()

        formulario = ttk.LabelFrame(raiz, text="Onde estao suas fotos?", padding=12)
        formulario.grid(row=1, column=0, sticky="ew", pady=(14, 10))
        formulario.columnconfigure(1, weight=1)
        self.formulario = formulario

        self._linha_pasta("pasta", "Pasta escolhida", self.pasta_var, 0)
        self._linha_texto("ano_base", "Ano da pasta que sera conferida", self.ano_base_var, 1)
        self._linha_texto("ano_citado", "Ano que aparece no nome", self.ano_citado_var, 2)
        self._linha_texto("limite", "Quantidade maxima para mostrar", self.limite_var, 3)


        botoes = ttk.Frame(raiz)
        botoes.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        botoes.columnconfigure(0, weight=1)
        botoes.columnconfigure(1, weight=1)
        self.botao_analisar = ttk.Button(botoes, text="Analisar pedido", style="Acao.TButton", command=lambda: self._executar_pedido(efetuar=False))
        self.botao_efetuar = ttk.Button(botoes, text="Efetuar", style="Acao.TButton", command=lambda: self._executar_pedido(efetuar=True))
        self.botao_recuperar = ttk.Button(botoes, text="Recuperar última alteração", style="Acao.TButton", command=self._recuperar_ultima_alteracao)
        self.botao_analisar.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.botao_efetuar.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self.botao_recuperar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.botao_recuperar.configure(state="disabled")

        ttk.Label(raiz, text="Resultado").grid(row=4, column=0, sticky="w")
        self.saida = tk.Text(raiz, height=9, wrap="word", undo=False)
        self.saida.grid(row=5, column=0, sticky="nsew", pady=(6, 0))
        self.saida.configure(font=("Consolas", 10))
        self._configurar_menu_saida(self.saida)

        aviso = ttk.Label(
            raiz,
            text="Use Analisar pedido primeiro. Efetuar muda arquivos de verdade, entao use somente com backup.",
            wraplength=860,
        )
        aviso.grid(row=6, column=0, sticky="w", pady=(10, 0))

    def _linha_pasta(self, chave, rotulo, variavel, linha):
        label = ttk.Label(self.formulario, text=rotulo)
        entrada = ttk.Entry(self.formulario, textvariable=variavel)
        botao = ttk.Button(self.formulario, text="Clique aqui para escolher a pasta", command=lambda: self._escolher_pasta(variavel))
        dica = ttk.Label(self.formulario, text="Ou cole o caminho da pasta no campo acima.")
        label.grid(row=linha, column=0, sticky="w", pady=3, padx=(0, 10))
        entrada.grid(row=linha, column=1, sticky="ew", pady=3)
        botao.grid(row=linha, column=2, sticky="e", pady=3, padx=(8, 0))
        dica.grid(row=linha + 1, column=1, columnspan=2, sticky="w", pady=(0, 6))
        self._configurar_menu_entrada(entrada)
        self.campos[chave] = (label, entrada, botao, dica)

    def _linha_texto(self, chave, rotulo, variavel, linha):
        linha_real = linha + 1
        label = ttk.Label(self.formulario, text=rotulo)
        entrada = ttk.Entry(self.formulario, textvariable=variavel, width=12)
        label.grid(row=linha_real, column=0, sticky="w", pady=3, padx=(0, 10))
        entrada.grid(row=linha_real, column=1, sticky="w", pady=3)
        self._configurar_menu_entrada(entrada)
        self.campos[chave] = (label, entrada)

    def _mostrar_menu(self, menu, evento):
        try:
            evento.widget.focus_set()
            menu.tk_popup(evento.x_root, evento.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _selecionar_entrada(self, entrada):
        entrada.focus_set()
        entrada.selection_range(0, tk.END)
        entrada.icursor(tk.END)

    def _limpar_entrada(self, entrada):
        entrada.delete(0, tk.END)

    def _configurar_menu_entrada(self, entrada):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Recortar", command=lambda w=entrada: w.event_generate("<<Cut>>"))
        menu.add_command(label="Copiar", command=lambda w=entrada: w.event_generate("<<Copy>>"))
        menu.add_command(label="Colar", command=lambda w=entrada: w.event_generate("<<Paste>>"))
        menu.add_separator()
        menu.add_command(label="Selecionar tudo", command=lambda w=entrada: self._selecionar_entrada(w))
        menu.add_command(label="Limpar", command=lambda w=entrada: self._limpar_entrada(w))
        entrada.bind("<Button-3>", lambda evento, m=menu: self._mostrar_menu(m, evento))

    def _selecionar_texto(self, texto):
        texto.focus_set()
        texto.tag_add("sel", "1.0", "end-1c")
        texto.mark_set("insert", "end-1c")

    def _copiar_texto_tudo(self, texto):
        conteudo = texto.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(conteudo)

    def _configurar_menu_saida(self, texto):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Copiar selecionado", command=lambda w=texto: w.event_generate("<<Copy>>"))
        menu.add_command(label="Copiar tudo", command=lambda w=texto: self._copiar_texto_tudo(w))
        menu.add_separator()
        menu.add_command(label="Selecionar tudo", command=lambda w=texto: self._selecionar_texto(w))
        texto.bind("<Button-3>", lambda evento, m=menu: self._mostrar_menu(m, evento))

    def _selecionar_tarefa(self, tarefa_id):
        self.tarefa_var.set(TAREFAS_POR_ID[tarefa_id][1])
        self._atualizar_visibilidade()

    def _tarefa_mudou(self):
        self._atualizar_visibilidade()

    def _tarefa_id(self):
        valor = self.tarefa_var.get()
        return IDS_POR_NOME.get(valor, valor)

    def _recursos_atuais(self):
        tarefa_id = self._tarefa_id()
        return TAREFAS_POR_ID[tarefa_id]

    def _atualizar_visibilidade(self):
        tarefa_id, nome, _descricao, recursos = self._recursos_atuais()
        self.nome_tarefa.configure(text=f"Selecionado: {nome}")
        for chave, botao in getattr(self, "botoes_tarefa", {}).items():
            botao.configure(state="disabled" if chave == tarefa_id else "normal")

        for chave, widgets in self.campos.items():
            for widget in widgets:
                widget.grid() if chave in recursos else widget.grid_remove()


    def _escolher_pasta(self, variavel):
        inicial = variavel.get().strip() or str(Path.home())
        escolhido = filedialog.askdirectory(initialdir=inicial, title="Escolha a pasta onde estao suas fotos")
        if escolhido:
            variavel.set(escolhido)

    def _validar_pedido(self):
        _tarefa_id, _nome, _descricao, recursos = self._recursos_atuais()
        if "pasta" not in recursos:
            return True

        pasta = self.pasta_var.get().strip()
        if not pasta:
            messagebox.showwarning("Organizar Fotos", "Escolha ou cole o caminho da pasta primeiro.")
            return False
        if not Path(pasta).exists():
            messagebox.showwarning("Organizar Fotos", "Nao encontrei essa pasta. Confira o caminho informado.")
            return False
        return True

    def _montar_argumentos(self, efetuar):
        tarefa_id, _nome, _descricao, recursos = self._recursos_atuais()
        pasta = self.pasta_var.get().strip()
        args = [sys.executable, str(MAESTRO)]

        if tarefa_id == "album_organizar":
            args.extend(["organizar", pasta])
        elif tarefa_id == "album_quarentena":
            args.extend(["quarentena", pasta])
        elif tarefa_id == "album_auditar_anos":
            args.extend(["auditar-anos", pasta])
            self._adicionar_limite(args)

        if efetuar and "executar" in recursos:
            args.append("--executar")
        if "sim" in recursos:
            args.append("--sim")

        return args

    def _executar_pedido(self, efetuar):
        if self.processo_rodando:
            return
        if not self._validar_pedido():
            return

        _tarefa_id, nome, _descricao, recursos = self._recursos_atuais()
        if efetuar and "executar" in recursos:
            confirmou = messagebox.askyesno(
                "Confirmar execucao",
                "Isto vai mexer nos arquivos de verdade. Use somente se voce ja tem backup.\n\nDeseja continuar?",
            )
            if not confirmou:
                return

        comandos = self._montar_comandos(efetuar=efetuar)
        self.recuperando = False
        titulo = "EFETUANDO" if efetuar else "ANALISANDO"
        self._limpar_resultado()
        self._anexar_resultado(f"{titulo}: {nome}\n")
        self._anexar_resultado(f"Pasta: {self.pasta_var.get().strip()}\n\n")
        if not efetuar and "executar" in recursos:
            self._anexar_resultado("Modo teste: nada sera alterado nesta analise.\n\n")

        self._marcar_rodando(True)
        thread = threading.Thread(target=self._rodar_em_segundo_plano, args=(comandos,), daemon=True)
        thread.start()

    def _montar_comandos(self, efetuar):
        tarefa_id = self._tarefa_id()
        _id, _nome, _descricao, recursos = TAREFAS_POR_ID[tarefa_id]
        if tarefa_id != "album_auditar_anos":
            altera_arquivos = efetuar and "executar" in recursos
            return [(None, self._montar_argumentos(efetuar), altera_arquivos)]

        pasta = self.pasta_var.get().strip()
        comandos = []

        auditar = [sys.executable, str(MAESTRO), "auditar-anos", pasta]
        self._adicionar_limite(auditar)
        comandos.append(("1/3 - Procurando itens que parecem estar no ano errado", auditar, False))

        separar = [sys.executable, str(MAESTRO), "separar-conflitos", pasta]
        self._adicionar_anos(separar)
        self._adicionar_limite(separar)
        if efetuar:
            separar.append("--executar")
        separar.append("--sim")
        comandos.append(("2/3 - Movendo conflitos com ano claro para o local certo", separar, efetuar))

        resolver = [sys.executable, str(MAESTRO), "resolver-nao-sei", pasta]
        if efetuar:
            resolver.append("--executar")
        resolver.append("--sim")
        comandos.append(("3/3 - Tentando organizar arquivos sem data pelo nome", resolver, efetuar))

        return comandos

    def _rodar_em_segundo_plano(self, comandos):
        codigo = 0
        alteracoes_ok = 0
        try:
            for titulo, args, altera_arquivos in comandos:
                if titulo:
                    self.after(0, self._anexar_resultado, f"\n=== {titulo} ===\n")
                processo = subprocess.Popen(
                    args,
                    cwd=str(PASTA_PROGRAMA),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                )
                if processo.stdout:
                    for linha in processo.stdout:
                        self.after(0, self._anexar_resultado, linha)
                codigo = processo.wait()
                if codigo == 0 and altera_arquivos:
                    alteracoes_ok += 1
                if codigo != 0:
                    break
        except Exception as erro:
            codigo = 1
            self.after(0, self._anexar_resultado, f"\nErro ao executar: {erro}\n")
        self.after(0, self._finalizar_execucao, codigo, alteracoes_ok)

    def _limpar_resultado(self):
        self.saida.delete("1.0", "end")

    def _anexar_resultado(self, texto):
        self.saida.insert("end", texto)
        self.saida.see("end")

    def _marcar_rodando(self, rodando):
        self.processo_rodando = rodando
        estado = "disabled" if rodando else "normal"
        self.botao_analisar.configure(state=estado)
        self.botao_efetuar.configure(state=estado)
        if hasattr(self, "botao_recuperar"):
            pode_recuperar = bool(self.ultima_pasta_executada and self.ultimo_passos_recuperar)
            self.botao_recuperar.configure(state="normal" if pode_recuperar and not rodando else "disabled")
        for chave, botao in getattr(self, "botoes_tarefa", {}).items():
            if rodando:
                botao.configure(state="disabled")
            else:
                botao.configure(state="disabled" if chave == self._tarefa_id() else "normal")

    def _finalizar_execucao(self, codigo, alteracoes_ok=0):
        if codigo == 0:
            self._anexar_resultado("\nConcluido.\n")
            if self.recuperando:
                self.ultima_pasta_executada = None
                self.ultimo_passos_recuperar = 0
                self.recuperando = False
                self._anexar_resultado("Recuperação concluída.\n")
            elif alteracoes_ok:
                self.ultima_pasta_executada = self.pasta_var.get().strip()
                self.ultimo_passos_recuperar = alteracoes_ok
                self._anexar_resultado("Você pode usar 'Recuperar última alteração' se não gostar do resultado.\n")
        else:
            self._anexar_resultado(f"\nTerminou com erro. Codigo: {codigo}\n")
            if alteracoes_ok:
                self.ultima_pasta_executada = self.pasta_var.get().strip()
                self.ultimo_passos_recuperar = alteracoes_ok
                self._anexar_resultado("Uma parte foi feita antes do erro. O botão de recuperar ficou disponível para essa parte.\n")
            self.recuperando = False
        self._marcar_rodando(False)

    def _recuperar_ultima_alteracao(self):
        if self.processo_rodando:
            return
        if not self.ultima_pasta_executada or not self.ultimo_passos_recuperar:
            messagebox.showinfo("Nada para recuperar", "Nenhuma alteração feita por esta janela está pronta para recuperar.")
            return
        confirmou = messagebox.askyesno(
            "Recuperar última alteração",
            "Isto tenta voltar a pasta para antes da última ação feita por esta janela.\n\n"
            f"Pasta: {self.ultima_pasta_executada}\n"
            f"Etapas para recuperar: {self.ultimo_passos_recuperar}\n\n"
            "Deseja continuar?",
        )
        if not confirmou:
            return

        args = [
            sys.executable,
            str(MAESTRO),
            "desfazer",
            self.ultima_pasta_executada,
            "--passos",
            str(self.ultimo_passos_recuperar),
            "--executar",
            "--sim",
        ]
        self.recuperando = True
        self._limpar_resultado()
        self._anexar_resultado("RECUPERANDO ÚLTIMA ALTERAÇÃO\n")
        self._anexar_resultado(f"Pasta: {self.ultima_pasta_executada}\n\n")
        self._marcar_rodando(True)
        thread = threading.Thread(target=self._rodar_em_segundo_plano, args=([(None, args, False)],), daemon=True)
        thread.start()

    def _adicionar_anos(self, args):
        ano_base = self.ano_base_var.get().strip()
        ano_citado = self.ano_citado_var.get().strip()
        if ano_base:
            args.extend(["--ano-base", ano_base])
        if ano_citado:
            args.extend(["--ano-citado", ano_citado])

    def _adicionar_limite(self, args):
        limite = self.limite_var.get().strip()
        if limite and limite != "80":
            args.extend(["--limite", limite])


def main():
    app = AssistenteMaestro()
    app.mainloop()


if __name__ == "__main__":
    main()















