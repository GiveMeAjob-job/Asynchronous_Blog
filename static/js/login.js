LOGIN_JS = """
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
            const response = await axios.post('/api/v1/auth/login',
                new URLSearchParams({
                    'username': email,  // API接收username参数，但我们使用email
                    'password': password
                }),
                {
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded'
                    }
                }
            );

            // 登录成功，保存token
            localStorage.setItem('token', response.data.access_token);

            // 如果勾选了"记住我"，可以在这里设置持久化存储
            // 重定向到首页
            window.location.href = '/';
        } catch (error) {
            console.error('登录失败', error);

            let errorMessage = '登录失败，请检查您的邮箱和密码';
            if (error.response && error.response.data && error.response.data.detail) {
                errorMessage = error.response.data.detail;
            }

            loginError.textContent = errorMessage;
            loginError.classList.remove('d-none');
        }
    });
});
"""
