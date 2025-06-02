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

        // --- 调试代码开始 ---
        console.log("Username from form:", username); // 打印获取到的用户名
        const payload = {
            username: username,
            email: email,
            password: password,
            is_active: true,
            is_superuser: false
        };
        console.log("--- DEBUG: Register Payload ---");
        console.log("Username value from form: ", username);
        console.log("Payload object being sent: ", payload);
        console.log("Payload as JSON string: ", JSON.stringify(payload)); // 非常重要：查看 undefined 是否导致字段丢失
        console.log("--- END DEBUG ---");
        // --- 调试代码结束 ---

        try {
            const response = await axios.post('/auth/register', payload);


            // 注册成功，重定向到登录页
            window.location.href = '/login?registered=true';
        } catch (error) {
            console.error('注册失败', error);
            // ... (您现有的错误处理逻辑) ...
        let errorMessage = '注册失败，请稍后再试';
        if (error.response) { // 服务器有响应，但状态码不是 2xx
            console.error('服务器响应数据:', error.response.data);
            console.error('服务器响应状态:', error.response.status);
            console.error('服务器响应头:', error.response.headers);
            if (error.response.data && error.response.data.detail) {
                if (Array.isArray(error.response.data.detail)) {
                    errorMessage = error.response.data.detail.map(err => `${err.loc.join('.')} - ${err.msg}`).join('; ');
                } else {
                    errorMessage = error.response.data.detail;
                }
            } else if (error.response.status === 404) {
                errorMessage = '注册接口未找到，请联系管理员。'; // 针对 404 的特定消息
            }
        } else if (error.request) { // 请求已发出但没有收到响应
            console.error('请求已发出但无响应:', error.request);
            errorMessage = '请求已发出但没有收到响应，请检查网络连接或服务器状态。';
        } else { // 设置请求时发生错误
            console.error('请求设置错误:', error.message);
            errorMessage = `请求设置时发生错误: ${error.message}`;
        }

        const registerError = document.getElementById('register-error'); // 确保 registerError 在这里定义或可访问
        registerError.textContent = errorMessage;
        registerError.classList.remove('d-none');
    }
    });
});
