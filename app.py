from utils.helpers import rows_to_products, dict_to_product, rows_to_users, dict_to_user
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_mysqldb import MySQL
from flask_mail import Mail, Message
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import os
import datetime
from config import Config
from utils.database import init_db, get_db_connection
from utils.helpers import allowed_file, save_image, delete_image

app = Flask(__name__)
app.config.from_object(Config)

# 初始化扩展
mysql = MySQL(app)
mail = Mail(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = '请先登录'

# 用户加载回调
@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user_row = cursor.fetchone()
    cursor.close()
    conn.close()
    
    user = dict_to_user(user_row)
    if user:
        return User(user['id'], user['username'], user['email'], user['is_admin'])
    return None

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user_row = cursor.fetchone()
        cursor.close()
        conn.close()
        
        user = dict_to_user(user_row)
        if user and check_password_hash(user['password'], password):
            user_obj = User(user['id'], user['username'], user['email'], user['is_admin'])
            login_user(user_obj, remember=True)
            flash('登录成功', 'success')
            return redirect(url_for('index'))
        else:
            flash('用户名或密码错误', 'error')
    
    return render_template('auth/login.html')

class User:
    def __init__(self, id, username, email, is_admin=False):
        self.id = id
        self.username = username
        self.email = email
        self.is_admin = is_admin

    def get_id(self):
        return str(self.id)

    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

# 路由定义
@app.route('/')
def index():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE stock > 0 ORDER BY created_at DESC LIMIT 8")
    products_rows = cursor.fetchall()
    cursor.close()
    conn.close()
    
    # 转换查询结果为字典格式
    products = rows_to_products(products_rows)
    return render_template('index.html', products=products)

# 用户认证路由
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 检查用户是否已存在
        cursor.execute("SELECT * FROM users WHERE username = %s OR email = %s", (username, email))
        existing_user = cursor.fetchone()
        
        if existing_user:
            flash('用户名或邮箱已存在', 'error')
            return render_template('auth/register.html')
        
        # 创建新用户
        hashed_password = generate_password_hash(password)
        cursor.execute(
            "INSERT INTO users (username, email, password, created_at) VALUES (%s, %s, %s, %s)",
            (username, email, hashed_password, datetime.datetime.now())
        )
        conn.commit()
        cursor.close()
        conn.close()
        
        flash('注册成功，请登录', 'success')
        return redirect(url_for('login'))
    
    return render_template('auth/register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('已退出登录', 'success')
    return redirect(url_for('index'))

# 商品展示路由
@app.route('/products')
def product_list():
    search = request.args.get('search', '')
    category_id = request.args.get('category_id', '')
    
    # 获取分类列表
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM categories ORDER BY name")
    categories_rows = cursor.fetchall()
    
    categories = []
    for row in categories_rows:
        if isinstance(row, tuple):
            keys = ['id', 'name', 'description', 'created_at']
            categories.append(dict(zip(keys, row)))
        else:
            categories.append(row)
    
    # 构建商品查询
    query = """
        SELECT p.*, c.name as category_name 
        FROM products p 
        LEFT JOIN categories c ON p.category_id = c.id 
        WHERE p.stock > 0
    """
    params = []
    
    if search:
        query += " AND p.name LIKE %s"
        params.append(f'%{search}%')
    
    if category_id:
        query += " AND p.category_id = %s"
        params.append(category_id)
    
    query += " ORDER BY p.created_at DESC"
    
    cursor.execute(query, params)
    products_rows = cursor.fetchall()
    cursor.close()
    conn.close()
    
    # 转换商品数据
    products = []
    for row in products_rows:
        if isinstance(row, tuple):
            keys = ['id', 'name', 'description', 'price', 'stock', 'category_id', 'image_url', 'created_at', 'category_name']
            products.append(dict(zip(keys, row)))
        else:
            products.append(row)
    
    return render_template('product/list.html', 
                         products=products, 
                         categories=categories,
                         search=search, 
                         category_id=category_id)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
    product_row = cursor.fetchone()
    cursor.close()
    conn.close()
    
    product = dict_to_product(product_row)
    
    if not product:
        flash('商品不存在', 'error')
        return redirect(url_for('product_list'))
    
    return render_template('product/detail.html', product=product)

# 购物车路由
@app.route('/cart')
@login_required
def cart():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, p.name, p.price, p.image_url, p.stock 
        FROM cart_items c 
        JOIN products p ON c.product_id = p.id 
        WHERE c.user_id = %s
    """, (current_user.id,))
    cart_items_rows = cursor.fetchall()
    cursor.close()
    conn.close()
    
    # 转换购物车项目
    cart_items = []
    for row in cart_items_rows:
        if isinstance(row, tuple):
            # 根据查询的字段顺序创建字典
            keys = ['id', 'user_id', 'product_id', 'quantity', 'created_at', 'name', 'price', 'image_url', 'stock']
            cart_items.append(dict(zip(keys, row)))
        else:
            cart_items.append(row)
    
    total = sum(item['price'] * item['quantity'] for item in cart_items)
    return render_template('cart/cart.html', cart_items=cart_items, total=total)

@app.route('/add_to_cart', methods=['POST'])
@login_required
def add_to_cart():
    product_id = request.form['product_id']
    quantity = int(request.form.get('quantity', 1))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 检查商品库存 - 修复这里
    cursor.execute("SELECT stock FROM products WHERE id = %s", (product_id,))
    product_row = cursor.fetchone()
    
    # 转换查询结果为字典格式
    if product_row:
        if isinstance(product_row, tuple):
            product = {'stock': product_row[0]}  # 使用索引访问元组
        else:
            product = product_row
    else:
        product = None
    
    if not product or product['stock'] < quantity:
        flash('库存不足', 'error')
        return redirect(url_for('product_detail', product_id=product_id))
    
    # 检查购物车是否已有该商品
    cursor.execute("SELECT * FROM cart_items WHERE user_id = %s AND product_id = %s", 
                  (current_user.id, product_id))
    existing_item = cursor.fetchone()
    
    if existing_item:
        # 转换现有购物车项
        if isinstance(existing_item, tuple):
            keys = ['id', 'user_id', 'product_id', 'quantity', 'created_at']
            existing_item_dict = dict(zip(keys, existing_item))
        else:
            existing_item_dict = existing_item
            
        new_quantity = existing_item_dict['quantity'] + quantity
        cursor.execute("UPDATE cart_items SET quantity = %s WHERE id = %s", 
                      (new_quantity, existing_item_dict['id']))
    else:
        cursor.execute(
            "INSERT INTO cart_items (user_id, product_id, quantity) VALUES (%s, %s, %s)",
            (current_user.id, product_id, quantity)
        )
    
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
    
    if quantity <= 0:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cart_items WHERE id = %s AND user_id = %s", 
                      (cart_item_id, current_user.id))
        conn.commit()
        cursor.close()
        conn.close()
    else:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE cart_items SET quantity = %s WHERE id = %s AND user_id = %s", 
                      (quantity, cart_item_id, current_user.id))
        conn.commit()
        cursor.close()
        conn.close()
    
    return redirect(url_for('cart'))

# 订单路由
@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    if request.method == 'POST':
        address = request.form['address']
        phone = request.form['phone']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取购物车商品
        cursor.execute("""
            SELECT c.*, p.name, p.price, p.stock 
            FROM cart_items c 
            JOIN products p ON c.product_id = p.id 
            WHERE c.user_id = %s
        """, (current_user.id,))
        cart_items_rows = cursor.fetchall()
        
        if not cart_items_rows:
            flash('购物车为空', 'error')
            return redirect(url_for('cart'))
        
        # 转换购物车项目
        cart_items = []
        for row in cart_items_rows:
            if isinstance(row, tuple):
                keys = ['id', 'user_id', 'product_id', 'quantity', 'created_at', 'name', 'price', 'stock']
                cart_items.append(dict(zip(keys, row)))
            else:
                cart_items.append(row)
        
        # 检查库存
        for item in cart_items:
            if item['stock'] < item['quantity']:
                flash(f'商品"{item["name"]}"库存不足', 'error')
                return redirect(url_for('cart'))
        
        # 创建订单
        total_amount = sum(item['price'] * item['quantity'] for item in cart_items)
        cursor.execute(
            "INSERT INTO orders (user_id, total_amount, status, address, phone, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
            (current_user.id, total_amount, 'pending', address, phone, datetime.datetime.now())
        )
        order_id = cursor.lastrowid
        
        # 创建订单项并更新库存
        for item in cart_items:
            cursor.execute(
                "INSERT INTO order_items (order_id, product_id, quantity, price) VALUES (%s, %s, %s, %s)",
                (order_id, item['product_id'], item['quantity'], item['price'])
            )
            cursor.execute(
                "UPDATE products SET stock = stock - %s WHERE id = %s",
                (item['quantity'], item['product_id'])
            )
        
        # 清空购物车
        cursor.execute("DELETE FROM cart_items WHERE user_id = %s", (current_user.id,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        # 发送确认邮件
        try:
            msg = Message('订单确认 - 在线购物网站',
                         sender=app.config['MAIL_DEFAULT_SENDER'],
                         recipients=[current_user.email])
            msg.body = f'''
尊敬的 {current_user.username}：

感谢您的订单！订单号：{order_id}
总金额：¥{total_amount:.2f}
收货地址：{address}
联系电话：{phone}

我们将尽快处理您的订单。
'''
            mail.send(msg)
        except Exception as e:
            print(f"邮件发送失败: {e}")
        
        flash('订单创建成功！已发送确认邮件', 'success')
        return redirect(url_for('order_history'))
    
    # GET请求：显示结算页面，需要传递购物车数据
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, p.name, p.price, p.image_url, p.stock 
        FROM cart_items c 
        JOIN products p ON c.product_id = p.id 
        WHERE c.user_id = %s
    """, (current_user.id,))
    cart_items_rows = cursor.fetchall()
    cursor.close()
    conn.close()
    
    # 转换购物车项目
    cart_items = []
    for row in cart_items_rows:
        if isinstance(row, tuple):
            # 根据查询的字段顺序创建字典
            keys = ['id', 'user_id', 'product_id', 'quantity', 'created_at', 'name', 'price', 'image_url', 'stock']
            cart_items.append(dict(zip(keys, row)))
        else:
            cart_items.append(row)
    
    total = sum(item['price'] * item['quantity'] for item in cart_items)
    
    return render_template('order/checkout.html', cart_items=cart_items, total=total)


@app.route('/orders')
@login_required
def order_history():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE user_id = %s ORDER BY created_at DESC", 
                  (current_user.id,))
    orders_rows = cursor.fetchall()
    cursor.close()
    conn.close()
    
    # 转换订单数据
    orders = []
    for row in orders_rows:
        if isinstance(row, tuple):
            keys = ['id', 'user_id', 'total_amount', 'status', 'address', 'phone', 'created_at']
            orders.append(dict(zip(keys, row)))
        else:
            orders.append(row)
            
    return render_template('order/history.html', orders=orders)

@app.route('/order/<int:order_id>')
@login_required
def order_detail(order_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = %s AND user_id = %s", 
                  (order_id, current_user.id))
    order_row = cursor.fetchone()
    
    if not order_row:
        flash('订单不存在', 'error')
        return redirect(url_for('order_history'))
    
    # 转换订单数据
    if isinstance(order_row, tuple):
        keys = ['id', 'user_id', 'total_amount', 'status', 'address', 'phone', 'created_at']
        order = dict(zip(keys, order_row))
    else:
        order = order_row
    
    cursor.execute("""
        SELECT oi.*, p.name, p.image_url 
        FROM order_items oi 
        JOIN products p ON oi.product_id = p.id 
        WHERE oi.order_id = %s
    """, (order_id,))
    items_rows = cursor.fetchall()
    cursor.close()
    conn.close()
    
    # 转换订单项数据
    items = []
    for row in items_rows:
        if isinstance(row, tuple):
            keys = ['id', 'order_id', 'product_id', 'quantity', 'price', 'name', 'image_url']
            items.append(dict(zip(keys, row)))
        else:
            items.append(row)
    
    return render_template('order/detail.html', order=order, items=items)

@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash('无权访问', 'error')
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 统计信息 - 修复这里
    cursor.execute("SELECT COUNT(*) as count FROM products")
    product_count_result = cursor.fetchone()
    product_count = product_count_result[0] if product_count_result else 0  # 使用索引访问元组
    
    cursor.execute("SELECT COUNT(*) as count FROM orders")
    order_count_result = cursor.fetchone()
    order_count = order_count_result[0] if order_count_result else 0
    
    cursor.execute("SELECT COUNT(*) as count FROM users")
    user_count_result = cursor.fetchone()
    user_count = user_count_result[0] if user_count_result else 0
    
    cursor.execute("SELECT SUM(total_amount) as revenue FROM orders WHERE status = 'completed'")
    revenue_result = cursor.fetchone()
    revenue = revenue_result[0] if revenue_result and revenue_result[0] else 0  # 处理None情况
    
    cursor.close()
    conn.close()
    
    return render_template('admin/dashboard.html', 
                         product_count=product_count, 
                         order_count=order_count, 
                         user_count=user_count, 
                         revenue=revenue)

@app.route('/admin/products', methods=['GET', 'POST'])
@login_required
def admin_products():
    if not current_user.is_admin:
        flash('无权访问', 'error')
        return redirect(url_for('index'))
    
    # 获取分类列表
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM categories ORDER BY name")
    categories_rows = cursor.fetchall()
    
    categories = []
    for row in categories_rows:
        if isinstance(row, tuple):
            keys = ['id', 'name', 'description', 'created_at']
            categories.append(dict(zip(keys, row)))
        else:
            categories.append(row)
    
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        price = float(request.form['price'])
        stock = int(request.form['stock'])
        category_id = int(request.form['category_id'])
        
        # 处理图片上传
        image_url = 'images/default-product.jpg'
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = save_image(file)
                image_url = f'uploads/products/{filename}'
        
        # 获取分类名称用于兼容性
        cursor.execute("SELECT name FROM categories WHERE id = %s", (category_id,))
        category_result = cursor.fetchone()
        category_name = category_result[0] if category_result else ''
        
        cursor.execute(
            "INSERT INTO products (name, description, price, stock, category_id, category, image_url, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (name, description, price, stock, category_id, category_name, image_url, datetime.datetime.now())
        )
        conn.commit()
        cursor.close()
        conn.close()
        
        flash('商品添加成功', 'success')
        return redirect(url_for('admin_products'))
    
    # 获取商品列表（包含分类名称）
    cursor.execute("""
        SELECT p.*, c.name as category_name 
        FROM products p 
        LEFT JOIN categories c ON p.category_id = c.id 
        ORDER BY p.created_at DESC
    """)
    products_rows = cursor.fetchall()
    cursor.close()
    conn.close()
    
    # 转换商品数据
    products = []
    for row in products_rows:
        if isinstance(row, tuple):
            keys = ['id', 'name', 'description', 'price', 'stock', 'category_id', 'category', 'image_url', 'created_at', 'category_name']
            products.append(dict(zip(keys, row)))
        else:
            products.append(row)
    
    return render_template('admin/product_manage.html', products=products, categories=categories)

@app.route('/admin/product/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    if not current_user.is_admin:
        flash('无权访问', 'error')
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 获取分类列表
    cursor.execute("SELECT * FROM categories ORDER BY name")
    categories_rows = cursor.fetchall()
    
    categories = []
    for row in categories_rows:
        if isinstance(row, tuple):
            keys = ['id', 'name', 'description', 'created_at']
            categories.append(dict(zip(keys, row)))
        else:
            categories.append(row)
    
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        price = float(request.form['price'])
        stock = int(request.form['stock'])
        category_id = int(request.form['category_id'])
        
        # 处理图片上传
        image_url = request.form.get('current_image')
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                # 删除旧图片（如果不是默认图片）
                if image_url and 'default-product' not in image_url:
                    delete_image(image_url)
                
                filename = save_image(file)
                image_url = f'uploads/products/{filename}'
        
        # 获取分类名称用于兼容性
        cursor.execute("SELECT name FROM categories WHERE id = %s", (category_id,))
        category_result = cursor.fetchone()
        category_name = category_result[0] if category_result else ''
        
        cursor.execute(
            "UPDATE products SET name=%s, description=%s, price=%s, stock=%s, category_id=%s, category=%s, image_url=%s WHERE id=%s",
            (name, description, price, stock, category_id, category_name, image_url, product_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
        
        flash('商品更新成功', 'success')
        return redirect(url_for('admin_products'))
    
    # 获取商品信息（包含分类名称）
    cursor.execute("""
        SELECT p.*, c.name as category_name 
        FROM products p 
        LEFT JOIN categories c ON p.category_id = c.id 
        WHERE p.id = %s
    """, (product_id,))
    product_row = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not product_row:
        flash('商品不存在', 'error')
        return redirect(url_for('admin_products'))
    
    # 转换商品数据
    if isinstance(product_row, tuple):
        keys = ['id', 'name', 'description', 'price', 'stock', 'category_id', 'category', 'image_url', 'created_at', 'category_name']
        product = dict(zip(keys, product_row))
    else:
        product = product_row
    
    return render_template('admin/product_edit.html', product=product, categories=categories)

@app.route('/admin/product/delete/<int:product_id>')
@login_required
def delete_product(product_id):
    if not current_user.is_admin:
        flash('无权访问', 'error')
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 获取商品图片路径
    cursor.execute("SELECT image_url FROM products WHERE id = %s", (product_id,))
    product = cursor.fetchone()
    
    if product and product['image_url'] and 'default-product' not in product['image_url']:
        delete_image(product['image_url'])
    
    cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))
    conn.commit()
    cursor.close()
    conn.close()
    
    flash('商品删除成功', 'success')
    return redirect(url_for('admin_products'))

@app.route('/admin/orders')
@login_required
def admin_orders():
    if not current_user.is_admin:
        flash('无权访问', 'error')
        return redirect(url_for('index'))
    
    status = request.args.get('status', '')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
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
    
    # 转换订单数据
    orders = []
    for row in orders_rows:
        if isinstance(row, tuple):
            keys = ['id', 'user_id', 'total_amount', 'status', 'address', 'phone', 'created_at', 'username']
            orders.append(dict(zip(keys, row)))
        else:
            orders.append(row)
    
    return render_template('admin/order_manage.html', orders=orders, status=status)

@app.route('/admin/order/update_status', methods=['POST'])
@login_required
def update_order_status():
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': '无权访问'})
    
    order_id = request.form['order_id']
    status = request.form['status']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("UPDATE orders SET status = %s WHERE id = %s", (status, order_id))
    
    # 如果订单发货，发送邮件通知
    if status == 'shipped':
        cursor.execute("SELECT u.email, u.username FROM orders o JOIN users u ON o.user_id = u.id WHERE o.id = %s", (order_id,))
        order_info = cursor.fetchone()
        
        if order_info:
            try:
                msg = Message('订单已发货 - 在线购物网站',
                             sender=app.config['MAIL_DEFAULT_SENDER'],
                             recipients=[order_info['email']])
                msg.body = f'''
尊敬的 {order_info['username']}：

您的订单 #{order_id} 已发货，请注意查收。

感谢您的购物！
'''
                mail.send(msg)
            except Exception as e:
                print(f"邮件发送失败: {e}")
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return jsonify({'success': True, 'message': '订单状态更新成功'})

@app.route('/admin/stats')
@login_required
def admin_stats():
    if not current_user.is_admin:
        flash('无权访问', 'error')
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 销售统计
    cursor.execute("""
        SELECT DATE(created_at) as date, COUNT(*) as order_count, SUM(total_amount) as revenue 
        FROM orders 
        WHERE status = 'completed' 
        GROUP BY DATE(created_at) 
        ORDER BY date DESC 
        LIMIT 30
    """)
    sales_data_rows = cursor.fetchall()
    
    # 转换销售数据
    sales_data = []
    for row in sales_data_rows:
        if isinstance(row, tuple):
            keys = ['date', 'order_count', 'revenue']
            sales_data.append(dict(zip(keys, row)))
        else:
            sales_data.append(row)
    
    # 热门商品
    cursor.execute("""
        SELECT p.name, SUM(oi.quantity) as total_sold 
        FROM order_items oi 
        JOIN products p ON oi.product_id = p.id 
        JOIN orders o ON oi.order_id = o.id 
        WHERE o.status = 'completed' 
        GROUP BY p.id, p.name 
        ORDER BY total_sold DESC 
        LIMIT 10
    """)
    popular_products_rows = cursor.fetchall()
    
    # 转换热门商品数据
    popular_products = []
    for row in popular_products_rows:
        if isinstance(row, tuple):
            keys = ['name', 'total_sold']
            popular_products.append(dict(zip(keys, row)))
        else:
            popular_products.append(row)
    
    cursor.close()
    conn.close()
    
    return render_template('admin/stats.html', 
                         sales_data=sales_data, 
                         popular_products=popular_products)

# 分类管理页面
@app.route('/admin/categories')
@login_required
def admin_categories():
    if not current_user.is_admin:
        flash('无权访问', 'error')
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM categories ORDER BY name")
    categories_rows = cursor.fetchall()
    cursor.close()
    conn.close()
    
    # 转换分类数据
    categories = []
    for row in categories_rows:
        if isinstance(row, tuple):
            keys = ['id', 'name', 'description', 'created_at']
            categories.append(dict(zip(keys, row)))
        else:
            categories.append(row)
    
    return render_template('admin/categories.html', categories=categories)

# 添加分类
@app.route('/admin/category/add', methods=['POST'])
@login_required
def add_category():
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': '无权访问'})
    
    name = request.form['name']
    description = request.form.get('description', '')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "INSERT INTO categories (name, description) VALUES (%s, %s)",
            (name, description)
        )
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'message': '分类添加成功'})
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        
        if 'Duplicate entry' in str(e):
            return jsonify({'success': False, 'message': '分类名称已存在'})
        else:
            return jsonify({'success': False, 'message': f'添加失败: {str(e)}'})

# 编辑分类
@app.route('/admin/category/edit/<int:category_id>', methods=['POST'])
@login_required
def edit_category(category_id):
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': '无权访问'})
    
    name = request.form['name']
    description = request.form.get('description', '')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "UPDATE categories SET name = %s, description = %s WHERE id = %s",
            (name, description, category_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'message': '分类更新成功'})
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        
        if 'Duplicate entry' in str(e):
            return jsonify({'success': False, 'message': '分类名称已存在'})
        else:
            return jsonify({'success': False, 'message': f'更新失败: {str(e)}'})

# 删除分类
@app.route('/admin/category/delete/<int:category_id>')
@login_required
def delete_category(category_id):
    if not current_user.is_admin:
        flash('无权访问', 'error')
        return redirect(url_for('admin_categories'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 检查是否有商品使用该分类
    cursor.execute("SELECT COUNT(*) FROM products WHERE category_id = %s", (category_id,))
    product_count = cursor.fetchone()[0]
    
    if product_count > 0:
        flash('无法删除该分类，因为有商品正在使用它', 'error')
        cursor.close()
        conn.close()
        return redirect(url_for('admin_categories'))
    
    cursor.execute("DELETE FROM categories WHERE id = %s", (category_id,))
    conn.commit()
    cursor.close()
    conn.close()
    
    flash('分类删除成功', 'success')
    return redirect(url_for('admin_categories'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
