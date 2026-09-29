"""
watcher.py
----------
Monitora uma pasta em busca de novos comprovantes de ponto — PDF ou
print/imagem (PNG, JPG) —, lê a data/hora automaticamente (mesma lógica do
app.py, via ponto_core) e insere direto no banco ponto.db — sem precisar
abrir o Streamlit.

Cada arquivo processado é movido para uma subpasta, para nunca ser reprocessado:
  <pasta>/processados/     -> leitura OK e gravado no banco
  <pasta>/erro_revisar/    -> não deu para ler automaticamente (ou já duplicado);
                               fica ali para você conferir e lançar manualmente
                               no app (aba "Registros" -> formulário manual)

Uso básico (fica rodando, checando a pasta a cada 15s):
    python watcher.py "C:\\Users\\voce\\Documents\\comprovantes_ponto"

Opções:
    --db CAMINHO        caminho do ponto.db (padrão: ./ponto.db)
    --intervalo N        segundos entre cada checagem da pasta (padrão: 15)
    --uma-vez            processa os arquivos que já estão na pasta agora e
                          encerra (útil para rodar via agendador de tarefas /
                          cron, em vez de deixar um processo aberto o tempo todo)

Requer as mesmas dependências do app.py (ver requirements.txt) — todas
instaláveis via pip, sem precisar instalar nenhum programa separado no
sistema (ver README.md).
"""

import argparse
import logging
import os
import sys
import time

import ponto_core as core


def processar_arquivo(caminho, conn, pasta_ok, pasta_erro):
    nome = os.path.basename(caminho)

    try:
        with open(caminho, "rb") as f:
            arquivo_bytes = f.read()
    except Exception as e:
        logging.error("%s: não foi possível abrir o arquivo (%s). Deixado na pasta.", nome, e)
        return

    try:
        data_val, hora_val, aviso, texto_bruto = core.extrair_data_hora_arquivo(arquivo_bytes, nome)
    except core.ErroLeituraPDF as e:
        logging.error("%s: %s", nome, e)
        core.mover_arquivo_processado(caminho, pasta_erro)
        return
    except Exception as e:
        logging.error("%s: erro inesperado ao ler o arquivo (%s).", nome, e)
        core.mover_arquivo_processado(caminho, pasta_erro)
        return

    if not (data_val and hora_val):
        logging.warning(
            "%s: não foi possível reconhecer data/hora automaticamente. "
            "Movido para '%s' — lance manualmente no app.",
            nome, pasta_erro,
        )
        core.mover_arquivo_processado(caminho, pasta_erro)
        return

    ok, erro = core.inserir_registro(conn, data_val, hora_val, origem=nome)
    if ok:
        logging.info("%s: marcação %s %s salva no banco.", nome, data_val, hora_val)
        core.mover_arquivo_processado(caminho, pasta_ok)
    else:
        # Duplicado (mesma data/hora já cadastrada) ou outro erro de banco.
        # Move para 'processados' mesmo assim, senão o watcher ficaria
        # tentando reprocessar o mesmo arquivo pra sempre.
        logging.warning("%s: %s (arquivo movido para '%s' sem duplicar no banco).",
                         nome, erro, pasta_ok)
        core.mover_arquivo_processado(caminho, pasta_ok)


def rodar(pasta, db_path, intervalo, uma_vez):
    pasta = os.path.abspath(pasta)
    pasta_ok = os.path.join(pasta, "processados")
    pasta_erro = os.path.join(pasta, "erro_revisar")

    conn = core.get_conn(db_path)
    logging.info("Banco: %s", os.path.abspath(db_path))
    logging.info("Monitorando pasta: %s", pasta)
    if not uma_vez:
        logging.info("Checando a cada %ss. Pressione Ctrl+C para parar.", intervalo)

    while True:
        pendentes = core.listar_arquivos_pasta(pasta)
        for nome in pendentes:
            processar_arquivo(os.path.join(pasta, nome), conn, pasta_ok, pasta_erro)

        if uma_vez:
            break
        time.sleep(intervalo)


def main():
    parser = argparse.ArgumentParser(
        description="Monitora uma pasta e importa comprovantes de ponto (PDF, PNG ou JPG) para o ponto.db automaticamente."
    )
    parser.add_argument("pasta", help="Pasta a monitorar em busca de novos comprovantes (PDF, PNG ou JPG).")
    parser.add_argument("--db", default=core.DB_PATH_PADRAO, help="Caminho do arquivo ponto.db (padrão: ./ponto.db).")
    parser.add_argument("--intervalo", type=int, default=15, help="Segundos entre cada checagem da pasta (padrão: 15).")
    parser.add_argument("--uma-vez", action="store_true", help="Processa os PDFs já presentes na pasta e encerra, sem ficar rodando em loop.")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        rodar(args.pasta, args.db, args.intervalo, args.uma_vez)
    except KeyboardInterrupt:
        logging.info("Encerrado pelo usuário.")
        sys.exit(0)


if __name__ == "__main__":
    main()