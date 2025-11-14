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