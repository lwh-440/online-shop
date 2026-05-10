from utils.database import get_db_connection
from itertools import combinations
from math import sqrt
import re

def update_similarities():
    """计算商品相似度（共现）"""
    conn = get_db_connection()
    if not conn:
        return
    cursor = conn.cursor(dictionary=True)
    cursor.execute("DELETE FROM product_similarity")
    cursor.execute("""
        SELECT oi.product_id, oi.order_id
        FROM order_items oi JOIN orders o ON oi.order_id = o.id
        WHERE o.status = 'completed'
    """)
    rows = cursor.fetchall()
    product_orders = {}
    for row in rows:
        pid = row['product_id']
        oid = row['order_id']
        product_orders.setdefault(pid, set()).add(oid)
    counts = {pid: len(orders) for pid, orders in product_orders.items()}
    similarities = {}
    for p1, p2 in combinations(product_orders.keys(), 2):
        common = len(product_orders[p1] & product_orders[p2])
        if common > 0:
            sim = common / sqrt(counts[p1] * counts[p2])
            similarities[(p1, p2)] = sim
    for (p1, p2), sim in similarities.items():
        cursor.execute(
            "INSERT INTO product_similarity (product_id, similar_product_id, score) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE score = VALUES(score)",
            (p1, p2, sim)
        )
        cursor.execute(
            "INSERT INTO product_similarity (product_id, similar_product_id, score) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE score = VALUES(score)",
            (p2, p1, sim)
        )
    conn.commit()
    cursor.close()
    conn.close()

def get_recommendations(product_id, limit=4):
    """获取基于订单共现的推荐（购买了此商品的人也买过）"""
    conn = get_db_connection()
    if not conn:
        return []
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT p.*, ps.score
        FROM product_similarity ps
        JOIN products p ON ps.similar_product_id = p.id
        WHERE ps.product_id = %s AND p.stock > 0
        ORDER BY ps.score DESC LIMIT %s
    """, (product_id, limit))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    for row in rows:
        row['price'] = float(row['price'])
        row['score'] = float(row['score'])
        row['stock'] = int(row['stock'])
    return rows

def get_interest_recommendations(product_id, limit=4):
    """
    猜你感兴趣：优先推荐同类别、名称关键词相似且最近浏览热的商品；
    若无结果，则退化为推荐同类别最新商品。
    """
    conn = get_db_connection()
    if not conn:
        return []
    cursor = conn.cursor(dictionary=True)

    # 获取当前商品信息
    cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
    current = cursor.fetchone()
    if not current:
        cursor.close()
        conn.close()
        return []

    category = current['category']
    name = current['name']
    # 提取关键词
    keywords = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', name.lower())
    valid_keywords = [kw for kw in keywords if len(kw) >= 2]

    rows = []
    if valid_keywords:
        # 构造同类别 + 关键词模糊匹配的查询
        like_clauses = []
        params = [category, product_id]
        for kw in valid_keywords:
            like_clauses.append("p.name LIKE %s")
            params.append(f"%{kw}%")

        sql = f"""
            SELECT p.*, COALESCE(bl_stats.total_dur,0) as total_duration, 
                   COALESCE(bl_stats.last_view, '2000-01-01') as last_view_time
            FROM products p
            LEFT JOIN (
                SELECT product_id, SUM(duration) as total_dur, MAX(end_time) as last_view
                FROM browsing_logs
                WHERE end_time IS NOT NULL
                GROUP BY product_id
            ) bl_stats ON p.id = bl_stats.product_id
            WHERE p.category = %s AND p.id != %s AND p.stock > 0
              AND ({' OR '.join(like_clauses)})
            ORDER BY total_duration DESC, last_view_time DESC, p.created_at DESC
            LIMIT %s
        """
        params.append(limit)
        cursor.execute(sql, params)
        rows = cursor.fetchall()

    # 如果关键词匹配无结果，则退化为同类别最新商品
    if not rows:
        sql_fallback = """
            SELECT p.*, COALESCE(bl_stats.total_dur,0) as total_duration,
                   COALESCE(bl_stats.last_view, '2000-01-01') as last_view_time
            FROM products p
            LEFT JOIN (
                SELECT product_id, SUM(duration) as total_dur, MAX(end_time) as last_view
                FROM browsing_logs
                WHERE end_time IS NOT NULL
                GROUP BY product_id
            ) bl_stats ON p.id = bl_stats.product_id
            WHERE p.category = %s AND p.id != %s AND p.stock > 0
            ORDER BY p.created_at DESC
            LIMIT %s
        """
        cursor.execute(sql_fallback, (category, product_id, limit))
        rows = cursor.fetchall()

    cursor.close()
    conn.close()

    for row in rows:
        row['price'] = float(row['price'])
        row['stock'] = int(row['stock'])
    return rows