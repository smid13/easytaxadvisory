from flask import Flask, render_template, request, Response, send_file, redirect, url_for
import os
import requests
import pandas as pd
import io
import sqlite3
from datetime import datetime

app = Flask(__name__)

# SQLite databáze pro komentáře
DB_PATH = "comments.db"
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            record_id TEXT PRIMARY KEY,
            comment TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

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

def get_comment(record_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT comment FROM comments WHERE record_id = ?", (record_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else ""

def save_comment(record_id, comment):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO comments (record_id, comment) VALUES (?, ?)",
              (record_id, comment))
    conn.commit()
    conn.close()

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

    # Přidání komentářů
    records = df.to_dict(orient="records")
    for rec in records:
        rec["Komentář"] = get_comment(rec["Interní číslo"])

    columns = list(df.columns) + ["Komentář"]

    return render_template("index.html", data=records, columns=columns, date=today)

@app.route("/save_comment", methods=["POST"])
def save_comment_route():
    record_id = request.form["record_id"]
    comment = request.form["comment"]
    save_comment(record_id, comment)
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
