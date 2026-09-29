# Controle de Ponto

Aplicativo em Streamlit para importar comprovantes de registro de ponto (PDF
ou um print/foto da tela), ler automaticamente a **data e hora** de cada
marcação e calcular o **banco de horas** (saldo positivo/negativo). Só
guarda data/hora — nome, PIS e empresa não são armazenados, já que não mudam.

## O que ele faz

- **Importar comprovantes**: duas formas —
  1. **Pasta `PONTO`**: coloque os arquivos (PDF, PNG ou JPG) dentro da pasta
     `PONTO`, na mesma pasta do `app.py`, e clique em "Buscar arquivos na
     pasta" — o app lê todos de uma vez. Os que ele reconhece com confiança
     podem ser salvos em lote ("Salvar reconhecidas automaticamente"); os
     que ficaram em dúvida você revisa um a um. Depois de processado, o
     arquivo é movido para `PONTO/processados/` (ou `PONTO/erro_revisar/`),
     então nunca é lido duas vezes.
  2. **Upload manual pelo navegador**: envie o arquivo direto pela tela,
     sem precisar copiar pra nenhuma pasta.

  Em ambos os casos, o app tenta ler a data/hora primeiro direto do texto do
  PDF e, se não achar (PDF escaneado ou imagem), usa OCR. Você
  confere/corrige antes de salvar.
- **Registros**: lista de todas as marcações salvas, com opção de excluir.
- **Banco de horas**: para cada dia, ordena as marcações e as agrupa em pares
  (1ª = entrada, 2ª = saída, 3ª = entrada, 4ª = saída...), soma o tempo
  trabalhado e compara com a jornada esperada configurada na barra lateral.
  Mostra o saldo do dia e o saldo acumulado (positivo ou negativo), além de
  um gráfico de evolução e exportação em CSV.

Dias com número ímpar de marcações (por exemplo, esqueceu de bater a saída)
ficam marcados como **incompletos** na tabela.

## Estrutura do projeto

- `app.py` — interface Streamlit (importar da pasta `PONTO` ou por upload,
  registros, banco de horas).
- `PONTO/` — pasta onde você solta os comprovantes para importação em lote
  direto pelo app (criada automaticamente na primeira busca).
- `watcher.py` — script standalone que monitora uma pasta e importa os
  arquivos automaticamente **sem precisar abrir o Streamlit** — útil se você
  quer isso rodando sozinho em segundo plano/agendado, em vez de clicar em
  "Buscar arquivos" no app.
- `ponto_core.py` — lógica compartilhada entre os dois (banco de dados,
  leitura do PDF/imagem, cálculo do banco de horas). Não precisa mexer nele.
- `ponto.db` — banco SQLite com os dados (criado automaticamente).

## Instalação

1. Instale o Python 3.9+ e os pacotes do projeto:

   ```bash
   pip install -r requirements.txt
   ```

   Pronto — **não precisa instalar nenhum programa separado no sistema**
   (nada de Tesseract, Poppler, instalador `.exe` nem mexer no PATH do
   Windows). A leitura de texto embutido em PDF usa `pdfplumber`, e o OCR
   (para PDF escaneado ou print/imagem) usa `pymupdf` + `rapidocr-onnxruntime`
   — todas bibliotecas Python instaladas via `pip`, com os modelos de OCR já
   incluídos no pacote.

2. Rode o app:

   ```bash
   streamlit run app.py
   ```

O navegador abrirá automaticamente em `http://localhost:8501`.

## Importação automática de PDFs (sem abrir o Streamlit)

Se você recebe os comprovantes numa pasta (por exemplo, uma pasta de
downloads ou sincronizada de um app do ponto no celular), o `watcher.py`
processa tudo sozinho: fica de olho na pasta, lê a data/hora de cada PDF ou
print/imagem (PNG, JPG) novo com a mesma lógica do app e grava direto no
`ponto.db` — sem precisar abrir o navegador.

```bash
python watcher.py "/caminho/da/pasta/comprovantes"
```

Por padrão ele fica rodando, checando a pasta a cada 15 segundos (Ctrl+C
para parar). Cada PDF processado é movido para uma subpasta dentro da pasta
monitorada, para nunca ser lido duas vezes:

- `processados/` — leitura deu certo e a marcação foi salva no banco.
- `erro_revisar/` — não foi possível reconhecer a data/hora automaticamente
  (ou o arquivo não pôde ser lido); confira esses arquivos e lance a marcação
  manualmente no app, na aba "Registros".

Opções disponíveis:

| Opção         | Padrão      | Para que serve                                                   |
|---------------|-------------|-------------------------------------------------------------------|
| `--db`        | `ponto.db`  | Caminho do banco (use o mesmo do `app.py` para os dados aparecerem juntos). |
| `--intervalo` | `15`        | Segundos entre cada checagem da pasta.                            |
| `--uma-vez`   | desligado   | Processa os arquivos já presentes na pasta e encerra, em vez de ficar rodando. Útil para agendar via **Agendador de Tarefas** (Windows), **cron** (Linux/macOS) ou similar, rodando o comando a cada X minutos, em vez de deixar um processo aberto o tempo todo. |

Exemplo processando uma vez só e apontando para um banco específico:

```bash
python watcher.py "/caminho/da/pasta" --db "C:\Ponto\ponto.db" --uma-vez
```

O `watcher.py` usa as mesmas dependências do `app.py` (`requirements.txt`) —
todas via `pip`, sem nenhum programa extra pra instalar no sistema. Se algo
estiver faltando, os erros aparecem no terminal (e nos registros de log)
explicando o que instalar.

## Não está conseguindo ler o comprovante?

Abra a barra lateral do app e expanda **"Diagnóstico do sistema"** — ele
mostra exatamente qual dependência está faltando (pdfplumber, PyMuPDF,
RapidOCR ou Pillow), com o comando `pip install` certo pra cada uma. Como
todas são bibliotecas Python (sem programa externo pra instalar), a causa
mais comum é uma só:

- **`pip install -r requirements.txt` não foi rodado**, ou foi rodado num
  ambiente/virtualenv diferente do que você usa para `streamlit run app.py`
  (ou `python watcher.py`).

Outras causas possíveis:

- **A qualidade do print/PDF está ruim** (foto tremida, muito zoom out,
  compressão pesada) — o OCR erra mais quanto pior a legibilidade. Tente um
  print mais nítido, com o texto grande e legível.
- **O layout do comprovante é diferente do esperado** — o app procura o
  padrão `Data: DD/MM/AAAA ... HH:MM` no texto reconhecido. Se o seu
  comprovante usa outro formato, o app avisa que não achou automaticamente e
  mostra o texto bruto reconhecido (pra você conferir o que o OCR leu) —
  você preenche a data/hora manualmente nesse caso.

Se mesmo assim a leitura falhar, o app mostra a mensagem de erro específica
na tela (em vez de travar), e você sempre pode preencher a data/hora
manualmente logo abaixo do aviso.

## Onde ficam os dados

Tudo é salvo em um arquivo `ponto.db` (SQLite) na mesma pasta do `app.py`.
Faça backup desse arquivo se quiser preservar o histórico — ele não é
enviado para lugar nenhum, fica só na sua máquina.

> **Importante se você fez deploy no Streamlit Community Cloud**: a
> importação pela pasta `PONTO` (e o `watcher.py`) só funcionam rodando o
> app **localmente na sua máquina**, porque dependem de acessar uma pasta no
> seu disco. No Streamlit Cloud você não tem acesso ao sistema de arquivos
> do servidor pra colocar arquivos lá — nesse caso use sempre o upload
> manual pelo navegador (segunda opção na aba "Importar comprovantes").

## Observações

- Se o OCR não reconhecer algum comprovante (layout diferente, PDF de baixa
  qualidade, etc.), você ainda pode preencher os campos manualmente na tela
  de importação, ou usar o formulário "adicionar marcação manualmente" na
  mesma aba.
- A jornada diária esperada e se sábado/domingo contam como dia esperado são
  configuráveis na barra lateral, a qualquer momento.
