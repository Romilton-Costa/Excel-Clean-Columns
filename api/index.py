from flask import Flask, request, jsonify, send_file, render_template
import pandas as pd
import os
from werkzeug.utils import secure_filename
from flask_cors import CORS

app = Flask(__name__, template_folder="../templates")
CORS(app)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

SESSION = {
    "df": None,
    "filename": None,
    "colunas_processadas": []
}


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"erro": "Nenhum arquivo enviado"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"erro": "Nome de arquivo vazio"}), 400

    filename = secure_filename(file.filename)
    path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(path)

    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(path, encoding="utf-8")
        else:
            df = pd.read_excel(path)
    except Exception as e:
        return jsonify({"erro": f"Erro ao ler arquivo: {str(e)}"}), 400

    SESSION["df"] = df
    SESSION["filename"] = filename
    SESSION["colunas_processadas"] = []

    return jsonify({
        "colunas": list(df.columns),
        "total_linhas": len(df),
        "filename": filename
    })


@app.route("/preview", methods=["GET"])
def preview():
    df = SESSION.get("df")
    if df is None:
        return jsonify({"erro": "Sem arquivo carregado"}), 400

    preview_df = df.head(5).fillna("").astype(str)
    return jsonify({
        "colunas": list(df.columns),
        "linhas": preview_df.values.tolist()
    })


@app.route("/processar", methods=["POST"])
def processar():
    df = SESSION.get("df")

    if df is None:
        return jsonify({"erro": "Sem arquivo carregado. Envie um arquivo primeiro."}), 400

    coluna = request.json.get("coluna")

    if not coluna:
        return jsonify({"erro": "Coluna não informada"}), 400

    if coluna not in df.columns:
        return jsonify({"erro": f"Coluna '{coluna}' não encontrada no arquivo"}), 400

    if coluna in SESSION["colunas_processadas"]:
        return jsonify({"aviso": f"Coluna '{coluna}' já foi processada anteriormente", "ok": True})

    total_antes = df[coluna].notna().sum()
    vistos = set()

    def limpar(v):
        if pd.isna(v):
            return v
        if v in vistos:
            return ""
        vistos.add(v)
        return v

    df[coluna] = df[coluna].apply(limpar)
    SESSION["df"] = df
    SESSION["colunas_processadas"].append(coluna)

    duplicatas_removidas = total_antes - df[coluna].replace("", pd.NA).notna().sum()

    return jsonify({
        "ok": True,
        "coluna": coluna,
        "duplicatas_removidas": int(duplicatas_removidas),
        "colunas_processadas": SESSION["colunas_processadas"]
    })


@app.route("/status", methods=["GET"])
def status():
    df = SESSION.get("df")
    if df is None:
        return jsonify({"carregado": False})

    return jsonify({
        "carregado": True,
        "filename": SESSION.get("filename"),
        "total_linhas": len(df),
        "colunas": list(df.columns),
        "colunas_processadas": SESSION["colunas_processadas"]
    })


@app.route("/remover_vazios", methods=["POST"])
def remover_vazios():
    df = SESSION.get("df")

    if df is None:
        return jsonify({"erro": "Sem arquivo carregado. Envie um arquivo primeiro."}), 400

    dados = request.json or {}
    colunas = dados.get("colunas")  # lista de colunas para checar, ou None = todas

    linhas_antes = len(df)

    if colunas:
        # Remove linhas onde TODAS as colunas especificadas estão vazias
        colunas_validas = [c for c in colunas if c in df.columns]
        if not colunas_validas:
            return jsonify({"erro": "Nenhuma coluna válida informada"}), 400
        mask = df[colunas_validas].replace("", pd.NA).isna().all(axis=1)
    else:
        # Remove linhas onde TODAS as colunas estão vazias
        mask = df.replace("", pd.NA).isna().all(axis=1)

    df = df[~mask].reset_index(drop=True)
    SESSION["df"] = df

    linhas_removidas = linhas_antes - len(df)

    return jsonify({
        "ok": True,
        "linhas_removidas": linhas_removidas,
        "linhas_restantes": len(df)
    })


@app.route("/reset", methods=["POST"])
def reset():
    SESSION["df"] = None
    SESSION["filename"] = None
    SESSION["colunas_processadas"] = []
    return jsonify({"ok": True})


@app.route("/finalizar")
def finalizar():
    df = SESSION.get("df")

    if df is None:
        return jsonify({"erro": "Nenhum arquivo carregado ou sessão expirada. Envie o arquivo novamente."}), 400

    output = os.path.join(UPLOAD_FOLDER, "resultado.xlsx")

    try:
        df.to_excel(output, index=False)
    except Exception as e:
        return jsonify({"erro": f"Erro ao gerar arquivo: {str(e)}"}), 500

    return send_file(output, as_attachment=True, download_name="resultado_limpo.xlsx")


if __name__ == "__main__":
    app.run(debug=True, port=8080)