在线购物网站
基于 Flask + MySQL 的完整在线购物系统，支持用户注册登录、商品管理、购物车、订单流程、退款审核、推荐系统及数据可视化。

功能特性
顾客功能
用户注册/登录（邮箱验证码、密码强度校验）
商品浏览、分类筛选、关键词搜索
商品详情页（双推荐板块：购买过的人还买了 & 猜你感兴趣）
购物车管理
订单创建（模拟付款 → 卖家发货 → 确认收货）
退款申请（仅退款/退货退款，上传凭据）
订单历史与状态跟踪

销售人员功能
商品管理（添加/编辑/删除，仅可操作自己负责的商品）
商品分类管理（创建/删除，删除时商品移至“其他”）
查看、处理订单（修改状态为已发货等）
浏览用户浏览日志与操作日志
销售统计（图表与热门商品）

管理员功能
所有销售人员权限
用户管理（添加销售/管理员、重置密码）
销售业绩查询（按商品归属统计）
退款审核（查看用户申请详情、凭据，同意或拒绝）
数据大屏（实时销售数据、趋势图、分类占比、订单滚动）
完整的浏览/操作日志查看
推荐模型手动更新

技术栈
后端框架	Flask
数据库	MySQL (mysql-connector-python)
身份认证	Flask-Login
邮件服务	Flask-Mail (QQ邮箱SMTP)
前端	HTML, CSS, JavaScript, Jinja2
图表库	ECharts (数据可视化)
图片处理	Pillow
部署	Gunicorn + Nginx (Ubuntu)

环境要求
Python 3.8+
MySQL 5.7+ (或 8.0)
推荐：Ubuntu 20.04+ 或 Windows 10/11

测试账号
管理员	admin	admin123
销售人员	sales	sales123
普通顾客	自行注册	注册时设置

项目结构
online-shop/
├── app.py                # 主应用程序
├── config.py             # 配置文件
├── run.py                # 开发运行入口
├── requirements.txt      # Python 依赖
├── utils/
│   ├── database.py       # 数据库连接与初始化
│   ├── helpers.py        # 辅助函数（图片处理、密码校验等）
│   ├── logger.py         # 日志记录（操作日志、登录日志）
│   └── recommend.py      # 推荐算法（共现相似度、兴趣推荐）
├── templates/            # Jinja2 模板
│   ├── auth/             # 登录、注册
│   ├── product/          # 商品列表、详情
│   ├── order/            # 订单相关（结算、详情、付款、退款申请）
│   ├── cart/             # 购物车
│   ├── admin/            # 管理后台（仪表盘、商品、分类、订单、统计、用户、业绩、日志、大屏）
│   └── base.html         # 基础布局
├── static/
│   ├── css/style.css     # 样式表
│   ├── js/script.js      # 通用脚本
│   ├── images/           # 默认商品图片
│   └── uploads/          # 用户上传文件（products, refunds）
└── README.md

注意事项
配置文件：config.py 包含敏感信息，部署时最好手动创建。
邮件服务：需要 QQ 邮箱开启 SMTP 并获取授权码，填入 config.py。
数据库初始化：首次启动时会自动建表并插入示例数据，升级时兼容旧表结构（自动添加缺失列）。
上传目录：确保 static/uploads/products 和 static/uploads/refunds 有写入权限。
推荐系统：订单数据较多时才能体现效果，可在管理后台手动触发相似度更新。

许可证
本项目仅用于学习和课程设计，请勿用于商业用途。
