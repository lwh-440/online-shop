import os
from datetime import timedelta

class Config:
    SECRET_KEY = 'your-secret-key-here'
    
    # MySQL数据库配置
    MYSQL_HOST = 'localhost'
    MYSQL_USER = 'shop_user'
    MYSQL_PASSWORD = 'user123456'
    MYSQL_DB = 'online_shop'
    MYSQL_CURSORCLASS = 'DictCursor'
    
    # 邮件配置 - QQ邮箱
    MAIL_SERVER = 'smtp.qq.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = '2085139328@qq.com'
    MAIL_PASSWORD = 'kxoqoqqincatchca'  # QQ邮箱授权码
    MAIL_DEFAULT_SENDER = '2085139328@qq.com'
    
    # 文件上传配置
    UPLOAD_FOLDER = 'static/uploads/products'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    
    # Flask-Login配置
    REMEMBER_COOKIE_DURATION = timedelta(days=7)
    
    @staticmethod
    def init_app(app):
        # 确保上传目录存在
        if not os.path.exists(Config.UPLOAD_FOLDER):
            os.makedirs(Config.UPLOAD_FOLDER)