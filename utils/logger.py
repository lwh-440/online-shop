from flask import request
from flask_login import current_user
from utils.database import get_db_connection

def log_operation(action, detail=''):
    """记录销售/管理员的操作日志"""
    if not current_user.is_authenticated:
        return
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "INSERT INTO operation_logs (user_id, ip, action, detail) VALUES (%s, %s, %s, %s)",
            (current_user.id, request.remote_addr, action, detail)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"操作日志记录失败: {e}")

def log_login(user_id, event='login'):
    """记录登录/登出事件"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "INSERT INTO login_logs (user_id, ip, event_type) VALUES (%s, %s, %s)",
            (user_id, request.remote_addr, event)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"登录日志记录失败: {e}")
