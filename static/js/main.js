// 检查用户登录状态并更新UI
function checkAuthStatus() {
    const token = localStorage.getItem('token');
    const authButtons = document.getElementById('auth-buttons');
    const userMenu = document.getElementById('user-menu');

    if (token) {
        // 解析JWT获取用户名（仅用于显示，不做验证）
        try {
            const base64Url = token.split('.')[1];
            const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
            const jsonPayload = decodeURIComponent(atob(base64).split('').map(c => {
                return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
            }).join(''));

            const payload = JSON.parse(jsonPayload);
            document.getElementById('username').textContent = payload.username || '用户';
        } catch (e) {
            console.error('解析token失败', e);
        }

        authButtons.classList.add('d-none');
        userMenu.classList.remove('d-none');
    } else {
        authButtons.classList.remove('d-none');
        userMenu.classList.add('d-none');
    }
}

// 退出登录
document.addEventListener('DOMContentLoaded', function() {
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', function(e) {
            e.preventDefault();
            localStorage.removeItem('token');
            window.location.href = '/';
        });
    }

    // 初始检查登录状态
    checkAuthStatus();
});

// 设置axios默认配置
axios.defaults.baseURL = '/api/v1';
axios.interceptors.request.use(function (config) {
    const token = localStorage.getItem('token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// 添加响应拦截器处理401错误
axios.interceptors.response.use(
    response => response,
    error => {
        if (error.response && error.response.status === 401) {
            // 清除本地存储的token
            localStorage.removeItem('token');
            // 重定向到登录页
            window.location.href = '/login';
        }
        return Promise.reject(error);
    }
);
