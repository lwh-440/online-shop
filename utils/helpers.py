import os
from werkzeug.utils import secure_filename
from config import Config
from PIL import Image

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS

def save_image(file):
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # 添加时间戳避免重名
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_")
        filename = timestamp + filename
        
        filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        # 压缩图片
        try:
            img = Image.open(filepath)
            if img.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            
            if img.size[0] > 800 or img.size[1] > 800:
                img.thumbnail((800, 800), Image.Resampling.LANCZOS)
            
            img.save(filepath, 'JPEG', quality=85)
        except Exception as e:
            print(f"图片处理错误: {e}")
        
        return filename
    return None

def delete_image(image_url):
    if image_url and 'default-product' not in image_url:
        try:
            filename = image_url.split('/')[-1]
            filepath = os.path.join(Config.UPLOAD_FOLDER, filename)
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            print(f"删除图片错误: {e}")
            
def dict_to_product(product_dict):
    """将数据库查询结果转换为易于使用的字典"""
    if not product_dict:
        return None
    
    # 如果是元组，转换为字典
    if isinstance(product_dict, tuple):
        # 根据数据库表结构映射字段
        # 顺序: id, name, description, price, stock, category, image_url, created_at
        keys = ['id', 'name', 'description', 'price', 'stock', 'category', 'image_url', 'created_at']
        product_dict = dict(zip(keys, product_dict))
    
    return product_dict

def rows_to_products(rows):
    """将多行查询结果转换为产品列表"""
    if not rows:
        return []
    
    products = []
    for row in rows:
        products.append(dict_to_product(row))
    return products

def dict_to_user(user_dict):
    """将用户查询结果转换为字典"""
    if not user_dict:
        return None
    
    if isinstance(user_dict, tuple):
        keys = ['id', 'username', 'email', 'password', 'is_admin', 'created_at']
        user_dict = dict(zip(keys, user_dict))
    
    return user_dict

def rows_to_users(rows):
    """将多行用户查询结果转换为列表"""
    if not rows:
        return []
    
    users = []
    for row in rows:
        users.append(dict_to_user(row))
    return users