"""
Controle de Ponto
------------------
Aplicação Streamlit para importar comprovantes de registro de ponto (PDF ou
print/imagem), extrair automaticamente a data/hora de cada marcação (texto
direto do PDF ou OCR) e calcular o banco de horas (saldo positivo/negativo).

Toda a lógica de banco de dados, leitura de PDF/imagem e cálculo do banco de
horas fica em ponto_core.py — é o mesmo módulo usado pelo watcher.py (script
que monitora uma pasta e importa arquivos sem precisar abrir este app).

Como rodar:
    pip install -r requirements.txt
    streamlit run app.py

Não depende de nenhum programa externo instalado no sistema — toda a leitura
(pdfplumber, PyMuPDF, RapidOCR) é feita com bibliotecas Python via pip.
"""

import os
import re
from datetime import date, datetime

import altair as alt
import pandas as pd
import streamlit as st

import ponto_core as core

# ----------------------------------------------------------------------------
# Interface Streamlit
# ----------------------------------------------------------------------------

# Ícone da aba do navegador (favicon) — usa o arquivo icon_webpage.png
# que deve ficar na mesma pasta do app.py (ex.: icon_webpage.png).
_ICONE_PADRAO = "🕒"
_caminho_icone = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon_webpage.png")
_pagina_icone = _caminho_icone if os.path.isfile(_caminho_icone) else _ICONE_PADRAO

st.set_page_config(page_title="Controle de Ponto", page_icon=_pagina_icone, layout="wide")
conn = core.get_conn()

# ----------------------------------------------------------------------------
# Estilo visual (tema escuro estilo "CRM Dashboard": roxo/ciano neon)
# Só CSS — nenhuma lógica ou estrutura do app foi alterada.
# ----------------------------------------------------------------------------
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap');

:root {
    --bg:        #0e1022;
    --bg-side:   #12142b;
    --card:      #171a34;
    --card-2:    #1d2140;
    --border:    #262a4d;
    --text:      #e9eaf6;
    --muted:     #8b8fb5;
    --pink:      #b463e6;  /* rosa puxado pro roxo */
    --purple:    #a55eea;
    --violet:    #6d5ce8;
    --cyan:      #22e4d3;
    --blue:      #3d7bfd;

    /* >>> COR DAS ABAS (mude aqui) <<< */
    --aba-texto:      #b463e6;   /* texto da aba selecionada / hover */
    --aba-linha-1:    #b463e6;   /* sublinhado: início do degradê */
    --aba-linha-2:    #a55eea;   /* sublinhado: fim do degradê (repita o valor 1 p/ cor sólida) */
}

html, body, [class*="css"], .stApp, .stMarkdown, button, input, textarea, label {
    font-family: 'Poppins', sans-serif !important;
}

/* Fundo geral */
.stApp {
    background: radial-gradient(1200px 600px at 80% -10%, #1a1d40 0%, var(--bg) 55%) fixed;
    color: var(--text);
}
[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 2.2rem; }

/* Títulos */
h1 {
    font-weight: 600 !important; letter-spacing: .3px;
    background: linear-gradient(90deg, #ffffff 0%, #c9a7ff 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
h2, h3 { color: var(--text) !important; font-weight: 500 !important; }
[data-testid="stCaptionContainer"], .stCaption, small { color: var(--muted) !important; }
hr { border-color: var(--border) !important; }

/* Sidebar */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, var(--bg-side) 0%, #0f1126 100%);
    border-right: 1px solid var(--border);
}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
    color: var(--pink) !important; -webkit-text-fill-color: var(--pink);
    font-size: 1rem !important; text-transform: uppercase; letter-spacing: 1.2px;
    background: none;
}

/* Abas — texto simples; só a aba selecionada ganha a cor do tema */
.stTabs [data-baseweb="tab-list"] {
    gap: 28px; background: transparent !important; box-shadow: none !important; padding: 0;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important; border: none !important; border-radius: 0 !important;
    box-shadow: none !important; padding-left: 2px !important; padding-right: 2px !important;
    color: var(--text) !important; transition: color .15s ease;
}
.stTabs [data-baseweb="tab"] p { color: inherit !important; }
.stTabs [data-baseweb="tab"]:hover { color: var(--aba-texto) !important; }
.stTabs [data-baseweb="tab"][aria-selected="true"] { color: var(--aba-texto) !important; }
.stTabs [data-baseweb="tab-highlight"] {
    height: 3px !important; border-radius: 3px;
    background: linear-gradient(90deg, var(--aba-linha-1) 0%, var(--aba-linha-2) 100%) !important;
}
.stTabs [data-baseweb="tab-border"] { background: var(--border) !important; }

/* Cards de métricas (Banco de horas) — 1º roxo, 2º ciano, 3º escuro */
[data-testid="stMetric"] {
    border-radius: 18px; padding: 20px 22px;
    background: var(--card); border: 1px solid var(--border);
    box-shadow: 0 8px 24px rgba(0,0,0,.35);
}
[data-testid="stMetricLabel"] p { color: rgba(255,255,255,.85) !important; font-size: .85rem; }
[data-testid="stMetricValue"]   { color: #fff !important; font-weight: 600; font-size: 2.3rem; }

[data-testid="stColumn"]:nth-of-type(1) [data-testid="stMetric"],
[data-testid="column"]:nth-of-type(1)   [data-testid="stMetric"] {
    background: linear-gradient(135deg, #b463e6 0%, #7b4fe0 100%); border: none;
    box-shadow: 0 10px 30px rgba(165,94,234,.35);
}
[data-testid="stColumn"]:nth-of-type(2) [data-testid="stMetric"],
[data-testid="column"]:nth-of-type(2)   [data-testid="stMetric"] {
    background: linear-gradient(135deg, #1de9d3 0%, #5b6cf0 100%); border: none;
    box-shadow: 0 10px 30px rgba(34,228,211,.28);
}

/* Botões (pílula roxa em degradê) */
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {
    color: #fff; border: none; border-radius: 999px; padding: .5rem 1.4rem;
    background: linear-gradient(90deg, #a855e0 0%, #7b4fe0 100%);
    box-shadow: 0 6px 18px rgba(165,94,234,.35);
    transition: transform .15s ease, box-shadow .15s ease, filter .15s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover, [data-testid="stFormSubmitButton"] > button:hover {
    color: #fff; transform: translateY(-1px); filter: brightness(1.1);
    box-shadow: 0 10px 24px rgba(165,94,234,.5);
}
.stButton > button:disabled { opacity: .4; box-shadow: none; }

/* Expanders, forms e popover como cards */
[data-testid="stExpander"], [data-testid="stForm"] {
    background: var(--card); border: 1px solid var(--border) !important;
    border-radius: 16px; box-shadow: 0 6px 20px rgba(0,0,0,.25);
}
[data-testid="stExpander"] summary:hover { color: var(--pink); }

/* Campos de entrada */
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="select"] > div,
[data-testid="stDateInput"] > div > div, [data-testid="stTimeInput"] > div > div {
    background: var(--card-2) !important; border-color: var(--border) !important;
    border-radius: 10px !important; color: var(--text);
}
input, textarea { color: var(--text) !important; }
[data-baseweb="input"]:focus-within, [data-baseweb="select"] > div:focus-within {
    border-color: var(--purple) !important; box-shadow: 0 0 0 1px var(--purple);
}

/* Uploader */
[data-testid="stFileUploaderDropzone"] {
    background: var(--card); border: 1.5px dashed var(--violet); border-radius: 16px;
}

/* Tabelas / gráficos */
[data-testid="stDataFrame"], [data-testid="stDataEditor"], [data-testid="stVegaLiteChart"], [data-testid="stArrowVegaLiteChart"] {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 16px; padding: 6px; overflow: hidden;
}

/* Alertas com a paleta do tema */
[data-testid="stAlert"] { border-radius: 14px; border: 1px solid var(--border); background: var(--card-2); }

/* Bloco de código */
[data-testid="stCode"] pre, code { background: #0b0d1c !important; color: var(--cyan) !important; border-radius: 10px; }

/* Scrollbar */
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 8px; }
::-webkit-scrollbar-thumb:hover { background: var(--violet); }
</style>
""",
    unsafe_allow_html=True,
)

st.title("Controle de Ponto e Banco de Horas")

with st.sidebar:
    st.header("Configurações")
    st.caption("Jornada esperada por dia da semana (HH:MM). Use 00:00 para dias sem expediente.")

    jornada_atual = core.carregar_jornada_por_dia(conn)
    tabela_jornada = pd.DataFrame({
        "Dia": core.DIAS_SEMANA,
        "Horas esperadas": [core.fmt_min_abs(jornada_atual.get(i, 0)) for i in range(7)],
    })
    tabela_editada = st.data_editor(
        tabela_jornada, hide_index=True, use_container_width=True,
        disabled=["Dia"], key="editor_jornada",
    )

    if st.button("Salvar configuração"):
        nova_jornada = {}
        erro_formato = False
        for i, valor in enumerate(tabela_editada["Horas esperadas"]):
            try:
                h, m = str(valor).split(":")
                nova_jornada[i] = int(h) * 60 + int(m)
            except Exception:
                erro_formato = True
        if erro_formato:
            st.error("Use o formato HH:MM em todas as linhas (ex.: 09:00).")
        else:
            core.salvar_jornada_por_dia(conn, nova_jornada)
            st.success("Configuração salva.")
            st.rerun()

    jornada_por_dia = core.carregar_jornada_por_dia(conn)

    with st.expander("Diagnóstico do sistema (leitura de PDF)"):
        for ok, msg in core.diagnosticar_ambiente():
            (st.success if ok else st.error)(msg)

    with st.expander("Importação automática (sem abrir este app)"):
        st.caption(
            "Você pode processar comprovantes em lote com o script `watcher.py`, "
            "que monitora uma pasta e importa PDFs e prints/imagens direto para o "
            "mesmo `ponto.db`, sem precisar abrir o navegador:"
        )
        st.code("python watcher.py \"C:\\caminho\\da\\pasta\\comprovantes\"", language="bash")
        st.caption(
            "Ele lê cada arquivo novo (PDF, PNG ou JPG), grava a marcação no banco "
            "e move o arquivo para uma subpasta `processados/` (ou `erro_revisar/` "
            "se não conseguir reconhecer a data/hora). Veja o README para todas as opções."
        )

tab_banco, tab_registros, tab_importar = st.tabs(
    ["Banco de horas", "Registros", "Registrar"]
)

# --- Aba: Registrar ----------------------------------------------------------
with tab_importar:
    st.subheader(f"Importar da pasta '{core.PASTA_IMPORTACAO_PADRAO}'")
    st.caption(
        f"Coloque os comprovantes (PDF, PNG ou JPG) dentro da pasta "
        f"`{core.PASTA_IMPORTACAO_PADRAO}`, na mesma pasta do app.py, e clique "
        f"no botão abaixo para o app ler todos automaticamente."
    )

    pasta_importacao = os.path.join(os.path.dirname(os.path.abspath(__file__)), core.PASTA_IMPORTACAO_PADRAO)

    if st.button("Buscar arquivos na pasta", key="buscar_pasta"):
        os.makedirs(pasta_importacao, exist_ok=True)
        nomes_encontrados = core.listar_arquivos_pasta(pasta_importacao)
        st.session_state.setdefault("extraidos_pasta", {})
        if not nomes_encontrados:
            st.info(f"Nenhum arquivo novo encontrado em '{pasta_importacao}'.")
        for nome in nomes_encontrados:
            if nome in st.session_state["extraidos_pasta"]:
                continue
            caminho = os.path.join(pasta_importacao, nome)
            with st.spinner(f"Lendo {nome}..."):
                eh_imagem = nome.lower().endswith(core.EXTENSOES_IMAGEM)
                try:
                    with open(caminho, "rb") as f:
                        conteudo = f.read()
                except Exception as e:
                    st.error(f"Não foi possível abrir '{nome}': {e}")
                    continue
                resultado = {"caminho": caminho, "eh_imagem": eh_imagem, "bytes": conteudo if eh_imagem else None}
                try:
                    data_val, hora_val, aviso, texto_bruto = core.extrair_data_hora_arquivo(conteudo, nome)
                    resultado["data"] = data_val
                    resultado["hora"] = hora_val
                    resultado["aviso"] = aviso
                    resultado["texto_bruto"] = texto_bruto
                except core.ErroLeituraPDF as e:
                    resultado["erro"] = str(e)
                except Exception as e:
                    resultado["erro"] = f"Erro inesperado ao ler o arquivo: {e}"
            st.session_state["extraidos_pasta"][nome] = resultado

    if st.session_state.get("msg_lote_pasta"):
        st.success(st.session_state.pop("msg_lote_pasta"))

    itens_pasta = st.session_state.get("extraidos_pasta", {})
    if itens_pasta:
        prontos = [
            nome for nome, c in itens_pasta.items()
            if c.get("data") and c.get("hora") and not c.get("erro")
        ]
        if st.button(
            f"Salvar {len(prontos)} reconhecida(s) automaticamente",
            disabled=not prontos, use_container_width=True, key="salvar_lote_pasta",
        ):
            pasta_ok = os.path.join(pasta_importacao, "processados")
            pasta_erro = os.path.join(pasta_importacao, "erro_revisar")
            salvos, duplicados = 0, 0
            for nome in prontos:
                campos = itens_pasta[nome]
                ok, erro = core.inserir_registro(conn, campos["data"], campos["hora"], origem=nome)
                if ok:
                    salvos += 1
                else:
                    duplicados += 1
                core.mover_arquivo_processado(campos["caminho"], pasta_ok)
                del st.session_state["extraidos_pasta"][nome]
            st.session_state["msg_lote_pasta"] = f"{salvos} marcações salvas. {duplicados} já existiam (ignoradas)."
            st.rerun()

        for nome, campos in list(itens_pasta.items()):
            with st.expander(f"{nome}", expanded=bool(campos.get("erro") or campos.get("aviso"))):
                if campos.get("eh_imagem") and campos.get("bytes"):
                    st.image(campos["bytes"], width=280)
                if campos.get("erro"):
                    st.error(campos["erro"])
                    st.caption(
                        "Confira o painel 'Diagnóstico do sistema' na barra lateral, "
                        "ou preencha a marcação manualmente abaixo."
                    )
                if campos.get("aviso"):
                    st.warning(campos["aviso"])
                    if campos.get("texto_bruto"):
                        with st.popover("Ver texto reconhecido"):
                            st.text(campos["texto_bruto"])

                col1, col2 = st.columns(2)
                try:
                    data_default = (
                        datetime.strptime(campos.get("data"), "%Y-%m-%d").date()
                        if campos.get("data") else date.today()
                    )
                except Exception:
                    data_default = date.today()
                data_val = col1.date_input("Data", value=data_default, key=f"data_pasta_{nome}")
                hora_val = col2.text_input("Hora (HH:MM)", value=campos.get("hora") or "", key=f"hora_pasta_{nome}")

                c1, c2 = st.columns(2)
                if c1.button("Salvar esta marcação", key=f"salvar_pasta_{nome}", use_container_width=True):
                    if not re.match(r"^\d{1,2}:\d{2}$", hora_val.strip() or ""):
                        st.error("Informe a hora no formato HH:MM antes de salvar.")
                    else:
                        hh, mm = hora_val.strip().split(":")
                        hora_norm = f"{int(hh):02d}:{mm}"
                        ok, erro = core.inserir_registro(conn, data_val.strftime("%Y-%m-%d"), hora_norm, origem=nome)
                        pasta_ok = os.path.join(pasta_importacao, "processados")
                        core.mover_arquivo_processado(campos["caminho"], pasta_ok)
                        if ok:
                            st.success("Marcação salva!")
                        else:
                            st.warning(f"{erro} (arquivo movido para 'processados' mesmo assim).")
                        del st.session_state["extraidos_pasta"][nome]
                        st.rerun()
                if c2.button("Ignorar (mover para erro_revisar)", key=f"ignorar_pasta_{nome}", use_container_width=True):
                    pasta_erro = os.path.join(pasta_importacao, "erro_revisar")
                    core.mover_arquivo_processado(campos["caminho"], pasta_erro)
                    del st.session_state["extraidos_pasta"][nome]
                    st.rerun()

    st.divider()

    st.subheader("Enviar arquivo pelo navegador")
    st.caption(
        "Envie um ou mais comprovantes de registro de ponto — o PDF original ou "
        "um print/foto da tela (PNG, JPG). A data e a hora da marcação são "
        "lidas automaticamente. Confira antes de salvar."
    )

    arquivos = st.file_uploader(
        "Comprovantes (PDF, PNG ou JPG)",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
    )

    if arquivos:
        if "extraidos" not in st.session_state:
            st.session_state["extraidos"] = {}

        for arq in arquivos:
            if arq.name not in st.session_state["extraidos"]:
                with st.spinner(f"Lendo {arq.name}..."):
                    conteudo = arq.getvalue()
                    eh_imagem = arq.name.lower().endswith(core.EXTENSOES_IMAGEM)
                    resultado = {"eh_imagem": eh_imagem, "bytes": conteudo if eh_imagem else None}
                    try:
                        data_val, hora_val, aviso, texto_bruto = core.extrair_data_hora_arquivo(
                            conteudo, arq.name
                        )
                        resultado["data"] = data_val
                        resultado["hora"] = hora_val
                        resultado["aviso"] = aviso
                        resultado["texto_bruto"] = texto_bruto
                    except core.ErroLeituraPDF as e:
                        resultado["erro"] = str(e)
                    except Exception as e:
                        resultado["erro"] = f"Erro inesperado ao ler o arquivo: {e}"
                st.session_state["extraidos"][arq.name] = resultado

        for nome_arq, campos in list(st.session_state["extraidos"].items()):
            with st.expander(f" {nome_arq}", expanded=True):
                if campos.get("eh_imagem") and campos.get("bytes"):
                    st.image(campos["bytes"], width=280)
                if campos.get("erro"):
                    st.error(campos["erro"])
                    st.caption(
                        "Confira o painel 'Diagnóstico do sistema' na barra lateral, "
                        "ou preencha a marcação manualmente abaixo."
                    )
                if campos.get("aviso"):
                    st.warning(campos["aviso"])
                    if campos.get("texto_bruto"):
                        with st.popover("Ver texto reconhecido no PDF"):
                            st.text(campos["texto_bruto"])

                col1, col2 = st.columns(2)
                try:
                    data_default = (
                        datetime.strptime(campos.get("data"), "%Y-%m-%d").date()
                        if campos.get("data") else date.today()
                    )
                except Exception:
                    data_default = date.today()
                data_val = col1.date_input("Data", value=data_default, key=f"data_{nome_arq}")
                hora_val = col2.text_input("Hora (HH:MM)", value=campos.get("hora") or "", key=f"hora_{nome_arq}")

                if st.button(" Salvar esta marcação", key=f"salvar_{nome_arq}"):
                    if not re.match(r"^\d{1,2}:\d{2}$", hora_val.strip() or ""):
                        st.error("Informe a hora no formato HH:MM antes de salvar.")
                    else:
                        hh, mm = hora_val.strip().split(":")
                        hora_norm = f"{int(hh):02d}:{mm}"
                        ok, erro = core.inserir_registro(
                            conn, data_val.strftime("%Y-%m-%d"), hora_norm, origem=nome_arq
                        )
                        if ok:
                            st.success("Marcação salva!")
                            del st.session_state["extraidos"][nome_arq]
                            st.rerun()
                        else:
                            st.error(erro)

    st.divider()
    st.subheader("Ou adicionar uma marcação manualmente")
    with st.form("form_manual"):
        c1, c2 = st.columns(2)
        m_data = c1.date_input("Data", value=date.today())
        m_hora = c2.time_input("Hora")
        if st.form_submit_button("Adicionar marcação"):
            ok, erro = core.inserir_registro(
                conn, m_data.strftime("%Y-%m-%d"), m_hora.strftime("%H:%M"), origem="manual"
            )
            if ok:
                st.success("Marcação adicionada!")
                st.rerun()
            else:
                st.error(erro)

# --- Aba: Registros ------------------------------------------------------------
with tab_registros:
    st.subheader("Todas as marcações")
    df = core.carregar_registros(conn)
    if df.empty:
        st.info("Nenhuma marcação cadastrada ainda. Registre um comprovante na aba Registrar.")
    else:
        df = df.sort_values(["data", "hora"], ascending=False).reset_index(drop=True)
        tabela_reg = df.copy()
        tabela_reg.insert(0, "#", tabela_reg["id"].apply(lambda i: f"#{i}"))
        st.dataframe(tabela_reg.drop(columns=["id"]), use_container_width=True, hide_index=True)

        st.markdown("**Excluir uma marcação**")
        opcoes = {f"#{r.id} — {r.data} {r.hora}": r.id for r in df.itertuples()}
        escolhido = st.selectbox("Selecione a marcação", list(opcoes.keys()))
        if st.button("Excluir"):
            core.excluir_registro(conn, opcoes[escolhido])
            st.success("Marcação excluída.")
            st.rerun()

# --- Aba: Banco de horas --------------------------------------------------------
with tab_banco:
    st.subheader("Banco de horas")
    df = core.carregar_registros(conn)
    resumo = core.calcular_banco_horas(df, jornada_por_dia)

    if resumo.empty:
        st.info("Sem marcações suficientes para calcular o banco de horas.")
    else:
        saldo_final = resumo["saldo_acumulado_min"].iloc[-1]
        col1, col2, col3 = st.columns(3)
        col1.metric("Saldo acumulado", core.fmt_min(saldo_final))
        col2.metric("Dias com marcação", len(resumo))
        col3.metric("Dias incompletos (nº ímpar de marcações)", int(resumo["incompleto"].sum()))

        tabela = resumo.copy()
        tabela["Trabalhado"] = tabela["trabalhado_min"].apply(core.fmt_min_abs)
        tabela["Esperado"] = tabela["esperado_min"].apply(core.fmt_min_abs)
        tabela["Saldo do dia"] = tabela["saldo_min"].apply(core.fmt_min)
        tabela["Saldo acumulado"] = tabela["saldo_acumulado_min"].apply(core.fmt_min)
        tabela["Marcações"] = tabela["marcacoes"]
        tabela["Incompleto"] = tabela["incompleto"].map({True: "⚠️ sim", False: ""})

        st.markdown("**Evolução do saldo acumulado**")
        graf = resumo[["data", "saldo_acumulado_min", "saldo_min"]].copy()
        graf["data"] = pd.to_datetime(graf["data"])
        graf["saldo_acum_h"] = graf["saldo_acumulado_min"] / 60
        graf["saldo_dia_h"] = graf["saldo_min"] / 60
        graf["saldo_acum_fmt"] = graf["saldo_acumulado_min"].apply(core.fmt_min)
        graf["saldo_dia_fmt"] = graf["saldo_min"].apply(core.fmt_min)

        COR_TEXTO, COR_GRADE = "#8b8fb5", "#2a2e55"
        eixo_x = alt.X(
            "data:T", title=None, scale=alt.Scale(padding=32),
            axis=alt.Axis(format="%d/%m", labelColor=COR_TEXTO, labelAngle=0, labelOverlap="greedy",
                          grid=True, gridColor=COR_GRADE, gridDash=[2, 4], domainColor=COR_GRADE,
                          tickColor=COR_GRADE),
        )
        eixo_y = alt.Y(
            "saldo_acum_h:Q", title=None, scale=alt.Scale(padding=28),
            axis=alt.Axis(labelColor=COR_TEXTO, gridColor=COR_GRADE, gridDash=[2, 4], domain=False,
                          labelExpr="datum.value + 'h'"),
        )
        dica = [
            alt.Tooltip("data:T", title="Data", format="%d/%m/%Y"),
            alt.Tooltip("saldo_acum_fmt:N", title="Saldo acumulado"),
            alt.Tooltip("saldo_dia_fmt:N", title="Saldo do dia"),
        ]

        gradiente_area = alt.Gradient(
            gradient="linear", x1=1, x2=1, y1=1, y2=0,
            stops=[alt.GradientStop(color="rgba(79,195,247,0.00)", offset=0),
                   alt.GradientStop(color="rgba(109,92,232,0.55)", offset=1)],
        )
        gradiente_linha = alt.Gradient(
            gradient="linear", x1=0, x2=1, y1=0, y2=0,
            stops=[alt.GradientStop(color="#a55eea", offset=0),
                   alt.GradientStop(color="#22e4d3", offset=1)],
        )

        base = alt.Chart(graf).encode(x=eixo_x, y=eixo_y)
        area = base.mark_area(interpolate="monotone", color=gradiente_area, line=False)
        linha = base.mark_line(interpolate="monotone", strokeWidth=3, color=gradiente_linha)
        zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(
            color="#b463e6", strokeDash=[6, 4], opacity=.6).encode(y="y:Q")

        # ponto/linha que acompanham o mouse, com tooltip
        cursor = alt.selection_point(nearest=True, on="pointerover", fields=["data"], empty=False)
        seletor = alt.Chart(graf).mark_point(opacity=0).encode(x="data:T").add_params(cursor)
        pontos = base.mark_point(filled=True, size=110, color="#22e4d3", stroke="#ffffff", strokeWidth=2).encode(
            opacity=alt.condition(cursor, alt.value(1), alt.value(0)))
        guia = alt.Chart(graf).mark_rule(color="#8b8fb5", strokeDash=[4, 4], opacity=.6).encode(
            x="data:T", tooltip=dica).transform_filter(cursor)

        # destaque do maior saldo (estilo "Max = 68" da referência) e do saldo atual.
        # Máx fica SEMPRE acima do ponto (dy negativo) e Atual SEMPRE abaixo (dy
        # positivo) — como o valor máximo nunca é menor que o atual, o ponto do
        # Máx já fica mais alto no gráfico, então os dois rótulos nunca se tocam,
        # mesmo quando as datas são vizinhas ou iguais.
        idx_max = graf["saldo_acumulado_min"].idxmax()
        idx_ultimo = graf.index[-1]
        camadas_destaque = []

        if idx_max == idx_ultimo:
            # o saldo atual também é o maior de todos -> um único rótulo, sem duplicar o ponto
            unico = graf.loc[[idx_ultimo]].assign(rotulo="Atual (máx): " + graf.loc[idx_ultimo, "saldo_acum_fmt"])
            camadas_destaque += [
                alt.Chart(unico).mark_point(filled=True, size=420, color="#22e4d3", opacity=.25).encode(
                    x="data:T", y="saldo_acum_h:Q"),
                alt.Chart(unico).mark_point(filled=True, size=90, color="#b463e6", stroke="#fff", strokeWidth=2).encode(
                    x="data:T", y="saldo_acum_h:Q"),
                alt.Chart(unico).mark_text(dy=-20, dx=-46, align="right", color="#ffffff", fontSize=12, fontWeight=600).encode(
                    x="data:T", y="saldo_acum_h:Q", text="rotulo:N"),
            ]
        else:
            destaque = graf.loc[[idx_max]].assign(rotulo="Máx: " + graf.loc[idx_max, "saldo_acum_fmt"])
            ultimo = graf.loc[[idx_ultimo]].assign(rotulo="Atual: " + graf.loc[idx_ultimo, "saldo_acum_fmt"])
            camadas_destaque += [
                alt.Chart(destaque).mark_point(filled=True, size=420, color="#a55eea", opacity=.25).encode(
                    x="data:T", y="saldo_acum_h:Q"),
                alt.Chart(destaque).mark_point(filled=True, size=90, color="#a55eea", stroke="#fff", strokeWidth=2).encode(
                    x="data:T", y="saldo_acum_h:Q"),
                alt.Chart(destaque).mark_text(dy=-20, color="#ffffff", fontSize=12, fontWeight=600).encode(
                    x="data:T", y="saldo_acum_h:Q", text="rotulo:N"),
                alt.Chart(ultimo).mark_point(filled=True, size=420, color="#e05cc8", opacity=.25).encode(
                    x="data:T", y="saldo_acum_h:Q"),
                alt.Chart(ultimo).mark_point(filled=True, size=90, color="#b463e6", stroke="#fff", strokeWidth=2).encode(
                    x="data:T", y="saldo_acum_h:Q"),
                alt.Chart(ultimo).mark_text(dy=26, dx=-46, align="right", color="#ffffff", fontSize=12, fontWeight=600).encode(
                    x="data:T", y="saldo_acum_h:Q", text="rotulo:N"),
            ]

        grafico_saldo = (
            alt.layer(area, zero, linha, *camadas_destaque, guia, seletor, pontos)
            .properties(height=340)
            .configure(background="rgba(0,0,0,0)")
            .configure_view(strokeWidth=0)
        )
        st.altair_chart(grafico_saldo, use_container_width=True, theme=None)

        st.markdown("**Saldo por dia — últimos 5 dias vs. média do mesmo dia da semana**")

        # média histórica por dia da semana (ignora dias incompletos, que distorceriam a média)
        hist = resumo.copy()
        hist["dow"] = pd.to_datetime(hist["data"]).dt.dayofweek
        base_media = hist[~hist["incompleto"].astype(bool)]
        media_dow = base_media.groupby("dow")["saldo_min"].agg(["mean", "count"])

        linhas = []
        for r in hist.tail(5).itertuples():
            d = pd.to_datetime(r.data)
            rot = f"{core.DIAS_SEMANA[r.dow][:3]} {d.strftime('%d/%m')}"
            linhas.append({"dia": rot, "serie": "Saldo do dia", "valor_min": r.saldo_min,
                           "base": "", "cor": "#22e4d3" if r.saldo_min >= 0 else "#b463e6"})
            if r.dow in media_dow.index:
                m = media_dow.loc[r.dow, "mean"]
                linhas.append({"dia": rot, "serie": "Média do dia da semana", "valor_min": m,
                               "base": f"{int(media_dow.loc[r.dow, 'count'])} dias", "cor": "#a55eea"})
        ult5 = pd.DataFrame(linhas)
        ult5["valor_h"] = ult5["valor_min"] / 60
        ult5["valor_fmt"] = ult5["valor_min"].apply(lambda v: core.fmt_min(int(round(v))))
        ordem_dias = list(dict.fromkeys(ult5["dia"]))

        eixo_dia = alt.X("dia:N", title=None, sort=ordem_dias,
                         axis=alt.Axis(labelColor=COR_TEXTO, labelAngle=0, labelPadding=8,
                                       domainColor=COR_GRADE, tickColor=COR_GRADE, labelFontSize=12))
        barras_base = alt.Chart(ult5).encode(
            x=eixo_dia,
            xOffset=alt.XOffset("serie:N", sort=["Saldo do dia", "Média do dia da semana"]),
            y=alt.Y("valor_h:Q", title=None, scale=alt.Scale(padding=20),
                    axis=alt.Axis(labelColor=COR_TEXTO, gridColor=COR_GRADE, gridDash=[2, 4], domain=False,
                                  labelExpr="datum.value + 'h'")),
        )
        barras = barras_base.mark_bar(size=34, cornerRadiusTopLeft=6, cornerRadiusTopRight=6).encode(
            color=alt.Color("cor:N", scale=None),
            tooltip=[alt.Tooltip("dia:N", title="Dia"), alt.Tooltip("serie:N", title="Série"),
                     alt.Tooltip("valor_fmt:N", title="Saldo"), alt.Tooltip("base:N", title="Base da média")],
        )
        rot_pos = barras_base.mark_text(dy=-9, color="#ffffff", fontSize=12, fontWeight=600).encode(
            text="valor_fmt:N").transform_filter(alt.datum.valor_h >= 0)
        rot_neg = barras_base.mark_text(dy=14, color="#ffffff", fontSize=12, fontWeight=600).encode(
            text="valor_fmt:N").transform_filter(alt.datum.valor_h < 0)
        zero_dia = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color=COR_TEXTO, opacity=.5).encode(y="y:Q")

        grafico_dia = (
            alt.layer(barras, zero_dia, rot_pos, rot_neg)
            .properties(height=380)
            .configure(background="rgba(0,0,0,0)")
            .configure_view(strokeWidth=0)
        )
        st.altair_chart(grafico_dia, use_container_width=True, theme=None)
        st.caption(
            "Ciano/rosa = saldo do dia (positivo/negativo) · Roxo = média já registrada para o mesmo "
            "dia da semana (dias incompletos ficam fora da média)."
        )

        st.markdown("**Detalhamento por dia**")
        st.dataframe(
            tabela[["data", "Marcações", "Trabalhado", "Esperado", "Saldo do dia", "Saldo acumulado", "Incompleto"]]
            .sort_values("data", ascending=False)
            .rename(columns={"data": "Data"}),
            use_container_width=True, hide_index=True,
        )

        csv = tabela[["data", "Marcações", "Trabalhado", "Esperado", "Saldo do dia", "Saldo acumulado"]].to_csv(index=False).encode("utf-8")
        st.download_button("Baixar resumo em CSV", csv, file_name="banco_de_horas.csv", mime="text/csv")