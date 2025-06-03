// static/js/reset_password.js
// Handle setting new password using token from query parameter

document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('reset-password-form');
    const errorDiv = document.getElementById('reset-error');
    const successDiv = document.getElementById('reset-success');

    if (!form) return;

    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get('token');

    form.addEventListener('submit', async function (e) {
        e.preventDefault();

        const password = document.getElementById('password').value;
        const confirmPassword = document.getElementById('confirm-password').value;

        errorDiv.classList.add('d-none');
        successDiv.classList.add('d-none');

        if (password !== confirmPassword) {
            errorDiv.textContent = '两次输入的密码不一致';
            errorDiv.classList.remove('d-none');
            return;
        }

        try {
            await axios.post('/api/v1/auth/reset-password', { token, new_password: password });
            successDiv.textContent = '密码已重置，请重新登录。';
            successDiv.classList.remove('d-none');
            form.reset();
        } catch (err) {
            const msg = err.response && err.response.data && err.response.data.detail
                ? err.response.data.detail
                : '重置失败，请稍后重试';
            errorDiv.textContent = msg;
            errorDiv.classList.remove('d-none');
        }
    });
});
