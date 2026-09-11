// 语言切换功能
function switchLanguage(lang, event) {
    event.preventDefault();
    
    // 发送AJAX请求更新语言
    fetch(`/api/switch_language?lang=${lang}`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // 重新加载当前页面以获取新的翻译
            window.location.reload();
        }
    })
    .catch(error => {
        console.error('Language switch failed:', error);
        // 显示错误提示
        showMessage('Language switch failed. Please try again.', 'error');
    });
}

// 显示消息提示
function showMessage(message = 'success', type = 'info') {
    // 创建消息元素
    const messageElement = document.createElement('div');
    messageElement.className = `alert alert-${type} alert-dismissible fade show position-fixed top-0 end-0 m-3 z-3`;
    messageElement.style.minWidth = '300px';
    messageElement.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    // 添加到页面
    document.body.appendChild(messageElement);
    
    // 3秒后自动移除
    setTimeout(() => {
        messageElement.classList.remove('show');
        setTimeout(() => {
            if (messageElement.parentNode) {
                messageElement.parentNode.removeChild(messageElement);
            }
        }, 1000);
    }, 3000);
}

// 显示遮罩层
function showLoading(message) {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) {
        overlay.classList.add('show');
        // 更新或隐藏进度区域
        const progressArea = document.getElementById('loading-progress');
        if (progressArea) {
            progressArea.style.display = message ? 'block' : 'none';
            if (message) progressArea.innerHTML = message;
        }
    }
}

// 更新遮罩层进度信息
function updateLoadingProgress(html) {
    const progressArea = document.getElementById('loading-progress');
    if (progressArea) {
        progressArea.style.display = 'block';
        progressArea.innerHTML = html;
    }
}

// 隐藏遮罩层
function hideLoading() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) {
        overlay.classList.remove('show');
        // 清空进度区域
        const progressArea = document.getElementById('loading-progress');
        if (progressArea) {
            progressArea.style.display = 'none';
            progressArea.innerHTML = '';
        }
    }
}

// 页面加载完成后初始化
 document.addEventListener('DOMContentLoaded', function() {
    // 初始化语言切换功能
    initLanguageSwitch();
});

// 初始化语言切换功能
function initLanguageSwitch() {
    // 获取当前语言
    const currentLang = document.documentElement.lang;
    
    // 更新语言切换按钮状态
    updateLanguageButton(currentLang);
}

// 更新语言切换按钮状态
function updateLanguageButton(lang) {
    // 这里可以添加代码来更新语言切换按钮的显示状态
    // 例如，高亮当前选中的语言
}

// 工具函数：获取URL参数
function getUrlParameter(name) {
    name = name.replace(/[\[]/, '\\[').replace(/[\]]/, '\\]');
    const regex = new RegExp('[\\?&]' + name + '=([^&#]*)');
    const results = regex.exec(location.search);
    return results === null ? '' : decodeURIComponent(results[1].replace(/\+/g, ' '));
}