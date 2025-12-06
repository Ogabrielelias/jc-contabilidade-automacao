import streamlit as st


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

with header_cols[1]:
    if st.button(":material/arrow_back: Voltar", use_container_width=True):
        st.switch_page("app.py")

st.markdown("<hr style='padding:0;margin:16px 0;'>", unsafe_allow_html=True)


with st.container(border=True):
    st.header("Ajuda")
    st.markdown("<hr style='padding:0;margin:16px 0;'>", unsafe_allow_html=True)

    with st.expander("Como usar a aplicação"):
        st.write("")

    with st.expander("Como baixar e utilizar as tabelas"):
        st.write("")

    with st.expander("Como imprimir as tabelas"):
        st.write("")

    with st.expander("Como alterar/adicionar códigos para cálculo na tabela"):
        st.write("")

    with st.expander("Como consultar os dados extraídos"):
        st.write("")
