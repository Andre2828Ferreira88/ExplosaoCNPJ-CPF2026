# app.py
# -*- coding: utf-8 -*-
import os
import unicodedata
import uuid
import pandas as pd
from flask import Flask, render_template, request, send_file, url_for

# ---------------- CONFIGURAÇÃO ----------------
app = Flask(__name__)
app.secret_key = "chave-super-segura"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ---------------- HELPERS ----------------
def normalize(text: str) -> str:
    base = unicodedata.normalize("NFKD", str(text))
    base = "".join(c for c in base if not unicodedata.combining(c))
    return base.lower().strip()


def read_any(path: str) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()

    if ext in [".xlsx", ".xls"]:
        try:
            return pd.read_excel(path)
        except:
            return pd.read_excel(path, engine="openpyxl")

    for enc in ["utf-8-sig", "latin1", "cp1252"]:
        try:
            return pd.read_csv(path, sep=None, engine="python", encoding=enc)
        except:
            continue

    return pd.read_csv(path, sep=";", encoding="latin1")


# ---------------- PROCESSAMENTO ----------------
def process_cnpj(df: pd.DataFrame) -> pd.DataFrame:
    """
    Explodir:
    - Grupo de serviços
    - Áreas primárias
    """
    colmap = {normalize(c): c for c in df.columns}

    col_grupo = next((v for k, v in colmap.items() if "grupo" in k and "serv" in k), None)
    col_area = next((v for k, v in colmap.items() if "area" in k and "primar" in k), None)

    if col_grupo is None or col_area is None:
        raise ValueError("As colunas de CNPJ não foram encontradas.")

    df[col_grupo] = df[col_grupo].astype(str).str.strip('"')
    df[col_area] = df[col_area].astype(str).str.strip('"')

    df[col_grupo] = df[col_grupo].apply(lambda x: [i.strip() for i in str(x).split(",")] if "," in str(x) else [x])
    df[col_area] = df[col_area].apply(lambda x: [i.strip() for i in str(x).split(",")] if "," in str(x) else [x])

    df = df.explode(col_grupo)
    df = df.explode(col_area)

    return df


def process_cpf(df: pd.DataFrame) -> pd.DataFrame:
    """
    Explodir:
    - Grupo de serviço
    - Área primária
    """
    colmap = {normalize(c): c for c in df.columns}

    col_grupo = next((v for k, v in colmap.items() if "grupo" in k and "serv" in k), None)
    col_area = next((v for k, v in colmap.items() if "area" in k and "primar" in k), None)

    if col_grupo is None or col_area is None:
        raise ValueError("As colunas de CPF não foram encontradas.")

    df[col_grupo] = df[col_grupo].astype(str).str.strip('"')
    df[col_area] = df[col_area].astype(str).str.strip('"')

    df[col_grupo] = df[col_grupo].apply(lambda x: [i.strip() for i in str(x).split(",")] if "," in str(x) else [x])
    df[col_area] = df[col_area].apply(lambda x: [i.strip() for i in str(x).split(",")] if "," in str(x) else [x])

    df = df.explode(col_grupo)
    df = df.explode(col_area)

    return df


# ---------------- ROTAS ----------------
@app.route("/", methods=["GET", "POST"])
def index():
    context = {
        "preview_cnpj": None,
        "preview_cpf": None,
        "download_cnpj": None,
        "download_cpf": None,
        "error_cnpj": None,
        "error_cpf": None,
    }

    # ------------------- PROCESSAR CNPJ -------------------
    if "upload_cnpj" in request.form:
        file = request.files.get("file_cnpj")
        if not file or file.filename == "":
            context["error_cnpj"] = "Nenhum arquivo enviado para CNPJ."
            return render_template("index.html", **context)

        ext = os.path.splitext(file.filename)[1]
        path = os.path.join(UPLOAD_DIR, f"cnpj_{uuid.uuid4().hex}{ext}")
        file.save(path)

        try:
            df = read_any(path)
            df_out = process_cnpj(df)

            result = f"cnpj_out_{uuid.uuid4().hex}.csv"
            result_path = os.path.join(OUTPUT_DIR, result)
            df_out.to_csv(result_path, index=False)

            context["preview_cnpj"] = df_out.head(30).to_html(
                classes="table table-striped table-sm table-hover",
                index=False,
            )
            context["download_cnpj"] = url_for("download_file", filename=result)

        except Exception as e:
            context["error_cnpj"] = str(e)

    # ------------------- PROCESSAR CPF -------------------
    if "upload_cpf" in request.form:
        file = request.files.get("file_cpf")
        if not file or file.filename == "":
            context["error_cpf"] = "Nenhum arquivo enviado para CPF."
            return render_template("index.html", **context)

        ext = os.path.splitext(file.filename)[1]
        path = os.path.join(UPLOAD_DIR, f"cpf_{uuid.uuid4().hex}{ext}")
        file.save(path)

        try:
            df = read_any(path)
            df_out = process_cpf(df)

            result = f"cpf_out_{uuid.uuid4().hex}.csv"
            result_path = os.path.join(OUTPUT_DIR, result)
            df_out.to_csv(result_path, index=False)

            context["preview_cpf"] = df_out.head(30).to_html(
                classes="table table-striped table-sm table-hover",
                index=False,
            )
            context["download_cpf"] = url_for("download_file", filename=result)

        except Exception as e:
            context["error_cpf"] = str(e)

    return render_template("index.html", **context)


@app.route("/download/<filename>")
def download_file(filename):
    path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(path):
        return "Arquivo não encontrado.", 404

    return send_file(
        path,
        as_attachment=True,
        download_name=filename,
        mimetype="text/csv",
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
