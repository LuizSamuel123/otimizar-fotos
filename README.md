# Otimizar Fotos

> Este projeto foi desenvolvido em colaboração com inteligência artificial (IA), inclusive na geração e revisão de código e documentação.

Ferramentas locais em Python para organizar fotos e vídeos por data e contexto,
separar duplicatas em quarentena e revisar datas duvidosas. Inclui interface
Tkinter, comandos de terminal e utilitários para triagem de imagens.

Este repositório contém o programa. Os álbuns, fotos, pranchas, listas de
triagem, relatórios e históricos gerados ficam fora do Git.

## Instalar e executar

Requer Python 3.10 ou mais recente com Tkinter.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe assistente_fotos.py
```

No Windows, `abrir_assistente_fotos.vbs` abre a interface sem console, usando
primeiro o ambiente `.venv` do projeto e depois o Python disponível no PATH.

Para consultar os comandos e simular a organização:

```powershell
.\.venv\Scripts\python.exe otimizar_fotos.py --help
.\.venv\Scripts\python.exe otimizar_fotos.py organizar "C:\album-de-teste"
```

As alterações dependem de `--executar`. Faça uma cópia do álbum antes de
aplicar operações. A quarentena separa duplicatas sem apagá-las automaticamente.

## Recursos adicionais

- Pillow permite ler metadados de imagens e gerar pranchas de triagem.
- `detectar_pessoas_fotos.py` usa OpenCV, disponível com
  `python -m pip install -r requirements-opcionais.txt`.
- A leitura de datas de vídeos pode usar `ffprobe`, se estiver instalado no PATH.

## Arquivos locais

O Git acompanha código, documentação e recursos gráficos do aplicativo. O
`.gitignore` usa uma lista de tipos e arquivos permitidos: ambientes virtuais,
caches, fotos de usuários, relatórios, históricos, bancos de dados e chaves
locais não são incluídos. Não use `git add -f` para esses arquivos.
