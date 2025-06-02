// 全局变量存储认证状态
let currentUser = null;
let isAuthenticated = false;

// 检查认证状态
async function checkAuthStatus() {
    const token = localStorage.getItem('token');
    const authButtons = document.getElementById('auth-buttons');
    const userMenu = document.getElementById('user-menu');

    if (token) {
        try {
            // 验证 token 是否有效
            const response = await axios.get('/users/me', {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            
            if (response.data) {
                currentUser = response.data;
                isAuthenticated = true;
                
                // 更新用户名显示
                const navUsernameElement = document.getElementById('navUsername');
                if (navUsernameElement) {
                    navUsernameElement.textContent = currentUser.username || '用户';
                }
                
                // 显示用户菜单，隐藏登录按钮
                if (authButtons) {
                    authButtons.classList.add('d-none');
                }
                if (userMenu) {
                    userMenu.classList.remove('d-none');
                }
                
                // 隐藏注册按钮（如果存在）
                const sidebarRegisterBtn = document.getElementById('sidebar-register-btn');
                if (sidebarRegisterBtn) {
                    sidebarRegisterBtn.style.display = 'none';
                }
                
                return true;
            }
        } catch (error) {
            console.log('Token 验证失败:', error);
            // Token 无效，清除本地存储
            localStorage.removeItem('token');
            document.cookie = 'access_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
        }
    }
    
    // 未认证状态
    currentUser = null;
    isAuthenticated = false;
    
    if (authButtons) {
        authButtons.classList.remove('d-none');
    }
    if (userMenu) {
        userMenu.classList.add('d-none');
    }
    
    // 显示注册按钮（如果存在）
    const sidebarRegisterBtn = document.getElementById('sidebar-register-btn');
    if (sidebarRegisterBtn) {
        sidebarRegisterBtn.style.display = 'block';
    }
    
    return false;
}

// 获取当前用户信息
function getCurrentUser() {
    return currentUser;
}

// 检查是否已认证
function getAuthStatus() {
    return isAuthenticated;
}

// 退出登录
function logout() {
    localStorage.removeItem('token');
    document.cookie = 'access_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
    currentUser = null;
    isAuthenticated = false;
    window.location.href = '/';
}

// DOM 加载完成后初始化
document.addEventListener('DOMContentLoaded', async function() {
    // 检查认证状态
    await checkAuthStatus();
    
    // 退出登录按钮事件
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', function(e) {
            e.preventDefault();
            logout();
        });
    }
    
    // 检查是否在需要认证的页面
    const currentPath = window.location.pathname;
    if (currentPath.startsWith('/dashboard') && !isAuthenticated) {
        // 重定向到登录页
        window.location.href = '/login?redirect=' + encodeURIComponent(window.location.pathname + window.location.search);
    }
});

// 设置 axios 默认配置
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
    async error => {
        if (error.response && error.response.status === 401) {
            console.log('收到401错误，清除认证状态');
            
            // 清除本地存储的token
            localStorage.removeItem('token');
            document.cookie = 'access_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
            
            // 更新认证状态
            currentUser = null;
            isAuthenticated = false;
            
            // 只有不在登录页面时才重定向
            if (window.location.pathname !== '/login' && window.location.pathname !== '/register') {
                const redirectUrl = encodeURIComponent(window.location.pathname + window.location.search);
                window.location.href = `/login?session_expired=true&redirect=${redirectUrl}`;
            }
        }
        return Promise.reject(error);
    }
);

function interceptPageNavigation() {
    // 拦截所有指向仪表盘的链接点击
    document.addEventListener('click', function(e) {
        const link = e.target.closest('a');
        if (!link) return;

        const href = link.getAttribute('href');
        if (href && href.startsWith('/dashboard')) {
            e.preventDefault();
            navigateToAuthenticatedPage(href);
        }
    });

    // 拦截浏览器的前进后退
    window.addEventListener('popstate', function(e) {
        if (window.location.pathname.startsWith('/dashboard')) {
            e.preventDefault();
            navigateToAuthenticatedPage(window.location.pathname + window.location.search);
        }
    });
}

// 带认证的页面导航
async function navigateToAuthenticatedPage(url) {
    const token = localStorage.getItem('token');

    if (!token) {
        window.location.href = `/login?redirect=${encodeURIComponent(url)}`;
        return;
    }

    try {
        // 使用 fetch 而不是直接导航，这样可以发送 Authorization header
        const response = await fetch(url, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
            },
            credentials: 'same-origin'
        });

        if (response.ok) {
            const html = await response.text();
            // 更新页面内容
            document.documentElement.innerHTML = html;
            // 更新浏览器地址栏
            history.pushState(null, '', url);
            // 重新初始化页面脚本
            reinitializePage();
        } else if (response.status === 401) {
            // Token 过期或无效
            localStorage.removeItem('token');
            window.location.href = `/login?session_expired=true&redirect=${encodeURIComponent(url)}`;
        } else {
            // 其他错误
            console.error('Page navigation failed:', response.status);
            window.location.href = url; // 降级到普通导航
        }
    } catch (error) {
        console.error('Navigation error:', error);
        window.location.href = url; // 降级到普通导航
    }
}

// 重新初始化页面脚本
function reinitializePage() {
    // 重新检查认证状态
    checkAuthStatus();

    // 重新绑定退出登录事件
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', function(e) {
            e.preventDefault();
            logout();
        });
    }

    // 重新初始化其他页面特定的脚本
    initializePageSpecificScripts();
}

// 初始化页面特定脚本
function initializePageSpecificScripts() {
    // 如果是文章管理页面，初始化删除按钮
    const deleteButtons = document.querySelectorAll('.delete-post');
    deleteButtons.forEach(button => {
        button.addEventListener('click', function() {
            const postId = this.getAttribute('data-id');
            const postTitle = this.getAttribute('data-title');

            if (confirm(`确定要删除文章《${postTitle}》吗？此操作不可恢复。`)) {
                axios.delete(`/posts/${postId}`)
                    .then(() => {
                        window.location.reload();
                    })
                    .catch(error => {
                        alert('删除失败：' + (error.response?.data?.detail || '未知错误'));
                    });
            }
        });
    });

    // 如果是新建文章页面，初始化表单
    const newPostForm = document.getElementById('new-post-form');
    if (newPostForm) {
        initializeNewPostForm();
    }
}

// 初始化新建文章表单
function initializeNewPostForm() {
    const form = document.getElementById('new-post-form');
    const errorDiv = document.getElementById('post-error');
    const successDiv = document.getElementById('post-success');

    if (!form) return;

    form.addEventListener('submit', async function(e) {
        e.preventDefault();

        if (errorDiv) errorDiv.classList.add('d-none');
        if (successDiv) successDiv.classList.add('d-none');

        const data = {
            title: document.getElementById('title')?.value,
            slug: document.getElementById('slug')?.value || undefined,
            content: document.getElementById('content')?.value,
            category_id: parseInt(document.getElementById('category')?.value) || null,
            published: document.getElementById('published')?.checked || false,
            tags: document.getElementById('tags')?.value.split(',').map(t => t.trim()).filter(t => t) || []
        };

        try {
            const response = await axios.post('/posts', data);
            if (successDiv) {
                successDiv.textContent = '文章创建成功！';
                successDiv.classList.remove('d-none');
            }

            // 3秒后跳转到文章列表
            setTimeout(() => {
                navigateToAuthenticatedPage('/dashboard/posts');
            }, 3000);
        } catch (error) {
            console.error('创建文章失败', error);
            if (errorDiv) {
                errorDiv.textContent = error.response?.data?.detail || '创建文章失败，请稍后再试';
                errorDiv.classList.remove('d-none');
            }
        }
    });

    // 自动生成slug
    const titleInput = document.getElementById('title');
    const slugInput = document.getElementById('slug');
    if (titleInput && slugInput) {
        titleInput.addEventListener('blur', function() {
            if (!slugInput.value) {
                slugInput.value = this.value.toLowerCase()
                    .replace(/[^a-z0-9\u4e00-\u9fa5]/g, '-')
                    .replace(/-+/g, '-')
                    .replace(/^-|-$/g, '');
            }
        });
    }
}

// 修改 DOMContentLoaded 事件监听器
document.addEventListener('DOMContentLoaded', async function() {
    // 检查认证状态
    await checkAuthStatus();

    // 初始化页面导航拦截
    interceptPageNavigation();

    // 退出登录按钮事件
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', function(e) {
            e.preventDefault();
            logout();
        });
    }

    // 初始化页面特定脚本
    initializePageSpecificScripts();

    // 检查当前页面是否需要认证
    const currentPath = window.location.pathname;
    if (currentPath.startsWith('/dashboard')) {
        const token = localStorage.getItem('token');
        if (!token) {
            window.location.href = '/login?redirect=' + encodeURIComponent(window.location.pathname + window.location.search);
        } else {
            // 如果已经在仪表盘页面但没有正确加载，尝试重新加载
            if (document.body.innerHTML.includes('{"detail":"Not authenticated"}')) {
                navigateToAuthenticatedPage(currentPath);
            }
        }
    }
});

// 为了向后兼容，导出一些函数到全局作用域
window.checkAuthStatus = checkAuthStatus;
window.getCurrentUser = getCurrentUser;
window.getAuthStatus = getAuthStatus;
window.logout = logout;
