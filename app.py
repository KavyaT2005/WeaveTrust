from flask import Flask, render_template, request, redirect, session
import sqlite3
from datetime import datetime
from twilio.rest import Client

app = Flask(__name__)
app.secret_key = "weavetrust_secret"

import os

TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH = os.getenv("TWILIO_AUTH")
TWILIO_NUMBER = "whatsapp:+14155238886"


client = Client(TWILIO_SID, TWILIO_AUTH)

# ---------------- DB HELPER ----------------
def get_db():
    conn = sqlite3.connect(
        "weavetrust.db",
        timeout=30,
        check_same_thread=False
    )
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
        db.execute(
            "INSERT INTO users(username,password,role,phone) VALUES (?,?,?,?)",
            (
                request.form["username"],
                request.form["password"],
                request.form["role"],
                request.form["phone"]
            )
        )
        db.commit()
        db.close()
        return redirect("/login")
    return render_template("signup.html")

# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (request.form["username"], request.form["password"])
        ).fetchone()
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
    return redirect("/owner" if session["role"] == "owner" else "/weaver")

# ---------------- OWNER PANEL ----------------
@app.route("/owner", methods=["GET", "POST"])
def owner():
    if "user" not in session:
        return redirect("/login")

    db = get_db()

    if request.method == "POST":
        db.execute("""
            INSERT INTO orders(owner,weaver,cloth,meters,produced,rate,status)
            VALUES (?,?,?,?,?,?,?)
        """, (
            session["user"],
            request.form["weaver"],
            request.form["cloth"],
            int(request.form["meters"]),
            0,
            int(request.form["rate"]),
            "Assigned"
        ))
        db.commit()

    # Active weavers on top
    weavers = db.execute("""
        SELECT
            weaver,
            MAX(CASE WHEN status != 'Completed' THEN 1 ELSE 0 END) AS active
        FROM orders
        WHERE owner=?
        GROUP BY weaver
        ORDER BY active DESC, weaver
    """, (session["user"],)).fetchall()

    db.close()
    return render_template("owner.html", weavers=weavers)

# ---------------- OWNER → WEAVER ORDERS ----------------
@app.route("/owner/weaver/<weaver_name>")
def owner_weaver_orders(weaver_name):
    if "user" not in session:
        return redirect("/login")

    db = get_db()
    orders = db.execute("""
        SELECT * FROM orders
        WHERE owner=? AND weaver=?
    """, (session["user"], weaver_name)).fetchall()
    db.close()

    return render_template(
        "owner_weaver_orders.html",
        weaver_name=weaver_name,
        orders=orders
    )

# ---------------- WEAVER PANEL ----------------
@app.route("/weaver", methods=["GET", "POST"])
def weaver():
    if "user" not in session:
        return redirect("/login")

    db = get_db()
    username = session["user"]

    if request.method == "POST":
        oid = request.form.get("id")
        produced_input = int(request.form.get("meters", 0))

        order = db.execute(
            "SELECT * FROM orders WHERE id=? AND weaver=?",
            (oid, username)
        ).fetchone()

        if order and produced_input > 0:
            old_produced = order["produced"]
            target = order["meters"]
            produced = min(produced_input, target - old_produced)

            if produced > 0:
                db.execute(
                    "UPDATE orders SET produced = produced + ? WHERE id=?",
                    (produced, oid)
                )

                db.execute(
                    "INSERT INTO history(order_id,weaver,meters,date) VALUES (?,?,?,?)",
                    (oid, username, produced, datetime.now().strftime("%d-%m-%Y"))
                )
                db.commit()

                new_produced = old_produced + produced

                if old_produced < target and new_produced >= target:
                    db.execute(
                        "UPDATE orders SET status='Completed' WHERE id=?",
                        (oid,)
                    )
                    db.commit()

                    owner = db.execute(
                        "SELECT phone FROM users WHERE username=?",
                        (order["owner"],)
                    ).fetchone()

                    if owner and owner["phone"]:
                        client.messages.create(
                            body=f"""✅ Order Completed
Weaver: {username}
Cloth: {order['cloth']}
Total: {target}m
Completed Successfully 🎉""",
                            from_=TWILIO_NUMBER,
                            to=f"whatsapp:{owner['phone']}"
                        )
                else:
                    db.execute(
                        "UPDATE orders SET status='In Progress' WHERE id=?",
                        (oid,)
                    )
                    db.commit()

    orders = db.execute(
        "SELECT * FROM orders WHERE weaver=?",
        (username,)
    ).fetchall()

    history = db.execute("""
        SELECT h.date, h.meters, o.owner
        FROM history h
        JOIN orders o ON h.order_id = o.id
        WHERE o.weaver=?
        ORDER BY h.id DESC
    """, (username,)).fetchall()

    db.close()
    return render_template("weaver.html", orders=orders, history=history)

# ---------------- WEAVER → OWNER ORDERS ----------------
@app.route("/weaver/owner/<owner_name>")
def weaver_owner_orders(owner_name):
    if "user" not in session:
        return redirect("/login")

    db = get_db()
    username = session["user"]

    orders = db.execute("""
        SELECT * FROM orders
        WHERE weaver=? AND owner=?
    """, (username, owner_name)).fetchall()

    history = db.execute("""
        SELECT h.date, h.meters
        FROM history h
        JOIN orders o ON h.order_id = o.id
        WHERE o.weaver=? AND o.owner=?
        ORDER BY h.id DESC
    """, (username, owner_name)).fetchall()

    db.close()

    return render_template(
        "weaver_owner_orders.html",
        owner_name=owner_name,
        orders=orders,
        history=history
    )

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)
