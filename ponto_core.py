"""
ponto_core.py
-------------
Lógica compartilhada entre o app Streamlit (app.py) e o watcher de pasta
(watcher.py): acesso ao banco SQLite, extração de data/hora de comprovantes
em PDF (texto direto ou OCR) e cálculo do banco de horas.

Mantida separada da interface para que os dois programas usem exatamente as
mesmas regras de leitura e gravação.
"""

import io
import json
import os
import re
import shutil
import sqlite3
import time
from datetime import datetime

import pandas as pd

DB_PATH_PADRAO = "ponto.db"

# ----------------------------------------------------------------------------
# Banco de dados
# ----------------------------------------------------------------------------

def get_conn(db_path=DB_PATH_PADRAO):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,        -- YYYY-MM-DD
            hora TEXT NOT NULL,        -- HH:MM
            origem TEXT,               -- nome do arquivo ou 'manual'
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(data, hora)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS config (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)
    conn.commit()
    return conn


def get_config(conn, chave, default=None):
    row = conn.execute("SELECT valor FROM config WHERE chave=?", (chave,)).fetchone()
    return row[0] if row else default


def set_config(conn, chave, valor):
    conn.execute(
        "INSERT INTO config (chave, valor) VALUES (?, ?) "
        "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
        (chave, valor),
    )
    conn.commit()


def inserir_registro(conn, data_str, hora_str, origem):
    try:
        conn.execute(
            "INSERT INTO registros (data, hora, origem) VALUES (?, ?, ?)",
            (data_str, hora_str, origem),
        )
        conn.commit()
        return True, None
    except sqlite3.IntegrityError:
        return False, "Já existe uma marcação igual (mesma data e hora)."
    except Exception as e:
        return False, str(e)


def carregar_registros(conn):
    return pd.read_sql_query(
        "SELECT id, data, hora, origem FROM registros ORDER BY data, hora", conn
    )


def excluir_registro(conn, reg_id):
    conn.execute("DELETE FROM registros WHERE id=?", (reg_id,))
    conn.commit()


# ----------------------------------------------------------------------------
# Diagnóstico do ambiente
# ----------------------------------------------------------------------------
#
# Desde a versão que lê prints/imagens, o OCR usa PyMuPDF + RapidOCR — as duas
# são bibliotecas Python puras (instaladas com `pip install -r requirements.txt`),
# sem precisar baixar/instalar nenhum programa separado nem mexer no PATH do
# sistema (diferente do antigo Poppler + Tesseract).

def diagnosticar_ambiente():
    """Verifica se as dependências de leitura/OCR estão disponíveis e retorna
    uma lista de (ok: bool, mensagem: str)."""
    resultados = []

    try:
        import pdfplumber  # noqa: F401
        resultados.append((True, "pdfplumber instalado (extração direta de texto de PDF)."))
    except ImportError:
        resultados.append((False, "pdfplumber NÃO instalado — rode: pip install pdfplumber"))

    try:
        import fitz  # noqa: F401  (PyMuPDF)
        resultados.append((True, "PyMuPDF instalado (converte PDF escaneado em imagem para OCR)."))
    except ImportError:
        resultados.append((False, "PyMuPDF NÃO instalado — rode: pip install pymupdf"))

    try:
        import rapidocr_onnxruntime  # noqa: F401
        resultados.append((True, "RapidOCR instalado (leitura de texto em imagens/prints)."))
    except ImportError:
        resultados.append((False, "RapidOCR NÃO instalado — rode: pip install rapidocr-onnxruntime"))

    try:
        import PIL  # noqa: F401
        resultados.append((True, "Pillow instalado."))
    except ImportError:
        resultados.append((False, "Pillow NÃO instalado — rode: pip install pillow"))

    return resultados


# ----------------------------------------------------------------------------
# Extração de data/hora do comprovante em PDF
# ----------------------------------------------------------------------------

class ErroLeituraPDF(Exception):
    pass


def _regex_data_hora(texto):
    m = re.search(r"Data:\s*(\d{2})/(\d{2})/(\d{4}).{0,40}?(\d{1,2}):(\d{2})", texto, flags=re.DOTALL)
    if not m:
        return None, None
    dia, mes, ano, hh, mm = m.groups()
    return f"{ano}-{mes}-{dia}", f"{int(hh):02d}:{mm}"


def extrair_texto_direto(pdf_bytes):
    """Tenta extrair texto embutido no PDF (sem OCR). Retorna '' se não houver."""
    import pdfplumber
    texto = ""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for pagina in pdf.pages:
            texto += (pagina.extract_text() or "") + "\n"
    return texto


_rapidocr_engine = None  # carregado uma única vez (o modelo demora ~1s para subir)


def _get_rapidocr_engine():
    global _rapidocr_engine
    if _rapidocr_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            raise ErroLeituraPDF(
                "A biblioteca 'rapidocr-onnxruntime' não está instalada. Rode: "
                "pip install rapidocr-onnxruntime"
            )
        _rapidocr_engine = RapidOCR()
    return _rapidocr_engine


def extrair_texto_ocr_imagem(imagem_bytes):
    """Roda OCR direto em uma imagem (print/foto do comprovante) usando
    RapidOCR. Biblioteca Python pura — não depende de nenhum programa externo
    instalado no sistema."""
    try:
        import numpy as np
        from PIL import Image, UnidentifiedImageError
    except ImportError:
        raise ErroLeituraPDF(
            "As bibliotecas 'pillow'/'numpy' não estão instaladas. Rode: "
            "pip install pillow numpy"
        )

    try:
        img = Image.open(io.BytesIO(imagem_bytes)).convert("RGB")
    except UnidentifiedImageError:
        raise ErroLeituraPDF("O arquivo enviado não parece ser uma imagem válida (png/jpg).")
    except Exception as e:
        raise ErroLeituraPDF(f"Não foi possível abrir a imagem: {e}")

    engine = _get_rapidocr_engine()
    try:
        resultado, _ = engine(np.array(img))
    except Exception as e:
        raise ErroLeituraPDF(f"Falha ao rodar OCR na imagem: {e}")

    if not resultado:
        return ""
    return "\n".join(item[1] for item in resultado)


def extrair_texto_ocr_pdf(pdf_bytes):
    """Converte cada página do PDF em imagem (via PyMuPDF, sem precisar do
    Poppler) e roda OCR (RapidOCR, sem precisar do Tesseract) em cada uma."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise ErroLeituraPDF(
            "A biblioteca 'PyMuPDF' não está instalada. Rode: pip install pymupdf"
        )

    try:
        documento = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        raise ErroLeituraPDF(f"Falha ao abrir o PDF para OCR: {e}")

    try:
        textos = []
        for pagina in documento:
            pix = pagina.get_pixmap(dpi=300)
            textos.append(extrair_texto_ocr_imagem(pix.tobytes("png")))
    finally:
        documento.close()

    return "\n".join(textos)


def extrair_data_hora_pdf(pdf_bytes):
    """
    Estratégia: primeiro tenta ler texto embutido no PDF (rápido, sem
    dependências externas). Se não achar data/hora, cai para OCR (PDF
    escaneado / "impresso" sem texto real).
    Sempre retorna (data, hora, aviso, texto_bruto) — os dois últimos podem ser None.
    """
    try:
        texto = extrair_texto_direto(pdf_bytes)
    except Exception:
        texto = ""

    data_val, hora_val = _regex_data_hora(texto) if texto else (None, None)
    if data_val and hora_val:
        return data_val, hora_val, None, None

    texto_ocr = extrair_texto_ocr_pdf(pdf_bytes)  # pode levantar ErroLeituraPDF
    data_val, hora_val = _regex_data_hora(texto_ocr)
    if not (data_val and hora_val):
        aviso = (
            "Não foi possível localizar automaticamente a data/hora neste "
            "comprovante. Confira o texto reconhecido abaixo e preencha manualmente."
        )
        return None, None, aviso, texto_ocr
    return data_val, hora_val, None, None


EXTENSOES_IMAGEM = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
EXTENSOES_SUPORTADAS = (".pdf",) + EXTENSOES_IMAGEM

PASTA_IMPORTACAO_PADRAO = "PONTO"


def listar_arquivos_pasta(pasta):
    """Lista os arquivos suportados (PDF/imagem) direto na pasta (não entra
    em subpastas, então processados/ e erro_revisar/ são ignoradas)."""
    try:
        nomes = os.listdir(pasta)
    except FileNotFoundError:
        return []
    return sorted(
        n for n in nomes
        if n.lower().endswith(EXTENSOES_SUPORTADAS) and os.path.isfile(os.path.join(pasta, n))
    )


def mover_arquivo_processado(caminho, pasta_destino):
    """Move um arquivo já processado para uma subpasta (processados/ ou
    erro_revisar/), sem sobrescrever se já existir um arquivo com esse nome."""
    os.makedirs(pasta_destino, exist_ok=True)
    nome = os.path.basename(caminho)
    destino = os.path.join(pasta_destino, nome)
    if os.path.exists(destino):
        base, ext = os.path.splitext(nome)
        destino = os.path.join(pasta_destino, f"{base}_{int(time.time())}{ext}")
    shutil.move(caminho, destino)
    return destino


def extrair_data_hora_arquivo(conteudo_bytes, nome_arquivo):
    """Ponto de entrada único do app e do watcher: decide, pela extensão do
    arquivo, se é um PDF ou um print/imagem, e aplica a extração adequada.
    Sempre retorna (data, hora, aviso, texto_bruto)."""
    nome_lower = (nome_arquivo or "").lower()

    if nome_lower.endswith(EXTENSOES_IMAGEM):
        texto = extrair_texto_ocr_imagem(conteudo_bytes)  # pode levantar ErroLeituraPDF
        data_val, hora_val = _regex_data_hora(texto)
        if not (data_val and hora_val):
            aviso = (
                "Não foi possível localizar automaticamente a data/hora neste "
                "print. Confira o texto reconhecido abaixo e preencha manualmente."
            )
            return None, None, aviso, texto
        return data_val, hora_val, None, None

    return extrair_data_hora_pdf(conteudo_bytes)


# ----------------------------------------------------------------------------
# Cálculo do banco de horas
# ----------------------------------------------------------------------------

DIAS_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


def jornada_padrao_por_dia():
    """Segunda a quinta = 10h, sexta = 9h, fim de semana = 0h."""
    return {0: 600, 1: 600, 2: 600, 3: 600, 4: 540, 5: 0, 6: 0}


def carregar_jornada_por_dia(conn):
    bruto = get_config(conn, "jornada_por_dia")
    if not bruto:
        return jornada_padrao_por_dia()
    try:
        salvo = json.loads(bruto)
        return {int(k): int(v) for k, v in salvo.items()}
    except Exception:
        return jornada_padrao_por_dia()


def salvar_jornada_por_dia(conn, jornada_por_dia):
    set_config(conn, "jornada_por_dia", json.dumps(jornada_por_dia))


def calcular_banco_horas(df, jornada_por_dia):
    """
    Para cada dia, ordena os horários e faz o pareamento sequencial
    (1º=entrada, 2º=saída, 3º=entrada, 4º=saída, ...).
    A jornada esperada varia conforme o dia da semana (jornada_por_dia).
    Retorna um DataFrame diário com minutos trabalhados, esperados e saldo.
    """
    if df.empty:
        return pd.DataFrame(columns=[
            "data", "marcacoes", "trabalhado_min", "esperado_min",
            "saldo_min", "saldo_acumulado_min", "incompleto"
        ])

    linhas = []
    for dia, grupo in df.groupby("data"):
        horarios = sorted(grupo["hora"].tolist())
        minutos = [int(h[:2]) * 60 + int(h[3:5]) for h in horarios]

        trabalhado = 0
        incompleto = len(minutos) % 2 == 1
        for i in range(0, len(minutos) - 1, 2):
            trabalhado += minutos[i + 1] - minutos[i]

        data_dt = datetime.strptime(dia, "%Y-%m-%d").date()
        esperado = jornada_por_dia.get(data_dt.weekday(), 0)

        linhas.append({
            "data": dia,
            "marcacoes": " / ".join(horarios),
            "trabalhado_min": trabalhado,
            "esperado_min": esperado,
            "saldo_min": trabalhado - esperado,
            "incompleto": incompleto,
        })

    resultado = pd.DataFrame(linhas).sort_values("data").reset_index(drop=True)
    resultado["saldo_acumulado_min"] = resultado["saldo_min"].cumsum()
    return resultado


def fmt_min(minutos):
    """Formata minutos (podendo ser negativo) como '+HH:MM' / '-HH:MM'."""
    sinal = "-" if minutos < 0 else "+"
    minutos = abs(int(minutos))
    return f"{sinal}{minutos // 60:02d}:{minutos % 60:02d}"


def fmt_min_abs(minutos):
    minutos = int(minutos)
    return f"{minutos // 60:02d}:{minutos % 60:02d}"