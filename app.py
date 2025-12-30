import streamlit as st
import pandas as pd
import fitz
import httpx
import io
import csv
import re
from datetime import datetime, timedelta
from streamlit import session_state as ss
from supabase import create_client
import json

SUPABASE_URL = st.secrets["supabase_url"]
SUPABASE_KEY = st.secrets["supabase_key"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def has_supabase_error(resp):
    if hasattr(resp, "error") and resp.error is not None:
        st.error(f"Erro ao carregar informações do banco de dados.")
        print(f"{resp.error.message}")
        return True
    return False


def salvar_config(chave, valor):
    try:
        supabase.table("configuracoes_codigos").upsert(
            {"chave": chave, "valor": valor}, on_conflict="chave"
        ).execute()
    except httpx.HTTPError as e:
        st.toast(
            f"Erro conectar no banco de dados para salvar os códigos contábeis. Se o erro persistir contate o suporte."
        )
        print(e)
    except Exception as e:
        st.toast(
            f"Erro inesperado ao salvar os códigos contábeis no banco de dados. Se o erro persistir contate o suporte."
        )
        print(e)


def carregar_config(chave, default=None):
    try:
        resp = (
            supabase.table("configuracoes_codigos")
            .select("valor")
            .eq("chave", chave)
            .execute()
        )
        if resp.data and not has_supabase_error(resp):
            return resp.data[0]["valor"]
    except httpx.HTTPError as e:
        st.toast(
            f"Erro ao carregar os códigos contábeis do banco de dados, será usado códigos padrões. Se o erro persistir contate o suporte."
        )
        print(e)
    except Exception as e:
        st.toast(
            f"Erro inesperado ao carregar os códigos contábeis do banco de dados. Se o erro persistir contate o suporte."
        )
        print(e)
    return default


def mapear_filial(valor):
    valor = str(valor).strip()

    if valor.lower() == "matriz":
        return "Matriz"

    m = re.match(r"Buffon\s+(\d+)", valor, re.IGNORECASE)
    if m:
        numero = int(m.group(1))
        return f"Filial {numero - 1}"

    return valor


def sort_buffon(value):
    value = str(value).strip()

    if value.lower() == "matriz":
        return (0, 0)

    m = re.match(r"Buffon\s+(\d+)", value)
    if m:
        return (1, int(m.group(1)))

    return (2, value)


def sort_filial(value):
    value = str(value).strip()

    if value.lower() == "matriz":
        return (0, 0)

    m = re.match(r"Filial\s+(\d+)", value)
    if m:
        return (1, int(m.group(1)))

    return (2, value)


def sort_tipo(value):
    order = {
        "Provento": 0,
        "Desconto": 1,
    }
    return order.get(value, 99)


def detectar_filial(texto):
    match = regex_filial.search(texto)
    if not match:
        return None
    tipo = match.group(1).capitalize()
    numero = match.group(2)
    return f"Filial {int(numero) - 1}" if tipo == "Filial" else "Matriz"


def detectar_funcionarios(texto):
    match = regex_funcionarios.search(texto)
    if not match:
        return None
    return int(match.group(1))


def detectar_salario(texto):
    match = regex_salario.search(texto)
    if match:
        return match.group(1)
    return None


def br_to_float(v):
    return (
        str(v).replace("R$", "").replace(".", "").replace(",", ".").strip()
        if pd.notna(v)
        else "0"
    )


def separar_header_em_duas_linhas(header_list):
    codigos = []
    descricoes = []
    for col in header_list:
        if " - " not in col:
            codigos.append("")
            descricoes.append(col)
        else:
            codigo, nome = col.split(" - ", 1)
            codigos.append(codigo.strip())
            descricoes.append(nome.strip())
    return codigos, descricoes


st.set_page_config(page_title="JC Contabilidade - Postos Buffon", layout="wide")

st.markdown(
    """
    <style>
    .stMainBlockContainer {
      padding-top: 2.5rem;
    }
    h1, h2, h3, h4, h5, h6 {
      padding: 0 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

header_cols = st.columns([0.8, 0.2], vertical_alignment="center")

with header_cols[0]:
    st.title("JC Contabilidade")

# with header_cols[1]:
#     if st.button(":material/help: Ajuda", width='stretch'):
#         st.switch_page("pages/ajuda.py")

st.markdown("<hr style='padding:0;margin:16px 0;'>", unsafe_allow_html=True)

with st.container(border=True):
    st.header("Postos Buffon - Folha de Salários")

    st.markdown("<hr style='padding:0;margin:16px 0;'>", unsafe_allow_html=True)

    upload_cols = st.columns(2)
    st.markdown("<hr style='padding:0;margin:16px 0;'>", unsafe_allow_html=True)
    upload_cols_2 = st.columns(2)

    with upload_cols[0]:
        st.write(
            "Envie aqui o arquivo **CSV (Planilha Excel)** para extrair as informações contábeis."
        )
        uploaded_file = st.file_uploader("Selecione o arquivo CSV", type=["csv"])

    with upload_cols[1]:
        st.write(
            "Envie aqui o arquivo **PDF** para agregar as informações de funcionários de cada filial."
        )
        pdf_file = st.file_uploader(
            "Selecione o arquivo PDF", type=["pdf"], key="pdf_funcionarios"
        )

    with upload_cols_2[0]:
        st.write(
            "Envie aqui o arquivo **PDF** extrair as informações do FGTS de cada filial."
        )
        pdf_quebra_file = st.file_uploader(
            "Selecione o arquivo PDF", type=["pdf"], key="pdf_quebra"
        )

    regex_filial = re.compile(r"RESUMO\s+(Filial|Matriz):\s*(\d+)", re.IGNORECASE)
    regex_funcionarios = re.compile(r"Nesta\s+Folha\s+(\d+)", re.IGNORECASE)
    regex_salario = re.compile(
        r"Mensal\s*\+\s*13º\s*Salário\s+([\d\.]+,\d{2})", re.IGNORECASE
    )

    if pdf_quebra_file:
        doc_quebra = fitz.open(stream=pdf_quebra_file.read(), filetype="pdf")
        resultados_quebra = []

        for i, page in enumerate(doc_quebra):
            text = page.get_text()
            filial = detectar_filial(text)
            salario = detectar_salario(text)

            if filial is not None:
                resultados_quebra.append(
                    {
                        "Filial": filial,
                    }
                )

            if salario is not None and resultados_quebra[-1].get("Salário") is None:
                resultados_quebra[-1]["Salário"] = salario

    if pdf_file:
        doc = fitz.open(stream=pdf_file.read(), filetype="pdf")
        resultados = []

        for i, page in enumerate(doc):
            text = page.get_text()
            filial = detectar_filial(text)
            funcionarios = detectar_funcionarios(text)
            if filial is not None:
                resultados.append(
                    {
                        "Filial": filial,
                        "Func.": (
                            funcionarios
                            if funcionarios is not None
                            else "Não encontrado"
                        ),
                    }
                )

        if len(resultados) == 0:
            st.warning(
                "Nenhuma filial foi detectada no arquivo PDF enviado. "
                "Verifique se o arquivo enviado está correto."
            )

        df_pdf = pd.DataFrame(resultados)

    if (uploaded_file and pdf_file) or (uploaded_file and pdf_quebra_file):
        # Extrair ano e mês do CSV (padrão 202XMM)
        csv_name = uploaded_file.name
        m_csv = re.search(r"202\d(\d{2})", csv_name)
        ano_csv = re.search(r"20\d{2}", csv_name)

        csv_mes = None
        csv_ano = None

        if m_csv and ano_csv:
            csv_ano = ano_csv.group(0)
            csv_mes = m_csv.group(1)

        ss["csv_mes"] = csv_mes
        ss["csv_ano"] = csv_ano

        pdf_mes = None
        pdf_ano = None

        if pdf_file:
            # Extrair ano e mês do PDF (padrão MM 202X)
            pdf_name = pdf_file.name
            m_pdf = re.search(r"(\d{1,2})\s+20\d{2}", pdf_name)
            ano_pdf = re.search(r"202\d", pdf_name)

            if m_pdf and ano_pdf:
                pdf_mes = m_pdf.group(1).zfill(2)
                pdf_ano = ano_pdf.group(0)

        pdf_qmes = None
        pdf_qano = None

        if pdf_quebra_file:
            pdf_q_name = pdf_quebra_file.name
            mq_pdf = re.search(r"(\d{1,2})\s+20\d{2}", pdf_q_name)
            anoq_pdf = re.search(r"202\d", pdf_q_name)

            if mq_pdf and anoq_pdf:
                pdf_qmes = mq_pdf.group(1).zfill(2)
                pdf_qano = anoq_pdf.group(0)
        if ((csv_ano != pdf_ano or csv_mes != pdf_mes) and pdf_file) or (
            (csv_ano != pdf_qano or csv_mes != pdf_qmes) and pdf_quebra_file
        ):
            st.warning(
                f":orange[Os arquivos enviados parecem ser de meses diferentes, confira suas datas: Planilha Excel ({csv_mes}/{csv_ano}) {f'x PDF Salários ({pdf_mes}/{pdf_ano}) 'if pdf_mes and pdf_ano else ''}{f'x PDF FGTS ({pdf_qmes}/{pdf_qano})'if pdf_qmes and pdf_qano else ''}]"
            )

    if uploaded_file is not None:
        try:
            uploaded_file.seek(0)
            uploaded_file = io.BytesIO(uploaded_file.read())
            content = uploaded_file.getvalue().decode("utf-8", errors="ignore")
            sniffer = csv.Sniffer()
            delimiter = sniffer.sniff(content.splitlines()[0]).delimiter

            df = pd.read_csv(
                io.StringIO(content),
                delimiter=delimiter,
                engine="python",
                on_bad_lines="skip",
                header=None,
            )

            df = df.dropna(axis=1, how="all")
            df = df.dropna(axis=0, how="all")

            min_cols = 15
            num_cols = df.shape[1]

            if num_cols < min_cols:
                for i in range(num_cols + 1, min_cols + 1):
                    df[f"col_{i}"] = None

            df.columns = [
                "col_1",
                "col_2",
                "col_3",
                "contabilidade",
                "col_5",
                "col_6",
                "col_7",
                "codigo",
                "descricao",
                "valor",
                "nome",
                "divisor",
                "filial",
                "cnpj",
                "digito",
            ] + list(df.columns[15:])

            if "contabilidade" in df.columns:
                df = df[
                    (df["contabilidade"].astype(str).str.strip() == "1")
                    | (df["contabilidade"].astype(str).str.strip() == "6")
                ]
                df = df[df["digito"] != "N"]

            if df.shape[1] > 9:
                primeiras_colunas = df.iloc[:, :8]
                colunas_para_juntar = df.iloc[:, 8:]

                df["Informações_Complementares"] = colunas_para_juntar.astype(
                    str
                ).apply(
                    lambda x: " ".join(
                        [
                            v.strip().replace("(", "").replace(")", "")
                            for v in x
                            if str(v).strip() not in ["", "nan", "None"]
                        ]
                    ),
                    axis=1,
                )
                df = pd.concat(
                    [primeiras_colunas, df["Informações_Complementares"]], axis=1
                )
            else:
                st.warning(
                    "O arquivo possui menos de 8 colunas. Nenhuma junção foi feita."
                )

            def extrair_info(texto):
                texto = str(texto)
                padrao = re.compile(
                    r"^(?P<descricao>.*?)\s+(?P<valor>\d+(?:[.,]\d{1,2}))\s+(?P<nome>.+?)\s+(?P<divisor>-\d*)\s+(?P<filial>.+?)\s+(?P<cnpj>\d{14})\s+(?P<digito>[PDN])$"
                )
                match = padrao.search(texto.strip())
                if match:
                    return match.groupdict()
                else:
                    return {
                        "descricao": None,
                        "valor": None,
                        "nome": None,
                        "divisor": None,
                        "filial": None,
                        "cnpj": None,
                        "digito": None,
                    }

            extraidos = (
                df["Informações_Complementares"].apply(extrair_info).apply(pd.Series)
            )
            df_final = pd.concat(
                [df.drop(columns=["Informações_Complementares"]), extraidos], axis=1
            )

            df_final["valor_num"] = pd.to_numeric(
                df_final["valor"].astype(str).str.replace(",", "."), errors="coerce"
            )

            df_final["valor"] = df_final["valor_num"].apply(
                lambda x: (
                    f"R${x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    if pd.notnull(x)
                    else x
                )
            )

            df_final = df_final.drop(df_final.columns[:7], axis=1)
            df_final = df_final[df_final["digito"] != "N"]

            codigos_excluir = [
                "3101",
                "4000",
                "4006",
                "4013",
                "4017",
                "4019",
                "4025",
                "20069",
            ]

            if "1.4" in df_final.columns:
                df_final = df_final[
                    ~(
                        (df_final["digito"] == "P")
                        & (df_final["1.4"].astype(str).isin(codigos_excluir))
                    )
                ]

        except Exception as e:
            st.error(
                "O arquivo enviado não corresponde ao padrão esperado. "
                "Certifique-se de utilizar o CSV original recebido por e-mail ou contate o suporte."
            )
            print(f"[ERRO] {e}")
            st.stop()

if uploaded_file is not None and "df_final" in locals():
    with st.container(border=True):
        res_cols = st.columns([0.8, 0.2], vertical_alignment="bottom")

        with res_cols[0]:
            st.header("Resultados da extração")

        try:

            tabs = st.tabs(
                [
                    "Resumo Salários",
                    "Resumo FGTS",
                    "Resumo prolabore",
                    "Dados Extraídos",
                ]
            )

            with tabs[3]:
                st.write(
                    "Tabela com todos os lançamentos extraídos do arquivo. "
                    "Você pode filtrar por **filial** e **tipo (Provento, Desconto)**."
                )
                df_table = df_final[
                    ["codigo", "descricao", "valor", "nome", "filial", "cnpj", "digito"]
                ]
                digito_map = {
                    "P": "Provento",
                    "D": "Desconto",
                }

                df_table["digito"] = df_table["digito"].apply(
                    lambda x: digito_map.get(x, x)
                )

                df_table["filial"] = df_table["filial"].apply(mapear_filial)

                df_table = df_table.sort_values(
                    by=["filial", "digito"],
                    key=lambda col: (
                        col.map(sort_filial)
                        if col.name == "filial"
                        else col.map(sort_tipo)
                    ),
                )

                df_table["codigo_fmt"] = (
                    df_table["codigo"].astype(str)
                    + " – "
                    + df_table["descricao"].astype(str)
                )

                codigo_map = dict(
                    zip(df_table["codigo_fmt"], df_table["codigo"].astype(str))
                )

                col1, col2, col3 = st.columns(3)

                with col1:
                    filiais_opcoes = sorted(
                        df_table["filial"].dropna().unique(), key=sort_filial
                    )
                    filiais_selecionadas = st.multiselect(
                        "Filtrar por Filial:",
                        filiais_opcoes,
                        default=None,
                        placeholder="Selecione uma ou mais filiais",
                    )

                with col2:
                    tipos_opcoes = sorted(
                        df_table["digito"].dropna().unique(), key=sort_tipo
                    )
                    tipos_selecionados = st.multiselect(
                        "Filtrar por Tipo:",
                        tipos_opcoes,
                        default=None,
                        placeholder="Selecione um ou mais tipos",
                    )

                with col3:
                    codigos_opcoes = sorted(
                        df_table["codigo_fmt"].dropna().unique(),
                        key=lambda x: int(x.split(" – ")[0]),
                    )
                    codigos_selecionados_fmt = st.multiselect(
                        "Filtrar por Código:",
                        codigos_opcoes,
                        default=None,
                        placeholder="Selecione um ou mais códigos",
                    )

                    codigos_selecionados = [
                        codigo_map[x] for x in codigos_selecionados_fmt
                    ]

                df_filtrado = df_table.copy()

                if len(filiais_selecionadas) > 0:
                    df_filtrado = df_filtrado[
                        df_filtrado["filial"].isin(filiais_selecionadas)
                    ]

                if len(tipos_selecionados) > 0:
                    df_filtrado = df_filtrado[
                        df_filtrado["digito"].isin(tipos_selecionados)
                    ]
                if len(codigos_selecionados) > 0:
                    df_filtrado = df_filtrado[
                        df_filtrado["codigo"].astype(str).isin(codigos_selecionados)
                    ]

                df_filtrado = df_filtrado.rename(
                    columns={
                        "codigo": "Código",
                        "descricao": "Descrição",
                        "valor": "Valor",
                        "nome": "Nome",
                        "filial": "Filial",
                        "cnpj": "CNPJ",
                        "digito": "Tipo",
                    }
                )

                df_filtrado = df_filtrado[
                    ["Filial", "Código", "Descrição", "Valor", "Tipo", "Nome", "CNPJ"]
                ]

                df_filtrado.reset_index(drop=True, inplace=True)

                st.dataframe(df_filtrado, width="stretch")

            # ===============================
            # PROVENTOS POR FILIAL
            # ===============================
            with tabs[0]:
                st.subheader("Resumo de Salários")
                st.write("")
                df_soma = (
                    df_final[df_final["digito"] == "P"]
                    .groupby("filial", as_index=False)["valor_num"]
                    .sum()
                )

                df_soma.rename(columns={"filial": "Nome da Filial"}, inplace=True)

                df_soma["Filial"] = df_soma["Nome da Filial"].apply(mapear_filial)

                # 🔧 CORREÇÃO AQUI — manter somente colunas existentes
                df_soma = df_soma[["Filial", "Nome da Filial", "valor_num"]]

                df_soma["total_proventos"] = df_soma["valor_num"].apply(
                    lambda x: f"R${x:,.2f}".replace(",", "X")
                    .replace(".", ",")
                    .replace("X", ".")
                )

                COLUNAS_ESPECIAIS = carregar_config(
                    "COLUNAS_ESPECIAIS",
                    default={
                        "C-270.4 - INSS": ["901"],
                        "C-147.3 - IRF rec.": ["941"],
                        "C-275.5 - V.T.": ["93", "240"],
                        "C-297.6 - Farm.": ["231"],
                        "C-51.5 - Ad. Sal.": [
                            "30",
                            "31",
                            "32",
                            "33",
                            "34",
                            "35",
                            "36",
                            "37",
                            "38",
                            "150",
                            "151",
                            "152",
                            "153",
                            "154",
                            "155",
                            "156",
                            "157",
                            "158",
                        ],
                        "C-51.5 - Desc. Ad. Sal.": ["44"],
                        "C-2267.5 - Conf. dívida": ["20053"],
                        "C-142.2 - P.Alim.": ["908"],
                        "C-297.6 - Pl. Saúde": [
                            "233",
                            "241",
                            "242",
                            "262",
                            "20091",
                        ],
                        "C-146.5 - Sind. Rec.": [
                            "933",
                            "11992",
                            "20078",
                            "20088",
                            "20090",
                        ],
                        "C-302.6 - Cest. Bas.": ["258", "20080"],
                        "D-54.0 - Sal. Fam.": ["907"],
                        "D-53.1 - Sal. Mat.": ["130"],
                        "D-52.3 - Ad 13° Sal.": ["169", "170", "171", "173"],
                        "C-22667 - D-CAIXA (Desc. emp. Consig.)": ["20086"],
                    },
                )

                codigos_padrao = carregar_config(
                    "codigos_padrao",
                    default=[
                        "17",
                        "130",
                        "169",
                        "170",
                        "171",
                        "173",
                        "907",
                        "3",
                        "6",
                        "19",
                        "22",
                        "23",
                        "24",
                        "911",
                        "938",
                    ],
                )

                # ==========================================================
                # 🔹 Construir opções no formato "codigo - descricao"
                # ==========================================================

                # Criar dicionário: código → descrição
                mapa_codigos = (
                    df_final[["codigo", "descricao"]]
                    .drop_duplicates()
                    .assign(codigo=lambda df: df["codigo"].astype(str))
                    .set_index("codigo")["descricao"]
                    .to_dict()
                )

                # Criar lista de opções formatadas
                opcoes_formatadas = []

                for cod in df_final["codigo"].astype(str).unique():
                    desc = mapa_codigos.get(cod, "")
                    opcoes_formatadas.append(f"{cod} - {desc}")

                # Adicionar também códigos dos defaults já existentes em COLUNAS_ESPECIAIS
                for lista in COLUNAS_ESPECIAIS.values():
                    for cod in lista:
                        if cod not in mapa_codigos:
                            # códigos que vêm apenas do default
                            opcoes_formatadas.append(f"{cod} - (sem descrição)")

                # Remover duplicados mantendo ordem
                opcoes_formatadas = list(dict.fromkeys(opcoes_formatadas))

                # ==========================================================
                # 🔹 Função para converter "codigo - descricao" → apenas "codigo"
                # ==========================================================
                def extrair_codigo(item):
                    return item.split(" - ")[0].strip()

                # ==========================================================
                # 🔹 Renderizar Multiselects (2 colunas)
                # ==========================================================
                with st.expander("Configuração de códigos somados por coluna"):
                    st.markdown(
                        """
As colunas especiais representam grupos de códigos de proventos e descontos que devem ser somados para compor cada categoria exibida na tabela final.  
Cada coluna é formada pela soma dos valores de todos os códigos selecionados a baixo.

Você pode ajustar livremente quais códigos pertencem a cada coluna.  
Qualquer alteração feita aqui afeta diretamente os cálculos da tabela abaixo, incluindo:

- o total de salário líquido (**D-266.6 - T. salário**)
- o subtotal (**C-152.0 - Sub. T.**)  
- o salário a pagar (**C-152.0 - Sal. a pagar**)  
- o resultado final (**Resultado**)  
- e todos os totais gerais

Ou seja, esta área define **a lógica de cálculo da planilha**. Cada coluna especial nada mais é do que a soma dos códigos escolhidos para ela.

Por padrão, cada categoria já vem preenchida com os códigos mais utilizados, mas você pode adicionar ou remover códigos conforme necessário.
                    """
                    )
                    col1, col2 = st.columns(2)
                    col_toggle = False
                    codigos_escolhidos = {}

                    todos_codigos = sorted(
                        df_final["codigo"].astype(str).dropna().unique(),
                        key=lambda x: int(x),
                    )

                    codigos_existentes = (
                        df_final["codigo"].astype(str).unique().tolist()
                    )

                    # Criar código – descrição apenas dentro do tipo correto
                    df_final["codigo_desc"] = (
                        df_final["codigo"].astype(str)
                        + " – "
                        + df_final["descricao"].astype(str)
                    )

                    codigo_map = dict(
                        zip(df_final["codigo_desc"], df_final["codigo"].astype(str))
                    )

                    codigos_formatados = sorted(
                        [c for c in codigo_map if codigo_map[c] in codigos_existentes],
                        key=lambda x: int(x.split(" – ")[0]),
                    )

                    # Filtrar padrões que realmente existem no CSV
                    codigos_default_fmt = [
                        c for c in codigos_formatados if codigo_map[c] in codigos_padrao
                    ]
                    with col1:
                        with st.expander(
                            "Códigos para calculo da D-266.6 - T. Salário"
                        ):

                            codigos_select_fmt = st.multiselect(
                                "Selecione os códigos para **D-266.6 - T. Salário**",
                                options=codigos_formatados,
                                default=codigos_default_fmt,
                            )

                            codigos_selecionados = [
                                codigo_map[x] for x in codigos_select_fmt
                            ]

                            salvar_config("codigos_padrao", codigos_selecionados)

                        df_codigos_especiais = (
                            df_final[
                                (
                                    (
                                        df_final["codigo"]
                                        .astype(str)
                                        .isin(codigos_selecionados)
                                    )
                                )
                            ]
                            .groupby("filial", as_index=False)["valor_num"]
                            .sum()
                        )

                        df_codigos_especiais.rename(
                            columns={"valor_num": "total_codigos_especiais"},
                            inplace=True,
                        )

                        df_soma = df_soma.merge(
                            df_codigos_especiais,
                            left_on="Nome da Filial",
                            right_on="filial",
                            how="left",
                        ).drop(columns=["filial"])

                        df_soma["total_codigos_especiais"] = df_soma[
                            "total_codigos_especiais"
                        ].fillna(0)

                        df_soma["total_codigos_especiais_fmt"] = df_soma[
                            "total_codigos_especiais"
                        ].apply(
                            lambda x: f"R${x:,.2f}".replace(",", "X")
                            .replace(".", ",")
                            .replace("X", ".")
                        )

                        df_soma["total_liquido"] = (
                            df_soma["valor_num"] - df_soma["total_codigos_especiais"]
                        )

                        df_soma["total_liquido_fmt"] = df_soma["total_liquido"].apply(
                            lambda x: f"R${x:,.2f}".replace(",", "X")
                            .replace(".", ",")
                            .replace("X", ".")
                        )

                        df_soma = df_soma.sort_values(
                            by="Nome da Filial", key=lambda col: col.map(sort_buffon)
                        )

                    for coluna, lista_default_codigos in COLUNAS_ESPECIAIS.items():

                        # Converter defaults para o novo formato
                        defaults_formatados = []
                        for cod in lista_default_codigos:
                            desc = mapa_codigos.get(str(cod), None)
                            if desc is not None:
                                defaults_formatados.append(f"{cod} - {desc}")

                        # Selecionar coluna visual
                        if col_toggle:
                            container = col1
                        else:
                            container = col2
                        with container:
                            with st.expander(f"Códigos para {coluna}"):
                                selecionados_formatados = st.multiselect(
                                    f"Selecione os códigos para **{coluna}**:",
                                    options=opcoes_formatadas,
                                    default=defaults_formatados,
                                    key=f"multi_{coluna}",
                                )

                        # Converter de volta para códigos puros
                        codigos_escolhidos[coluna] = [
                            extrair_codigo(s) for s in selecionados_formatados
                        ]

                        col_toggle = not col_toggle

                    # Atualiza COLUNAS_ESPECIAIS com os valores selecionados
                    COLUNAS_ESPECIAIS = codigos_escolhidos

                    salvar_config("COLUNAS_ESPECIAIS", COLUNAS_ESPECIAIS)

                # ==========================================================
                # FUNÇÃO PARA SOMAR CÓDIGOS POR FILIAL
                # ==========================================================

                def somar_codigos_por_filial(codigos):
                    codigos_str = set(str(c) for c in codigos)
                    return (
                        df_final[df_final["codigo"].astype(str).isin(codigos_str)]
                        .groupby("filial", as_index=False)["valor_num"]
                        .sum()
                        .rename(columns={"valor_num": "valor"})
                    )

                # ==========================================================
                # GERAR DATAFRAMES INDIVIDUAIS PARA CADA CATEGORIA
                # ==========================================================

                dfs_merged = []

                for nome_coluna, codigos in COLUNAS_ESPECIAIS.items():
                    df_temp = somar_codigos_por_filial(codigos)
                    df_temp.rename(columns={"valor": nome_coluna}, inplace=True)
                    dfs_merged.append(df_temp)

                # ==========================================================
                # MERGE SEGURO (REUTILIZÁVEL)
                # ==========================================================

                def merge_seguro(base, novo):
                    base = base.merge(
                        novo, left_on="Nome da Filial", right_on="filial", how="left"
                    )
                    base = base.drop(columns=["filial"])
                    return base

                # ==========================================================
                # MERGE DE TODAS AS COLUNAS NO DF PRINCIPAL
                # ==========================================================

                for df_temp in dfs_merged:
                    df_soma = merge_seguro(df_soma, df_temp)

                # ==========================================================
                # TRATAR VALORES FALTANTES
                # ==========================================================

                for col in COLUNAS_ESPECIAIS.keys():
                    df_soma[col] = df_soma[col].fillna(0)

                # ==========================================================
                # FORMATAR EM REAIS
                # ==========================================================

                def fmt_real(v):
                    return (
                        f"{v:,.2f}".replace(",", "X")
                        .replace(".", ",")
                        .replace("X", ".")
                    )

                for col in COLUNAS_ESPECIAIS.keys():
                    df_soma[col + "_fmt"] = df_soma[col].apply(fmt_real)

                # ==========================================================
                # MONTAR DATAFRAME FINAL
                # ==========================================================

                colunas_fmt = [c + "_fmt" for c in [*COLUNAS_ESPECIAIS.keys()][0:11]]
                colunas_fmt_2 = [c + "_fmt" for c in [*COLUNAS_ESPECIAIS.keys()][11:14]]
                colunas_fmt_3 = [c + "_fmt" for c in [*COLUNAS_ESPECIAIS.keys()][14:]]

                # Lista das colunas especiais já existentes em df_soma
                colunas_calc_sub_t = list(COLUNAS_ESPECIAIS.keys())[0:11]

                # Converter valores de D-266.6 - T. salário para número
                df_soma["D-266.6_num"] = (
                    df_soma["total_liquido_fmt"]
                    .str.replace("R$", "")
                    .str.replace(".", "")
                    .str.replace(",", ".")
                    .astype(float)
                )

                # Converter valores das colunas especiais para número
                for col in colunas_calc_sub_t:
                    df_soma[col + "_num"] = (
                        df_soma[col + "_fmt"]
                        .str.replace("R$", "")
                        .str.replace(".", "")
                        .str.replace(",", ".")
                        .astype(float)
                    )

                # Subt = Total salário - soma das colunas especiais
                df_soma["C-152.0 -  Sub. T."] = df_soma["D-266.6_num"] - df_soma[
                    [c + "_num" for c in colunas_calc_sub_t]
                ].sum(axis=1)

                # Formatar
                df_soma["C-152.0 -  Sub. T._fmt"] = df_soma["C-152.0 -  Sub. T."].apply(
                    fmt_real
                )

                # ==========================================================
                # NOVA COLUNA: C-152.0 - Sal. a pagar
                # ==========================================================

                # Colunas especiais que devem ser subtraídas
                colunas_salario_a_pagar = list(COLUNAS_ESPECIAIS.keys())[11:14]

                # Converter essas colunas para número (se ainda não tiverem)
                for col in colunas_salario_a_pagar:
                    df_soma[col + "_num"] = (
                        df_soma[col + "_fmt"]
                        .str.replace("R$", "")
                        .str.replace(".", "")
                        .str.replace(",", ".")
                        .astype(float)
                    )

                # Calcular soma das três colunas
                df_soma["soma_especiais_sal_pagar"] = df_soma[
                    [c + "_num" for c in colunas_salario_a_pagar]
                ].sum(axis=1)

                # Calcular Salário a Pagar
                df_soma["C-152.0 - Sal. a pagar"] = (
                    df_soma["C-152.0 -  Sub. T."] + df_soma["soma_especiais_sal_pagar"]
                )

                # Formatar
                df_soma["C-152.0 - Sal. a pagar_fmt"] = df_soma[
                    "C-152.0 - Sal. a pagar"
                ].apply(fmt_real)

                # ==========================================================
                # NOVA COLUNA: RESULTADO
                # resultado = (C-152.0 - Sal. a pagar) - (C-22667 - D-CAIXA ...)
                # ==========================================================

                col_dcaixa = list(COLUNAS_ESPECIAIS.keys())[14]

                # Converter a coluna D-CAIXA para número
                df_soma[col_dcaixa + "_num"] = (
                    df_soma[col_dcaixa + "_fmt"]
                    .str.replace("R$", "")
                    .str.replace(".", "")
                    .str.replace(",", ".")
                    .astype(float)
                )

                # Calcular o resultado final
                df_soma["Resultado"] = (
                    df_soma["C-152.0 - Sal. a pagar"] - df_soma[col_dcaixa + "_num"]
                )

                # Formatar para R$
                df_soma["Resultado_fmt"] = df_soma["Resultado"].apply(fmt_real)

                df_resumo = df_soma[
                    [
                        "Filial",
                        "total_proventos",
                        "total_codigos_especiais_fmt",
                        "total_liquido_fmt",
                    ]
                    + colunas_fmt
                    + ["C-152.0 -  Sub. T._fmt"]
                    + colunas_fmt_2
                    + ["C-152.0 - Sal. a pagar_fmt"]
                    + colunas_fmt_3
                    + ["Resultado_fmt"]
                ].rename(
                    columns={
                        "total_proventos": "Total proventos",
                        "total_codigos_especiais_fmt": "Total proventos e descontos selecionados",
                        "total_liquido_fmt": "D-266.6 - T. salário",
                        **{c + "_fmt": c for c in COLUNAS_ESPECIAIS.keys()},
                        "C-152.0 -  Sub. T._fmt": "C-152.0 -  Sub. T.",
                        "C-152.0 - Sal. a pagar_fmt": "C-152.0 - Sal. a pagar",
                        "Resultado_fmt": "Resultado",
                    }
                )

                df_resumo.reset_index(drop=True, inplace=True)

                mostrar_proventos = st.toggle(
                    "Mostrar valores utilizadas para calculo de salário", value=False
                )

                df_resumo_view = df_resumo.copy()

                if not mostrar_proventos:
                    df_resumo_view = df_resumo_view.drop(
                        ["Total proventos", "Total proventos e descontos selecionados"],
                        axis=1,
                    )
                for col in df_resumo_view.columns:
                    if (
                        df_resumo_view[col].dtype == object
                        and df_resumo_view[col].str.contains("R\$").any()
                    ):
                        df_resumo_view[col] = df_resumo_view[col].str.replace(
                            "R$", "", regex=False
                        )

                df_totais = df_resumo_view.copy()

                # Identificar colunas numéricas que estão no formato R$
                colunas_monetarias = [
                    col
                    for col in df_totais.columns
                    if df_totais[col].dtype == object
                    and df_totais[col].str.contains(",").any()
                ]

                # Converter temporariamente para float
                for col in colunas_monetarias:
                    df_totais[col + "_num"] = (
                        df_totais[col]
                        .str.replace(".", "")
                        .str.replace(",", ".")
                        .astype(float)
                    )

                # Criar dicionário da linha de totais
                linha_total = {"Filial": "", "Filial": "T. GERAL"}

                # Para cada coluna monetária, soma
                for col in colunas_monetarias:
                    total = df_totais[col + "_num"].sum()
                    linha_total[col] = (
                        f"{total:,.2f}".replace(",", "X")
                        .replace(".", ",")
                        .replace("X", ".")
                    )

                if "df_pdf" in locals() and not df_pdf.empty:
                    df_totais = pd.merge(
                        df_totais, df_pdf, on="Filial", how="outer"
                    ).fillna(0)

                    df_totais["Func."] = df_totais["Func."].astype(int)

                # Outras colunas numéricas não-R$ (se existirem)
                colunas_numericas = [
                    col
                    for col in df_totais.select_dtypes(include=["number"]).columns
                    if col.endswith("_num") is False
                ]

                for col in colunas_numericas:
                    linha_total[col] = df_totais[col].sum()

                # Adicionar linha ao final do dataframe
                columns = list(df_resumo_view.columns)

                if "Func." in df_totais.columns:
                    columns = ["Func."] + columns

                df_totais = df_totais[columns].copy()
                df_totais.loc[len(df_totais)] = linha_total

                df_totais = df_totais.sort_values(
                    by="Filial", key=lambda col: col.map(sort_filial)
                )

                df_totais.set_index("Filial", inplace=True)

                def bold_last_row(row):
                    return [
                        "font-weight: bold" if row.name == "TOTAL GERAL" else ""
                        for _ in row
                    ]

                df_resumo_styled = df_totais.style.set_table_styles(
                    [
                        {
                            "selector": "th.row_heading",
                            "props": [("min-width", "200px")],
                        },
                        {
                            "selector": "th.col_heading",
                            "props": [("min-width", "200px")],
                        },
                    ]
                ).apply(bold_last_row, axis=1)
                # Exibir tabela com linha de total
                st.dataframe(df_resumo_styled, width="stretch")

            with tabs[2]:
                st.subheader("Resumo Prolabore")
                st.write("")

                # --- Tabela Prolabore / INSS / Total Líquido ---

                # Filtrar valores
                df_prolabore = (
                    df_final[df_final["codigo"] == 17]
                    .groupby("filial")["valor_num"]
                    .sum()
                    .reset_index()
                )
                df_prolabore.rename(columns={"valor_num": "prolabore"}, inplace=True)

                df_inss = (
                    df_final[df_final["codigo"] == 940]
                    .groupby("filial")["valor_num"]
                    .sum()
                    .reset_index()
                )
                df_inss.rename(columns={"valor_num": "inss"}, inplace=True)

                # Unir prolabore + inss em uma só tabela
                df_extra = pd.merge(
                    df_prolabore, df_inss, on="filial", how="outer"
                ).fillna(0)

                # Calcular total líquido
                df_extra["total_liquido"] = df_extra["prolabore"] - df_extra["inss"]

                # 🔥 Criar linha de total geral
                total_prolabore = df_extra["prolabore"].sum()
                total_inss = df_extra["inss"].sum()
                total_liquido = df_extra["total_liquido"].sum()

                df_total = pd.DataFrame(
                    {
                        "filial": ["T. GERAL"],
                        "prolabore": [total_prolabore],
                        "inss": [total_inss],
                        "total_liquido": [total_liquido],
                    }
                )

                # Adicionar a linha ao dataframe
                df_extra = pd.concat([df_extra, df_total], ignore_index=True)

                # Formatar valores
                df_extra_fmt = df_extra.copy()
                df_extra_fmt["prolabore"] = df_extra_fmt["prolabore"].apply(fmt_real)
                df_extra_fmt["inss"] = df_extra_fmt["inss"].apply(fmt_real)
                df_extra_fmt["total_liquido"] = df_extra_fmt["total_liquido"].apply(
                    fmt_real
                )

                # Ordenar mantendo TOTAL GERAL no final
                df_extra_fmt["__ordem__"] = df_extra_fmt["filial"].apply(
                    lambda x: (999, "") if x == "T. GERAL" else sort_buffon(x)
                )
                df_extra_fmt = df_extra_fmt.sort_values("__ordem__").drop(
                    columns="__ordem__"
                )

                # Renomear colunas
                df_extra_fmt.rename(
                    columns={
                        "filial": "Filial",
                        "prolabore": "Prolabore",
                        "inss": "INSS",
                        "total_liquido": "Total Líquido",
                    },
                    inplace=True,
                )

                df_extra_fmt["Filial"] = df_extra_fmt["Filial"].apply(mapear_filial)

                df_extra_fmt.set_index("Filial", inplace=True)

                df_extra_fmt_styled = df_extra_fmt.style.set_table_styles(
                    [
                        {
                            "selector": "th.row_heading",
                            "props": [("min-width", "200px")],
                        },
                        {
                            "selector": "th.col_heading",
                            "props": [("min-width", "200px")],
                        },
                    ]
                ).apply(bold_last_row, axis=1)

                st.dataframe(df_extra_fmt_styled, width="stretch")

            if "resultados_quebra" in locals():
                df_quebra = pd.DataFrame(resultados_quebra)

                with tabs[1]:
                    st.subheader("Resumo FGTS")

                    st.write("")

                    if "df_quebra" in locals() and not df_quebra.empty:
                        # Padronizar nome da filial (mesma lógica das outras tabelas)
                        df_quebra["Filial"] = df_quebra["Filial"].apply(mapear_filial)

                        df_quebra.rename(
                            columns={"Salário": "D-271.2 FGTS - C-145.7 FGTS a rec"},
                            inplace=True,
                        )

                        # 🔹 Coluna D-266.6 - T. salário
                        # reaproveita o valor do salário da quebra
                        df_quebra = df_quebra.merge(
                            df_totais.reset_index()[["Filial", "D-266.6 - T. salário"]],
                            on="Filial",
                            how="left",
                        )

                        df_quebra["D-266.6 - T. salário_num"] = (
                            df_quebra["D-266.6 - T. salário"]
                            .str.replace("R$", "", regex=False)
                            .str.replace(".", "", regex=False)
                            .str.replace(",", ".", regex=False)
                            .astype(float)
                        )

                        df_quebra["D-269.1 13° sal - C-162.7 Prov 13° sal"] = (
                            df_quebra["D-266.6 - T. salário_num"] / 12
                        )

                        df_quebra["D-269.1 13° sal - C-162.7 Prov 13° sal"] = df_quebra[
                            "D-269.1 13° sal - C-162.7 Prov 13° sal"
                        ].apply(fmt_real)

                        df_quebra["D-269.1 13° sal - C-162.7 Prov 13° sal_num"] = (
                            df_quebra["D-269.1 13° sal - C-162.7 Prov 13° sal"]
                            .str.replace("R$", "", regex=False)
                            .str.replace(".", "", regex=False)
                            .str.replace(",", ".", regex=False)
                            .astype(float)
                        )

                        df_quebra["D-1324.2 enc s/ 13° sal - C-162.7 13° sal"] = (
                            df_quebra["D-269.1 13° sal - C-162.7 Prov 13° sal_num"]
                            * 0.258
                        ).apply(fmt_real)

                        df_quebra["D-1324.2 enc s/ 13° sal - C-162.7 13° sal_num"] = (
                            df_quebra["D-1324.2 enc s/ 13° sal - C-162.7 13° sal"]
                            .str.replace("R$", "", regex=False)
                            .str.replace(".", "", regex=False)
                            .str.replace(",", ".", regex=False)
                            .astype(float)
                        )

                        df_quebra["Total prov 13°"] = (
                            df_quebra["D-269.1 13° sal - C-162.7 Prov 13° sal_num"]
                            + df_quebra["D-1324.2 enc s/ 13° sal - C-162.7 13° sal_num"]
                        ).apply(fmt_real)

                        # Ordenar filiais no mesmo padrão
                        df_quebra = df_quebra.sort_values(
                            by="Filial", key=lambda col: col.map(sort_filial)
                        )

                        cols_soma = df_quebra.columns.drop("Filial").tolist()

                        for col in cols_soma:
                            df_quebra[col + "_num"] = df_quebra[col].apply(
                                lambda x: float(br_to_float(x))
                            )

                        total_geral = {"Filial": "TOTAL GERAL"}

                        for col in cols_soma:
                            total_geral[col] = df_quebra[col + "_num"].sum()
                            total_geral[col] = fmt_real(total_geral[col])

                        df_quebra = pd.concat(
                            [df_quebra, pd.DataFrame([total_geral])], ignore_index=True
                        )

                        df_quebra = df_quebra.rename(
                            columns={"D-266.6 - T. salário": "Salário"}
                        )

                        df_quebra = df_quebra.drop(
                            columns=[c for c in df_quebra.columns if c.endswith("_num")]
                        )

                        df_quebra.set_index("Filial", inplace=True)

                        st.dataframe(df_quebra, width="stretch")

                    else:
                        st.info(
                            "Nenhuma informação de FGTS encontrado. Verifique o arquivo enviado"
                        )

            else:
                with tabs[1]:
                    st.subheader("Resumo FGTS")
                    st.write("")

                    st.info(
                        "Informações de FGTS não encontrado. Verifique o arquivo enviado"
                    )
                    df_quebra = pd.DataFrame()

            # ===============================
            # 🔹 DOWNLOADS
            # ===============================
            output = io.BytesIO()

            # Preparar dataframes
            df_download_totais = df_totais.reset_index().copy()
            df_download_extra = df_extra_fmt.reset_index().copy()
            df_download_extra = df_download_extra.sort_values(
                by="Filial", key=lambda col: col.map(sort_buffon)
            )
            df_download_extra_caixa = df_quebra.reset_index().copy()

            col_filial_original = df_download_totais["Filial"].copy()

            pos = len(df_download_totais.columns) - 2

            df_download_totais.insert(pos, "Filial ", col_filial_original)

            # Função para quebrar header
            def separar_header_em_duas_linhas(header_list):
                codigos = []
                descricoes = []
                for col in header_list:
                    if " - " not in col:  # Filial, Funcionários, Resultado, etc
                        codigos.append("")
                        descricoes.append(col)
                    else:
                        codigo, nome = col.split(" - ", 1)
                        codigos.append(codigo.strip())
                        descricoes.append(nome.strip())
                return codigos, descricoes

            # Obter header original do df_totais
            header_original = df_download_totais.columns.tolist()
            header_codigos, header_nomes = separar_header_em_duas_linhas(
                header_original
            )

            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                workbook = writer.book

                fmt_right = workbook.add_format({"align": "right", "valign": "vcenter"})

                # Escreve o DF começando na linha 3 (0=linha4 na planilha)
                df_download_totais.to_excel(
                    writer, index=False, sheet_name="Resumo Salários", startrow=4
                )

                if "Func." in df_totais.columns:
                    df_download_salario = df_totais[
                        ["Func.", "D-266.6 - T. salário"]
                    ].reset_index()

                    df_download_salario.to_excel(
                        writer,
                        index=False,
                        sheet_name="Resumo Salários e Funcionários",
                        startrow=2,
                    )

                df_empresas = pd.DataFrame(
                    {
                        "Empresa": [
                            "Petrifacill",
                            "Petrogass",
                            "Volares",
                            "Solyda",
                        ],
                        "Func.": ["", "", "", ""],
                        "Salário": ["", "", "", ""],
                    }
                )

                worksheet = writer.sheets["Resumo Salários"]

                worksheet.set_column(
                    f"B6:V{len(df_download_totais) + 7}", None, fmt_right
                )

                # FORMATOS
                format_title = workbook.add_format(
                    {
                        "bold": True,
                        "align": "left",
                        "valign": "vcenter",
                        "font_size": 14,
                    }
                )
                format_sub = workbook.add_format(
                    {
                        "bold": True,
                        "align": "left",
                        "valign": "vcenter",
                        "font_size": 12,
                    }
                )
                mes_csv = ss.get("csv_mes")
                ano_csv = ss.get("csv_ano")

                first_day_this_month = datetime.now().replace(day=1)
                last_day_prev_month = first_day_this_month - timedelta(days=1)
                mes_ano_excel = last_day_prev_month.strftime("%m/%Y")

                if mes_csv and ano_csv:
                    mes_ano_excel = f"{mes_csv}/{ano_csv}"

                # ===============================
                # 🔹 RESUMO SALÁRIOS E FUNCIONÁRIOS
                # ===============================

                if "Func." in df_totais.columns:
                    worksheet_func = writer.sheets["Resumo Salários e Funcionários"]

                    # Descobrir a última linha usada pela tabela principal
                    start_row_empresas = len(df_download_salario) + 5

                    # Título da mini tabela
                    worksheet_func.merge_range(
                        start_row_empresas - 1,
                        0,
                        start_row_empresas - 1,
                        2,
                        "Resumo por Empresa",
                        workbook.add_format(
                            {"bold": True, "font_size": 12, "align": "left"}
                        ),
                    )

                    # Escrever a mini tabela
                    df_empresas.to_excel(
                        writer,
                        sheet_name="Resumo Salários e Funcionários",
                        startrow=start_row_empresas,
                        index=False,
                    )

                    worksheet_func.set_column(
                        f"B4:C{len(df_download_extra) + 4}", None, fmt_right
                    )

                    worksheet_func.merge_range(
                        "A1:G1",
                        "COMERCIAL BUFFON COMB. E TRANSPORTES LTDA",
                        format_title,
                    )

                    worksheet_func.merge_range(
                        "A2:E2",
                        f"SALÁRIOS REFERENTES MÊS {mes_ano_excel}",
                        format_sub,
                    )

                fmt_num = workbook.add_format(
                    {"align": "center", "valign": "vcenter", "bold": True}
                )
                fmt_cont_cods = workbook.add_format(
                    {"align": "left", "valign": "vcenter", "bold": True}
                )

                # ===============================
                # 🔹 ESCREVER AS LINHAS 1 E 2 DO HEADER
                # ===============================

                # Linha 1 → somente códigos
                for col_idx, codigo in enumerate(header_codigos):
                    worksheet.write(3, col_idx, codigo, fmt_num)

                # Linha 2 → nomes
                for col_idx, nome in enumerate(header_nomes):
                    worksheet.write(4, col_idx, nome, fmt_num)

                HEADER_NUMBERS = {
                    "C-270.4 - INSS": "10",
                    "C-147.3 - IRF rec.": "11",
                    "C-275.5 - V.T.": "12",
                    "C-297.6 - Farm.": "13",
                    "C-51.5 - Ad. Sal.": "90",
                    "C-51.5 - Desc. Ad. Sal.": "91",
                    "C-2267.5 - Conf. dívida": "150",
                    "C-142.2 - P.Alim.": "15",
                    "C-297.6 - Pl. Saúde": "16",
                    "C-146.5 - Sind. Rec.": "17",
                    "C-302.6 - Cest. Bas.": "18",
                    "C-152.0 -  Sub. T.": "19",
                    "C-22667 - D-CAIXA (Desc. emp. Consig.)": "152",
                }

                col_names = df_download_totais.columns.tolist()

                for col_idx, col_name in enumerate(col_names):
                    codigo = HEADER_NUMBERS.get(col_name, "")
                    worksheet.write(2, col_idx, codigo, fmt_num)

                # Aplica o título "Códigos contábeis" apenas sobre as duas primeiras colunas
                worksheet.merge_range("A3:C3", "Códigos contábeis", fmt_cont_cods)
                # ===============================
                # 🔹 TITULOS DO DOCUMENTO
                # ===============================
                worksheet.merge_range(
                    "A1:G1",
                    "COMERCIAL BUFFON COMB. E TRANSPORTES LTDA",
                    format_title,
                )

                last_row_totais = len(df_download_totais) + 6

                worksheet.write(last_row_totais + 1, 0, " ")

                format_section = workbook.add_format(
                    {"bold": True, "font_size": 12, "align": "left"}
                )
                worksheet.merge_range(
                    last_row_totais + 3,
                    2,
                    last_row_totais + 3,
                    4,
                    "Cálculo de Pró-Labore",
                    format_section,
                )
                df_download_extra.to_excel(
                    writer,
                    index=False,
                    sheet_name="Resumo Salários",
                    startrow=last_row_totais + 4,
                    startcol=2,
                )

                worksheet.merge_range(
                    "A2:G2", f"SALÁRIOS REFERENTES MÊS {mes_ano_excel}", format_sub
                )

                # Bold na última linha
                last_fmt = workbook.add_format(
                    {"bold": True, "align": "right", "valign": "vcenter"}
                )
                last_row = len(df_download_totais)
                worksheet.set_row(last_row + 4, None, last_fmt)

                # ===============================
                # 🔹 EXTRA CAIXA — MESMO HEADER DO RESUMO SALÁRIOS
                # ===============================

                if df_download_extra_caixa.empty is False:

                    worksheet_caixa = workbook.add_worksheet("FGTS e Honorários")
                    writer.sheets["FGTS e Honorários"] = worksheet_caixa

                    # Header base
                    header_caixa = df_download_extra_caixa.columns.tolist()
                    header_codigos_caixa, header_nomes_caixa = (
                        separar_header_em_duas_linhas(header_caixa)
                    )

                    # Escrever dataframe começando na mesma linha
                    df_download_extra_caixa.to_excel(
                        writer, index=False, sheet_name="FGTS e Honorários", startrow=3
                    )

                    # Linha 1 → códigos contábeis
                    for col_idx, codigo in enumerate(header_codigos_caixa):
                        worksheet_caixa.write(2, col_idx, codigo, fmt_num)

                    # Linha 2 → descrições
                    for col_idx, nome in enumerate(header_nomes_caixa):
                        worksheet_caixa.write(3, col_idx, nome, fmt_num)

                    worksheet_caixa.set_column(
                        f"B6:F{len(df_download_extra_caixa) + 3}", None, fmt_right
                    )

                    # Linha 0 → título
                    worksheet_caixa.merge_range(
                        "A1:G1",
                        "COMERCIAL BUFFON COMB. E TRANSPORTES LTDA",
                        format_title,
                    )

                    # Linha 1 → subtítulo (mesmo mês)
                    worksheet_caixa.merge_range(
                        "A2:G2",
                        f"FGTS REFERENTE MÊS {mes_ano_excel}",
                        format_sub,
                    )

                    df_honorarios = pd.DataFrame(
                        {
                            "Descrição": [
                                "D-288.7 - Honorários",
                                "C-154.6 - Hon. a pagar",
                                f"Vl. Hon. no mês {mes_ano_excel}",
                            ],
                            "Valor": ["", "", ""],
                        }
                    )

                    start_row_honorarios = len(df_download_extra_caixa) + 6

                    worksheet_caixa.merge_range(
                        start_row_honorarios - 1,
                        3,
                        start_row_honorarios - 1,
                        5,
                        "Honorários",
                        workbook.add_format(
                            {"bold": True, "font_size": 12, "align": "left"}
                        ),
                    )

                    # Escrever a mini tabela
                    df_honorarios.to_excel(
                        writer,
                        sheet_name="FGTS e Honorários",
                        startrow=start_row_honorarios,
                        startcol=3,
                        index=False,
                    )

            # Gerar bytes
            xlsx_data = output.getvalue()

            # Nome do arquivo
            if mes_csv and ano_csv:
                nome_arquivo = f"resumo_salarios_buffon_{mes_csv}-{ano_csv}.xlsx"
            else:
                mes_ano = last_day_prev_month.strftime("%m-%Y")
                nome_arquivo = f"resumo_salarios_buffon_{mes_ano}.xlsx"

            with res_cols[1]:
                # Botão de download
                st.download_button(
                    label=":material/download: Baixar resultado geral",
                    data=xlsx_data,
                    file_name=nome_arquivo,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary",
                    use_container_width=True,
                )

        except Exception as e:
            st.error("Ocorreu um erro ao processar os dados extraídos.")
            print(f"[ERRO] - {e}")
