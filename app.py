from flask import Flask, jsonify, render_template, request, send_file
import sqlite3
from datetime import datetime, timedelta
import os
from twilio.rest import Client
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

app = Flask(__name__)

# ================= DATABASE =================
DB_PATH = "attendance.db"

# ================= TWILIO ==================
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH = os.getenv("TWILIO_AUTH")

TWILIO_WHATSAPP_NUMBER = "whatsapp:+14155238886"
HR_NUMBER = "whatsapp:+918870350032"

BASE_URL = "https://qr-attendance-2-robt.onrender.com"
LIVE_LINK = BASE_URL + "/attendance"
PDF_LINK = BASE_URL + "/daily_pdf"

# ================= TIME (IST) =================
def ist_time():
    return datetime.utcnow() + timedelta(hours=5, minutes=30)

# ================= DB INIT =================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS employees(
        employee_id TEXT PRIMARY KEY,
        name TEXT,
        role TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS attendance(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id TEXT,
        date TEXT,
        in_time TEXT,
        out_time TEXT
    )
    """)

    cur.execute("""
    INSERT OR IGNORE INTO employees VALUES
    ('EMP101','Santhosh','Intern'),
    ('EMP102','Barani','Staff')
    """)

    conn.commit()
    conn.close()

init_db()

# ================= ATTENDANCE =================
def mark_attendance(emp_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    emp_id = emp_id.upper().strip()
    cur.execute("SELECT name, role FROM employees WHERE employee_id=?", (emp_id,))
    emp = cur.fetchone()

    if not emp:
        conn.close()
        return None, None, "Employee not registered"

    name, role = emp
    IST = ist_time()
    today = IST.strftime("%Y-%m-%d")
    now = IST.strftime("%H:%M:%S")

    cur.execute("""
        SELECT id, in_time, out_time FROM attendance
        WHERE employee_id=? AND date=?
    """, (emp_id, today))

    row = cur.fetchone()

    if row is None:
        cur.execute("""
            INSERT INTO attendance(employee_id, date, in_time)
            VALUES(?,?,?)
        """, (emp_id, today, now))
        status = "IN marked"

    elif row[1] and row[2] is None:
        cur.execute("""
            UPDATE attendance SET out_time=? WHERE id=?
        """, (now, row[0]))
        status = "OUT marked"
    else:
        status = "Attendance completed"

    conn.commit()
    conn.close()
    return name, role, status

# ================= ROUTES =================
@app.route("/")
def kiosk():
    return render_template("kiosk.html")

@app.route("/mark", methods=["POST"])
def mark():
    emp_id = request.json.get("employee_id", "")
    name, role, status = mark_attendance(emp_id)
    if name is None:
        return jsonify({"error": status})
    return jsonify({"name": name, "role": role, "status": status})

@app.route("/attendance")
def attendance_view():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT a.employee_id, e.name, a.date, a.in_time, a.out_time
        FROM attendance a
        JOIN employees e ON a.employee_id = e.employee_id
        ORDER BY a.date DESC, a.in_time DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return render_template("attendance.html", records=rows)

# ================= PDF =================
def generate_pdf():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT a.employee_id, e.name, a.in_time, a.out_time
        FROM attendance a
        JOIN employees e ON a.employee_id=e.employee_id
        WHERE a.date = DATE('now')
    """)
    rows = cur.fetchall()
    conn.close()

    file_name = "daily_attendance.pdf"
    c = canvas.Canvas(file_name, pagesize=A4)
    width, height = A4

    y = height - 40
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, "Daily Attendance Summary")
    y -= 30
    c.setFont("Helvetica", 11)

    for r in rows:
        c.drawString(40, y, f"{r[0]} | {r[1]} | {r[2]} | {r[3]}")
        y -= 18
        if y < 40:
            c.showPage()
            y = height - 40

    c.save()
    return file_name

@app.route("/daily_pdf")
def daily_pdf():
    generate_pdf()
    return send_file("daily_attendance.pdf", as_attachment=False)

# ================= WHATSAPP =================
def send_live_link():
    Client(TWILIO_SID, TWILIO_AUTH).messages.create(
        from_=TWILIO_WHATSAPP_NUMBER,
        to=HR_NUMBER,
        body=f"Good Morning HR 👋\nLive Attendance:\n{LIVE_LINK}"
    )

def send_pdf():
    generate_pdf()
    Client(TWILIO_SID, TWILIO_AUTH).messages.create(
        from_=TWILIO_WHATSAPP_NUMBER,
        to=HR_NUMBER,
        body="Today's Attendance Summary PDF 📄",
        media_url=[PDF_LINK]
    )

# ================= CRON ROUTES =================
@app.route("/cron/send_link")
def cron_send_link():
    send_live_link()
    return "Morning WhatsApp link sent", 200

@app.route("/cron/send_pdf")
def cron_send_pdf():
    send_pdf()
    return "Evening PDF sent", 200

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
