// 通用JavaScript功能

// 页面加载完成后执行
document.addEventListener('DOMContentLoaded', function() {
    // 初始化工具提示
    initTooltips();
    
    // 初始化表单验证
    initFormValidation();
    
    // 初始化图片预览
    initImagePreview();
    
    // 初始化购物车功能
    initCartFunctions();
});

// 工具提示初始化
function initTooltips() {
    const tooltips = document.querySelectorAll('[data-toggle="tooltip"]');
    tooltips.forEach(tooltip => {
        tooltip.addEventListener('mouseenter', function() {
            const tooltipText = this.getAttribute('title');
            const tooltipEl = document.createElement('div');
            tooltipEl.className = 'custom-tooltip';
            tooltipEl.textContent = tooltipText;
            document.body.appendChild(tooltipEl);
            
            const rect = this.getBoundingClientRect();
            tooltipEl.style.left = (rect.left + rect.width / 2 - tooltipEl.offsetWidth / 2) + 'px';
            tooltipEl.style.top = (rect.top - tooltipEl.offsetHeight - 5) + 'px';
            
            this.setAttribute('data-tooltip-active', 'true');
        });
        
        tooltip.addEventListener('mouseleave', function() {
            const activeTooltip = document.querySelector('.custom-tooltip');
            if (activeTooltip) {
                activeTooltip.remove();
            }
            this.removeAttribute('data-tooltip-active');
        });
    });
}

// 表单验证初始化
function initFormValidation() {
    const forms = document.querySelectorAll('.needs-validation');
    
    forms.forEach(form => {
        form.addEventListener('submit', function(event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            
            form.classList.add('was-validated');
        });
    });
}

// 图片预览功能
function initImagePreview() {
    const imageInputs = document.querySelectorAll('input[type="file"][accept^="image/"]');
    
    imageInputs.forEach(input => {
        input.addEventListener('change', function() {
            const file = this.files[0];
            if (file) {
                const reader = new FileReader();
                const previewId = this.getAttribute('data-preview');
                const previewElement = document.getElementById(previewId);
                
                reader.onload = function(e) {
                    if (previewElement) {
                        previewElement.src = e.target.result;
                        previewElement.style.display = 'block';
                    }
                };
                
                reader.readAsDataURL(file);
            }
        });
    });
}

// 购物车功能
function initCartFunctions() {
    // 数量增减按钮
    const quantityButtons = document.querySelectorAll('.quantity-btn');
    
    quantityButtons.forEach(button => {
        button.addEventListener('click', function() {
            const input = this.parentElement.querySelector('.quantity-input');
            let quantity = parseInt(input.value);
            
            if (this.classList.contains('increase')) {
                quantity++;
            } else if (this.classList.contains('decrease') && quantity > 1) {
                quantity--;
            }
            
            input.value = quantity;
            
            // 触发输入事件以更新总价
            input.dispatchEvent(new Event('input'));
        });
    });
    
    // 实时计算总价
    const quantityInputs = document.querySelectorAll('.quantity-input');
    
    quantityInputs.forEach(input => {
        input.addEventListener('input', function() {
            updateCartTotal();
        });
    });
}

// 更新购物车总价
function updateCartTotal() {
    const cartItems = document.querySelectorAll('.cart-item');
    let total = 0;
    
    cartItems.forEach(item => {
        const price = parseFloat(item.querySelector('.cart-item-price').textContent.replace('¥', ''));
        const quantity = parseInt(item.querySelector('.quantity-input').value);
        const subtotal = price * quantity;
        
        item.querySelector('.cart-item-subtotal').textContent = '¥' + subtotal.toFixed(2);
        total += subtotal;
    });
    
    document.querySelector('.cart-total').textContent = '总计: ¥' + total.toFixed(2);
}

// 导航栏动态效果
function initNavbarEffects() {
    const navLinks = document.querySelectorAll('.nav-link');
    
    navLinks.forEach(link => {
        // 鼠标悬停效果
        link.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-2px) scale(1.05)';
        });
        
        link.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0) scale(1)';
        });
        
        // 点击效果
        link.addEventListener('click', function() {
            this.style.transform = 'scale(0.95)';
            setTimeout(() => {
                this.style.transform = 'scale(1)';
            }, 150);
        });
    });
    
    // 滚动时导航栏效果
    window.addEventListener('scroll', function() {
        const navbar = document.querySelector('.navbar');
        if (window.scrollY > 50) {
            navbar.style.background = 'linear-gradient(135deg, #5a6fd8 0%, #6a42a5 100%)';
            navbar.style.boxShadow = '0 4px 30px rgba(0,0,0,0.3)';
        } else {
            navbar.style.background = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
            navbar.style.boxShadow = '0 4px 20px rgba(0,0,0,0.1)';
        }
    });
}

// 在DOM加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    initNavbarEffects();
});

// AJAX请求辅助函数
function ajaxRequest(url, method, data, callback) {
    const xhr = new XMLHttpRequest();
    xhr.open(method, url, true);
    xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
    
    xhr.onreadystatechange = function() {
        if (xhr.readyState === 4) {
            if (xhr.status === 200) {
                try {
                    const response = JSON.parse(xhr.responseText);
                    callback(null, response);
                } catch (e) {
                    callback(e, null);
                }
            } else {
                callback(new Error('请求失败: ' + xhr.status), null);
            }
        }
    };
    
    const formData = new URLSearchParams();
    for (const key in data) {
        formData.append(key, data[key]);
    }
    
    xhr.send(formData);
}

// 显示加载动画
function showLoading() {
    const loadingEl = document.createElement('div');
    loadingEl.className = 'loading-overlay';
    loadingEl.innerHTML = '<div class="spinner"></div>';
    document.body.appendChild(loadingEl);
}

// 隐藏加载动画
function hideLoading() {
    const loadingEl = document.querySelector('.loading-overlay');
    if (loadingEl) {
        loadingEl.remove();
    }
}

// 显示消息
function showMessage(message, type = 'success') {
    const messageEl = document.createElement('div');
    messageEl.className = `alert alert-${type} message-alert`;
    messageEl.textContent = message;
    
    document.body.insertBefore(messageEl, document.body.firstChild);
    
    setTimeout(() => {
        messageEl.remove();
    }, 5000);
}

// 管理员功能
if (typeof Admin !== 'undefined') {
    // 更新订单状态
    Admin.updateOrderStatus = function(orderId, status) {
        showLoading();
        
        ajaxRequest('/admin/order/update_status', 'POST', {
            order_id: orderId,
            status: status
        }, function(error, response) {
            hideLoading();
            
            if (error) {
                showMessage('更新失败: ' + error.message, 'error');
            } else {
                if (response.success) {
                    showMessage(response.message);
                    // 刷新页面或更新状态显示
                    location.reload();
                } else {
                    showMessage(response.message, 'error');
                }
            }
        });
    };
    
    // 删除商品确认
    Admin.confirmDelete = function(productId, productName) {
        if (confirm(`确定要删除商品 "${productName}" 吗？此操作不可撤销。`)) {
            window.location.href = `/admin/product/delete/${productId}`;
        }
    };
}

// 购物车功能
if (typeof Cart !== 'undefined') {
    Cart.updateQuantity = function(cartItemId, quantity) {
        showLoading();
        
        ajaxRequest('/update_cart', 'POST', {
            cart_item_id: cartItemId,
            quantity: quantity
        }, function(error, response) {
            hideLoading();
            
            if (error) {
                showMessage('更新失败: ' + error.message, 'error');
            } else {
                location.reload();
            }
        });
    };
}

// 添加CSS样式
const style = document.createElement('style');
style.textContent = `
    .custom-tooltip {
        position: fixed;
        background: rgba(0, 0, 0, 0.8);
        color: white;
        padding: 5px 10px;
        border-radius: 4px;
        font-size: 12px;
        z-index: 10000;
        pointer-events: none;
    }
    
    .loading-overlay {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(255, 255, 255, 0.8);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 9999;
    }
    
    .spinner {
        border: 4px solid #f3f3f3;
        border-top: 4px solid #007bff;
        border-radius: 50%;
        width: 40px;
        height: 40px;
        animation: spin 1s linear infinite;
    }
    
    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    
    .message-alert {
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 10000;
        min-width: 300px;
    }
`;
document.head.appendChild(style);