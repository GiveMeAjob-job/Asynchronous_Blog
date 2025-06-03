// static/js/forgot_password.js
// Handle password reset request form

document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('forgot-password-form');
    const errorDiv = document.getElementById('forgot-error');
    const successDiv = document.getElementById('forgot-success');

    if (!form) return;

    form.addEventListener('submit', async function (e) {
        e.preventDefault();

        const email = document.getElementById('email').value;
        errorDiv.classList.add('d-none');
        successDiv.classList.add('d-none');

        try {
            await axios.post('/api/v1/auth/request-password-reset', { email });
            successDiv.textContent = '重置链接已发送，请检查邮箱。';
            successDiv.classList.remove('d-none');
            form.reset();
        } catch (err) {
            const msg = err.response && err.response.data && err.response.data.detail
                ? err.response.data.detail
                : '请求失败，请稍后重试';
            errorDiv.textContent = msg;
            errorDiv.classList.remove('d-none');
        }
    });
});
