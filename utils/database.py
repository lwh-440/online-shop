import mysql.connector
from mysql.connector import Error
from config import Config

def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host=Config.MYSQL_HOST,
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASSWORD,
            database=Config.MYSQL_DB
        )
        return conn
    except Error as e:
        print(f"数据库连接错误: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if conn is None:
        return
    
    cursor = conn.cursor()
    
    # 创建用户表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(80) UNIQUE NOT NULL,
            email VARCHAR(120) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            is_admin BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 创建商品表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            price DECIMAL(10, 2) NOT NULL,
            stock INT NOT NULL,
            category VARCHAR(100),
            image_url VARCHAR(500),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 创建购物车表
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
    
    # 创建订单表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            total_amount DECIMAL(10, 2) NOT NULL,
            status ENUM('pending', 'paid', 'shipped', 'completed', 'cancelled') DEFAULT 'pending',
            address TEXT NOT NULL,
            phone VARCHAR(20) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # 创建订单项表
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
    
    # 创建管理员用户
    cursor.execute("SELECT * FROM users WHERE username = 'admin'")
    admin_user = cursor.fetchone()
    
    if not admin_user:
        from werkzeug.security import generate_password_hash
        hashed_password = generate_password_hash('admin123')
        cursor.execute(
            "INSERT INTO users (username, email, password, is_admin) VALUES (%s, %s, %s, %s)",
            ('admin', 'admin@shop.com', hashed_password, True)
        )
    
    # 插入示例商品
    cursor.execute("SELECT COUNT(*) as count FROM products")
    product_count = cursor.fetchone()[0]
    
    if product_count == 0:
        sample_products = [
            ('智能手机', '高性能智能手机', 2999.00, 50, 'electronics', 'images/default-product.jpg'),
            ('笔记本电脑', '轻薄便携笔记本电脑', 5999.00, 30, 'electronics', 'images/default-product.jpg'),
            ('T恤', '纯棉舒适T恤', 89.00, 100, 'clothing', 'images/default-product.jpg'),
            ('运动鞋', '透气运动鞋', 299.00, 80, 'shoes', 'images/default-product.jpg'),
            ('书籍', '编程学习书籍', 59.00, 200, 'books', 'images/default-product.jpg')
        ]
        
        for product in sample_products:
            cursor.execute(
                "INSERT INTO products (name, description, price, stock, category, image_url) VALUES (%s, %s, %s, %s, %s, %s)",
                product
            )
    
    conn.commit()
    cursor.close()
    conn.close()
    print("数据库初始化完成")