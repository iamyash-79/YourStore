import razorpay
from flask import Flask, render_template, request, g, redirect, session, url_for, flash, jsonify, current_app
import sqlite3, os, json, random, string, smtplib, ssl, time, uuid
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from flask_login import LoginManager, current_user, login_required, logout_user
import mysql.connector

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
app.permanent_session_lifetime = timedelta(days=100)

client = razorpay.Client(auth=("rzp_live_api", "password"))

APP_NAME = "Yash Cyber Cafe"
EMAIL_ADDRESS = "example@gmail.com"
EMAIL_PASSWORD = "yourapppassword"

def generate_random_otp(length=6):
    import random
    return ''.join(random.choices('0123456789', k=length))

def send_otp_to_email(email, otp):
    import smtplib, ssl

    subject = f"{APP_NAME} - OTP Verification"
    body = f"""Hello,

Your OTP for {APP_NAME} is: {otp}

This code is valid for 5 minutes. Please do not share it with anyone.

Regards,
{APP_NAME} Team
"""

    # Add custom From header (may be ignored by Gmail)
    message = f"From: {APP_NAME} <{EMAIL_ADDRESS}>\nSubject: {subject}\n\n{body}"

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, email, message)
        return True
    except Exception as e:
        print("OTP send error:", e)
        return False

# ✅ MySQL connection function
def get_mysql_connection():
    return mysql.connector.connect(
        host="localhost",
        user="username_database",
        password="password_database",
        database="username_database",
        auth_plugin='mysql_native_password'
    )

# ✅ Visits Table: (ip, user_agent, page, timestamp)
@app.before_request
def log_traffic():
    ip = request.remote_addr
    user_agent = request.headers.get("User-Agent")
    page = request.path
    now = datetime.now()
    one_hour_ago = now - timedelta(hours=1)

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT COUNT(*) AS count FROM visits
        WHERE ip = %s AND timestamp >= %s
    """, (ip, one_hour_ago))
    already_logged = cursor.fetchone()["count"]

    if already_logged == 0:
        cursor.execute("""
            INSERT INTO visits (ip, user_agent, page, timestamp)
            VALUES (%s, %s, %s, %s)
        """, (ip, user_agent, page, now))
        conn.commit()

    conn.close()

def get_total_visitors():
    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT COUNT(*) AS total FROM visits")
    result = cursor.fetchone()
    conn.close()
    return result["total"]

@app.context_processor
def inject_traffic():
    return {"total_visitors": get_total_visitors()}

# ✅ Common MySQL connection helper
def get_db():
    if 'db' not in g:
        g.db = get_mysql_connection()
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# ✅ Fetch user details
def get_user():
    user_id = session.get("user_id")
    user_meta = session.get("user")

    if not user_id or not user_meta:
        return None

    role = user_meta.get("role")
    table = "admins" if role in ("admin", "seller", "owner") else "users"

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"""
        SELECT id, full_name, email, profile_image, role, contact, gender_id
        FROM {table}
        WHERE id = %s
    """, (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

@app.context_processor
def inject_user():
    return dict(current_user=get_user())

# ✅ Login handler
def handle_login(expected_role):
    email = request.form.get("email")
    password = request.form.get("password")

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()
    conn.close()

    if user and check_password_hash(user["password"], password):
        if user["role"] != expected_role:
            flash("Invalid login for this portal.", "error")
            return redirect(request.path)

        session["user_id"] = user["id"]
        flash("Logged in successfully!", "success")
        return redirect(url_for("seller_dashboard"))

    flash("Invalid credentials", "error")
    return redirect(request.path)

# ✅ Get owner id
def get_owner_id():
    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM admins WHERE role = 'owner' LIMIT 1")
    result = cursor.fetchone()
    conn.close()
    return result['id'] if result else None

# ✅ Date formatting filters
@app.template_filter('datetimeformat')
def format_datetime(value):
    try:
        utc = datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
        ist = utc + timedelta(hours=5, minutes=30)
        return ist.strftime("%d/%m/%Y %I:%M %p")
    except Exception:
        return value

# users route ====users route=======users route=============users route=============users route===================users route=============users route================users route=================users route=

@app.route("/")
def user_home():
    user = get_user()

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    # products table (plural)
    cursor.execute("SELECT id, name, price, discount_price, images FROM products WHERE is_visible = 1")
    rows = cursor.fetchall()
    conn.close()

    product_items = []
    for row in rows:
        # Parse images safely
        try:
            images = json.loads(row["images"]) if isinstance(row["images"], str) and row["images"].strip().startswith("[") else [row["images"]]
        except Exception:
            images = [row["images"]] if row["images"] else []

        # Handle discount safely
        try:
            discount_price = float(row["discount_price"]) if row["discount_price"] not in (None, "", "None") else 0.0
        except Exception:
            discount_price = 0.0

        product_items.append({
            "id": row["id"],
            "name": row["name"],
            "price": float(row["price"]),
            "discount_price": discount_price,
            "images": images
        })

    return render_template(
        "user_home.html",
        user=user,
        full_name=user["full_name"] if user else None,
        product_items=product_items
    )


# ✅ Shop Page
@app.route("/user_shop")
def user_shop():
    user = get_user()

    # Redirect sellers
    if user and user.get("role") == "seller":
        return redirect(url_for("seller_dashboard"))

    query = request.args.get("q", "").strip().lower()

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name, price, discount_price, images, description FROM products WHERE is_visible = 1")
    rows = cursor.fetchall()
    conn.close()

    product_items = []
    for row in rows:
        name = row["name"]
        description = row.get("description", "")

        # Filter by search
        if query and (query not in name.lower() and query not in description.lower()):
            continue

        # Parse image
        try:
            images = json.loads(row["images"]) if isinstance(row["images"], str) and row["images"].strip().startswith("[") else [row["images"]]
        except Exception:
            images = [row["images"]] if row["images"] else []

        # Discount
        try:
            discount_price = float(row["discount_price"]) if row["discount_price"] not in (None, "", "None") else 0.0
        except Exception:
            discount_price = 0.0

        product_items.append({
            "id": row["id"],
            "name": name,
            "price": float(row["price"]),
            "discount_price": discount_price,
            "images": images
        })

    return render_template(
        "user_shop.html",
        user=user,
        full_name=user["full_name"] if user else None,
        product_items=product_items,
        query=query
    )

@app.route('/user_products_details/<int:product_id>')
def user_products_details(product_id):
    user = get_user()

    # Redirect sellers
    if user and user.get("role") == "seller":
        return redirect(url_for("seller_dashboard"))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
    product = cursor.fetchone()
    conn.close()

    if not product:
        return redirect(url_for("user_shop"))

    # Parse images safely
    try:
        images_raw = product['images']
        if isinstance(images_raw, str) and images_raw.strip().startswith("["):
            images = json.loads(images_raw)
        else:
            images = [img.strip() for img in images_raw.split(',') if img.strip()]
    except Exception:
        images = []

    product_data = {
        'id': product['id'],
        'name': product['name'],
        'description': product['description'],
        'price': float(product['price']),
        'discount_price': float(product['discount_price']) if product['discount_price'] not in (None, '', 'None') else None,
        'images': images
    }

    return render_template('user_products_details.html', product=product_data, user=user)


# ✅ Checkout Page (Buy Now + Cart)
@app.route('/user_checkout', defaults={'product_id': None})
@app.route('/user_checkout/<int:product_id>')
def user_checkout(product_id):
    user = get_user()

    if user and user["role"] == "seller":
        return redirect(url_for("seller_dashboard"))

    cart = []
    subtotal = 0

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    if product_id:
        # ➤ Buy Now flow
        cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
        product = cursor.fetchone()

        if not product:
            conn.close()
            flash("Product not found.", "error")
            return redirect(url_for("user_shop"))

        try:
            images = json.loads(product["images"]) if isinstance(product["images"], str) and product["images"].strip().startswith("[") else [
                img.strip() for img in product["images"].split(",") if img.strip()
            ]
        except:
            images = []

        price = float(product["discount_price"] or product["price"] or 0)

        cart.append({
            "id": product["id"],
            "name": product["name"],
            "description": product["description"],
            "price": price,
            "qty": 1,
            "images": images
        })

        subtotal = price

    else:
        # ➤ Full Cart Checkout
        if user and user["role"] == "user":
            user_id = user["id"]

            # Fetch from carts table
            cursor.execute("SELECT * FROM carts WHERE user_id = %s", (user_id,))
            cart_items = cursor.fetchall()

            for item in cart_items:
                cursor.execute("SELECT * FROM products WHERE id = %s", (item["product_id"],))
                product = cursor.fetchone()
                if product:
                    price = float(product["discount_price"] or product["price"] or 0)
                    cart.append({
                        "id": product["id"],
                        "name": product["name"],
                        "qty": item["quantity"],
                        "price": price
                    })
                    subtotal += price * item["quantity"]

        else:
            # ➤ Guest session cart
            guest_cart = session.get("guest_cart", {})
            for pid_str, qty in guest_cart.items():
                cursor.execute("SELECT * FROM products WHERE id = %s", (int(pid_str),))
                product = cursor.fetchone()
                if product:
                    price = float(product["discount_price"] or product["price"] or 0)
                    cart.append({
                        "id": product["id"],
                        "name": product["name"],
                        "qty": qty,
                        "price": price
                    })
                    subtotal += price * qty

    conn.close()

    if not cart:
        return redirect(url_for("user_cart"))

    # ✅ Handling Fee & Total
    handling_fee = round(subtotal * 0.02, 2) if cart else 0
    total = subtotal + handling_fee

    # ✅ Fetch last order for autofill
    latest_order = {}
    if user:
        conn_orders = get_mysql_connection()
        cursor_orders = conn_orders.cursor(dictionary=True)
        cursor_orders.execute("""
            SELECT address1, address2, city, pincode
            FROM orders
            WHERE user_email = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (user.get("email"),))
        result = cursor_orders.fetchone()
        conn_orders.close()

        if result:
            latest_order = dict(result)

    latest_order["state"] = "Chhattisgarh"

    return render_template(
        "user_checkout.html",
        user=user,
        cart=cart,
        subtotal=subtotal,
        handling_fee=handling_fee,
        total=total,
        is_buy_now=bool(product_id),
        order=latest_order
    )

@app.route('/add_to_cart/<int:product_id>')
def add_to_cart(product_id):
    user = get_user()
    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    if user and user.get("role") == "user":
        user_id = user["id"]

        # Check if product already exists
        cursor.execute("SELECT * FROM carts WHERE user_id = %s AND product_id = %s", (user_id, product_id))
        existing = cursor.fetchone()

        if existing:
            cursor.execute("UPDATE carts SET quantity = quantity + 1 WHERE id = %s", (existing["id"],))
        else:
            cursor.execute("INSERT INTO carts (user_id, product_id, quantity) VALUES (%s, %s, %s)", (user_id, product_id, 1))
    else:
        # Guest cart stored in session
        guest_cart = session.get("guest_cart", {})
        product_id_str = str(product_id)
        guest_cart[product_id_str] = guest_cart.get(product_id_str, 0) + 1
        session["guest_cart"] = guest_cart

    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Item added to cart successfully!"})


@app.route("/user_cart")
def user_cart():
    user = get_user()

    if user and user.get("role") == "seller":
        return redirect(url_for("seller_dashboard"))

    if not user or user.get("role") != "user":
        flash("Please log in to view your cart.", "login_error")

        user_agent = request.headers.get('User-Agent', '').lower()
        is_mobile = "mobi" in user_agent or "android" in user_agent or "iphone" in user_agent
        return redirect("/user_shop" if is_mobile else url_for("user_home"))

    user_id = user["id"]
    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT c.id AS cart_id, c.quantity, 
               p.id AS product_id, p.name, p.price, p.discount_price, p.images
        FROM carts c
        JOIN products p ON c.product_id = p.id
        WHERE c.user_id = %s
    """, (user_id,))
    cart_items = cursor.fetchall()

    enriched_items, subtotal = [], 0
    for item in cart_items:
        price = float(item["discount_price"] or item["price"] or 0)
        total = price * item["quantity"]

        try:
            images = json.loads(item["images"]) if item["images"].strip().startswith("[") else item["images"].split(",")
            image = images[0].strip() if images else "default.jpg"
        except:
            image = "default.jpg"

        enriched_items.append({
            "cart_id": item["cart_id"],
            "product_id": item["product_id"],
            "name": item["name"],
            "price": price,
            "quantity": item["quantity"],
            "total": total,
            "image": image
        })
        subtotal += total

    handling = round(subtotal * 0.02, 2) if enriched_items else 0
    total = subtotal + handling

    cursor.close()
    conn.close()

    return render_template("user_cart.html", user=user, cart=enriched_items,
                           subtotal=subtotal, handling=handling, total=total)


@app.route('/update_cart/<int:cart_id>', methods=['POST'])
def update_cart(cart_id):
    user = get_user()
    if not user:
        return redirect(url_for('user_login'))

    action = request.form.get("action")
    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM carts WHERE id = %s AND user_id = %s", (cart_id, user["id"]))
    item = cursor.fetchone()

    if item:
        if action == "increase":
            cursor.execute("UPDATE carts SET quantity = quantity + 1 WHERE id = %s", (cart_id,))
        elif action == "decrease" and item["quantity"] > 1:
            cursor.execute("UPDATE carts SET quantity = quantity - 1 WHERE id = %s", (cart_id,))
        elif action == "decrease":
            cursor.execute("DELETE FROM carts WHERE id = %s", (cart_id,))

    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for("user_cart"))


@app.route('/remove_from_cart/<int:cart_id>', methods=['POST'])
def remove_from_cart(cart_id):
    user = get_user()
    if not user:
        return redirect(url_for('user_login'))

    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM carts WHERE id = %s AND user_id = %s", (cart_id, user["id"]))
    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for("user_cart"))


@app.route("/place_cod_order", methods=["POST"])
def place_cod_order():
    user = get_user()
    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    name = request.form.get("full_name", "").strip()
    phone = request.form.get("phone", "").strip()
    address1 = request.form.get("address1", "").strip()
    address2 = request.form.get("address2", "").strip()
    city = request.form.get("city", "").strip()
    state = request.form.get("state", "").strip()
    pincode = request.form.get("pincode", "").strip()
    country = request.form.get("country", "").strip()

    if not all([name, phone, address1, city, state, pincode, country]):
        flash("Please fill all required fields.", "error")
        return redirect(url_for("user_checkout"))

    user_id = user["id"] if user else None
    user_email = user["email"] if user else "guest@example.com"
    created_at = datetime.now().strftime("%d %b %Y, %I:%M %p")

    # Fetch cart items
    cursor.execute("""
        SELECT c.quantity, p.id AS product_id, p.name, p.price, p.discount_price, p.images, p.seller_id
        FROM carts c
        JOIN products p ON c.product_id = p.id
        WHERE c.user_id = %s
    """, (user_id,))
    cart_items = cursor.fetchall()

    if not cart_items:
        flash("Cart is empty!", "error")
        return redirect(url_for("user_cart"))

    for item in cart_items:
        qty = item["quantity"]
        price = float(item["discount_price"] or item["price"] or 0)
        total = qty * price

        try:
            images = json.loads(item["images"]) if item["images"].strip().startswith("[") else item["images"].split(",")
            image = images[0].strip() if images else "default.jpg"
        except:
            image = "default.jpg"

        cursor.execute("""
            INSERT INTO orders (
                item_id, item_name, quantity, amount, status,
                address1, address2, city, pincode, order_date,
                user_id, user_name, user_contact, user_email, image,
                created_at, seller_id
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            item["product_id"], item["name"], qty, total, "pending",
            address1, address2, city, pincode, created_at,
            user_id, name, phone, user_email, image,
            created_at, item["seller_id"]
        ))

    # Clear cart after order placement
    cursor.execute("DELETE FROM carts WHERE user_id = %s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()

    flash("Your COD order has been placed successfully!", "success")
    return redirect(url_for("user_orders"))

@app.route("/place_online_order", methods=["POST"])
def place_online_order():
    user = get_user()
    user_id = user["id"] if user else None
    user_email = user["email"] if user and "email" in user else "guest@example.com"

    # Collect shipping details
    name = request.form.get("full_name", "").strip()
    phone = request.form.get("phone", "").strip()
    address1 = request.form.get("address1", "").strip()
    address2 = request.form.get("address2", "").strip()
    city = request.form.get("city", "").strip()
    state = request.form.get("state", "").strip()
    pincode = request.form.get("pincode", "").strip()
    country = request.form.get("country", "").strip()
    payment_id = request.form.get("razorpay_payment_id", "").strip()

    if not all([name, phone, address1, city, state, pincode, country, payment_id]):
        flash("Missing required fields.", "error")
        return redirect(url_for("user_checkout"))

    created_at = datetime.now().strftime("%d %b %Y, %I:%M %p")
    cart = session.get("cart", [])

    if not cart or not isinstance(cart, list):
        flash("Your cart is empty or expired.", "error")
        return redirect(url_for("user_shop"))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    for item in cart:
        product_id = item.get("id")
        quantity = int(item.get("qty", 1))
        price = float(item.get("price", 0))
        total = quantity * price
        name_p = item.get("name", "Unknown Product")

        cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
        product = cursor.fetchone()
        if not product:
            continue

        try:
            raw = product["images"]
            images = json.loads(raw) if raw.strip().startswith("[") else [x.strip() for x in raw.split(",") if x.strip()]
            image = images[0] if images else "default.jpg"
        except:
            image = "default.jpg"

        seller_id = product.get("seller_id", 1)

        cursor.execute("""
            INSERT INTO orders (
                item_id, item_name, quantity, amount, status,
                address1, address2, city, pincode, order_date,
                user_id, user_name, user_contact, user_email, image,
                created_at, seller_id, payment_id, is_paid
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            product_id, name_p, quantity, total, "accepted",
            address1, address2, city, pincode, created_at,
            user_id, name, phone, user_email, image,
            created_at, seller_id, payment_id, 1
        ))

    conn.commit()
    cursor.close()
    conn.close()

    session.pop("cart", None)
    flash("✅ Payment successful! Your order has been placed.", "success")
    return redirect(url_for("user_orders") if user_id else url_for("user_shop"))


@app.route('/create_payment', methods=["POST"])
def create_payment():
    data = request.get_json()
    total = float(data.get("total", 0))
    form = data.get("form", {})

    if total <= 0:
        return jsonify({"error": "Invalid total"}), 400

    amount_in_paise = int(total * 100)

    razorpay_order = client.order.create({
        "amount": amount_in_paise,
        "currency": "INR",
        "payment_capture": "1"
    })

    session["cart"] = data.get("cart", [])
    session["checkout_form"] = form

    return jsonify({
        "order_id": razorpay_order["id"],
        "amount": amount_in_paise,
        "key_id": "rzp_live_Bs8iGWDy31UcPw",
        "name": form.get("full_name", ""),
        "email": form.get("email", ""),
        "contact": form.get("phone", "")
    })


@app.route("/payment_success", methods=["POST"])
def payment_success():
    data = request.get_json()
    payment_id = data.get("payment_id")
    cart = data.get("cart")
    form = data.get("form")

    if not payment_id or not cart or not form:
        return jsonify({"success": False, "error": "Missing payment ID or data"}), 400

    created_at = datetime.now().strftime("%d %b %Y, %I:%M %p")
    user = get_user()
    user_id = user["id"] if user else None
    user_email = user["email"] if user and "email" in user else "guest@example.com"

    try:
        conn = get_mysql_connection()
        cursor = conn.cursor(dictionary=True)

        for item in cart:
            product_id = item.get("id")
            quantity = int(item.get("qty", 1))
            price = float(item.get("price", 0))
            total = quantity * price
            name = item.get("name", "Unknown Product")

            cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
            product = cursor.fetchone()
            if not product:
                continue

            try:
                raw = product["images"]
                images = json.loads(raw) if raw.strip().startswith("[") else [x.strip() for x in raw.split(",") if x.strip()]
                image = images[0] if images else "default.jpg"
            except:
                image = "default.jpg"

            seller_id = product.get("seller_id", 1)

            cursor.execute("""
                INSERT INTO orders (
                    item_id, item_name, quantity, amount, status,
                    address1, address2, city, pincode, order_date,
                    user_id, user_name, user_contact, user_email, image,
                    created_at, seller_id, is_paid, payment_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                product_id, name, quantity, total, "accepted",
                form.get("address1", ""), form.get("address2", ""), form.get("city", ""), form.get("pincode", ""),
                created_at, user_id, form.get("full_name", ""), form.get("phone", ""), user_email,
                image, created_at, seller_id, 1, payment_id
            ))

        conn.commit()

        if user_id:
            cart_conn = get_mysql_connection()
            cart_cursor = cart_conn.cursor()
            cart_cursor.execute("DELETE FROM cart WHERE user_id = %s", (user_id,))
            cart_conn.commit()
            cart_cursor.close()
            cart_conn.close()

        return jsonify({"success": True})

    except Exception as e:
        print("⚠️ Insert failed:", e)
        return jsonify({"success": False, "error": str(e)}), 500

    finally:
        cursor.close()
        conn.close()

@app.route("/user_settings")
def user_settings():
    user = get_user()

    if user and user.get("role") in ("seller"):
        return redirect(url_for("seller_dashboard"))

    return render_template("user_settings.html", user=user)

@app.route("/mobile_settings")
def mobile_settings():
    user = get_user()
    return render_template("mobile_settings.html", user=user)

@app.route("/deactivate-account", methods=["POST"])
def deactivate_account():
    user = get_user()
    if not user:
        return jsonify(success=False, message="Not logged in.")

    if user["role"] in ["admin", "seller", "owner"]:
        return jsonify(success=False, message="Admins and Owners cannot deactivate.")

    try:
        conn = get_mysql_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("DELETE FROM users WHERE id = %s", (user["id"],))
        conn.commit()
        conn.close()

        session.clear()
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, message=str(e))



@app.route("/user_account", methods=["GET", "POST"])
def user_account():
    user = get_user()

    if not user:
        return redirect(url_for("user_home"))

    if user.get("role") in ("seller"):
        return redirect(url_for("seller_dashboard"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        gender_id = request.form.get("gender_id", 1)

        conn = get_mysql_connection()
        cursor = conn.cursor(dictionary=True)

        # ✅ If user clicked "Remove Image"
        if 'remove_image' in request.form:
            cursor.execute("UPDATE users SET profile_image = NULL WHERE id = %s", (user["id"],))

        # ✅ Handle profile image upload
        image = request.files.get("image")
        if image and allowed_file(image.filename):
            filename = secure_filename(image.filename)

            upload_folder = os.path.join(current_app.root_path, "static/images")
            os.makedirs(upload_folder, exist_ok=True)

            filepath = os.path.join(upload_folder, filename)
            image.save(filepath)

            image_url = f"/static/images/{filename}"
            cursor.execute("UPDATE users SET profile_image = %s WHERE id = %s", (image_url, user["id"]))

        # ✅ Update name and gender
        cursor.execute("UPDATE users SET full_name = %s, gender_id = %s WHERE id = %s",
                       (full_name, gender_id, user["id"]))
        conn.commit()
        conn.close()

        flash("Account updated successfully.", "success")
        return redirect(url_for("user_account"))

    return render_template("user_account.html", user=user)

@app.route("/change-info", methods=["POST"])
def change_info():
    user = get_user()
    if not user:
        flash("Session expired. Please log in again.", "error")
        return redirect(url_for("user_account"))

    email = request.form.get("email", "").strip()
    contact = request.form.get("contact", "").strip()

    if not email and not contact:
        flash("Please provide at least one field to update.", "error")
        return redirect(url_for("user_account"))

    conn = get_mysql_connection()
    cur = conn.cursor(dictionary=True)

    # ✅ Update email if needed
    if email and email != user["email"]:
        if not session.get("otp_verified"):
            flash("Please verify OTP before changing your email.", "error")
            conn.close()
            return redirect(url_for("user_account"))
        cur.execute("UPDATE users SET email = %s WHERE id = %s", (email, user["id"]))

    # ✅ Update contact if needed
    if contact and contact != user.get("contact"):
        cur.execute("UPDATE users SET contact = %s WHERE id = %s", (contact, user["id"]))

    conn.commit()

    # ✅ Reload updated user info
    cur.execute("SELECT * FROM users WHERE id = %s", (user["id"],))
    updated_user = cur.fetchone()

    session["user"] = {
        "email": updated_user["email"],
        "role": updated_user["role"],
        "name": updated_user["full_name"],
        "contact": updated_user["contact"]
    }

    # ✅ Clear OTP session data
    session.pop("otp_code", None)
    session.pop("otp_email", None)
    session.pop("otp_expiry", None)
    session.pop("otp_verified", None)

    cur.close()
    conn.close()
    flash("Information updated successfully.", "success")
    return redirect(url_for("user_account"))


@app.route("/send-user-otp", methods=["POST"])
def send_user_otp():
    email = request.json.get("email", "").strip()
    if not email:
        return jsonify(success=False, message="Email is required.")

    user_id = session.get("user_id")
    is_logged_in = bool(user_id)

    conn = get_mysql_connection()
    cur = conn.cursor(dictionary=True)

    cur.execute("SELECT * FROM users WHERE email = %s", (email,))
    existing_user = cur.fetchone()

    # ✅ Logged in: user changing email
    if is_logged_in:
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        current_user = cur.fetchone()

        if not current_user:
            conn.close()
            return jsonify(success=False, message="User not found.")
        if email == current_user["email"]:
            conn.close()
            return jsonify(success=False, message="This is already your current email.")
        if existing_user:
            conn.close()
            return jsonify(success=False, message="This email is already in use.")

    # ✅ Not logged in: new user registering
    elif not existing_user:
        try:
            cur.execute("""
                INSERT INTO users (email, full_name, role, contact)
                VALUES (%s, '', 'user', '0000000000')
            """, (email,))
            conn.commit()
        except Exception as e:
            conn.close()
            return jsonify(success=False, message="Registration failed: " + str(e))

    conn.close()

    # ✅ Send OTP and store session context
    otp = generate_random_otp()
    session["user_otp_email"] = email
    session["user_otp_code"] = otp
    session["user_otp_expiry"] = time.time() + 300  # 5 min

    if send_otp_to_email(email, otp):
        return jsonify(success=True, message="OTP sent to email.")
    else:
        return jsonify(success=False, message="Failed to send OTP.")


@app.route("/verify-user-otp", methods=["POST"])
def verify_user_otp():
    user_otp = request.json.get("otp", "").strip()
    stored_otp = session.get("user_otp_code")
    target_email = session.get("user_otp_email")
    expiry = session.get("user_otp_expiry", 0)

    if not user_otp or not stored_otp or not target_email:
        return jsonify(verified=False, message="Session expired or missing data.")
    if time.time() > expiry:
        return jsonify(verified=False, message="OTP expired. Please try again.")
    if user_otp != stored_otp:
        return jsonify(verified=False, message="Incorrect OTP.")

    conn = get_mysql_connection()
    cur = conn.cursor(dictionary=True)
    user_id = session.get("user_id")

    # ✅ Case 1: logged in user updating email
    if user_id:
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        current = cur.fetchone()
        if not current:
            conn.close()
            return jsonify(verified=False, message="User not found.")

        cur.execute("SELECT * FROM users WHERE email = %s", (target_email,))
        email_in_use = cur.fetchone()
        if email_in_use:
            conn.close()
            return jsonify(verified=False, message="Email already in use.")

        cur.execute("UPDATE users SET email = %s WHERE id = %s", (target_email, user_id))
        conn.commit()
        session["user"]["email"] = target_email
        conn.close()
        return jsonify(verified=True, message="Email updated successfully.")

    # ✅ Case 2: OTP-based login
    cur.execute("SELECT * FROM users WHERE email = %s", (target_email,))
    user = cur.fetchone()
    conn.close()

    if not user:
        return jsonify(verified=False, message="User not found.")
    if user["role"] in ("admin", "seller", "owner"):
        return jsonify(verified=False, message="Admins not allowed here.")

    session["user_id"] = user["id"]
    session["user"] = {
        "email": user["email"],
        "role": user["role"],
        "name": user["full_name"] or ""
    }

    return jsonify(verified=True, message="Logged in successfully.")

@app.route("/user_categories")
def user_categories():
    user = get_user()

    if user and user.get("role") in ("seller"):
        return redirect(url_for("seller_dashboard"))

    return render_template("user_categories.html")

@app.route("/user_orders")
def user_orders():
    user = get_user()  # Can be None
    email = user["email"] if user else None
    user_orders = []

    if email:
        conn = get_mysql_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT id, item_name, quantity, status, address1, address2, city, pincode,
                   created_at, is_paid, amount, image
            FROM orders
            WHERE user_email = %s
            ORDER BY id DESC
        """, (email,))

        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            order = dict(row)
            raw_image = order.get("image", "")

            # ✅ Fix image handling
            try:
                if raw_image and raw_image.strip().startswith("["):
                    images = json.loads(raw_image)
                else:
                    images = [img.strip() for img in raw_image.split(",") if img.strip()]
                order["image"] = images[0] if images else "default.jpg"
            except Exception:
                order["image"] = "default.jpg"

            # ✅ Date parsing (MySQL stores datetime differently)
            try:
                if isinstance(order["created_at"], str):
                    order["created_at_obj"] = datetime.strptime(order["created_at"], "%d %b %Y, %I:%M %p")
                else:
                    order["created_at_obj"] = order["created_at"]
            except Exception:
                order["created_at_obj"] = order["created_at"]

            user_orders.append(order)

    return render_template(
        "user_orders.html",
        user=user,
        full_name=user.get("full_name", "") if user else "",
        user_orders=user_orders,
        razorpay_key="rzp_live_Bs8iGWDy31UcPw"
    )

@app.route("/user_order_details/<int:order_id>")
def user_order_details(order_id):
    user = get_user()
    if not user or user.get("role") != "user":
        return redirect(url_for("user_home"))

    user_email = user.get("email")
    user_contact = user.get("contact", "")

    conn = get_mysql_connection()
    cur = conn.cursor(dictionary=True)

    # ✅ Fetch order details from orders table
    cur.execute("""
        SELECT id, item_id, item_name, quantity, amount, status, image,
               address1, address2, city, pincode,
               created_at, accepted_at, cancelled_at, delivered_at,
               user_email, user_contact
        FROM orders
        WHERE id = %s AND user_email = %s
    """, (order_id, user_email))
    order = cur.fetchone()

    if not order:
        conn.close()
        flash("Order not found.", "error")
        return redirect(url_for("user_orders"))

    # ✅ Ensure fallback email/contact
    order['user_email'] = order.get('user_email', user_email)
    order['user_contact'] = order.get('user_contact', user_contact)

    # ✅ Fetch product info from products table
    cur.execute("SELECT id AS product_id, images FROM products WHERE id = %s", (order['item_id'],))
    product = cur.fetchone()

    if product:
        order['product_id'] = product['product_id']
        order['product_image'] = product['images']
    else:
        order['product_id'] = None
        order['product_image'] = None

    cur.close()
    conn.close()

    # ✅ Parse datetime fields (string → datetime object)
    date_fields = ['created_at', 'accepted_at', 'cancelled_at', 'delivered_at']
    for field in date_fields:
        value = order.get(field)
        if isinstance(value, str):
            try:
                order[field] = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            except:
                order[field] = None

    return render_template(
        "user_order_details.html",
        user=user,
        full_name=user.get("full_name", ""),
        order=order
    )


@app.route('/user_contact', methods=["GET", "POST"])
def user_contact():
    user = get_user()

    # ✅ Redirect seller to dashboard
    if user and user.get("role") == "seller":
        return redirect(url_for("seller_dashboard"))

    if request.method == "POST":
        flash("Messaging system is disabled.", "info")

    return render_template(
        "user_contact.html",
        full_name=user["full_name"] if user else "",
        user=user
    )

@app.route("/ys_policy")
def ys_policy():
    user = get_user()
    return render_template("ys_policy.html", user=user)

@app.route("/ys_about")
def ys_about():
    user = get_user()
    return render_template("ys_about.html", user=user)

@app.route("/ys_shipping")
def ys_shipping():
    user = get_user()
    return render_template("ys_shipping.html", user=user)

@app.route("/ys_terms")
def ys_terms():
    user = get_user()
    return render_template("ys_terms.html", user=user)

@app.route("/ys_refund")
def ys_refund():
    user = get_user()
    return render_template("ys_refund.html", user=user)

@app.route("/ys_privacy")
def ys_privacy():
    user = get_user()
    return render_template("ys_privacy.html", user=user)

@app.route("/ys_faq")
def ys_faq():
    user = get_user()
    return render_template("ys_faq.html", user=user)

# seller and owners route ====seller and owners route=======seller and owners route=============seller and owners route=============seller and owners route===================seller and owners route======

@app.route("/seller_login", methods=["GET", "POST"])
def seller_login():
    if "user_id" in session:
        return redirect(url_for("seller_dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        if not email or not password:
            flash("Please fill in all fields.", "error")
            return redirect(url_for("seller_login"))

        conn = get_mysql_connection()
        cur = conn.cursor(dictionary=True)

        cur.execute("SELECT * FROM admins WHERE LOWER(email) = %s", (email,))
        admin = cur.fetchone()
        conn.close()

        if not admin or not admin["password"]:
            flash("Invalid email or password.", "error")
            return redirect(url_for("seller_login"))

        if not check_password_hash(admin["password"], password):
            flash("Invalid email or password.", "error")
            return redirect(url_for("seller_login"))

        db_role = admin.get("role", "user")
        if db_role not in ("seller", "owner"):
            flash("You are not authorized to log in as Seller.", "error")
            return redirect(url_for("seller_login"))

        session["user_id"] = admin["id"]
        session["user"] = {
            "email": admin["email"],
            "role": db_role,
            "name": admin["full_name"]
        }

        return redirect(url_for("seller_dashboard"))

    return render_template("seller_login.html")


@app.route("/seller_dashboard")
def seller_dashboard():
    user = get_user()

    if not user:
        return redirect(url_for("seller_login"))
    if user.get("role") == "user":
        return redirect(url_for("user_home"))

    is_seller = user.get("role") == "seller"
    user_id = user.get("id")

    conn = get_mysql_connection()
    cur = conn.cursor(dictionary=True)

    where_clause = ""
    params = []
    if is_seller:
        where_clause = "WHERE seller_id = %s"
        params.append(user_id)

    # ✅ Total Orders
    cur.execute(f"SELECT COUNT(*) AS total FROM orders {where_clause}", params)
    total_orders = cur.fetchone()["total"]

    # ✅ Pending Orders
    cur.execute(f"""
        SELECT COUNT(*) AS count FROM orders
        {where_clause + (' AND' if where_clause else 'WHERE')} status = 'pending'
    """, params)
    pending_orders = cur.fetchone()["count"]

    # ✅ Delivered Orders
    cur.execute(f"""
        SELECT COUNT(*) AS count FROM orders
        {where_clause + (' AND' if where_clause else 'WHERE')} status = 'delivered'
    """, params)
    delivered_orders = cur.fetchone()["count"]

    # ✅ Total Revenue
    cur.execute(f"""
        SELECT SUM(amount) AS total FROM orders
        {where_clause + (' AND' if where_clause else 'WHERE')} status = 'delivered'
    """, params)
    total_revenue = cur.fetchone()["total"] or 0

    # ✅ Revenue trend (last 30 days)
    today = datetime.today()
    date_labels = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(29, -1, -1)]
    revenue_map = {d: 0 for d in date_labels}

    cur.execute(f"""
        SELECT DATE(order_date) AS order_date, amount FROM orders
        {where_clause + (' AND' if where_clause else 'WHERE')} status = 'delivered'
    """, params)
    for row in cur.fetchall():
        order_date = str(row["order_date"])
        if order_date in revenue_map:
            revenue_map[order_date] += float(row["amount"] or 0)

    chart_labels = list(revenue_map.keys())
    chart_data = [round(revenue_map[d], 2) for d in chart_labels]

    # ✅ Top 3 Products
    cur.execute(f"""
        SELECT item_id, item_name, SUM(quantity) AS total_qty, SUM(amount) AS total_sales
        FROM orders
        {where_clause + (' AND' if where_clause else 'WHERE')} status = 'delivered'
        GROUP BY item_id
        ORDER BY total_qty DESC
        LIMIT 3
    """, params)
    top_products = cur.fetchall()

    cur.close()
    conn.close()

    # ✅ Razorpay Data Fetch
    try:
        razorpay_data = client.payment.all({"count": 100})

        if isinstance(razorpay_data, dict) and 'items' in razorpay_data:
            payments = []
            for payment in razorpay_data['items']:
                payments.append({
                    'payment_id': payment.get('id', 'N/A'),
                    'order_id': payment.get('order_id', 'N/A'),
                    'amount': payment.get('amount', 0) / 100,
                    'status': payment.get('status', 'N/A'),
                    'created_at': datetime.utcfromtimestamp(payment.get('created_at', 0)).strftime('%Y-%m-%d %H:%M:%S'),
                    'vpa': payment.get('vpa', 'N/A'),
                    'contact': payment.get('contact', 'N/A')
                })
        else:
            payments = []
    except Exception as e:
        print(f"Error fetching payments from Razorpay: {e}")
        payments = []

    return render_template("seller_dashboard.html",
        user=user,
        full_name=user.get("full_name", "Seller"),
        total_orders=total_orders,
        pending_orders=pending_orders,
        delivered_orders=delivered_orders,
        total_revenue=int(total_revenue),
        chart_labels=json.dumps(chart_labels),
        chart_data=json.dumps(chart_data),
        top_products=top_products,
        payments=payments
    )


@app.route("/seller_orders")
def seller_orders():
    user = get_user()
    if not user:
        return redirect(url_for("seller_login"))
    if user.get("role") == "user":
        return redirect(url_for("user_home"))

    status_filter = request.args.get("status")
    date_filter = request.args.get("date")

    conn = get_mysql_connection()
    cur = conn.cursor(dictionary=True)

    query = "SELECT * FROM orders WHERE 1=1"
    params = []

    if user.get('role') == 'seller':
        query += " AND seller_id = %s"
        params.append(user.get('id'))

    if status_filter:
        query += " AND status = %s"
        params.append(status_filter)

    if date_filter:
        query += " AND DATE(order_date) = %s"
        params.append(date_filter)

    query += " ORDER BY order_date DESC"
    cur.execute(query, params)
    orders = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "seller_orders.html",
        user=user,
        full_name=user.get("full_name", ""),
        orders=orders,
        selected_status=status_filter or "",
        selected_date=date_filter or ""
    )

@app.route('/edit_order/<int:order_id>', methods=['POST'])
def edit_order(order_id):
    action = request.form.get("action")
    user = get_user()

    if not user or user.get("role") not in ("seller", "owner"):
        flash("Unauthorized", "error")
        return redirect(url_for("seller_orders"))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
    order = cursor.fetchone()

    if not order:
        flash("Order not found.", "error")
        cursor.close()
        conn.close()
        return redirect(url_for("seller_orders"))

    # ✅ Seller can only edit their own orders
    if user["role"] == "seller" and order["seller_id"] != user["id"]:
        flash("You are not authorized to update this order.", "error")
        cursor.close()
        conn.close()
        return redirect(url_for("seller_orders"))

    now = datetime.now().strftime("%d %b %Y, %I:%M %p")

    if action == "accept" and order["status"] == "pending":
        cursor.execute("UPDATE orders SET status = %s, accepted_at = %s WHERE id = %s", ("accepted", now, order_id))
        flash("Order accepted.", "success")

    elif action == "cancel" and order["status"] == "pending":
        cursor.execute("UPDATE orders SET status = %s, cancelled_at = %s WHERE id = %s", ("cancelled", now, order_id))
        flash("Order cancelled.", "success")

    elif action == "deliver" and order["status"] == "accepted":
        cursor.execute("UPDATE orders SET status = %s, delivered_at = %s WHERE id = %s", ("delivered", now, order_id))
        flash("Order marked as delivered.", "success")

    else:
        flash("Invalid or not allowed action.", "error")

    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for("seller_orders"))


@app.route('/accept_order/<int:order_id>', methods=['POST'])
def accept_order(order_id):
    user = get_user()
    if not user or user.get('role') not in ('seller', 'owner'):
        flash("Unauthorized", "error")
        return redirect(url_for('user_shop'))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT seller_id FROM orders WHERE id = %s", (order_id,))
    order = cursor.fetchone()

    if not order:
        flash("Order not found.", "error")
        cursor.close()
        conn.close()
        return redirect(url_for('seller_orders'))

    if user['role'] == 'seller' and order['seller_id'] != user['id']:
        flash("You are not authorized to accept this order.", "error")
        cursor.close()
        conn.close()
        return redirect(url_for('seller_orders'))

    accepted_at = datetime.now().strftime("%d %b %Y, %I:%M %p")
    cursor.execute("UPDATE orders SET status = %s, accepted_at = %s WHERE id = %s", ('accepted', accepted_at, order_id))
    conn.commit()

    cursor.close()
    conn.close()
    flash("Order accepted.", "success")
    return redirect(url_for('seller_orders'))


@app.route('/cancel_order/<int:order_id>', methods=['POST'])
def cancel_order(order_id):
    user = get_user()
    if not user:
        flash("Unauthorized access.", "error")
        return redirect(url_for("user_home"))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT user_email, status, seller_id FROM orders WHERE id = %s", (order_id,))
    order = cursor.fetchone()

    if not order:
        flash("Order not found.", "error")
        cursor.close()
        conn.close()
        return redirect(url_for("user_shop"))

    is_user = user['email'] == order['user_email']
    is_seller = user.get('role') == 'seller' and order['seller_id'] == user['id']
    is_owner = user.get('role') == 'owner'

    if not (is_user or is_seller or is_owner):
        flash("You are not authorized to cancel this order.", "error")
        cursor.close()
        conn.close()
        return redirect(url_for("user_shop"))

    if order['status'] != 'pending':
        flash("Only pending orders can be cancelled.", "error")
        cursor.close()
        conn.close()
        return redirect(url_for("user_orders"))

    cancelled_at = datetime.now().strftime("%d %b %Y, %I:%M %p")
    cursor.execute("UPDATE orders SET status = %s, cancelled_at = %s WHERE id = %s", ('cancelled', cancelled_at, order_id))
    conn.commit()

    cursor.close()
    conn.close()
    flash("Order cancelled successfully.", "success")

    if user.get('role') in ('seller', 'owner'):
        return redirect(url_for('seller_orders'))
    else:
        return redirect(url_for('user_orders'))


@app.route('/deliver_order/<int:order_id>', methods=['POST'])
def deliver_order(order_id):
    user = get_user()
    if not user or user.get('role') not in ('seller', 'owner'):
        flash("Unauthorized access.", "error")
        return redirect(url_for("user_shop"))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT status, seller_id FROM orders WHERE id = %s", (order_id,))
    order = cursor.fetchone()

    if not order:
        flash("Order not found.", "error")
        cursor.close()
        conn.close()
        return redirect(url_for("seller_orders"))

    if user['role'] == 'seller' and order['seller_id'] != user['id']:
        flash("You are not authorized to deliver this order.", "error")
        cursor.close()
        conn.close()
        return redirect(url_for("seller_orders"))

    if order['status'] == 'accepted':
        delivered_at = datetime.now().strftime("%d %b %Y, %I:%M %p")
        cursor.execute("UPDATE orders SET status = %s, delivered_at = %s WHERE id = %s", ('delivered', delivered_at, order_id))
        conn.commit()
        flash("Order marked as delivered.", "success")
    else:
        flash("Only accepted orders can be marked as delivered.", "error")

    cursor.close()
    conn.close()
    return redirect(url_for("seller_orders"))


@app.route('/delete_order/<int:order_id>', methods=['POST'])
def delete_order(order_id):
    user = get_user()
    if not user or user.get('role') != 'owner':  # ✅ Only owner
        flash("Unauthorized", "error")
        return redirect(url_for('user_shop'))

    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM orders WHERE id = %s", (order_id,))
    conn.commit()

    cursor.close()
    conn.close()
    flash("Order deleted.", "success")
    return redirect(url_for('seller_orders'))
    
@app.route("/seller_catalogs", methods=["GET", "POST"])
def seller_catalogs():
    user = get_user()
    if not user:
        return redirect(url_for("seller_login"))

    if user.get("role") == "user":
        return redirect(url_for("user_home"))

    full_name = user.get("full_name", "Guest")
    is_owner = user.get("role") == "owner"

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        if request.method == "POST":
            name = request.form["name"]
            description = request.form.get("description", "")
            price = request.form["price"]
            discount_price = request.form["discount_price"]
            image_files = request.files.getlist("images")

            if not image_files or image_files[0].filename == "":
                flash("Please upload at least one image.", "error")
                return redirect(url_for("seller_catalogs"))

            upload_folder = os.path.join(current_app.root_path, "static/uploads/products")
            os.makedirs(upload_folder, exist_ok=True)

            filenames = []
            for image in image_files:
                if image and allowed_file(image.filename):
                    filename = secure_filename(image.filename)
                    image.save(os.path.join(upload_folder, filename))
                    filenames.append(filename)
                else:
                    flash("All uploaded files must be valid images.", "error")
                    return redirect(url_for("seller_catalogs"))

            cursor.execute("""
                INSERT INTO products (name, description, price, discount_price, images, seller_id, is_visible)
                VALUES (%s, %s, %s, %s, %s, %s, 1)
            """, (name, description, price, discount_price, json.dumps(filenames), user["id"]))
            conn.commit()

            flash("Catalog added successfully!", "success")
            return redirect(url_for("seller_catalogs"))

        # GET method
        if is_owner:
            cursor.execute("SELECT * FROM products ORDER BY id DESC")
        else:
            cursor.execute("SELECT * FROM products WHERE seller_id = %s ORDER BY id DESC", (user["id"],))

        rows = cursor.fetchall()
        product_items = []
        for row in rows:
            images_data = row.get("images") or "[]"
            images = json.loads(images_data) if images_data.strip().startswith("[") else [images_data]

            product_items.append({
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "price": row["price"],
                "discount_price": row["discount_price"],
                "images": images,
                "is_visible": row.get("is_visible", 1)
            })

        return render_template("seller_catalogs.html", product_items=product_items, full_name=full_name, user=user)

    finally:
        cursor.close()
        conn.close()


@app.route("/edit_catalog/<int:item_id>", methods=["POST"])
def edit_catalog(item_id):
    user = get_user()
    if not user or user["role"] not in ["seller", "owner"]:
        flash("Unauthorized", "error")
        return redirect(url_for("seller_catalogs"))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT images, seller_id, is_visible FROM products WHERE id = %s", (item_id,))
    product = cursor.fetchone()

    if not product:
        flash("Catalog not found", "error")
        cursor.close()
        conn.close()
        return redirect(url_for("seller_catalogs"))

    if user["role"] == "seller" and product["seller_id"] != user["id"]:
        flash("Not allowed to edit this product", "error")
        cursor.close()
        conn.close()
        return redirect(url_for("seller_catalogs"))

    name = request.form["name"]
    description = request.form.get("description", "")
    price = request.form["price"]
    discount_price = request.form["discount_price"]
    image_files = request.files.getlist("images")
    is_visible = 1 if request.form.get("is_visible") else 0

    old_images_data = product.get("images") or "[]"
    old_images = json.loads(old_images_data) if old_images_data.strip().startswith("[") else [old_images_data]
    upload_folder = os.path.join(current_app.root_path, "static/uploads/products")
    new_filenames = old_images

    if image_files and image_files[0].filename != "":
        for img in old_images:
            img_path = os.path.join(upload_folder, img)
            if os.path.exists(img_path):
                try:
                    os.remove(img_path)
                except:
                    pass

        new_filenames = []
        for image in image_files:
            if image and allowed_file(image.filename):
                filename = secure_filename(image.filename)
                image.save(os.path.join(upload_folder, filename))
                new_filenames.append(filename)
            else:
                flash("All uploaded files must be valid images.", "error")
                cursor.close()
                conn.close()
                return redirect(url_for("seller_catalogs"))

    cursor.execute("""
        UPDATE products
        SET name=%s, description=%s, price=%s, discount_price=%s, images=%s, is_visible=%s
        WHERE id=%s
    """, (name, description, price, discount_price, json.dumps(new_filenames), is_visible, item_id))
    conn.commit()

    cursor.close()
    conn.close()
    flash("Catalog updated", "success")
    return redirect(url_for("seller_catalogs"))

@app.route("/delete_catalog/<int:item_id>", methods=["POST"])
def delete_catalog(item_id):
    user = get_user()
    if not user or user["role"] not in ["seller", "owner"]:
        flash("Unauthorized", "error")
        return redirect(url_for("seller_catalogs"))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT images, seller_id FROM products WHERE id = %s", (item_id,))
    row = cursor.fetchone()

    if not row:
        flash("Catalog not found", "error")
        cursor.close()
        conn.close()
        return redirect(url_for("seller_catalogs"))

    if user["role"] == "seller" and row["seller_id"] != user["id"]:
        flash("Not allowed to delete", "error")
        cursor.close()
        conn.close()
        return redirect(url_for("seller_catalogs"))

    images_data = row.get("images") or "[]"
    try:
        images = json.loads(images_data) if images_data.strip().startswith("[") else [images_data]
    except:
        images = [images_data]

    upload_folder = os.path.join(current_app.root_path, "static/uploads/products")
    for img in images:
        img_path = os.path.join(upload_folder, img)
        if os.path.exists(img_path):
            try:
                os.remove(img_path)
            except:
                pass

    cursor.execute("DELETE FROM products WHERE id = %s", (item_id,))
    conn.commit()

    cursor.close()
    conn.close()
    flash("Catalog deleted", "success")
    return redirect(url_for("seller_catalogs"))
    
@app.route("/seller_contact", methods=["GET", "POST"])
def seller_contact():
    user = get_user()  # Get current user for UI display, optional but good

    if not user:
        return redirect(url_for("seller_login"))

    if user.get("role") == "user":
        return redirect(url_for("user_home"))

    if request.method == "POST":
        # Collect form inputs
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()

        # Validate input
        if not name or not email or not subject or not message:
            flash("All fields are required.", "error")
            return redirect(url_for("seller_contact"))

        # Compose email to seller
        seller_subject = f"[Contact Form] {subject}"
        seller_body = f"""You received a message from your website contact form:

🧑 Name: {name}
📧 Email: {email}
📝 Subject: {subject}
💬 Message:
{message}
"""

        # Compose thank-you email to user
        user_subject = "Thank you for contacting Yash Cyber Cafe"
        user_body = f"""Hi {name},

Thank you for reaching out to Yash Cyber Cafe. We have received your message and will respond as soon as possible.

🙋 Subject: {subject}
📩 Message: {message}

Best regards,
Yash Cyber Cafe Team
"""

        # Send both emails
        try:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
                server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)

                # Email to seller
                server.sendmail(
                    EMAIL_ADDRESS,
                    EMAIL_ADDRESS,
                    f"Subject: {seller_subject}\n\n{seller_body}"
                )

                # Thank-you email to user
                server.sendmail(
                    EMAIL_ADDRESS,
                    email,
                    f"Subject: {user_subject}\n\n{user_body}"
                )

            flash("✅ Your message has been sent successfully!", "success")

        except Exception as e:
            print("Email sending error:", e)
            flash("❌ Failed to send your message. Try again later.", "error")

        return redirect(url_for("seller_contact"))

    return render_template("seller_contact.html", user=user)

@app.route("/seller_create", methods=["GET", "POST"])
def seller_create():
    user = get_user()

    if not user:
        return redirect(url_for("seller_login"))

    if user.get("role") == "user":
        return redirect(url_for("user_home"))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        contact = request.form.get("contact", "").strip()
        address = request.form.get("address", "").strip()

        if not full_name or not email or not contact or not address:
            flash("All fields are required.", "seller_error")
            cursor.close()
            conn.close()
            return redirect(url_for("seller_create"))

        # ✅ OTP check
        if not session.get("seller_otp_verified_create"):
            flash("OTP verification is required before submission.", "seller_error")
            cursor.close()
            conn.close()
            return redirect(url_for("seller_create"))

        cursor.execute("SELECT * FROM admins WHERE email = %s", (email,))
        existing_user = cursor.fetchone()
        if existing_user:
            flash("Email already exists.", "seller_error")
            cursor.close()
            conn.close()
            return redirect(url_for("seller_create"))

        default_password = "1234"
        password_hash = generate_password_hash(default_password)

        try:
            cursor.execute(
                """
                INSERT INTO admins (full_name, email, contact, address, password, role)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (full_name, email, contact, address, password_hash, "seller")
            )
            conn.commit()

            # ✅ Send welcome email
            subject = "Your Seller Account Credentials"
            body = f"""Hi {full_name},

Your seller account has been created successfully.

📧 Email: {email}
🔐 Default Password: {default_password}
🏠 Address: {address}

Please log in and change your password immediately from your account settings.

Best regards,
Yash Cyber Cafe Team
"""
            message = f"Subject: {subject}\n\n{body}"

            import smtplib, ssl
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
                server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                server.sendmail(EMAIL_ADDRESS, email, message)

            flash("✅ Seller user created and email sent with default credentials.", "seller_success")

            # ✅ Clear OTP session
            session.pop("seller_create_otp", None)
            session.pop("seller_create_email", None)
            session.pop("seller_otp_verified_create", None)
            session.pop("seller_otp_expiry_create", None)

        except Exception as e:
            print("Seller creation or email error:", e)
            flash("Seller created, but email sending failed.", "seller_error")

    # ✅ Always show list of sellers
    cursor.execute(
        "SELECT id, full_name, email, contact FROM admins WHERE role = 'seller'"
    )
    admins = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template("seller_create.html", user=user, admins=admins)


@app.route('/delete_seller/<int:seller_id>', methods=['POST'])
def delete_seller(seller_id):
    user = get_user()
    if not user or user.get('role') not in ['seller', 'owner']:
        flash("Unauthorized access.", "error")
        return redirect(url_for('user_home'))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("DELETE FROM admins WHERE id = %s AND role = 'seller'", (seller_id,))
    conn.commit()

    cursor.close()
    conn.close()

    flash("Seller deleted successfully.", "success")
    return redirect(url_for('seller_create'))

@app.route("/seller_settings", methods=["GET", "POST"])
def seller_settings():
    user = get_user()

    if not user:
        return redirect(url_for("seller_login"))

    if user.get("role") == "user":
        return redirect(url_for("user_home"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()

        if full_name:
            conn = get_mysql_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("UPDATE admins SET full_name = %s WHERE id = %s", (full_name, user["id"]))
            conn.commit()
            cursor.close()
            conn.close()

            # Update session
            session["user"]["full_name"] = full_name
            flash("Name updated successfully.", "success")
        else:
            flash("Name cannot be empty.", "error")

        return redirect(url_for("seller_settings"))

    return render_template("seller_settings.html", user=user)


@app.route("/change-sellerinfo", methods=["POST"])
def change_sellerinfo():
    user = get_user()
    if not user:
        flash("Session expired. Please log in again.", "error")
        return redirect(url_for("seller_login"))

    user_id = user.get("id")
    role = user.get("role")
    if role == "user":
        return redirect(url_for("user_home"))

    new_email = request.form.get("email", "").strip()
    otp = request.form.get("otp", "").strip()
    new_contact = request.form.get("contact", "").strip()

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    changes_made = False

    # ✅ Email update (requires OTP)
    if new_email and new_email != user["email"]:
        expected_otp = session.get("seller_otp_change")
        verified_flag = session.get("seller_otp_verified_change")

        if not expected_otp or not verified_flag or otp != expected_otp:
            cursor.close()
            conn.close()
            flash("❌ Invalid or missing OTP for email change.", "error")
            return redirect(url_for("seller_settings"))

        cursor.execute("UPDATE admins SET email = %s WHERE id = %s", (new_email, user_id))
        changes_made = True
        flash("✅ Email updated successfully.", "success")

        # Clear OTP session data
        session.pop("seller_otp_change", None)
        session.pop("seller_otp_email_change", None)
        session.pop("seller_otp_expiry_change", None)
        session.pop("seller_otp_verified_change", None)

    # ✅ Contact update (no OTP required)
    if new_contact and new_contact != user.get("contact"):
        cursor.execute("UPDATE admins SET contact = %s WHERE id = %s", (new_contact, user_id))
        changes_made = True
        flash("📞 Mobile number updated successfully.", "success")

    if changes_made:
        conn.commit()
        cursor.execute("SELECT * FROM admins WHERE id = %s", (user_id,))
        updated = cursor.fetchone()
        session["user"] = {
            "id": updated["id"],
            "email": updated["email"],
            "full_name": updated["full_name"],
            "contact": updated["contact"],
            "role": updated["role"]
        }
    else:
        flash("⚠️ No changes were made.", "warning")

    cursor.close()
    conn.close()
    return redirect(url_for("seller_settings"))


@app.route("/change-password", methods=["POST"])
def change_password():
    user = get_user()
    if not user:
        flash("Session expired. Please log in again.", "error")
        return redirect(url_for("seller_settings"))

    old_pw = request.form.get("old_password", "").strip()
    new_pw = request.form.get("new_password", "").strip()
    confirm_pw = request.form.get("confirm_password", "").strip()

    if not old_pw or not new_pw or not confirm_pw:
        flash("All fields are required.", "error")
        return redirect(url_for("seller_settings"))

    if new_pw != confirm_pw:
        flash("New password and confirmation do not match.", "error")
        return redirect(url_for("seller_settings"))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT password FROM admins WHERE email = %s", (user["email"],))
    row = cursor.fetchone()

    if not row:
        cursor.close()
        conn.close()
        flash("User not found.", "error")
        return redirect(url_for("seller_settings"))

    db_password = row["password"]

    if not check_password_hash(db_password, old_pw):
        cursor.close()
        conn.close()
        flash("Current password is incorrect.", "error")
        return redirect(url_for("seller_settings"))

    new_hashed = generate_password_hash(new_pw)
    cursor.execute("UPDATE admins SET password = %s WHERE email = %s", (new_hashed, user["email"]))
    conn.commit()

    cursor.close()
    conn.close()

    flash("Password updated successfully.", "success")
    return redirect(url_for("seller_settings"))


@app.route("/send-otp", methods=["POST"])
def send_seller_otp():
    data = request.json or {}
    email = data.get("email", "").strip()
    mode = data.get("mode", "create")  # 'create' or 'change'

    if not email:
        return jsonify(success=False, message="Email is required.")

    now = time.time()
    expiry_key = "seller_otp_expiry_" + mode
    otp_key = "seller_otp_" + mode
    email_key = "seller_otp_email_" + mode
    verified_key = "seller_otp_verified_" + mode

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT id FROM admins WHERE email = %s", (email,))
    existing = cursor.fetchone()

    if mode == "create" and existing:
        cursor.close()
        conn.close()
        return jsonify(success=False, message="⚠️ Email already exists. Choose another.")

    if mode == "change":
        user = get_user()
        if not user:
            cursor.close()
            conn.close()
            return jsonify(success=False, message="Session expired.")
        if email == user["email"]:
            cursor.close()
            conn.close()
            return jsonify(success=False, message="This is already your current email.")
        if existing:
            cursor.close()
            conn.close()
            return jsonify(success=False, message="Email already in use.")

    cursor.close()
    conn.close()

    if session.get(expiry_key, 0) > now:
        remaining = int((session[expiry_key] - now) // 60)
        return jsonify(success=False, message=f"OTP already sent. Try again after {remaining} min.")

    otp = generate_random_otp()
    session[otp_key] = otp
    session[email_key] = email
    session[expiry_key] = now + 300
    session[verified_key] = False

    if send_otp_to_email(email, otp):
        return jsonify(success=True)
    else:
        return jsonify(success=False, message="❌ Failed to send OTP.")

@app.route("/verify-otp", methods=["POST"])
def verify_seller_otp():
    data = request.json or {}
    user_otp = data.get("otp", "").strip()
    mode = data.get("mode", "create")  # 'create' or 'change'

    otp_key = "seller_otp_" + mode
    expiry_key = "seller_otp_expiry_" + mode
    verified_key = "seller_otp_verified_" + mode

    actual_otp = session.get(otp_key, "")
    expiry = session.get(expiry_key, 0)

    if time.time() > expiry:
        return jsonify(verified=False, message="OTP expired. Please request a new one.")

    if user_otp == actual_otp:
        session[verified_key] = True
        return jsonify(verified=True)

    return jsonify(verified=False, message="Incorrect OTP.")

# admin ====admin=======admin=============admin=============admin===================admin=============admin================admin=================admin=

@app.route("/admin_create", methods=["GET", "POST"])
def admin_create():
    user = get_user()

    if not user:
        return redirect(url_for("admin_login"))

    if user.get("role") == "user":
        return redirect(url_for("user_home"))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        contact = request.form.get("contact", "").strip()
        address = request.form.get("address", "").strip()

        if not full_name or not email or not contact or not address:
            flash("All fields are required.", "admin_error")
            cursor.close()
            conn.close()
            return redirect(url_for("admin_create"))

        # ✅ OTP check
        if not session.get("admin_otp_verified_create"):
            flash("OTP verification is required before submission.", "admin_error")
            cursor.close()
            conn.close()
            return redirect(url_for("admin_create"))

        cursor.execute("SELECT * FROM admins WHERE email = %s", (email,))
        existing_user = cursor.fetchone()
        if existing_user:
            flash("Email already exists.", "admin_error")
            cursor.close()
            conn.close()
            return redirect(url_for("admin_create"))

        default_password = "1234"
        password_hash = generate_password_hash(default_password)

        try:
            cursor.execute(
                """
                INSERT INTO admins (full_name, email, contact, address, password, role)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (full_name, email, contact, address, password_hash, "admin")
            )
            conn.commit()

            # ✅ Send welcome email
            subject = "Your Admin Account Credentials"
            body = f"""Hi {full_name},

Your admin account has been created successfully.

📧 Email: {email}
🔐 Default Password: {default_password}
🏠 Address: {address}

Please log in and change your password immediately from your account settings.

Best regards,
Yash Cyber Cafe Team
"""
            message = f"Subject: {subject}\n\n{body}"

            import smtplib, ssl
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
                server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                server.sendmail(EMAIL_ADDRESS, email, message)

            flash("✅ Admin user created and email sent with default credentials.", "admin_success")

            # ✅ Clear OTP session
            session.pop("admin_create_otp", None)
            session.pop("admin_create_email", None)
            session.pop("admin_otp_verified_create", None)
            session.pop("admin_otp_expiry_create", None)

        except Exception as e:
            print("Admin creation or email error:", e)
            flash("Admin created, but email sending failed.", "admin_error")

    # ✅ Always show list of admins
    cursor.execute(
        "SELECT id, full_name, email, contact FROM admins WHERE role = 'admin'"
    )
    admins = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("admin_create.html", user=user, admins=admins)


@app.route('/delete_admin/<int:admin_id>', methods=['POST'])
def delete_admin(admin_id):
    user = get_user()
    if not user or user.get('role') not in ['admin', 'owner']:
        flash("Unauthorized access.", "error")
        return redirect(url_for('user_home'))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("DELETE FROM admins WHERE id = %s AND role = 'admin'", (admin_id,))
    conn.commit()

    cursor.close()
    conn.close()

    flash("Admin deleted successfully.", "success")
    return redirect(url_for('admin_create'))


@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    # ✅ Redirect only if already logged in as admin/owner
    user = session.get("user")
    if user and user.get("role") in ("admin", "owner"):
        return redirect(url_for("admin_lookup"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        if not email or not password:
            flash("Please enter both email and password.", "error")
            return redirect(url_for("admin_login"))

        conn = get_mysql_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM admins WHERE LOWER(email) = %s", (email,))
        admin = cursor.fetchone()
        cursor.close()
        conn.close()

        if not admin:
            flash("❌ Invalid email or password.", "error")
            return redirect(url_for("admin_login"))

        if not check_password_hash(admin["password"], password):
            flash("❌ Invalid email or password.", "error")
            return redirect(url_for("admin_login"))

        role = admin.get("role", "user")
        if role not in ("admin", "owner"):
            flash("❌ You are not authorized to log in as Admin.", "error")
            return redirect(url_for("admin_login"))

        session["user_id"] = admin["id"]
        session["user"] = {
            "email": admin["email"],
            "role": role,
            "full_name": admin["full_name"]
        }

        return redirect(url_for("admin_lookup"))

    return render_template("admin_login.html")


@app.route("/admin_lookup")
def admin_lookup():
    user = get_user()
    if not user or user.get("role") not in ("admin", "owner"):
        return redirect(url_for("admin_login"))
    return render_template("admin_lookup.html", user=user)


@app.route("/api/seller/<int:id>")
def api_seller(id):
    try:
        conn = get_mysql_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, full_name, email, contact, address FROM admins WHERE id = %s AND role = 'seller'",
            (id,)
        )
        seller = cursor.fetchone()
        cursor.close()
        conn.close()

        if not seller:
            return jsonify({"success": False, "message": "Seller not found"})

        return jsonify({"success": True, "details": seller})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/product/<int:id>")
def api_product(id):
    try:
        conn = get_mysql_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, name, price, discount_price, seller_id FROM products WHERE id = %s",
            (id,)
        )
        product = cursor.fetchone()
        cursor.close()
        conn.close()

        if not product:
            return jsonify({"success": False, "message": "Product not found"})

        return jsonify({"success": True, "details": product})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/order/<int:id>")
def api_order(id):
    try:
        conn = get_mysql_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM orders WHERE id = %s", (id,))
        order = cursor.fetchone()
        cursor.close()
        conn.close()

        if not order:
            return jsonify({"success": False, "message": "Order not found"})

        return jsonify({"success": True, "details": order})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/user/<int:id>")
def api_user(id):
    try:
        conn = get_mysql_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, full_name, email, contact FROM users WHERE id = %s",
            (id,)
        )
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if not user:
            return jsonify({"success": False, "message": "User not found"})

        return jsonify({"success": True, "details": user})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# 🔁 Impersonation Helpers

def impersonate_seller(seller_id):
    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM admins WHERE id = %s AND role = 'seller'", (seller_id,))
    seller = cursor.fetchone()
    cursor.close()
    conn.close()
    return seller


@app.route("/admin/seller-panel/<int:id>/dashboard")
def admin_seller_dashboard(id):
    seller = impersonate_seller(id)
    if not seller:
        flash("Seller not found", "error")
        return redirect(url_for("admin_lookup"))

    session["user_id"] = seller["id"]
    session["user"] = {
        "email": seller["email"],
        "role": "seller",
        "full_name": seller["full_name"]
    }
    return redirect(url_for("seller_dashboard"))


@app.route("/admin/seller-panel/<int:id>/orders")
def admin_seller_orders(id):
    seller = impersonate_seller(id)
    if not seller:
        flash("Seller not found", "error")
        return redirect(url_for("admin_lookup"))

    session["user_id"] = seller["id"]
    session["user"] = {
        "email": seller["email"],
        "role": "seller",
        "full_name": seller["full_name"]
    }
    return redirect(url_for("seller_orders"))


@app.route("/admin/seller-panel/<int:id>/products")
def admin_seller_products(id):
    seller = impersonate_seller(id)
    if not seller:
        flash("Seller not found", "error")
        return redirect(url_for("admin_lookup"))

    session["user_id"] = seller["id"]
    session["user"] = {
        "email": seller["email"],
        "role": "seller",
        "full_name": seller["full_name"]
    }
    return redirect(url_for("seller_products"))


@app.route("/admin/seller-panel/<int:id>/contact")
def admin_seller_contact(id):
    seller = impersonate_seller(id)
    if not seller:
        flash("Seller not found", "error")
        return redirect(url_for("admin_lookup"))

    session["user_id"] = seller["id"]
    session["user"] = {
        "email": seller["email"],
        "role": "seller",
        "full_name": seller["full_name"]
    }
    return redirect(url_for("seller_contact"))


@app.route("/admin/seller-panel/<int:id>/settings")
def admin_seller_settings(id):
    seller = impersonate_seller(id)
    if not seller:
        flash("Seller not found", "error")
        return redirect(url_for("admin_lookup"))

    session["user_id"] = seller["id"]
    session["user"] = {
        "email": seller["email"],
        "role": "seller",
        "full_name": seller["full_name"]
    }
    return redirect(url_for("seller_settings"))


def impersonate_user(user_id):
    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user


@app.route("/admin/user-panel/<int:id>/home")
def admin_user_home(id):
    user = impersonate_user(id)
    if not user:
        flash("User not found", "error")
        return redirect(url_for("admin_lookup"))

    session["user_id"] = user["id"]
    session["user"] = {
        "email": user["email"],
        "role": "user",
        "full_name": user["full_name"]
    }
    return redirect(url_for("user_home"))


@app.route("/admin/user-panel/<int:id>/shop")
def admin_user_shop(id):
    user = impersonate_user(id)
    if not user:
        flash("User not found", "error")
        return redirect(url_for("admin_lookup"))

    session["user_id"] = user["id"]
    session["user"] = {
        "email": user["email"],
        "role": "user",
        "full_name": user["full_name"]
    }
    return redirect(url_for("shop"))  # or use the appropriate route if named differently


@app.route("/admin/user-panel/<int:id>/categories")
def admin_user_categories(id):
    user = impersonate_user(id)
    if not user:
        flash("User not found", "error")
        return redirect(url_for("admin_lookup"))

    session["user_id"] = user["id"]
    session["user"] = {
        "email": user["email"],
        "role": "user",
        "full_name": user["full_name"]
    }
    return redirect(url_for("categories"))


@app.route("/admin/user-panel/<int:id>/orders")
def admin_user_orders(id):
    user = impersonate_user(id)
    if not user:
        flash("User not found", "error")
        return redirect(url_for("admin_lookup"))

    session["user_id"] = user["id"]
    session["user"] = {
        "email": user["email"],
        "role": "user",
        "full_name": user["full_name"]
    }
    return redirect(url_for("my_orders"))


@app.route("/admin/user-panel/<int:id>/profile")
def admin_user_profile(id):
    user = impersonate_user(id)
    if not user:
        flash("User not found", "error")
        return redirect(url_for("admin_lookup"))

    session["user_id"] = user["id"]
    session["user"] = {
        "email": user["email"],
        "role": "user",
        "full_name": user["full_name"]
    }
    return redirect(url_for("account"))


@app.route("/admin/user-panel/<int:id>/cart")
def admin_user_cart(id):
    user = impersonate_user(id)
    if not user:
        flash("User not found", "error")
        return redirect(url_for("admin_lookup"))

    session["user_id"] = user["id"]
    session["user"] = {
        "email": user["email"],
        "role": "user",
        "full_name": user["full_name"]
    }
    return redirect(url_for("cart"))


@app.route("/admin/user-panel/<int:id>/settings")
def admin_user_settings(id):
    user = impersonate_user(id)
    if not user:
        flash("User not found", "error")
        return redirect(url_for("admin_lookup"))

    session["user_id"] = user["id"]
    session["user"] = {
        "email": user["email"],
        "role": "user",
        "full_name": user["full_name"]
    }
    return redirect(url_for("setting"))

# misclaneous ====misclaneous=======misclaneous=============misclaneous=============misclaneous===================misclaneous=============misclaneous================misclaneous=================misclaneous=

def fetch_all(table_name):
    allowed_tables = ["users", "orders", "products", "admins", "carts", "morders", "movies"]
    
    if table_name not in allowed_tables:
        return [] 

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM `{table_name}`")
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return data

@app.route("/view")
def view_all():
    data = {
        "users": fetch_all("users"),
        "orders": fetch_all("orders"),
        "products": fetch_all("products"),
        "admins": fetch_all("admins"),
        "carts": fetch_all("carts"),
        "morders": fetch_all("morders"),
        "movies": fetch_all("movies"),
    }
    return render_template("view.html", data=data)

@app.route("/logout")
def logout():
    user = session.get("user")
    role = user.get("role") if user else None

    session.pop("user", None)
    session.pop("user_id", None)

    if role in ("seller", "owner"):
        return redirect(url_for("seller_login"))

    user_agent = request.headers.get('User-Agent', '').lower()
    is_mobile = any(x in user_agent for x in ["mobi", "android", "iphone"])

    return redirect("/user_shop" if is_mobile else url_for("user_home"))

# ✅ Movies Hub
@app.route("/movieshub")
def movieshub():
    user = get_user()

    # ✅ Redirect sellers to their dashboard
    if user and user.get("role") == "seller":
        return redirect(url_for("seller_dashboard"))

    query = request.args.get("q", "").strip().lower()
    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        if query:
            cursor.execute("""
                SELECT id, name, price, discount_price, images, description
                FROM movies
                WHERE is_visible = 1
                  AND (LOWER(name) LIKE %s OR LOWER(description) LIKE %s)
                ORDER BY created_at DESC
            """, (f"%{query}%", f"%{query}%"))
        else:
            cursor.execute("""
                SELECT id, name, price, discount_price, images, description
                FROM movies
                WHERE is_visible = 1
                ORDER BY created_at DESC
            """)

        rows = cursor.fetchall()
    except Exception as e:
        print("⚠️ Movies fetch error:", e)
        rows = []

    movie_items = []
    for row in rows:
        try:
            # ✅ Safely load JSON image list or single image
            images = json.loads(row["images"]) if row["images"] and row["images"].strip().startswith("[") else [row["images"]]
        except Exception:
            images = [row["images"]] if row.get("images") else []

        try:
            discount_price = float(row["discount_price"] or 0)
        except Exception:
            discount_price = 0.0

        movie_items.append({
            "id": row["id"],
            "name": row.get("name", ""),
            "price": float(row.get("price", 0)),
            "discount_price": discount_price,
            "images": images,
            "description": row.get("description", "")
        })

    cursor.close()
    conn.close()

    return render_template(
        "movieshub.html",
        user=user,
        full_name=user["full_name"] if user else None,
        movie_items=movie_items,
        query=query
    )

@app.route('/movieshub_details/<int:movie_id>')
def movieshub_details(movie_id):
    user = session.get("user")
    if user and user.get("role") == "seller":
        return redirect(url_for("seller_dashboard"))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM movies WHERE id = %s", (movie_id,))
    movie = cursor.fetchone()
    cursor.close()
    conn.close()

    if not movie:
        flash("Movie not found", "error")
        return redirect(url_for('movieshub'))

    try:
        images_raw = movie.get('images', '')
        if images_raw and images_raw.strip().startswith("["):
            images = json.loads(images_raw)
        else:
            images = [img.strip() for img in images_raw.split(',') if img.strip()]
    except Exception as e:
        print("Image parse error:", e)
        images = []

    movie_data = {
        'id': movie['id'],
        'name': movie['name'],
        'description': movie.get('description', ''),
        'price': float(movie.get('price') or 0),
        'discount_price': float(movie.get('discount_price') or 0),
        'images': images
    }

    return render_template('movieshub_details.html', movie=movie_data, user=user)

# ✅ Movie Checkout
@app.route('/user_checkoutm/<int:movie_id>')
def user_checkoutm(movie_id):
    user = session.get("user")
    if user and user["role"] == "seller":
        return redirect(url_for("seller_dashboard"))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM movies WHERE id = %s", (movie_id,))
    movie = cursor.fetchone()

    if not movie:
        conn.close()
        flash("Movie not found.", "error")
        return redirect(url_for("movieshub"))

    try:
        images = json.loads(movie["images"]) if movie["images"] and movie["images"].strip().startswith("[") else [
            img.strip() for img in movie["images"].split(",") if img.strip()
        ]
    except:
        images = []

    price = float(movie["discount_price"] or movie["price"] or 0)
    qty = 1
    subtotal = price * qty
    handling_fee = round(subtotal * 0.02, 2)
    total = subtotal + handling_fee

    latest_order = {}
    if user:
        cursor.execute("""
            SELECT * FROM morders
            WHERE user_email = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (user.get("email"),))
        result = cursor.fetchone()
        if result:
            latest_order = dict(result)

    latest_order["state"] = latest_order.get("state", "Chhattisgarh")
    conn.close()

    return render_template(
        "user_checkoutm.html",
        user=user,
        movie={
            "id": movie["id"],
            "name": movie["name"],
            "description": movie["description"],
            "price": price,
            "images": images
        },
        qty=qty,
        subtotal=subtotal,
        handling_fee=handling_fee,
        total=total,
        is_buy_now=True,
        order=latest_order
    )
    
@app.route('/create_payment_m', methods=["POST"])
def create_payment_m():
    data = request.get_json()
    total = float(data.get("total", 0))
    form = data.get("form", {})
    movie = data.get("movie", {})
    qty = int(data.get("qty", 1))

    if total <= 0 or not movie:
        return jsonify({"error": "Invalid payment request"}), 400

    amount_in_paise = int(total * 100)

    razorpay_order = client.order.create({
        "amount": amount_in_paise,
        "currency": "INR",
        "payment_capture": "1"
    })

    session["buy_movie"] = movie
    session["buy_qty"] = qty
    session["checkout_form"] = form

    return jsonify({
        "order_id": razorpay_order["id"],
        "amount": amount_in_paise,
        "key_id": "rzp_live_Bs8iGWDy31UcPw",
        "name": form.get("full_name", ""),
        "email": form.get("email", ""),
        "contact": form.get("phone", "")
    })

@app.route("/payment_success_m", methods=["POST"])
def payment_success_m():
    data = request.get_json()
    payment_id = data.get("payment_id")
    movie = data.get("movie")
    qty = int(data.get("qty", 1))
    form = data.get("form")

    if not payment_id or not movie or not form:
        return jsonify({"success": False, "error": "Missing payment ID or data"}), 400

    created_at = datetime.now().strftime("%d %b %Y, %I:%M %p")
    user = get_user()
    user_id = user["id"] if user else None
    user_email = user["email"] if user and "email" in user else "guest@example.com"

    try:
        conn = get_mysql_connection()
        cursor = conn.cursor(dictionary=True)

        prod_conn = get_mysql_connection()
        prod_cursor = prod_conn.cursor(dictionary=True)

        movie_id = movie.get("id")
        name = movie.get("name", "Unknown movie")
        price = float(movie.get("price", 0))
        total = price * qty

        # ✅ Fetch movie record
        prod_cursor.execute("SELECT * FROM movies WHERE id = %s", (movie_id,))
        movie_row = prod_cursor.fetchone()
        if not movie_row:
            prod_cursor.close()
            prod_conn.close()
            cursor.close()
            conn.close()
            return jsonify({"success": False, "error": "Movie not found"}), 404

        # ✅ Extract image
        try:
            raw = movie_row.get("images", "")
            images = json.loads(raw) if raw.strip().startswith("[") else [
                x.strip() for x in raw.split(",") if x.strip()
            ]
            image = images[0] if images else "default.jpg"
        except:
            image = "default.jpg"

        seller_id = movie_row.get("seller_id", 1)
        link1 = movie_row.get("link1", "")
        link2 = movie_row.get("link2", "")
        link3 = movie_row.get("link3", "")
        link4 = movie_row.get("link4", "")

        # ✅ Insert into MySQL morders
        cursor.execute("""
            INSERT INTO morders (
                item_id, item_name, quantity, amount, status, order_date,
                user_id, user_name, user_contact, user_email, image,
                created_at, seller_id, is_paid, payment_id,
                link1, link2, link3, link4
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            movie_id, name, qty, total, "accepted", "",
            user_id, form.get("full_name", ""), form.get("phone", ""), user_email,
            image, created_at, seller_id, 1, payment_id,
            link1, link2, link3, link4
        ))
        conn.commit()

        # ✅ Get last order id
        cursor.execute(
            "SELECT id FROM morders WHERE payment_id = %s ORDER BY id DESC LIMIT 1",
            (payment_id,)
        )
        last_order = cursor.fetchone()
        order_id = last_order["id"] if last_order else None

        prod_cursor.close()
        prod_conn.close()
        cursor.close()
        conn.close()

        if order_id:
            return jsonify({
                "success": True,
                "redirect_url": url_for("payment_success_page", order_id=order_id)
            })
        else:
            return jsonify({"success": False, "error": "Order not found"}), 400

    except Exception as e:
        print("⚠️ Insert failed:", e)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/payment_success/<int:order_id>')
def payment_success_page(order_id):
    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM morders WHERE id = %s", (order_id,))
    order = cursor.fetchone()

    cursor.close()
    conn.close()

    if not order:
        flash("Order not found.", "error")
        return redirect(url_for("user_orders"))

    return render_template("payment_success.html", order=order)

@app.route('/m_contact', methods=["GET", "POST"])
def m_contact():
    user = get_user()

    if user and user.get("role") in ("seller"):
        return redirect(url_for("seller_dashboard"))

    if request.method == "POST":
        flash("Messaging system is disabled.", "info")

    return render_template("m_contact.html", full_name=user["full_name"] if user else "", user=user)

@app.route("/m_policy")
def m_policy():
    user = get_user()
    return render_template("m_policy.html", user=user)

@app.route("/m_about")
def m_about():
    user = get_user()
    return render_template("m_about.html", user=user)

@app.route("/m_terms")
def m_terms():
    user = get_user()
    return render_template("m_terms.html", user=user)

@app.route("/m_refund")
def m_refund():
    user = get_user()
    return render_template("m_refund.html", user=user)

@app.route("/m_privacy")
def m_privacy():
    user = get_user()
    return render_template("m_privacy.html", user=user)

@app.route("/wp")
def wp():
    user = get_user()
    return render_template("wp.html", user=user)

# seller and owners route ====seller and owners route=======seller and owners route=============seller and owners route=============seller and owners route===================seller and owners route======

@app.route("/seller_morders")
def seller_morders():
    user = get_user()

    if not user:
        return redirect(url_for("seller_login"))
    if user.get("role") == "user":
        return redirect(url_for("movieshub"))

    status_filter = request.args.get("status")
    date_filter = request.args.get("date")

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    # ✅ Make sure table name matches your DB
    query = "SELECT * FROM morders WHERE 1=1"
    params = []

    if user.get('role') == 'seller':
        query += " AND seller_id = %s"
        params.append(user.get('id'))

    if status_filter:
        query += " AND status = %s"
        params.append(status_filter)

    if date_filter:
        # Change `order_date` if your column is named differently
        query += " AND DATE(order_date) = %s"
        params.append(date_filter)

    query += " ORDER BY id DESC"

    cursor.execute(query, params)
    morders = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "seller_morders.html",
        user=user,
        full_name=user.get("full_name", ""),
        morders=morders,
        selected_status=status_filter or "",
        selected_date=date_filter or ""
    )


@app.route('/delete_morder/<int:order_id>', methods=['POST'])
def delete_morder(order_id):
    user = get_user()
    if not user or user.get('role') != 'owner':
        flash("Unauthorized", "error")
        return redirect(url_for('movieshub'))

    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM morders WHERE id = %s", (order_id,))
    conn.commit()
    cursor.close()
    conn.close()

    flash("Order deleted successfully.", "success")
    return redirect(url_for('seller_morders'))


# ✅ SELLER MOVIES (ADD / VIEW)
@app.route("/seller_movies", methods=["GET", "POST"])
def seller_movies():
    user = get_user()
    if not user:
        return redirect(url_for("seller_login"))
    if user.get("role") == "user":
        return redirect(url_for("movieshub"))

    full_name = user.get("full_name", "Guest")
    is_owner = user.get("role") == "owner"

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        link1 = request.form.get("link1", "")
        link2 = request.form.get("link2", "")
        link3 = request.form.get("link3", "")
        link4 = request.form.get("link4", "")
        price = request.form.get("price", "0").strip()
        discount_price = request.form.get("discount_price", "0").strip()
        is_visible = int(request.form.get("is_visible", 1))
        image_files = request.files.getlist("images")

        if not name or not price:
            flash("Movie name and price are required.", "error")
            return redirect(url_for("seller_movies"))

        if not image_files or image_files[0].filename == "":
            flash("Please upload at least one image.", "error")
            return redirect(url_for("seller_movies"))

        upload_folder = os.path.join(current_app.root_path, "static/uploads")
        os.makedirs(upload_folder, exist_ok=True)

        filenames = []
        for image in image_files:
            if image and allowed_file(image.filename):
                filename = f"{uuid.uuid4().hex}_{secure_filename(image.filename)}"
                image.save(os.path.join(upload_folder, filename))
                filenames.append(filename)
            else:
                flash("Invalid image file type.", "error")
                return redirect(url_for("seller_movies"))

        try:
            cursor.execute("""
                INSERT INTO movies
                (name, description, link1, link2, link3, link4, price, discount_price, images, seller_id, is_visible, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            """, (
                name, description, link1, link2, link3, link4,
                float(price), float(discount_price or 0),
                json.dumps(filenames), user["id"], is_visible
            ))
            conn.commit()
            flash("Movie added successfully!", "success")
        except Exception as e:
            print("⚠️ Add movie error:", e)
            conn.rollback()
            flash("Database error while adding movie.", "error")

        return redirect(url_for("seller_movies"))

    # ✅ GET - Show all movies
    try:
        if is_owner:
            cursor.execute("SELECT * FROM movies ORDER BY id DESC")
        else:
            cursor.execute("SELECT * FROM movies WHERE seller_id=%s ORDER BY id DESC", (user["id"],))
        rows = cursor.fetchall()
    except Exception as e:
        print("⚠️ Fetch movies error:", e)
        rows = []

    movie_items = []
    for row in rows:
        try:
            imgs = json.loads(row["images"]) if row["images"] and row["images"].strip().startswith("[") else [row["images"]]
        except Exception:
            imgs = ["default.jpg"]
        movie_items.append({
            "id": row["id"],
            "name": row.get("name", ""),
            "description": row.get("description", ""),
            "link1": row.get("link1", ""),
            "link2": row.get("link2", ""),
            "link3": row.get("link3", ""),
            "link4": row.get("link4", ""),
            "price": row.get("price", 0),
            "discount_price": row.get("discount_price", 0),
            "images": imgs,
            "is_visible": row.get("is_visible", 1),
            "created_at": row.get("created_at", "")
        })

    cursor.close()
    conn.close()

    return render_template("seller_movies.html",
                           movie_items=movie_items,
                           full_name=full_name,
                           user=user)


# ✅ EDIT MOVIE
@app.route("/edit_movie/<int:item_id>", methods=["POST"])
def edit_movie(item_id):
    user = get_user()
    if not user or user["role"] not in ["seller", "owner"]:
        flash("Unauthorized access.", "error")
        return redirect(url_for("seller_movies"))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT images, seller_id FROM movies WHERE id=%s", (item_id,))
    movie = cursor.fetchone()

    if not movie:
        flash("Movie not found.", "error")
        return redirect(url_for("seller_movies"))

    if user["role"] == "seller" and movie["seller_id"] != user["id"]:
        flash("You cannot edit this movie.", "error")
        return redirect(url_for("seller_movies"))

    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    link1 = request.form.get("link1", "")
    link2 = request.form.get("link2", "")
    link3 = request.form.get("link3", "")
    link4 = request.form.get("link4", "")
    is_visible = int(request.form.get("is_visible", 1))
    image_files = request.files.getlist("images")

    try:
        price = float(request.form.get("price", "0").strip())
        discount_price = float(request.form.get("discount_price", "0").strip() or 0)
    except ValueError:
        flash("Invalid price or discount value.", "error")
        return redirect(url_for("seller_movies"))

    upload_folder = os.path.join(current_app.root_path, "static/uploads")
    os.makedirs(upload_folder, exist_ok=True)

    try:
        old_images = json.loads(movie["images"]) if movie["images"] and movie["images"].strip().startswith("[") else [movie["images"]]
    except Exception:
        old_images = []

    new_filenames = old_images

    # ✅ Replace images if new ones are uploaded
    if image_files and image_files[0].filename != "":
        for img in old_images:
            old_path = os.path.join(upload_folder, img)
            if os.path.exists(old_path):
                os.remove(old_path)

        new_filenames = []
        for image in image_files:
            if image and allowed_file(image.filename):
                filename = f"{uuid.uuid4().hex}_{secure_filename(image.filename)}"
                image.save(os.path.join(upload_folder, filename))
                new_filenames.append(filename)
            else:
                flash("Invalid image file type.", "error")
                return redirect(url_for("seller_movies"))

    try:
        cursor.execute("""
            UPDATE movies
            SET name=%s, description=%s, link1=%s, link2=%s, link3=%s, link4=%s,
                price=%s, discount_price=%s, images=%s, is_visible=%s
            WHERE id=%s
        """, (
            name, description, link1, link2, link3, link4,
            price, discount_price, json.dumps(new_filenames), is_visible, item_id
        ))
        conn.commit()
        flash("Movie updated successfully!", "success")
    except Exception as e:
        print("⚠️ Edit movie error:", e)
        conn.rollback()
        flash("Database error while updating movie.", "error")

    cursor.close()
    conn.close()
    return redirect(url_for("seller_movies"))


# ✅ DELETE MOVIE
@app.route("/delete_movie/<int:item_id>", methods=["POST"])
def delete_movie(item_id):
    user = get_user()
    if not user or user["role"] not in ["seller", "owner"]:
        flash("Unauthorized access.", "error")
        return redirect(url_for("seller_movies"))

    conn = get_mysql_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT images, seller_id FROM movies WHERE id=%s", (item_id,))
    movie = cursor.fetchone()

    if not movie:
        flash("Movie not found.", "error")
        cursor.close()
        conn.close()
        return redirect(url_for("seller_movies"))

    if user["role"] == "seller" and movie["seller_id"] != user["id"]:
        flash("You cannot delete this movie.", "error")
        cursor.close()
        conn.close()
        return redirect(url_for("seller_movies"))

    upload_folder = os.path.join(current_app.root_path, "static/uploads")

    try:
        raw = movie["images"]
        images = json.loads(raw) if raw and raw.strip().startswith("[") else [x.strip() for x in raw.split(",") if x.strip()]
        for img in images:
            img_path = os.path.join(upload_folder, img)
            if os.path.exists(img_path):
                os.remove(img_path)
    except Exception as e:
        print("⚠️ Image deletion error:", e)

    try:
        cursor.execute("DELETE FROM movies WHERE id=%s", (item_id,))
        conn.commit()
        flash("Movie deleted successfully!", "success")
    except Exception as e:
        print("⚠️ Delete movie error:", e)
        conn.rollback()
        flash("Error deleting movie from database.", "error")

    cursor.close()
    conn.close()
    return redirect(url_for("seller_movies"))

@app.route("/qr")
def qr():
    user = get_user()
    return render_template("qr.html", user=user)

if __name__ == "__main__":
    app.run(debug=True)
