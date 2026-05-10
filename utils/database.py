import mysql.connector
from mysql.connector import Error
from config import Config

def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host=Config.MYSQL_HOST,
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASSWORD,
            database=Config.MYSQL_DB,
            buffered=True
        )
        # 设置会话时区为北京时间
        cursor = conn.cursor()
        cursor.execute("SET time_zone = '+08:00'")
        cursor.close()
        return conn
    except Error as e:
        print(f"数据库连接错误: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if conn is None:
        return

    cursor = conn.cursor(dictionary=True)

    # ---------- 用户表 ----------
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(80) UNIQUE NOT NULL,
            email VARCHAR(120) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            role ENUM('customer', 'sales', 'admin') DEFAULT 'customer',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ---------- 商品表（含 seller_id）----------
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            price DECIMAL(10, 2) NOT NULL,
            stock INT NOT NULL,
            category VARCHAR(100),
            image_url VARCHAR(500),
            seller_id INT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (seller_id) REFERENCES users(id) ON DELETE SET NULL
        )
    ''')

    # ---------- 购物车表 ----------
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cart_items (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            product_id INT NOT NULL,
            quantity INT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    ''')

    # ---------- 订单表（完整退款字段）----------
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            total_amount DECIMAL(10, 2) NOT NULL,
            status ENUM('pending','paid','shipped','completed','cancelled','refunding','refunded') DEFAULT 'pending',
            prev_status VARCHAR(20) DEFAULT NULL,
            refund_reason TEXT DEFAULT NULL,
            refund_type VARCHAR(20) DEFAULT NULL,
            refund_evidence VARCHAR(500) DEFAULT NULL,
            address TEXT NOT NULL,
            phone VARCHAR(20) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # 兼容旧表：如果 orders 表已存在但缺少字段，自动添加
    # 1. 添加 prev_status 列（退款前状态）
    try:
        cursor.execute("ALTER TABLE orders ADD COLUMN prev_status VARCHAR(20) DEFAULT NULL")
    except:
        pass
    # 2. 添加 refund_reason 列（退款原因）
    try:
        cursor.execute("ALTER TABLE orders ADD COLUMN refund_reason TEXT DEFAULT NULL")
    except:
        pass
    # 3. 添加 refund_type 列（退款类型：only_refund/return_refund）
    try:
        cursor.execute("ALTER TABLE orders ADD COLUMN refund_type VARCHAR(20) DEFAULT NULL")
    except:
        pass
    # 4. 添加 refund_evidence 列（退款凭据路径）
    try:
        cursor.execute("ALTER TABLE orders ADD COLUMN refund_evidence VARCHAR(500) DEFAULT NULL")
    except:
        pass
    # 5. 如果 status 枚举类型缺少 'refunding' 和 'refunded'，则修改列
    try:
        cursor.execute("ALTER TABLE orders MODIFY COLUMN status ENUM('pending','paid','shipped','completed','cancelled','refunding','refunded') DEFAULT 'pending'")
    except:
        pass

    # ---------- 订单项表 ----------
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS order_items (
            id INT AUTO_INCREMENT PRIMARY KEY,
            order_id INT NOT NULL,
            product_id INT NOT NULL,
            quantity INT NOT NULL,
            price DECIMAL(10, 2) NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    ''')

    # ---------- 登录日志 ----------
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS login_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            ip VARCHAR(45),
            event_type ENUM('login', 'logout') DEFAULT 'login',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # ---------- 浏览日志 ----------
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS browsing_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            session_id VARCHAR(100),
            product_id INT,
            start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            end_time TIMESTAMP NULL,
            duration INT DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    ''')

    # ---------- 操作日志 ----------
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS operation_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            ip VARCHAR(45),
            action VARCHAR(200),
            detail TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # ---------- 商品相似度 ----------
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS product_similarity (
            id INT AUTO_INCREMENT PRIMARY KEY,
            product_id INT NOT NULL,
            similar_product_id INT NOT NULL,
            score FLOAT NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products(id),
            FOREIGN KEY (similar_product_id) REFERENCES products(id),
            UNIQUE KEY unique_pair (product_id, similar_product_id)
        )
    ''')

    # ---------- 创建示例用户 ----------
    from werkzeug.security import generate_password_hash
    cursor.execute("SELECT * FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        hashed_password = generate_password_hash('admin123')
        cursor.execute(
            "INSERT INTO users (username, email, password, role) VALUES (%s, %s, %s, %s)",
            ('admin', 'admin@shop.com', hashed_password, 'admin')
        )

    cursor.execute("SELECT * FROM users WHERE username = 'sales'")
    if not cursor.fetchone():
        hashed_password = generate_password_hash('sales123')
        cursor.execute(
            "INSERT INTO users (username, email, password, role) VALUES (%s, %s, %s, %s)",
            ('sales', 'sales@shop.com', hashed_password, 'sales')
        )

    # ---------- 插入示例商品 ----------
    cursor.execute("SELECT COUNT(*) as count FROM products")
    result = cursor.fetchone()
    if result and result['count'] == 0:
        sample_products = [
            ('智能手机', '高性能智能手机', 2999.00, 50, 'electronics', 'images/default-product.jpg'),
            ('笔记本电脑', '轻薄便携笔记本电脑', 5999.00, 30, 'electronics', 'images/default-product.jpg'),
            ('T恤', '纯棉舒适T恤', 89.00, 100, 'clothing', 'images/default-product.jpg'),
            ('运动鞋', '透气运动鞋', 299.00, 80, 'shoes', 'images/default-product.jpg'),
            ('书籍', '编程学习书籍', 59.00, 200, 'books', 'images/default-product.jpg')
        ]
        for prod in sample_products:
            cursor.execute(
                "INSERT INTO products (name, description, price, stock, category, image_url, seller_id) VALUES (%s, %s, %s, %s, %s, %s, NULL)",
                prod
            )

    conn.commit()
    cursor.close()
    conn.close()
    print("数据库初始化/升级完成（角色、日志、推荐、销售归属、退款字段均已就绪）")