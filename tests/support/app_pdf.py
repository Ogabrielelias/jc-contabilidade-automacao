import io
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import streamlit as st
import supabase

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))


class Query:
    def select(self, *args):
        return self

    def eq(self, field, value):
        self.key = value
        return self

    def upsert(self, data, **kwargs):
        if st.session_state.get("test_fail_save"):
            raise RuntimeError("Falha de gravação simulada")
        self.key = data["chave"]
        st.session_state.setdefault("test_db", {})[self.key] = data["valor"]
        return self

    def execute(self):
        value = st.session_state.get("test_db", {}).get(self.key)
        return SimpleNamespace(data=[{"valor": value}] if value is not None else [], error=None)


def uploader(*args, **kwargs):
    if kwargs.get('key') in ('pdf_provisao_13', 'saldos_provisao_13') and st.session_state.get('test_provisao'):
        if kwargs['key'] == 'saldos_provisao_13' and st.session_state.get('test_provisao_incompleta'):
            return None
        nome = 'Provisão de 13° Buffon Final  09 - 2026.pdf' if kwargs['key'] == 'pdf_provisao_13' else 'prov 13 sal _09-2026 (3) nova.ods'
        arquivo = io.BytesIO((root / nome).read_bytes())
        arquivo.name = nome
        return arquivo
    if kwargs.get("key") in ("pdf_inss", "ods_inss") and st.session_state.get("test_inss"):
        if kwargs["key"] == "ods_inss" and st.session_state.get("test_inss_incompleto"):
            return None
        nome = "Resumo GPS Buffon 09 2026 (1).pdf" if kwargs["key"] == "pdf_inss" else "Buffon Inss Desconto Empregados 09.2026 (1).ods"
        arquivo = io.BytesIO((root / nome).read_bytes())
        arquivo.name = nome
        return arquivo
    if kwargs.get("key") == "pdf_prov" and st.session_state.get("test_pdf_13_invalido"):
        import fitz
        with fitz.open() as doc:
            doc.new_page().insert_text((30, 30), "Provisao de 13 salario - modelo antigo")
            arquivo = io.BytesIO(doc.tobytes())
        arquivo.name = "provisao_09_2026.pdf"
        return arquivo
    if kwargs.get("key") == "pdf_prov" and st.session_state.get("test_adiantamento"):
        path = root / "Buffon adiantamento 13° salário 09 2026.pdf"
        arquivo = io.BytesIO(path.read_bytes())
        arquivo.name = "adiantamento.pdf"
        return arquivo
    if kwargs.get("key") == "pdf_funcionarios":
        if st.session_state.get('test_somente_provisao'):
            return None
        if st.session_state.get("test_somente_adiantamento") or st.session_state.get("test_somente_inss"):
            return None
        path = root / "Buffon Folha de salário 09 2026.pdf"
        arquivo = io.BytesIO(path.read_bytes())
        arquivo.name = path.name
        return arquivo
    if args and args[0] == "Selecione o arquivo CSV":
        arquivo = io.BytesIO(
            b'x,x,x,1,x,x,x,1,Salario,"1000,00",Pessoa,-1,Matriz,93489243000100,P\n'
            b'x,x,x,1,x,x,x,901,INSS,"100,00",Pessoa,-1,Matriz,93489243000100,D\n'
        )
        arquivo.name = "folha_202609.csv"
        return arquivo
    return None


original_client = supabase.create_client
original_uploader = st.file_uploader
original_download = st.download_button


def download(*args, **kwargs):
    st.session_state["test_export"] = kwargs["data"]
    st.session_state["test_export_name"] = kwargs["file_name"]
    return original_download(*args, **kwargs)


try:
    supabase.create_client = lambda *a, **k: SimpleNamespace(table=lambda name: Query())
    st.file_uploader = uploader
    st.download_button = download
    runpy.run_path(str(root / "app.py"), run_name="__main__")
finally:
    supabase.create_client = original_client
    st.file_uploader = original_uploader
    st.download_button = original_download
