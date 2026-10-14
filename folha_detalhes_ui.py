"""Consulta dos dados originais do PDF, independente dos cálculos do CSV."""

import pandas as pd
import streamlit as st

from folha_pdf import extrair_detalhes_pdf


@st.cache_data(show_spinner=False)
def carregar_detalhes(conteudo):
    return extrair_detalhes_pdf(conteudo)


def mostrar_detalhes_folha(arquivo):
    with st.container(border=True):
        st.header("Dados completos do novo PDF da folha")
        if arquivo is None:
            st.info("Envie o novo PDF no campo de funcionários acima para consultar os dados completos, mesmo sem CSV.")
            return
        try:
            with st.spinner("Extraindo as tabelas da folha…"):
                dados = carregar_detalhes(arquivo.getvalue())
        except (ValueError, RuntimeError) as erro:
            st.error(f"Não foi possível extrair as tabelas deste PDF: {erro}")
            return
        if not dados["documento"]:
            st.info("Esta consulta detalhada está disponível para o novo padrão com estabelecimentos Buffon. O formato antigo continua disponível nos resumos acima.")
            return

        st.caption(f"Arquivo: {arquivo.name}. Valores e descrições conforme impressos no PDF; algumas descrições já aparecem abreviadas no relatório.")
        st.subheader("Identificação do relatório")
        st.dataframe(pd.DataFrame(dados["documento"]), hide_index=True, width="stretch")
        unidades = [r["Unidade"] for r in dados["resumos"] if r["Unidade"] != "Total da empresa"]
        unidades.sort(key=lambda u: (0, 0) if u == "Matriz" else (1, int(u.split()[-1])))
        selecao = st.selectbox(
            "Unidade para consulta", ["Todas as unidades", *unidades, "Total da empresa"],
            key="detalhes_pdf_unidade",
        )
        st.caption("“Todas as unidades” mostra apenas as unidades. Selecione “Total da empresa” para consultar o consolidado impresso no PDF.")

        def filtrar(linhas):
            return [r for r in linhas if (
                r["Unidade"] != "Total da empresa" if selecao == "Todas as unidades"
                else r["Unidade"] == selecao
            )]

        tabelas = [("Totais e contratos", filtrar(dados["resumos"]))]
        for tipo, titulo in (("Vencimento", "Vencimentos"), ("Desconto", "Descontos"), ("Base", "Bases e eventos informativos")):
            tabelas.append((titulo, [r for r in filtrar(dados["eventos"]) if r["Tipo"] == tipo]))
        tabelas.append(("Categorias de contratos", filtrar(dados["categorias"])))
        for titulo, linhas in tabelas:
            st.subheader(titulo)
            if linhas:
                st.dataframe(pd.DataFrame(linhas), hide_index=True, width="stretch")
                st.caption(f"{len(linhas)} registros")
            else:
                st.info("Nenhum registro nesta seleção.")
