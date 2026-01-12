# -*- coding: utf-8 -*-
import os
import unicodedata
import uuid
import logging
import pandas as pd
from flask import (
    Flask, render_template, request,
    send_file, url_for
)

# ======================================================
# CONFIGURAÇÃO GERAL
# ======================================================
app = Flask(__name__)
app.secret_key = "chave-super-segura"

# Limite de upload (20MB)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

# Logs (ESSENCIAL EM PRODUÇÃO)
logging.basicConfig(level=logging.INFO)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ======================================================
# HELPERS
# ======================================================
def normalize(text: str) -> str:
    base = unicodedata.normalize("NFKD", str(text))
    base = "".join(c for c in base if not unicodedata.combining(c))
    return base.lower().strip()


def read_any(path: str) -> pd.DataFrame:
    """
    Leitura segura para produção (CSV / Excel)
    """
    ext = os.path.splitext(path)[1].lower()

    if ext in [".xlsx", ".xls"]:
        return pd.read_excel(path, engine="openpyxl")

    # CSV – tentativa controlada
    try:
        return pd.read_csv(
            path,
            sep=";",
            encoding="latin1",
            low_memory=False
        )
    except:
        return pd.read_csv(
            path,
            sep=",",
            encoding="latin1",
            low_memory=False
        )


# ======================================================
# PROCESSAMENTO
# ======================================================
def explode_safe(df, col):
    df[col] = df[col].fillna("").astype(str)
    df[col] = df[col].apply(
        lambda x: [i.strip() for i in x.split(",")] if "," in x else [x]
    )
    return df.explode(col)


def process_base(df: pd.DataFrame, tipo="CNPJ") -> pd.DataFrame:
    """
    Processamento genérico para CNPJ e CPF
    """
    colmap = {normalize(c): c for c in df.columns}

    col_grupo = next(
        (v for k, v in colmap.items() if "grupo" in k and "serv" in k),
        None
    )
    col_area = next(
        (v for k, v in colmap.items() if "area" in k and "primar" in k),
        None
    )

    if not col_grupo or not col_area:
        raise ValueError(f"Colunas obrigatórias não encontradas ({tipo}).")

    # Limpeza inicial
    df = df[[col_grupo, col_area]].copy()
    df[col_grupo] = df[col_grupo].astype(str).str.strip('"')
    df[col_area] = df[col_area].astype(str).str.strip('"')

    # Remover vazios antes do explode (EVITA ESTOURO)
    df = df[
        (df[col_grupo] != "") &
        (df[col_area] != "")
    ]

    if len(df) > 200_000:
        raise ValueError("Planilha muito grande para processamento online.")

    # Explode controlado
    df = explode_safe(df, col_grupo)
    df = explode_safe(df, col_area)

    return df


# ======================================================
# ROTAS
# ======================================================
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

    # ------------------- CNPJ -------------------
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
            df_out = process_base(df, "CNPJ")

            result = f"cnpj_out_{uuid.uuid4().hex}.csv"
            result_path = os.path.join(OUTPUT_DIR, result)
            df_out.to_csv(result_path, index=False)

            context["preview_cnpj"] = (
                df_out.head(30)
                .astype(str)
                .to_html(
                    classes="table table-striped table-sm table-hover",
                    index=False,
                    escape=False
                )
            )
            context["download_cnpj"] = url_for(
                "download_file", filename=result
            )

        except Exception as e:
            app.logger.error(f"Erro CNPJ: {e}", exc_info=True)
            context["error_cnpj"] = "Erro ao processar a planilha de CNPJ."

    # ------------------- CPF -------------------
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
            df_out = process_base(df, "CPF")

            result = f"cpf_out_{uuid.uuid4().hex}.csv"
            result_path = os.path.join(OUTPUT_DIR, result)
            df_out.to_csv(result_path, index=False)

            context["preview_cpf"] = (
                df_out.head(30)
                .astype(str)
                .to_html(
                    classes="table table-striped table-sm table-hover",
                    index=False,
                    escape=False
                )
            )
            context["download_cpf"] = url_for(
                "download_file", filename=result
            )

        except Exception as e:
            app.logger.error(f"Erro CPF: {e}", exc_info=True)
            context["error_cpf"] = "Erro ao processar a planilha de CPF."

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


# ======================================================
# ERROS
# ======================================================
@app.errorhandler(413)
def file_too_large(e):
    return "Arquivo muito grande. Limite de 20MB.", 413


# ======================================================
# START
# ======================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
