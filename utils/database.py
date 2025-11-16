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
            buffered=True  # 添加这个参数
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
    
    # 创建分类表（新增）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) UNIQUE NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 修改商品表，添加分类外键
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            price DECIMAL(10, 2) NOT NULL,
            stock INT NOT NULL,
            category_id INT,
            category VARCHAR(100),  # 保留旧字段用于兼容性
            image_url VARCHAR(500),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES categories(id)
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
    
    # 插入默认分类
    cursor.execute("SELECT COUNT(*) as count FROM categories")
    category_count = cursor.fetchone()[0]
    
    if category_count == 0:
        default_categories = [
            ('electronics', '电子产品', '手机、电脑、相机等电子设备'),
            ('clothing', '服装', '上衣、裤子、外套等服装'),
            ('shoes', '鞋类', '运动鞋、皮鞋、休闲鞋等'),
            ('books', '图书', '各类书籍、教材等'),
            ('home', '家居', '家具、家居装饰等'),
            ('beauty', '美妆', '化妆品、护肤品等'),
            ('food', '食品', '零食、饮料、生鲜等')
        ]
        
        for category in default_categories:
            cursor.execute(
                "INSERT INTO categories (name, description) VALUES (%s, %s)",
                (category[1], category[2])
            )
    
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
        # 获取分类ID
        category_map = {}
        cursor.execute("SELECT id, name FROM categories")
        categories = cursor.fetchall()
        for category in categories:
            if isinstance(category, tuple):
                category_map[category[1]] = category[0]
            else:
                category_map[category['name']] = category['id']
        
        sample_products = [
            ('智能手机', '高性能智能手机', 2999.00, 50, 'electronics', 'images/default-product.jpg'),
            ('笔记本电脑', '轻薄便携笔记本电脑', 5999.00, 30, 'electronics', 'images/default-product.jpg'),
            ('T恤', '纯棉舒适T恤', 89.00, 100, 'clothing', 'images/default-product.jpg'),
            ('运动鞋', '透气运动鞋', 299.00, 80, 'shoes', 'images/default-product.jpg'),
            ('编程书籍', 'Python编程学习书籍', 59.00, 200, 'books', 'images/default-product.jpg')
        ]
        
        for product in sample_products:
            category_name = product[4]
            category_id = category_map.get(category_name)
            
            cursor.execute(
                "INSERT INTO products (name, description, price, stock, category_id, category, image_url) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (product[0], product[1], product[2], product[3], category_id, category_name, product[5])
            )
    
    # 迁移现有商品的分类（如果存在旧数据）
    try:
        # 检查是否有使用旧分类字段的商品
        cursor.execute("SELECT COUNT(*) FROM products WHERE category IS NOT NULL AND category_id IS NULL")
        products_to_migrate = cursor.fetchone()[0]
        
        if products_to_migrate > 0:
            print(f"迁移 {products_to_migrate} 个商品的分类数据...")
            
            # 获取所有分类映射
            cursor.execute("SELECT id, name FROM categories")
            categories = cursor.fetchall()
            category_name_to_id = {}
            for category in categories:
                if isinstance(category, tuple):
                    category_name_to_id[category[1]] = category[0]
                else:
                    category_name_to_id[category['name']] = category['id']
            
            # 获取需要迁移的商品
            cursor.execute("SELECT id, category FROM products WHERE category IS NOT NULL AND category_id IS NULL")
            products = cursor.fetchall()
            
            migrated_count = 0
            for product in products:
                product_id = product[0] if isinstance(product, tuple) else product['id']
                category_name = product[1] if isinstance(product, tuple) else product['category']
                
                category_id = category_name_to_id.get(category_name)
                if category_id:
                    cursor.execute(
                        "UPDATE products SET category_id = %s WHERE id = %s",
                        (category_id, product_id)
                    )
                    migrated_count += 1
                else:
                    # 如果分类不存在，创建新分类
                    cursor.execute(
                        "INSERT INTO categories (name) VALUES (%s)",
                        (category_name,)
                    )
                    new_category_id = cursor.lastrowid
                    category_name_to_id[category_name] = new_category_id
                    
                    cursor.execute(
                        "UPDATE products SET category_id = %s WHERE id = %s",
                        (new_category_id, product_id)
                    )
                    migrated_count += 1
            
            print(f"成功迁移 {migrated_count} 个商品的分类")
    
    except Exception as e:
        print(f"分类迁移过程中出现错误: {e}")
        # 继续执行，不中断初始化
    
    conn.commit()
    cursor.close()
    conn.close()
    print("数据库初始化完成")

def migrate_categories():
    """独立的分类迁移函数，用于后续更新"""
    conn = get_db_connection()
    if conn is None:
        print("数据库连接失败")
        return
    
    cursor = conn.cursor()
    
    try:
        # 检查是否有使用旧分类字段的商品
        cursor.execute("SELECT COUNT(*) FROM products WHERE category IS NOT NULL AND category_id IS NULL")
        products_to_migrate = cursor.fetchone()[0]
        
        if products_to_migrate == 0:
            print("没有需要迁移的分类数据")
            return
        
        print(f"开始迁移 {products_to_migrate} 个商品的分类数据...")
        
        # 获取所有分类映射
        cursor.execute("SELECT id, name FROM categories")
        categories = cursor.fetchall()
        category_name_to_id = {}
        for category in categories:
            if isinstance(category, tuple):
                category_name_to_id[category[1]] = category[0]
            else:
                category_name_to_id[category['name']] = category['id']
        
        # 获取需要迁移的商品
        cursor.execute("SELECT id, category FROM products WHERE category IS NOT NULL AND category_id IS NULL")
        products = cursor.fetchall()
        
        migrated_count = 0
        for product in products:
            product_id = product[0] if isinstance(product, tuple) else product['id']
            category_name = product[1] if isinstance(product, tuple) else product['category']
            
            category_id = category_name_to_id.get(category_name)
            if category_id:
                cursor.execute(
                    "UPDATE products SET category_id = %s WHERE id = %s",
                    (category_id, product_id)
                )
                migrated_count += 1
            else:
                # 如果分类不存在，创建新分类
                cursor.execute(
                    "INSERT INTO categories (name) VALUES (%s)",
                    (category_name,)
                )
                new_category_id = cursor.lastrowid
                category_name_to_id[category_name] = new_category_id
                
                cursor.execute(
                    "UPDATE products SET category_id = %s WHERE id = %s",
                    (new_category_id, product_id)
                )
                migrated_count += 1
        
        conn.commit()
        print(f"成功迁移 {migrated_count} 个商品的分类")
        
    except Exception as e:
        print(f"分类迁移失败: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def get_all_categories():
    """获取所有分类"""
    conn = get_db_connection()
    if conn is None:
        return []
    
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM categories ORDER BY name")
    categories_rows = cursor.fetchall()
    cursor.close()
    conn.close()
    
    # 转换为字典格式
    categories = []
    for row in categories_rows:
        if isinstance(row, tuple):
            keys = ['id', 'name', 'description', 'created_at']
            categories.append(dict(zip(keys, row)))
        else:
            categories.append(row)
    
    return categories

def get_category_by_id(category_id):
    """根据ID获取分类"""
    conn = get_db_connection()
    if conn is None:
        return None
    
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM categories WHERE id = %s", (category_id,))
    category_row = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not category_row:
        return None
    
    # 转换为字典格式
    if isinstance(category_row, tuple):
        keys = ['id', 'name', 'description', 'created_at']
        category = dict(zip(keys, category_row))
    else:
        category = category_row
    
    return category

def add_category(name, description=""):
    """添加新分类"""
    conn = get_db_connection()
    if conn is None:
        return False
    
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "INSERT INTO categories (name, description) VALUES (%s, %s)",
            (name, description)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        raise e

def update_category(category_id, name, description=""):
    """更新分类"""
    conn = get_db_connection()
    if conn is None:
        return False
    
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "UPDATE categories SET name = %s, description = %s WHERE id = %s",
            (name, description, category_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        raise e

def delete_category(category_id):
    """删除分类"""
    conn = get_db_connection()
    if conn is None:
        return False
    
    cursor = conn.cursor()
    
    try:
        # 检查是否有商品使用该分类
        cursor.execute("SELECT COUNT(*) FROM products WHERE category_id = %s", (category_id,))
        product_count = cursor.fetchone()[0]
        
        if product_count > 0:
            cursor.close()
            conn.close()
            return False, "无法删除该分类，因为有商品正在使用它"
        
        cursor.execute("DELETE FROM categories WHERE id = %s", (category_id,))
        conn.commit()
        cursor.close()
        conn.close()
        return True, "分类删除成功"
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return False, f"删除失败: {str(e)}"

def get_products_by_category(category_id):
    """根据分类ID获取商品"""
    conn = get_db_connection()
    if conn is None:
        return []
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.*, c.name as category_name 
        FROM products p 
        LEFT JOIN categories c ON p.category_id = c.id 
        WHERE p.category_id = %s AND p.stock > 0
        ORDER BY p.created_at DESC
    """, (category_id,))
    products_rows = cursor.fetchall()
    cursor.close()
    conn.close()
    
    # 转换为字典格式
    products = []
    for row in products_rows:
        if isinstance(row, tuple):
            keys = ['id', 'name', 'description', 'price', 'stock', 'category_id', 'category', 'image_url', 'created_at', 'category_name']
            products.append(dict(zip(keys, row)))
        else:
            products.append(row)
    
    return products

# 测试函数
if __name__ == "__main__":
    print("初始化数据库...")
    init_db()
    print("数据库初始化完成")
    
    # 测试分类功能
    print("\n测试分类功能:")
    categories = get_all_categories()
    print(f"共有 {len(categories)} 个分类:")
    for category in categories:
        print(f"  - {category['name']}: {category['description']}")
