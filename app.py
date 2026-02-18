from flask import Flask, render_template, request, redirect, session
import sqlite3
from datetime import datetime
from twilio.rest import Client
import pandas as pd
import os

app = Flask(__name__)
app.secret_key = "weavetrust_secret"

# ---------------- TWILIO CONFIG ----------------
#TWILIO_SID = "yours"
#TWILIO_AUTH = "ypurs"
TWILIO_NUMBER = "whatsapp:+14155238886"

client = Client(TWILIO_SID, TWILIO_AUTH)

# ---------------- DB HELPER ----------------
def get_db():
    conn = sqlite3.connect("weavetrust.db", timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# ---------------- HOME ----------------
@app.route("/")
def home():
    return render_template("splash.html")

# ---------------- SIGNUP ----------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        db = get_db()
        db.execute("""
            INSERT INTO users(username,password,role,phone)
            VALUES (?,?,?,?)
        """, (
            request.form["username"],
            request.form["password"],
            request.form["role"],
            request.form["phone"]
        ))
        db.commit()
        db.close()
        return redirect("/login")
    return render_template("signup.html")

# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        db = get_db()
        user = db.execute("""
            SELECT * FROM users
            WHERE username=? AND password=?
        """, (
            request.form["username"],
            request.form["password"]
        )).fetchone()
        db.close()

        if user:
            session["user"] = user["username"]
            session["role"] = user["role"]
            return redirect("/dashboard")

    return render_template("login.html")

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/login")
    return redirect("/owner" if session["role"]=="owner" else "/weaver")

# =====================================================
# ================= OWNER =============================
# =====================================================
@app.route("/owner", methods=["GET","POST"])
def owner():
    if "user" not in session:
        return redirect("/login")

    db = get_db()

    if request.method == "POST":
        weaver = request.form["weaver"]
        cloth = request.form["cloth"]
        meters = int(request.form["meters"])
        rate = int(request.form["rate"])

        db.execute("""
            INSERT INTO orders(owner,weaver,cloth,meters,produced,rate,status)
            VALUES (?,?,?,?,?,?,?)
        """, (
            session["user"],
            weaver,
            cloth,
            meters,
            0,
            rate,
            "Assigned"
        ))
        db.commit()

        weaver_user = db.execute("""
            SELECT phone FROM users
            WHERE username=? AND role='weaver'
        """, (weaver,)).fetchone()

        if weaver_user and weaver_user["phone"]:
            try:
                client.messages.create(
                    body=f"""🧵 New Order Assigned

Owner: {session['user']}
Cloth: {cloth}
Total Meters: {meters}
Rate: ₹{rate}/m""",
                    from_=TWILIO_NUMBER,
                    to=f"whatsapp:{weaver_user['phone']}"
                )
            except Exception as e:
                print("Twilio Assign Error:", e)

    search = request.args.get("q", "").strip()

    if search:
        weavers = db.execute("""
            SELECT 
                o.weaver,
                u.phone,
                MAX(CASE WHEN o.status!='Completed' THEN 1 ELSE 0 END) AS active
            FROM orders o
            LEFT JOIN users u ON o.weaver = u.username
            WHERE o.owner=?
              AND (o.weaver LIKE ? OR u.phone LIKE ?)
            GROUP BY o.weaver, u.phone
            ORDER BY active DESC, o.weaver
        """, (
            session["user"],
            f"%{search}%",
            f"%{search}%"
        )).fetchall()
    else:
        weavers = db.execute("""
            SELECT 
                o.weaver,
                u.phone,
                MAX(CASE WHEN o.status!='Completed' THEN 1 ELSE 0 END) AS active
            FROM orders o
            LEFT JOIN users u ON o.weaver = u.username
            WHERE o.owner=?
            GROUP BY o.weaver, u.phone
            ORDER BY active DESC, o.weaver
        """, (session["user"],)).fetchall()

    db.close()
    return render_template("owner.html", weavers=weavers)

# =====================================================
# ================= WEAVER ============================
# =====================================================
@app.route("/weaver")
def weaver():
    if "user" not in session:
        return redirect("/login")

    db = get_db()
    owners = db.execute("""
        SELECT DISTINCT owner
        FROM orders
        WHERE weaver=?
    """,(session["user"],)).fetchall()
    db.close()

    return render_template("weaver.html", owners=owners)
# ---------------- OWNER → WEAVER ORDERS ----------------
@app.route("/owner/weaver/<weaver_name>")
def owner_weaver_orders(weaver_name):
    if "user" not in session:
        return redirect("/login")

    db = get_db()
    owner = session["user"]

    orders = db.execute("""
        SELECT * FROM orders
        WHERE owner=? AND weaver=?
    """, (owner, weaver_name)).fetchall()

    # 🔹 Performance data (FIXED)
    performance_rows = db.execute("""
        SELECT h.date, SUM(h.meters) AS total
        FROM history h
        JOIN orders o ON h.order_id = o.id
        WHERE o.owner=? AND o.weaver=?
        GROUP BY h.date
        ORDER BY h.date
    """, (owner, weaver_name)).fetchall()

    performance = [
        {"date": row["date"], "total": row["total"]}
        for row in performance_rows
    ]

    db.close()

    return render_template(
        "owner_weaver_orders.html",
        weaver_name=weaver_name,
        orders=orders,
        performance=performance
    )
# ---------------- WEAVER → OWNER PAGE ----------------
@app.route("/weaver/owner/<owner_name>", methods=["GET","POST"])
def weaver_owner_orders(owner_name):
    if "user" not in session:
        return redirect("/login")

    db = get_db()
    username = session["user"]

    if request.method == "POST":
        oid = request.form["order_id"]
        meters = int(request.form["meters"])

        order = db.execute("""
            SELECT * FROM orders
            WHERE id=? AND weaver=?
        """,(oid, username)).fetchone()

        if order:
            remaining = order["meters"] - order["produced"]
            add = min(meters, remaining)

            if add > 0:
                db.execute("""
                    UPDATE orders
                    SET produced = produced + ?
                    WHERE id=?
                """,(add, oid))

                db.execute("""
                    INSERT INTO history(order_id,weaver,meters,date)
                    VALUES (?,?,?,?)
                """,(oid, username, add,
                    datetime.now().strftime("%d-%m-%Y")))
                db.commit()

                new_total = order["produced"] + add

                if new_total >= order["meters"]:
                    db.execute("""
                        UPDATE orders
                        SET status='Completed'
                        WHERE id=?
                    """,(oid,))
                    db.commit()

                    owner_phone = db.execute("""
                        SELECT phone FROM users WHERE username=?
                    """,(order["owner"],)).fetchone()

                    if owner_phone and owner_phone["phone"]:
                        try:
                            client.messages.create(
                                body=f"""✅ Order Completed

Order ID: {oid}
Cloth: {order['cloth']}
Weaver: {username}
Total: {order['meters']}m""",
                                from_=TWILIO_NUMBER,
                                to=f"whatsapp:{owner_phone['phone']}"
                            )
                        except Exception as e:
                            print("Twilio (Complete) Error:", e)

                    history_data = db.execute("""
                        SELECT h.date, h.meters, o.cloth
                        FROM history h
                        JOIN orders o ON h.order_id=o.id
                        WHERE h.order_id=?
                    """,(oid,)).fetchall()

                    df = pd.DataFrame(
                        history_data,
                        columns=["Date","Meters Added","Cloth"]
                    )

                    os.makedirs("reports", exist_ok=True)
                    df.to_excel(f"reports/order_{oid}.xlsx", index=False)

                    db.execute("DELETE FROM history WHERE order_id=?", (oid,))
                    db.commit()

    orders = db.execute("""
        SELECT * FROM orders
        WHERE weaver=? AND owner=?
    """,(username, owner_name)).fetchall()

    history = db.execute("""
        SELECT h.date, h.meters,
               o.id AS order_id,
               o.cloth
        FROM history h
        JOIN orders o ON h.order_id=o.id
        WHERE o.weaver=? AND o.owner=?
        ORDER BY h.id DESC
    """,(username, owner_name)).fetchall()

    # ================= PERFORMANCE GRAPH DATA (NEW) =================
    performance_data = db.execute("""
        SELECT 
            h.date,
            SUM(h.meters) AS total_meters
        FROM history h
        JOIN orders o ON h.order_id = o.id
        WHERE o.owner=? AND o.weaver=?
        GROUP BY h.date
        ORDER BY h.date
    """,(owner_name, username)).fetchall()

    db.close()

    return render_template(
        "weaver_owner_orders.html",
        owner_name=owner_name,
        orders=orders,
        history=history,
        performance_data=performance_data  # 👈 NEW
    )

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

if __name__ == "__main__":
    app.run(debug=True)
