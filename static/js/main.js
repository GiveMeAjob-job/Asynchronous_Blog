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
            // 确保您已经将 base.html 中对应的 span id 修改为 navUsername
            document.getElementById('navUsername').textContent = payload.username || '用户'; // 这是您修改后的正确代码
        } catch (e) {
            console.error('解析token失败', e);
            // 可选：如果解析失败，也显示默认“用户”或清空
            const navUsernameElement = document.getElementById('navUsername');
            if (navUsernameElement) {
                navUsernameElement.textContent = '用户';
            }
        }

        // 确保 authButtons 和 userMenu 元素在 DOM 中存在
        if (authButtons) {
            authButtons.classList.add('d-none');
        }
        if (userMenu) {
            userMenu.classList.remove('d-none');
        }
    } else {
        if (authButtons) {
            authButtons.classList.remove('d-none');
        }
        if (userMenu) {
            userMenu.classList.add('d-none');
        }
    }
}

// 退出登录
document.addEventListener('DOMContentLoaded', function() {
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', function(e) {
            e.preventDefault();
            localStorage.removeItem('token');
            // 清除cookie
            document.cookie = 'access_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
            window.location.href = '/'; // 重定向到首页
        });
    }

    // 初始检查登录状态
    checkAuthStatus();
});

// 保留默认 baseURL
axios.defaults.baseURL = '/api/v1';

// 请求拦截器
axios.interceptors.request.use((config) => {
    const token = localStorage.getItem('token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// 响应拦截器处理401错误
axios.interceptors.response.use(
    response => response,
    error => {
        if (error.response && error.response.status === 401) {
            // 清除本地存储的token
            localStorage.removeItem('token');
            // 重定向到登录页，并传递当前路径以便登录后返回
            // 但要注意避免重定向循环，如果 /login 本身也可能触发 401 (虽然不太可能)
            if (window.location.pathname !== '/login') {
                 // 可以考虑添加一个查询参数，指示用户是因为会话过期而被重定向
                window.location.href = '/login?session_expired=true&redirect=' + encodeURIComponent(window.location.pathname + window.location.search);
            }
        }
        return Promise.reject(error);
    }
);
