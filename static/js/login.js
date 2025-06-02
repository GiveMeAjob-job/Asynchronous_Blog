// 更新 static/js/login.js - 修复登录后跳转问题

document.addEventListener('DOMContentLoaded', function() {
    const loginForm = document.getElementById('login-form');
    const loginError = document.getElementById('login-error');

    loginForm.addEventListener('submit', async function(e) {
        e.preventDefault();

        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;
        const rememberMe = document.getElementById('remember-me').checked;

        loginError.classList.add('d-none');

        try {
            console.log('正在登录...');
            
            // 登录请求
            const response = await axios.post('/auth/login',
                new URLSearchParams({
                    'username': email,
                    'password': password
                }),
                {
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded'
                    }
                }
            );

            console.log('登录成功，获取到token');
            
            // 保存token
            const token = response.data.access_token;
            localStorage.setItem('token', token);
            
            // 设置cookie（重要：这样后端也能从cookie获取token）
            const maxAge = rememberMe ? 7 * 24 * 60 * 60 : 24 * 60 * 60;
            document.cookie = `access_token=${token}; path=/; max-age=${maxAge}; SameSite=Lax`;

            console.log('Token已保存到localStorage和cookie');

            // 更新页面认证状态
            if (window.checkAuthStatus) {
                await window.checkAuthStatus();
            }

            // 显示成功消息
            const successDiv = document.createElement('div');
            successDiv.className = 'form-message success';
            successDiv.textContent = '登录成功！正在跳转...';
            loginError.parentNode.insertBefore(successDiv, loginError);

            // 获取重定向URL
            const urlParams = new URLSearchParams(window.location.search);
            const redirect = urlParams.get('redirect') || '/dashboard';
            
            console.log('准备跳转到:', redirect);

            // 延迟跳转，确保token已保存
            setTimeout(() => {
                console.log('开始跳转...');
                
                // 如果是仪表盘页面，使用特殊的跳转方式
                if (redirect.startsWith('/dashboard')) {
                    // 先跳转到主页，再通过JavaScript导航到仪表盘
                    window.location.href = '/?auto_redirect=' + encodeURIComponent(redirect);
                } else {
                    window.location.href = redirect;
                }
            }, 1500);

        } catch (error) {
            console.error('登录失败', error);

            let errorMessage = '登录失败，请检查您的邮箱和密码';
            
            if (error.response) {
                if (error.response.data && error.response.data.detail) {
                    errorMessage = error.response.data.detail;
                } else if (error.response.status === 422) {
                    errorMessage = '请检查输入的邮箱和密码格式';
                } else if (error.response.status === 401) {
                    errorMessage = '邮箱或密码错误';
                }
            } else if (error.request) {
                errorMessage = '网络连接失败，请检查网络连接';
            }

            loginError.textContent = errorMessage;
            loginError.classList.remove('d-none');
        }
    });
    
    // 检查URL参数显示相应消息
    const urlParams = new URLSearchParams(window.location.search);
    
    if (urlParams.get('registered') === 'true') {
        const successAlert = document.createElement('div');
        successAlert.className = 'form-message success';
        successAlert.textContent = '注册成功！请登录您的账号。';
        loginError.parentNode.insertBefore(successAlert, loginError);
    }
    
    if (urlParams.get('session_expired') === 'true') {
        const warningAlert = document.createElement('div');
        warningAlert.className = 'form-message warning';
        warningAlert.textContent = '会话已过期，请重新登录。';
        loginError.parentNode.insertBefore(warningAlert, loginError);
    }
});
