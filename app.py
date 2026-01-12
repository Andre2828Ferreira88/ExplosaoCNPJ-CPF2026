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
    Leitura segura para CSV / Excel
    Detecta automaticamente o separador correto
    """

    ext = os.path.splitext(path)[1].lower()

    # Excel
    if ext in [".xlsx", ".xls"]:
        return pd.read_excel(path, engine="openpyxl")

    # CSV - tenta separadores comuns
    for sep in [";", ",", "\t"]:
        try:
            df = pd.read_csv(
                path,
                sep=sep,
                encoding="UTF-8",
                low_memory=False
            )

            # Se só veio uma coluna, o separador está errado
            if df.shape[1] == 1:
                continue

            return df
        except Exception:
            continue

    raise ValueError(
        "Não foi possível identificar o separador do CSV. "
        "Verifique o arquivo."
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


def find_column(colmap, keywords):
    for k, v in colmap.items():
        if all(word in k for word in keywords):
            return v
    return None


def process_base(df: pd.DataFrame, tipo="CNPJ") -> pd.DataFrame:
    """
    Processamento com colunas FIXAS (Leroy Merlin)
    """

    if tipo == "CNPJ":
        col_grupo = "Grupo de serviços"
    elif tipo == "CPF":
        col_grupo = "Grupo de servico"
    else:
        raise ValueError("Tipo inválido. Use CNPJ ou CPF.")

    col_area = "Áreas primárias"

    # Validação dura (erro claro)
    for col in [col_grupo, col_area]:
        if col not in df.columns:
            raise ValueError(
                f"Coluna obrigatória não encontrada: '{col}'. "
                f"Colunas disponíveis: {list(df.columns)}"
            )

    # Trabalhar só com as colunas necessárias
    # Colunas extras fixas
    col_nome = "Nome fantasia"
    col_id = "CNPJ" if tipo == "CNPJ" else "CPF"

    # Validação das colunas extras
    for col in [col_nome, col_id]:
        if col not in df.columns:
            raise ValueError(
                f"Coluna obrigatória não encontrada: '{col}'. "
                f"Colunas disponíveis: {list(df.columns)}"
            )

    # Manter todas as colunas necessárias
    df = df[[col_id, col_nome, col_grupo, col_area]].copy()


    df[col_grupo] = (
        df[col_grupo]
        .fillna("")
        .astype(str)
        .str.strip('"')
    )

    df[col_area] = (
        df[col_area]
        .fillna("")
        .astype(str)
        .str.strip('"')
    )

    # Remove linhas vazias
    df = df[
        (df[col_grupo] != "") &
        (df[col_area] != "")
    ]

    if len(df) > 200_000:
        raise ValueError("Planilha muito grande para processamento online.")

    # Explode
    df[col_grupo] = df[col_grupo].apply(
        lambda x: [i.strip() for i in x.split(",")] if "," in x else [x]
    )

    df[col_area] = df[col_area].apply(
        lambda x: [i.strip() for i in x.split(",")] if "," in x else [x]
    )

    df = df.explode(col_grupo)
    df = df.explode(col_area)

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
