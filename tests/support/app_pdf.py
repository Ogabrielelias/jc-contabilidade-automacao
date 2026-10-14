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
    if kwargs.get("key") == "pdf_funcionarios":
        path = next(root.glob("Buffon*.pdf"))
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
