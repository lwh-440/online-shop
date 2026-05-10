from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, abort
from flask_mysqldb import MySQL
from flask_mail import Mail, Message
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
import datetime
import json
import random
import string
from config import Config
from utils.database import init_db, get_db_connection
from utils.helpers import allowed_file, save_image, delete_image, dict_to_product, rows_to_products, dict_to_user, rows_to_users, check_password_strength
from utils.logger import log_operation, log_login
from utils.recommend import update_similarities, get_recommendations, get_interest_recommendations

app = Flask(__name__)
app.config.from_object(Config)

mysql = MySQL(app)
mail = Mail(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = '请先登录'

# ---------- 权限装饰器 ----------
def role_required(*roles):
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ---------- User 类 ----------
class User:
    def __init__(self, id, username, email, role='customer'):
        self.id = id
        self.username = username
        self.email = email
        self.role = role

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_sales(self):
        return self.role in ('sales', 'admin')

    def get_id(self):
        return str(self.id)

    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user_row = cursor.fetchone()
    cursor.close()
    conn.close()
    if user_row:
        return User(user_row['id'], user_row['username'], user_row['email'], user_row.get('role', 'customer'))
    return None

# ---------- 首页 ----------
@app.route('/')
def index():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM products WHERE stock > 0 ORDER BY created_at DESC LIMIT 8")
    products_rows = cursor.fetchall()
    cursor.close()
    conn.close()
    products = rows_to_products(products_rows)
    return render_template('index.html', products=products)

# ---------- 发送验证码 ----------
def generate_code():
    return ''.join(random.choices(string.digits, k=6))

@app.route('/send_code', methods=['POST'])
def send_code():
    email = request.json.get('email')
    if not email:
        return jsonify({'status': 'error', 'message': '邮箱不能为空'})
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
    if cursor.fetchone():
        cursor.close()
        conn.close()
        return jsonify({'status': 'error', 'message': '邮箱已注册'})
    cursor.close()
    conn.close()

    code = generate_code()
    session['verify_code'] = code
    session['verify_email'] = email
    try:
        msg = Message('验证码 - 在线购物网站',
                      sender=app.config['MAIL_DEFAULT_SENDER'],
                      recipients=[email])
        msg.body = f'您的验证码是：{code}，5分钟内有效。'
        mail.send(msg)
        return jsonify({'status': 'ok', 'message': '验证码已发送'})
    except Exception as e:
        print(e)
        return jsonify({'status': 'error', 'message': '邮件发送失败，请稍后重试'})

# ---------- 登录 ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user_row = cursor.fetchone()
        cursor.close()
        conn.close()
        user = dict_to_user(user_row)
        if user and check_password_hash(user['password'], password):
            user_obj = User(user['id'], user['username'], user['email'], user.get('role', 'customer'))
            login_user(user_obj, remember=True)
            flash('登录成功', 'success')
            log_login(user_obj.id, 'login')
            return redirect(url_for('index'))
        else:
            flash('用户名或密码错误', 'error')
    return render_template('auth/login.html')

# ---------- 注册 ----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        code = request.form.get('code', '')

        # 验证码检查
        if code != session.get('verify_code') or email != session.get('verify_email'):
            flash('验证码错误或已过期', 'error')
            return render_template('auth/register.html')

        # 密码强度检查
        ok, msg = check_password_strength(password)
        if not ok:
            flash(msg, 'error')
            return render_template('auth/register.html')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s OR email = %s", (username, email))
        if cursor.fetchone():
            flash('用户名或邮箱已存在', 'error')
            return render_template('auth/register.html')

        hashed_password = generate_password_hash(password)
        cursor.execute(
            "INSERT INTO users (username, email, password, role, created_at) VALUES (%s, %s, %s, %s, %s)",
            (username, email, hashed_password, 'customer', datetime.datetime.now())
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash('注册成功，请登录', 'success')
        return redirect(url_for('login'))
    return render_template('auth/register.html')

# ---------- 登出 ----------
@app.route('/logout')
@login_required
def logout():
    log_login(current_user.id, 'logout')
    logout_user()
    flash('已退出登录', 'success')
    return redirect(url_for('index'))

# ---------- 商品列表 ----------
@app.route('/products')
def product_list():
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    query = "SELECT * FROM products WHERE stock > 0"
    params = []
    if search:
        query += " AND name LIKE %s"
        params.append(f'%{search}%')
    if category:
        query += " AND category = %s"
        params.append(category)
    query += " ORDER BY created_at DESC"
    cursor.execute(query, params)
    products_rows = cursor.fetchall()
    cursor.close()
    conn.close()
    products = rows_to_products(products_rows)
    return render_template('product/list.html', products=products, search=search, category=category)

# ---------- 商品详情（含双推荐）----------
@app.route('/product/<int:product_id>')
def product_detail(product_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
    product_row = cursor.fetchone()
    product = dict_to_product(product_row)
    if not product:
        flash('商品不存在', 'error')
        return redirect(url_for('product_list'))

    # 订单共现推荐（购买了此商品的人也买过）
    similar_rows = get_recommendations(product_id, limit=4)
    similar_products = []
    for row in similar_rows:
        d = dict_to_product(row)
        d['score'] = row['score']
        similar_products.append(d)

    # 猜你感兴趣推荐
    interest_rows = get_interest_recommendations(product_id, limit=4)
    interest_products = []
    for row in interest_rows:
        d = dict_to_product(row)
        d['total_duration'] = row.get('total_duration', 0)
        d['last_view_time'] = row.get('last_view_time')
        interest_products.append(d)

    cursor.close()
    conn.close()
    return render_template('product/detail.html',
                           product=product,
                           recommendations=similar_products,
                           interest_products=interest_products)

# ---------- 浏览记录 API ----------
@app.route('/api/browsing/start', methods=['POST'])
def browsing_start():
    data = request.get_json()
    if not data or 'product_id' not in data:
        return jsonify({'error': 'Invalid data'}), 400
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = current_user.id if current_user.is_authenticated else None
    session_id = session.get('session_id', request.remote_addr)
    start_time = datetime.datetime.now()
    cursor.execute("""
        INSERT INTO browsing_logs (user_id, session_id, product_id, start_time)
        VALUES (%s, %s, %s, %s)
    """, (user_id, session_id, data['product_id'], start_time))
    log_id = cursor.lastrowid
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'log_id': log_id})

@app.route('/api/browsing/end', methods=['POST'])
def browsing_end():
    data = request.get_json()
    if not data or 'log_id' not in data:
        return jsonify({'error': 'Invalid data'}), 400
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    end_time = datetime.datetime.now()
    cursor.execute("""
        UPDATE browsing_logs
        SET end_time = %s, duration = TIMESTAMPDIFF(SECOND, start_time, %s)
        WHERE id = %s
    """, (end_time, end_time, data['log_id']))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True})

# ---------- 购物车 ----------
@app.route('/cart')
@login_required
def cart():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT c.*, p.name, p.price, p.image_url, p.stock
        FROM cart_items c
        JOIN products p ON c.product_id = p.id
        WHERE c.user_id = %s
    """, (current_user.id,))
    cart_items_rows = cursor.fetchall()
    cursor.close()
    conn.close()

    cart_items = []
    for row in cart_items_rows:
        cart_items.append({
            'id': row['id'],
            'user_id': row['user_id'],
            'product_id': row['product_id'],
            'quantity': int(row['quantity']),
            'name': row['name'],
            'price': float(row['price']),
            'image_url': row['image_url'],
            'stock': int(row['stock'])
        })
    total = sum(item['price'] * item['quantity'] for item in cart_items)
    return render_template('cart/cart.html', cart_items=cart_items, total=total)

@app.route('/add_to_cart', methods=['POST'])
@login_required
def add_to_cart():
    product_id = request.form['product_id']
    quantity = int(request.form.get('quantity', 1))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT stock FROM products WHERE id = %s", (product_id,))
    product = cursor.fetchone()
    if not product or int(product['stock']) < quantity:
        flash('库存不足', 'error')
        cursor.close()
        conn.close()
        return redirect(url_for('product_detail', product_id=product_id))
    cursor.execute("SELECT * FROM cart_items WHERE user_id = %s AND product_id = %s",
                   (current_user.id, product_id))
    existing = cursor.fetchone()
    if existing:
        new_qty = int(existing['quantity']) + quantity
        cursor.execute("UPDATE cart_items SET quantity = %s WHERE id = %s", (new_qty, existing['id']))
    else:
        cursor.execute("INSERT INTO cart_items (user_id, product_id, quantity) VALUES (%s, %s, %s)",
                       (current_user.id, product_id, quantity))
    conn.commit()
    cursor.close()
    conn.close()
    flash('商品已添加到购物车', 'success')
    return redirect(url_for('cart'))

@app.route('/update_cart', methods=['POST'])
@login_required
def update_cart():
    cart_item_id = request.form['cart_item_id']
    quantity = int(request.form['quantity'])
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    if quantity <= 0:
        cursor.execute("DELETE FROM cart_items WHERE id = %s AND user_id = %s", (cart_item_id, current_user.id))
    else:
        cursor.execute("UPDATE cart_items SET quantity = %s WHERE id = %s AND user_id = %s",
                       (quantity, cart_item_id, current_user.id))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('cart'))

# ---------- 结算 ----------
@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT c.*, p.name, p.price, p.stock, p.image_url
        FROM cart_items c
        JOIN products p ON c.product_id = p.id
        WHERE c.user_id = %s
    """, (current_user.id,))
    cart_rows = cursor.fetchall()
    cart_items = []
    for row in cart_rows:
        cart_items.append({
            'id': row['id'],
            'user_id': row['user_id'],
            'product_id': row['product_id'],
            'quantity': int(row['quantity']),
            'name': row['name'],
            'price': float(row['price']),
            'stock': int(row['stock']),
            'image_url': row['image_url']
        })
    total = sum(item['price'] * item['quantity'] for item in cart_items)

    if request.method == 'POST':
        address = request.form['address']
        phone = request.form['phone']
        if not cart_items:
            flash('购物车为空', 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('cart'))
        for item in cart_items:
            if item['stock'] < item['quantity']:
                flash(f'商品"{item["name"]}"库存不足', 'error')
                cursor.close()
                conn.close()
                return redirect(url_for('cart'))

        cursor.execute(
            "INSERT INTO orders (user_id, total_amount, status, address, phone, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
            (current_user.id, total, 'pending', address, phone, datetime.datetime.now())
        )
        order_id = cursor.lastrowid

        for item in cart_items:
            cursor.execute(
                "INSERT INTO order_items (order_id, product_id, quantity, price) VALUES (%s, %s, %s, %s)",
                (order_id, item['product_id'], item['quantity'], item['price'])
            )
            cursor.execute("UPDATE products SET stock = stock - %s WHERE id = %s",
                           (item['quantity'], item['product_id']))

        cursor.execute("DELETE FROM cart_items WHERE user_id = %s", (current_user.id,))
        conn.commit()
        log_operation('create_order', f'订单 #{order_id} 金额 {total}')
        cursor.close()
        conn.close()

        try:
            msg = Message('订单确认 - 在线购物网站',
                          sender=app.config['MAIL_DEFAULT_SENDER'],
                          recipients=[current_user.email])
            msg.body = f'尊敬的 {current_user.username}：\n\n感谢您的订单！订单号：{order_id}\n总金额：¥{total:.2f}\n收货地址：{address}\n联系电话：{phone}\n\n我们将尽快处理您的订单。'
            mail.send(msg)
        except Exception as e:
            print(f"邮件发送失败: {e}")

        flash('订单创建成功！已发送确认邮件', 'success')
        return redirect(url_for('order_history'))

    cursor.close()
    conn.close()
    return render_template('order/checkout.html', cart_items=cart_items, total=total)

# ---------- 用户订单 ----------
@app.route('/orders')
@login_required
def order_history():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM orders WHERE user_id = %s ORDER BY created_at DESC", (current_user.id,))
    orders_rows = cursor.fetchall()
    cursor.close()
    conn.close()
    orders = []
    for row in orders_rows:
        created_at = row['created_at']
        if isinstance(created_at, str):
            try:
                created_at = datetime.datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                pass
        orders.append({
            'id': row['id'],
            'total_amount': float(row['total_amount']),
            'status': row['status'],
            'address': row['address'],
            'phone': row['phone'],
            'created_at': created_at
        })
    return render_template('order/history.html', orders=orders)

@app.route('/order/<int:order_id>')
@login_required
def order_detail(order_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM orders WHERE id = %s AND user_id = %s", (order_id, current_user.id))
    order_row = cursor.fetchone()
    if not order_row:
        flash('订单不存在', 'error')
        cursor.close()
        conn.close()
        return redirect(url_for('order_history'))
    created_at = order_row['created_at']
    if isinstance(created_at, str):
        try:
            created_at = datetime.datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            pass
    order = {
        'id': order_row['id'],
        'total_amount': float(order_row['total_amount']),
        'status': order_row['status'],
        'address': order_row['address'],
        'phone': order_row['phone'],
        'created_at': created_at
    }
    cursor.execute("""
        SELECT oi.*, p.name, p.image_url
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE oi.order_id = %s
    """, (order_id,))
    items_rows = cursor.fetchall()
    items = []
    for row in items_rows:
        items.append({
            'id': row['id'],
            'product_id': row['product_id'],
            'quantity': int(row['quantity']),
            'price': float(row['price']),
            'name': row['name'],
            'image_url': row['image_url']
        })
    cursor.close()
    conn.close()
    return render_template('order/detail.html', order=order, items=items)

# ---------- 付款 ----------
@app.route('/order/pay/<int:order_id>', methods=['GET', 'POST'])
@login_required
def pay_order(order_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM orders WHERE id = %s AND user_id = %s", (order_id, current_user.id))
    order = cursor.fetchone()
    if not order or order['status'] != 'pending':
        flash('订单状态不允许付款', 'error')
        return redirect(url_for('order_history'))

    if request.method == 'POST':
        cursor.execute("UPDATE orders SET status = 'paid' WHERE id = %s", (order_id,))
        conn.commit()
        cursor.close()
        conn.close()
        flash('付款成功', 'success')
        return redirect(url_for('order_detail', order_id=order_id))

    cursor.close()
    conn.close()
    return render_template('order/pay.html', order=order)

# ---------- 收货 ----------
@app.route('/order/receive/<int:order_id>')
@login_required
def receive_order(order_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM orders WHERE id = %s AND user_id = %s", (order_id, current_user.id))
    order = cursor.fetchone()
    if not order or order['status'] != 'shipped':
        flash('订单当前状态不可收货', 'error')
        cursor.close()
        conn.close()
        return redirect(url_for('order_history'))
    cursor.execute("UPDATE orders SET status = 'completed' WHERE id = %s", (order_id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash('已确认收货', 'success')
    return redirect(url_for('order_detail', order_id=order_id))

# ---------- 退款申请 ----------
@app.route('/order/refund/<int:order_id>', methods=['GET', 'POST'])
@login_required
def refund_order(order_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM orders WHERE id = %s AND user_id = %s", (order_id, current_user.id))
    order = cursor.fetchone()
    if not order:
        flash('订单不存在', 'error')
        cursor.close()
        conn.close()
        return redirect(url_for('order_history'))

    allowed_status = ['paid', 'shipped']
    if order['status'] not in allowed_status:
        flash('当前状态不可退款', 'error')
        cursor.close()
        conn.close()
        return redirect(url_for('order_history'))

    if request.method == 'POST':
        refund_type = request.form.get('refund_type', 'only_refund')
        reason = request.form.get('reason', '')
        evidence_file = request.files.get('evidence')
        evidence_path = None
        if evidence_file and allowed_file(evidence_file.filename):
            filename = save_image(evidence_file)
            evidence_path = f'uploads/refunds/{filename}'

        prev_status = order['status']
        cursor.execute(
            "UPDATE orders SET status = 'refunding', prev_status = %s, refund_reason = %s, refund_type = %s, refund_evidence = %s WHERE id = %s",
            (prev_status, reason, refund_type, evidence_path, order_id)
        )
        conn.commit()
        cursor.close()
        conn.close()

        log_operation('apply_refund', f'用户申请退款订单 #{order_id}，类型：{refund_type}，原因：{reason}')
        flash('退款申请已提交，等待审核', 'success')
        return redirect(url_for('order_detail', order_id=order_id))

    cursor.close()
    conn.close()
    return render_template('order/refund.html', order=order)
# ---------- 管理员退款审核 ----------
@app.route('/admin/refund_review/<int:order_id>', methods=['POST'])
@role_required('admin')
def refund_review(order_id):
    action = request.form.get('action')
    reason = request.form.get('reason', '')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM orders WHERE id = %s AND status = 'refunding'", (order_id,))
    order = cursor.fetchone()
    if not order:
        flash('订单状态异常', 'error')
        cursor.close()
        conn.close()
        return redirect(url_for('admin_orders'))

    if action == 'approve':
        cursor.execute("UPDATE orders SET status = 'refunded' WHERE id = %s", (order_id,))
        flash('退款已批准', 'success')
    elif action == 'reject':
        # 恢复到退款前的状态
        prev = order.get('prev_status') or 'paid'   # 默认回退到已付款（兜底）
        cursor.execute("UPDATE orders SET status = %s WHERE id = %s", (prev, order_id))
        log_operation('refund_reject', f'拒绝订单 #{order_id} 退款，原因：{reason}，恢复为 {prev}')
        flash(f'退款已拒绝，订单恢复为“{prev}”状态', 'warning')
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('admin_orders'))
# ---------- 管理仪表盘 ----------
@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_admin and not current_user.is_sales:
        flash('无权访问', 'error')
        return redirect(url_for('index'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT COUNT(*) as count FROM products")
    product_count = cursor.fetchone()['count']
    cursor.execute("SELECT COUNT(*) as count FROM orders")
    order_count = cursor.fetchone()['count']
    cursor.execute("SELECT COUNT(*) as count FROM users")
    user_count = cursor.fetchone()['count']
    cursor.execute("SELECT SUM(total_amount) as revenue FROM orders WHERE status = 'completed'")
    revenue = float(cursor.fetchone()['revenue'] or 0)

    # 异常检测
    cursor.execute("SELECT COALESCE(SUM(total_amount),0) as revenue FROM orders WHERE DATE(created_at) = CURDATE() AND status = 'completed'")
    today_rev = float(cursor.fetchone()['revenue'])
    cursor.execute("""
        SELECT AVG(daily.revenue) as avg_rev FROM (
            SELECT SUM(total_amount) as revenue FROM orders WHERE status = 'completed' AND created_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY) GROUP BY DATE(created_at)
        ) daily
    """)
    avg_7d = float(cursor.fetchone()['avg_rev'] or 0)
    anomaly = None
    if avg_7d > 0 and today_rev > avg_7d * 2:
        anomaly = {'today_sales': today_rev, 'avg_7d': avg_7d, 'ratio': today_rev / avg_7d}

    cursor.close()
    conn.close()
    return render_template('admin/dashboard.html', product_count=product_count, order_count=order_count, user_count=user_count, revenue=revenue, anomaly=anomaly)

# ---------- 商品管理（销售/admin）----------
@app.route('/admin/products', methods=['GET', 'POST'])
@role_required('sales', 'admin')
def admin_products():
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        price = float(request.form['price'])
        stock = int(request.form['stock'])
        category = request.form['category']
        image_url = 'images/default-product.jpg'
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = save_image(file)
                image_url = f'uploads/products/{filename}'
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        seller_id = current_user.id if current_user.role == 'sales' else None
        cursor.execute(
            "INSERT INTO products (name, description, price, stock, category, image_url, seller_id, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (name, description, price, stock, category, image_url, seller_id, datetime.datetime.now())
        )
        conn.commit()
        cursor.close()
        conn.close()
        log_operation('add_product', f'添加商品 {name}')
        flash('商品添加成功', 'success')
        return redirect(url_for('admin_products'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    # 根据角色过滤商品
    if current_user.role == 'admin':
        cursor.execute("SELECT p.*, u.username as seller_name FROM products p LEFT JOIN users u ON p.seller_id = u.id ORDER BY p.created_at DESC")
    else:
        # 销售人员只看到自己的商品
        cursor.execute("SELECT p.*, u.username as seller_name FROM products p LEFT JOIN users u ON p.seller_id = u.id WHERE p.seller_id = %s ORDER BY p.created_at DESC", (current_user.id,))
    products_rows = cursor.fetchall()
    cursor.close()
    conn.close()

    # 为每个产品附加 seller_id 和安全标识
    products = []
    for row in products_rows:
        p = dict_to_product(row)
        p['seller_id'] = row.get('seller_id')
        p['seller_name'] = row.get('seller_name', '-')
        # 当前用户是否可以编辑/删除（管理员或本人）
        p['can_edit'] = (current_user.role == 'admin' or p['seller_id'] == current_user.id)
        products.append(p)

    return render_template('admin/product_manage.html', products=products,
                           current_user_role=current_user.role,
                           current_user_id=current_user.id)

@app.route('/admin/product/edit/<int:product_id>', methods=['GET', 'POST'])
@role_required('sales', 'admin')
def edit_product(product_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 获取商品信息
    cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
    product_row = cursor.fetchone()
    product = dict_to_product(product_row)
    if not product:
        flash('商品不存在', 'error')
        cursor.close()
        conn.close()
        return redirect(url_for('admin_products'))

    # 权限检查：管理员或商品负责人
    if current_user.role != 'admin' and product.get('seller_id') != current_user.id:
        flash('没有权限编辑此商品', 'error')
        cursor.close()
        conn.close()
        return redirect(url_for('admin_products'))

    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        price = float(request.form['price'])
        stock = int(request.form['stock'])
        category = request.form['category']
        image_url = request.form.get('current_image')
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                if image_url and 'default-product' not in image_url:
                    delete_image(image_url)
                filename = save_image(file)
                image_url = f'uploads/products/{filename}'
        cursor.execute("UPDATE products SET name=%s, description=%s, price=%s, stock=%s, category=%s, image_url=%s WHERE id=%s",
                       (name, description, price, stock, category, image_url, product_id))
        conn.commit()
        cursor.close()
        conn.close()
        log_operation('edit_product', f'编辑商品 #{product_id}')
        flash('商品更新成功', 'success')
        return redirect(url_for('admin_products'))

    cursor.close()
    conn.close()
    return render_template('admin/product_edit.html', product=product)

@app.route('/admin/product/delete/<int:product_id>')
@role_required('sales', 'admin')
def delete_product(product_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
    product = cursor.fetchone()
    if not product:
        flash('商品不存在', 'error')
        cursor.close()
        conn.close()
        return redirect(url_for('admin_products'))

    # 权限检查：管理员或商品负责人
    if current_user.role != 'admin' and product['seller_id'] != current_user.id:
        flash('没有权限删除此商品', 'error')
        cursor.close()
        conn.close()
        return redirect(url_for('admin_products'))

    if product['image_url'] and 'default-product' not in product['image_url']:
        delete_image(product['image_url'])
    cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))
    conn.commit()
    cursor.close()
    conn.close()
    log_operation('delete_product', f'删除商品 #{product_id}')
    flash('商品删除成功', 'success')
    return redirect(url_for('admin_products'))
# ---------- 订单管理（销售/admin）----------
@app.route('/admin/orders')
@role_required('sales', 'admin')
def admin_orders():
    status = request.args.get('status', '')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    query = "SELECT o.*, u.username FROM orders o JOIN users u ON o.user_id = u.id"
    params = []
    if status:
        query += " WHERE o.status = %s"
        params.append(status)
    query += " ORDER BY o.created_at DESC"
    cursor.execute(query, params)
    orders_rows = cursor.fetchall()
    cursor.close()
    conn.close()
    orders = []
    for row in orders_rows:
        created_at = row['created_at']
        if isinstance(created_at, str):
            try:
                created_at = datetime.datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                pass
        orders.append({
            'id': row['id'],
            'total_amount': float(row['total_amount']),
            'status': row['status'],
            'address': row['address'],
            'phone': row['phone'],
            'created_at': created_at,
            'username': row['username']
        })
    return render_template('admin/order_manage.html', orders=orders, status=status)

@app.route('/admin/refund_detail/<int:order_id>', methods=['GET', 'POST'])
@role_required('admin')
def refund_detail(order_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT o.*, u.username FROM orders o JOIN users u ON o.user_id = u.id WHERE o.id = %s", (order_id,))
    order = cursor.fetchone()
    if not order or order['status'] != 'refunding':
        flash('订单状态异常或不存在', 'error')
        cursor.close()
        conn.close()
        return redirect(url_for('admin_orders'))

    if request.method == 'POST':
        action = request.form.get('action')
        reject_reason = request.form.get('reject_reason', '')
        if action == 'approve':
            cursor.execute("UPDATE orders SET status = 'refunded' WHERE id = %s", (order_id,))
            flash('退款已批准', 'success')
        elif action == 'reject':
            prev = order.get('prev_status') or 'paid'
            cursor.execute("UPDATE orders SET status = %s WHERE id = %s", (prev, order_id))
            log_operation('refund_reject', f'拒绝订单 #{order_id} 退款，理由：{reject_reason}，恢复为 {prev}')
            flash(f'退款已拒绝，订单恢复为“{prev}”状态', 'warning')
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('admin_orders'))

    # GET：显示退款详情
    cursor.close()
    conn.close()
    return render_template('admin/refund_detail.html', order=order)

@app.route('/admin/order/update_status', methods=['POST'])
@role_required('sales', 'admin')
def update_order_status():
    order_id = request.form['order_id']
    status = request.form['status']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("UPDATE orders SET status = %s WHERE id = %s", (status, order_id))
    if status == 'shipped':
        cursor.execute("SELECT u.email, u.username FROM orders o JOIN users u ON o.user_id = u.id WHERE o.id = %s", (order_id,))
        info = cursor.fetchone()
        if info:
            try:
                msg = Message('订单已发货', sender=app.config['MAIL_DEFAULT_SENDER'], recipients=[info['email']])
                msg.body = f'尊敬的 {info["username"]}：\n您的订单 #{order_id} 已发货，请注意查收。'
                mail.send(msg)
            except Exception as e:
                print(f"邮件发送失败: {e}")
    conn.commit()
    cursor.close()
    conn.close()
    log_operation('update_order_status', f'订单 #{order_id} 状态更新为 {status}')
    return jsonify({'success': True, 'message': '订单状态更新成功'})

# ---------- 销售统计 ----------
@app.route('/admin/stats')
@login_required
def admin_stats():
    if not current_user.is_admin and not current_user.is_sales:
        flash('无权访问', 'error')
        return redirect(url_for('index'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT DATE(created_at) as date, COUNT(*) as order_count, SUM(total_amount) as revenue
        FROM orders WHERE status = 'completed'
        GROUP BY DATE(created_at) ORDER BY date DESC LIMIT 30
    """)
    sales_data_rows = cursor.fetchall()
    sales_data = []
    for row in sales_data_rows:
        sales_data.append({
            'date': str(row['date']),
            'order_count': int(row['order_count']),
            'revenue': float(row['revenue']) if row['revenue'] else 0.0
        })

    cursor.execute("""
        SELECT p.name, SUM(oi.quantity) as total_sold
        FROM order_items oi JOIN products p ON oi.product_id = p.id
        JOIN orders o ON oi.order_id = o.id
        WHERE o.status = 'completed'
        GROUP BY p.id, p.name ORDER BY total_sold DESC LIMIT 10
    """)
    popular_rows = cursor.fetchall()
    popular_products = [{'name': r['name'], 'total_sold': int(r['total_sold']) if r['total_sold'] else 0} for r in popular_rows]

    chart_dates = [d['date'] for d in sales_data]
    chart_revenues = [d['revenue'] for d in sales_data]
    chart_orders = [d['order_count'] for d in sales_data]

    cursor.close()
    conn.close()
    return render_template('admin/stats.html', sales_data=sales_data, popular_products=popular_products, chart_dates=chart_dates, chart_revenues=chart_revenues, chart_orders=chart_orders)

# ---------- 用户管理（仅管理员）----------
@app.route('/admin/users')
@role_required('admin')
def admin_users():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, username, email, role, created_at FROM users WHERE role IN ('sales', 'admin') ORDER BY created_at")
    users_rows = cursor.fetchall()
    cursor.close()
    conn.close()
    users = []
    for row in users_rows:
        created_at = row['created_at']
        if isinstance(created_at, str):
            try:
                created_at = datetime.datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                pass
        users.append({'id': row['id'], 'username': row['username'], 'email': row['email'], 'role': row['role'], 'created_at': created_at})
    return render_template('admin/user_manage.html', users=users)

@app.route('/admin/user/add', methods=['POST'])
@role_required('admin')
def add_user():
    username = request.form['username']
    email = request.form['email']
    password = request.form['password']
    role = request.form.get('role', 'sales')
    if role not in ('sales', 'admin'):
        flash('无效的角色', 'error')
        return redirect(url_for('admin_users'))
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    hashed_password = generate_password_hash(password)
    cursor.execute("INSERT INTO users (username, email, password, role) VALUES (%s, %s, %s, %s)", (username, email, hashed_password, role))
    conn.commit()
    cursor.close()
    conn.close()
    log_operation('add_user', f'管理员添加用户 {username}（角色 {role}）')
    flash('用户添加成功', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/user/reset_password/<int:user_id>', methods=['POST'])
@role_required('admin')
def reset_password(user_id):
    new_password = request.form['new_password']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    hashed_password = generate_password_hash(new_password)
    cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_password, user_id))
    conn.commit()
    cursor.close()
    conn.close()
    log_operation('reset_password', f'管理员重置用户 #{user_id} 密码')
    flash('密码重置成功', 'success')
    return redirect(url_for('admin_users'))

# ---------- 销售业绩（按商品归属）----------
@app.route('/admin/sales_performance')
@role_required('admin')
def sales_performance():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT u.id, u.username,
               COUNT(DISTINCT oi.id) as order_count,
               COALESCE(SUM(oi.quantity * oi.price), 0) as total_revenue
        FROM users u
        JOIN products p ON p.seller_id = u.id
        JOIN order_items oi ON oi.product_id = p.id
        JOIN orders o ON o.id = oi.order_id AND o.status = 'completed'
        WHERE u.role = 'sales'
        GROUP BY u.id, u.username
        ORDER BY total_revenue DESC
    """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    performance = []
    for row in rows:
        performance.append({
            'id': row['id'],
            'username': row['username'],
            'order_count': int(row['order_count']),
            'total_revenue': float(row['total_revenue'])
        })
    return render_template('admin/sales_performance.html', performance=performance)

# ---------- 浏览日志 ----------
@app.route('/admin/logs/browsing')
@role_required('sales', 'admin')
def browsing_logs():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page-1)*per_page
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT bl.*, COALESCE(u.username, '匿名') as username, p.name as product_name
        FROM browsing_logs bl
        LEFT JOIN users u ON bl.user_id = u.id
        LEFT JOIN products p ON bl.product_id = p.id
        ORDER BY bl.start_time DESC
        LIMIT %s OFFSET %s
    """, (per_page, offset))
    logs = cursor.fetchall()
    cursor.close()
    conn.close()
    for log in logs:
        for time_field in ['start_time', 'end_time']:
            if log.get(time_field) and isinstance(log[time_field], str):
                try:
                    log[time_field] = datetime.datetime.strptime(log[time_field], '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    pass
    return render_template('admin/browsing_logs.html', logs=logs, page=page)

# ---------- 操作日志 ----------
@app.route('/admin/logs/operation')
@role_required('sales', 'admin')
def operation_logs():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page-1)*per_page
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT ol.*, u.username
        FROM operation_logs ol
        LEFT JOIN users u ON ol.user_id = u.id
        ORDER BY ol.created_at DESC
        LIMIT %s OFFSET %s
    """, (per_page, offset))
    logs = cursor.fetchall()
    cursor.close()
    conn.close()
    for log in logs:
        if log.get('created_at') and isinstance(log['created_at'], str):
            try:
                log['created_at'] = datetime.datetime.strptime(log['created_at'], '%Y-%m-%d %H:%M:%S')
            except ValueError:
                pass
    return render_template('admin/operation_logs.html', logs=logs, page=page)

# ---------- 数据大屏 ----------
@app.route('/admin/bigscreen')
@role_required('admin')
def admin_bigscreen():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT COUNT(*) as count, COALESCE(SUM(total_amount),0) as revenue FROM orders WHERE DATE(created_at) = CURDATE()")
    today = cursor.fetchone()
    today_sales = int(today['count']) if today['count'] else 0
    today_revenue = float(today['revenue']) if today['revenue'] else 0.0
    cursor.execute("SELECT COUNT(*) as count FROM users")
    total_users = int(cursor.fetchone()['count'])
    cursor.execute("SELECT COUNT(*) as count FROM products WHERE stock > 0")
    total_products = int(cursor.fetchone()['count'])
    cursor.execute("""
        SELECT DATE(created_at) as date, COUNT(*) as order_count, SUM(total_amount) as revenue
        FROM orders WHERE status = 'completed'
        GROUP BY DATE(created_at) ORDER BY date DESC LIMIT 7
    """)
    trend_rows = cursor.fetchall()
    chart_dates = [str(r['date']) for r in reversed(trend_rows)]
    chart_revenues = [float(r['revenue']) if r['revenue'] else 0.0 for r in reversed(trend_rows)]
    cursor.execute("SELECT category, COUNT(*) as count FROM products WHERE stock > 0 GROUP BY category")
    cat_rows = cursor.fetchall()
    category_data = [{'name': r['category'], 'value': int(r['count'])} for r in cat_rows]
    cursor.execute("""
        SELECT o.id, o.total_amount, o.created_at, u.username
        FROM orders o JOIN users u ON o.user_id = u.id
        ORDER BY o.created_at DESC LIMIT 10
    """)
    recent_orders_rows = cursor.fetchall()
    recent_orders = []
    for row in recent_orders_rows:
        recent_orders.append({
            'id': row['id'],
            'total_amount': float(row['total_amount']),
            'created_at': row['created_at'],
            'username': row['username']
        })
    cursor.execute("""
        SELECT p.name, SUM(oi.quantity) as total_sold
        FROM order_items oi JOIN products p ON oi.product_id = p.id
        JOIN orders o ON oi.order_id = o.id
        WHERE o.status = 'completed'
        GROUP BY p.id, p.name ORDER BY total_sold DESC LIMIT 5
    """)
    popular_rows = cursor.fetchall()
    popular_products = [{'name': r['name'], 'total_sold': int(r['total_sold']) if r['total_sold'] else 0} for r in popular_rows]
    cursor.close()
    conn.close()
    return render_template('admin/bigscreen.html', today_sales=today_sales, today_revenue=today_revenue, total_users=total_users, total_products=total_products, chart_dates=chart_dates, chart_revenues=chart_revenues, category_data=category_data, recent_orders=recent_orders, popular_products=popular_products)

# ---------- 推荐相似度更新 ----------
@app.route('/admin/update_similarities')
@role_required('admin')
def trigger_update_similarities():
    update_similarities()
    flash('商品相似度更新完成', 'success')
    return redirect(url_for('admin_dashboard'))

# ---------- 错误处理 ----------
@app.errorhandler(403)
def forbidden(e):
    flash('您没有权限访问此页面', 'error')
    return redirect(url_for('index'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)