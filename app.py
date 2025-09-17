from flask import Flask, render_template, request, Response, send_file, redirect, url_for
import os
import requests
import pandas as pd
import io
import sqlite3
from datetime import datetime

app = Flask(__name__)

# API credentials
BASE_URL = os.environ.get("BASE_URL")
API_USER = os.environ.get("API_USER")
API_PASS = os.environ.get("API_PASS")

# Načtení zákazníků z env
CUSTOMERS = []
i = 1
while os.environ.get(f"CUSTOMER_{i}_USER"):
    CUSTOMERS.append({
        "user": os.environ.get(f"CUSTOMER_{i}_USER"),
        "pass": os.environ.get(f"CUSTOMER_{i}_PASS"),
        "code": os.environ.get(f"CUSTOMER_{i}_CODE")
    })
    i += 1

def get_customer(username):
    for cust in CUSTOMERS:
        if cust["user"] == username:
            return cust
    return None

def check_auth(username, password):
    cust = get_customer(username)
    return cust is not None and cust["pass"] == password

def authenticate():
    return Response('Přístup odepřen', 401,
                    {'WWW-Authenticate': 'Basic realm="Login"'})

@app.before_request
def require_auth():
    auth = request.authorization
    if not auth or not check_auth(auth.username, auth.password):
        return authenticate()

# -------------------------
# SQLite DB na komentáře
# -------------------------
DB_PATH = "comments.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            internal_id TEXT PRIMARY KEY,
            comment TEXT
        )
        """)

init_db()

def get_comment(internal_id):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT comment FROM comments WHERE internal_id=?", (internal_id,)).fetchone()
        return row[0] if row else ""

def save_comment(internal_id, comment):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT OR REPLACE INTO comments (internal_id, comment) VALUES (?, ?)", (internal_id, comment))


# -------------------------
# ROUTES
# -------------------------
@app.route("/")
def index():
    auth = request.authorization
    customer = get_customer(auth.username)
    if not customer:
        return authenticate()

    nazev_firmy_bez_data = customer["code"]
    today = datetime.today().strftime("%Y-%m-%d")

    # API dotaz
    url = "/banka/(zuctovano = False).csv?limit=0&detail=custom:banka,typPohybuK(showAs),cisSouhrnne,kod,popis,varSym,nazFirmy,datVyst,sumCelkem,sumCelkemMen,mena(showAs),buc,smerKod(showAs),zuctovano"
    response = requests.get(BASE_URL + nazev_firmy_bez_data + url, verify=False, auth=(API_USER, API_PASS))
    response.encoding = 'utf-8'

    if not response.text.strip():
        return "<h2>Žádná data k zobrazení</h2>"

    df = pd.read_csv(io.StringIO(response.text), encoding="utf-8")

    prehazeny_sloupce = [
        "banka",
        "typPohybuK@showAs",
        "cisSouhrnne",
        "kod",
        "popis",
        "varSym",
        "nazFirmy",
        "datVyst",
        "sumCelkem",
        "sumCelkemMen",
        "mena",
        "buc",
        "smerKod",
        "zuctovano"
    ]
    df = df[[col for col in prehazeny_sloupce if col in df.columns]]

    df.rename(columns={
        "banka": "Bank. účet",
        "typPohybuK@showAs": "Typ Pohybu",
        "cisSouhrnne": "Čís. výpisu",
        "kod": "Interní číslo",
        "popis": "Popis",
        "varSym": "Variabilní symbol",
        "nazFirmy": "Název Firmy nebo jméno osoby",
        "datVyst": "Vystaveno",
        "sumCelkem": "Celkem [Kč]",
        "sumCelkemMen": "Celkem [měna]",
        "mena": "Měna",
        "buc": "Číslo Bank. Účtu/Číslo karty",
        "smerKod": "Kód Banky",
        "zuctovano": "Zaúčtováno"
    }, inplace=True)

    df["Vystaveno"] = df["Vystaveno"].astype(str).str.replace(r'\+.*', '', regex=True)
    df['Vystaveno'] = pd.to_datetime(df['Vystaveno'], errors='coerce').dt.strftime('%d-%m-%Y')

    for col in ["Bank. účet", "Měna", "Kód Banky"]:
        df[col] = df[col].astype(str).str.replace("code:", "", regex=False).str.strip()

    # Převést na dict a doplnit komentáře
    records = df.to_dict(orient="records")
    for r in records:
        internal_id = r.get("Interní číslo")
        r["Komentář"] = get_comment(internal_id)

    columns = list(df.columns) + ["Komentář"]

    return render_template("index.html", data=records, columns=columns, date=today)


@app.route("/save_comments", methods=["POST"])
def save_comments():
    for key, value in request.form.items():
        if key.startswith("comment_"):
            internal_id = key.replace("comment_", "")
            save_comment(internal_id, value.strip())
    return redirect(url_for("index"))


# Excel export necháváme jak je (bez komentářů)
@app.route("/excel")
def download_excel():
    auth = request.authorization
    customer = get_customer(auth.username)
    if not customer:
        return authenticate()

    nazev_firmy_bez_data = customer["code"]
    today = datetime.today().strftime("%Y-%m-%d")
    url = "/banka/(zuctovano = False).csv?limit=0&detail=custom:banka,typPohybuK(showAs),cisSouhrnne,kod,popis,varSym,nazFirmy,datVyst,sumCelkem,sumCelkemMen,mena(showAs),buc,smerKod(showAs),zuctovano"
    response = requests.get(BASE_URL + nazev_firmy_bez_data + url, verify=False, auth=(API_USER, API_PASS))

    response.encoding = 'utf-8'
    df = pd.read_csv(io.StringIO(response.text), encoding="utf-8")

    prehazeny_sloupce = [
        "banka",
        "typPohybuK@showAs",
        "cisSouhrnne",
        "kod",
        "popis",
        "varSym",
        "nazFirmy",
        "datVyst",
        "sumCelkem",
        "sumCelkemMen",
        "mena",
        "buc",
        "smerKod",
        "zuctovano"
    ]
    df = df[[col for col in prehazeny_sloupce if col in df.columns]]

    df.rename(columns={
        "banka": "Bank. účet",
        "typPohybuK@showAs": "Typ Pohybu",
        "cisSouhrnne": "Čís. výpisu",
        "kod": "Interní číslo",
        "popis": "Popis",
        "varSym": "Variabilní symbol",
        "nazFirmy": "Název Firmy nebo jméno osoby",
        "datVyst": "Vystaveno",
        "sumCelkem": "Celkem [Kč]",
        "sumCelkemMen": "Celkem [měna]",
        "mena": "Měna",
        "buc": "Číslo Bank. Účtu/Číslo platební karty",
        "smerKod": "Kód Banky",
        "zuctovano": "Zaúčtováno"
    }, inplace=True)

    df["Vystaveno"] = df["Vystaveno"].astype(str).str.replace(r'\+.*', '', regex=True)
    df['Vystaveno'] = pd.to_datetime(df['Vystaveno'], errors='coerce').dt.strftime('%d-%m-%Y')

    for col in ["Bank. účet", "Měna", "Kód Banky"]:
        df[col] = df[col].astype(str).str.replace("code:", "", regex=False).str.strip()

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Data')

        worksheet = writer.sheets['Data']
        for i, col in enumerate(df.columns):
            max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
            worksheet.set_column(i, i, max_len)

        row_count, col_count = df.shape
        worksheet.autofilter(0, 0, row_count, col_count - 1)

    output.seek(0)

    return send_file(output, as_attachment=True, download_name=f"{nazev_firmy_bez_data}_{today}.xlsx")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
