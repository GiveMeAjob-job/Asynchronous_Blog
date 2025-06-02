
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
            const response = await axios.post('auth/login',
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

            // 登录成功，保存token到localStorage和cookie
            const token = response.data.access_token;
            localStorage.setItem('token', token);
            
            // 设置cookie
            const maxAge = rememberMe ? 7 * 24 * 60 * 60 : 24 * 60 * 60; // 7天或1天
            document.cookie = `access_token=${token}; path=/; max-age=${maxAge}`;

            // 重定向到首页或之前的页面
            const urlParams = new URLSearchParams(window.location.search);
            const redirect = urlParams.get('redirect') || '/';
            window.location.href = redirect;
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
    
    // 检查是否是从注册页面跳转过来的
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('registered') === 'true') {
        const successAlert = document.createElement('div');
        successAlert.className = 'alert alert-success';
        successAlert.textContent = '注册成功！请登录您的账号。';
        loginError.parentNode.insertBefore(successAlert, loginError);
    }
});
