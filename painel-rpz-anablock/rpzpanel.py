from flask import Flask, render_template, request, redirect, send_file, session, url_for
import os
import csv
from reportlab.pdfgen import canvas
from io import BytesIO
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'NavegaPainelSecret2024'

ZONE_FILE = '/var/cache/bind/rpz/db.rpz.zone'
BIND_RELOAD_CMD = 'rndc reload'
CNAME_TARGET = 'aviso.hostrios.com.br.'

LOGIN_USER = 'admin'
LOGIN_PASS = 'Navega@123##'

def read_zone_blocks():
    if not os.path.exists(ZONE_FILE):
        return [], []

    with open(ZONE_FILE, 'r') as f:
        lines = f.readlines()

    manual_block = []
    api_block = []
    current = None

    for line in lines:
        if '==== DOMINIOS MANUAIS ====' in line:
            current = 'manual'
            continue
        elif '==== DOMINIOS DA API ANABLOCK ====' in line:
            current = 'api'
            continue

        if current == 'manual' and '.rpz.zone.' in line and 'CNAME' in line:
            domain = line.strip().split()[0].replace('.rpz.zone.', '').replace('*.', '')
            manual_block.append(domain)
        elif current == 'api' and '.rpz.zone.' in line and 'CNAME' in line:
            domain = line.strip().split()[0].replace('.rpz.zone.', '').replace('*.', '')
            api_block.append(domain)

    return sorted(set(manual_block)), sorted(set(api_block))

def write_zone_file(manual_domains, api_domains):
    header = f"""$TTL 1H
@       IN      SOA localhost. {CNAME_TARGET} (
                {datetime.now().strftime('%Y%m%d%H')} ; Serial
                1h              ; Refresh
                15m             ; Retry
                30d             ; Expire
                2h              ; Negative Cache TTL
)
        NS  {CNAME_TARGET}

; ==== DOMINIOS MANUAIS ====
"""
    manual_block = ''.join([
        f"{d}.rpz.zone.    IN CNAME {CNAME_TARGET}\n*.{d}.rpz.zone.    IN CNAME {CNAME_TARGET}\n"
        for d in sorted(set(manual_domains))
    ])

    api_block = '; ==== DOMINIOS DA API ANABLOCK ====\n' + ''.join([
        f"{d}.rpz.zone.    IN CNAME {CNAME_TARGET}\n*.{d}.rpz.zone.    IN CNAME {CNAME_TARGET}\n"
        for d in sorted(set(api_domains))
    ])

    with open(ZONE_FILE, 'w') as f:
        f.write(header + manual_block + api_block)

    os.system(BIND_RELOAD_CMD)

@app.route('/', methods=['GET'])
def index():
    if not session.get("logged_in"):
        return redirect(url_for('login'))
    manual, api = read_zone_blocks()
    return render_template("index.html", manual=manual, api=api)

@app.route('/add', methods=['POST'])
def add_domain():
    if not session.get("logged_in"):
        return redirect(url_for('login'))
    new = request.form.get("domain", "").strip().lower()
    manual, api = read_zone_blocks()
    if new and new not in manual and new not in api:
        manual.append(new)
        write_zone_file(manual, api)
    return redirect('/')

@app.route('/remove', methods=['POST'])
def remove_domain():
    if not session.get("logged_in"):
        return redirect(url_for('login'))
    target = request.form.get("domain")
    manual, api = read_zone_blocks()
    if target in manual:
        manual.remove(target)
        write_zone_file(manual, api)
    return redirect('/')

@app.route('/export/csv')
def export_csv():
    if not session.get("logged_in"):
        return redirect(url_for('login'))
    manual, _ = read_zone_blocks()
    si = BytesIO()
    cw = csv.writer(si)
    cw.writerow(['dominio'])
    for d in manual:
        cw.writerow([d])
    si.seek(0)
    return send_file(si, mimetype='text/csv', download_name='rpz_lista.csv', as_attachment=True)

@app.route('/export/pdf')
def export_pdf():
    if not session.get("logged_in"):
        return redirect(url_for('login'))
    manual, _ = read_zone_blocks()
    buffer = BytesIO()
    c = canvas.Canvas(buffer)
    c.drawString(50, 800, "Domínios Manuais RPZ")
    y = 780
    for d in manual:
        c.drawString(50, y, d)
        y -= 15
        if y < 50:
            c.showPage()
            y = 800
    c.save()
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf', download_name='rpz_lista.pdf', as_attachment=True)

@app.route('/import', methods=['POST'])
def import_csv():
    if not session.get("logged_in"):
        return redirect(url_for('login'))
    file = request.files['csvfile']
    if file:
        lines = file.read().decode('utf-8').splitlines()
        reader = csv.DictReader(lines)
        manual, api = read_zone_blocks()
        for row in reader:
            d = row.get('dominio', '').strip().lower()
            if d and d not in manual and d not in api:
                manual.append(d)
        write_zone_file(manual, api)
    return redirect('/')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form.get("username")
        p = request.form.get("password")
        if u == LOGIN_USER and p == LOGIN_PASS:
            session["logged_in"] = True
            return redirect('/')
    return render_template("login.html")

@app.route('/logout')
def logout():
    session["logged_in"] = False
    return redirect('/login')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
