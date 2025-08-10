from flask import Flask, render_template
import requests
import pandas as pd
from io import StringIO
import os

app = Flask(__name__)

# Přístupové údaje z Environment Variables na Renderu
BASE_URL = os.environ.get("ABRA_BASE_URL")
COMPANY = os.environ.get("ABRA_COMPANY")
AUTH_USER = os.environ.get("ABRA_USER")
AUTH_PASS = os.environ.get("ABRA_PASS")

@app.route("/")
def index():
    url = "/banka/(zuctovano=false).csv?limit=0&detail=custom:banka(showAs),typPohybuK(showAs),popis,sumCelkem,zuctovano"
    response = requests.get(
        BASE_URL + COMPANY + url,
        auth=(AUTH_USER, AUTH_PASS),
        verify=False
    )
    df = pd.read_csv(StringIO(response.text))
    return render_template("index.html", tables=[df.to_html(classes='data', index=False, escape=False)])
