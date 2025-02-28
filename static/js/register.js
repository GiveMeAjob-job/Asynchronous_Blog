REGISTER_JS = """
document.addEventListener('DOMContentLoaded', function() {
    const registerForm = document.getElementById('register-form');
    const registerError = document.getElementById('register-error');

    registerForm.addEventListener('submit', async function(e) {
        e.preventDefault();

        const username = document.getElementById('username').value;
        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;
        const confirmPassword = document.getElementById('confirm-password').value;
        const agreeTerms = document.getElementById('agree-terms').checked;

        registerError.classList.add('d-none');

        // 基本表单验证
        if (password !== confirmPassword) {
            registerError.textContent = '两次输入的密码不一致';
            registerError.classList.remove('d-none');
            return;
        }

        if (!agreeTerms) {
            registerError.textContent = '请阅读并同意服务条款和隐私政策';
            registerError.classList.remove('d-none');
            return;
        }

        try {
            const response = await axios.post('/api/v1/auth/register', {
                username: username,
                email: email,
                password: password
            });

            // 注册成功，重定向到登录页
            window.location.href = '/login?registered=true';
        } catch (error) {
            console.error('注册失败', error);

            let errorMessage = '注册失败，请稍后再试';
            if (error.response && error.response.data && error.response.data.detail) {
                errorMessage = error.response.data.detail;
            }

            registerError.textContent = errorMessage;
            registerError.classList.remove('d-none');
        }
    });
});
"""
