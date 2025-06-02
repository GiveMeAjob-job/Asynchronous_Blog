document.addEventListener('DOMContentLoaded', function() {
    console.log('=== REGISTER.JS DEBUG START ===');

    // 1. 检查表单元素
    const registerForm = document.getElementById('register-form');
    console.log('1. Register form element:', registerForm);

    // 2. 检查错误显示元素
    const registerError = document.getElementById('register-error');
    console.log('2. Register error element:', registerError);

    // 3. 检查所有输入元素
    console.log('3. Checking all form inputs:');
    console.log('   - registerUsername input:', document.getElementById('registerUsername'));
    console.log('   - email input:', document.getElementById('email'));
    console.log('   - password input:', document.getElementById('password'));
    console.log('   - confirm-password input:', document.getElementById('confirm-password'));
    console.log('   - agree-terms checkbox:', document.getElementById('agree-terms'));

    // 4. 检查页面上所有包含 "username" 的元素
    console.log('4. All elements with "username" in ID:',
        Array.from(document.querySelectorAll('[id*="username"]')).map(el => ({
            id: el.id,
            tagName: el.tagName,
            type: el.type,
            value: el.value
        }))
    );

    if (!registerForm) {
        console.error('ERROR: Register form not found!');
        return;
    }

    registerForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        console.log('=== FORM SUBMIT DEBUG START ===');

        // 获取所有表单值并详细记录
        const usernameElement = document.getElementById('registerUsername');
        const emailElement = document.getElementById('email');
        const passwordElement = document.getElementById('password');
        const confirmPasswordElement = document.getElementById('confirm-password');
        const agreeTermsElement = document.getElementById('agree-terms');

        console.log('Form elements at submit time:');
        console.log('- Username element:', usernameElement);
        console.log('- Email element:', emailElement);
        console.log('- Password element:', passwordElement);
        console.log('- Confirm Password element:', confirmPasswordElement);
        console.log('- Agree Terms element:', agreeTermsElement);

        // 获取值
        const username = usernameElement ? usernameElement.value : undefined;
        const email = emailElement ? emailElement.value : undefined;
        const password = passwordElement ? passwordElement.value : undefined;
        const confirmPassword = confirmPasswordElement ? confirmPasswordElement.value : undefined;
        const agreeTerms = agreeTermsElement ? agreeTermsElement.checked : false;

        console.log('Form values:');
        console.log('- username:', username, typeof username);
        console.log('- email:', email, typeof email);
        console.log('- password:', password ? '[HIDDEN]' : undefined);
        console.log('- confirmPassword:', confirmPassword ? '[HIDDEN]' : undefined);
        console.log('- agreeTerms:', agreeTerms);

        // 如果 username 是 undefined，进行更深入的检查
        if (username === undefined || username === '') {
            console.error('USERNAME PROBLEM DETECTED!');
            console.log('Username element exists?', !!usernameElement);
            if (usernameElement) {
                console.log('Username element properties:');
                console.log('- id:', usernameElement.id);
                console.log('- name:', usernameElement.name);
                console.log('- type:', usernameElement.type);
                console.log('- value:', usernameElement.value);
                console.log('- defaultValue:', usernameElement.defaultValue);
                console.log('- disabled:', usernameElement.disabled);
                console.log('- readOnly:', usernameElement.readOnly);
                console.log('- required:', usernameElement.required);
                console.log('- placeholder:', usernameElement.placeholder);
                console.log('- offsetParent (visible?):', usernameElement.offsetParent);
                console.log('- parentElement:', usernameElement.parentElement);

                // 检查计算样式
                const styles = window.getComputedStyle(usernameElement);
                console.log('- display:', styles.display);
                console.log('- visibility:', styles.visibility);
                console.log('- opacity:', styles.opacity);
            }
        }

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

        // 构建请求数据
        const payload = {
            username: username,
            email: email,
            password: password,
            is_active: true,
            is_superuser: false
        };

        console.log('=== PAYLOAD DEBUG ===');
        console.log('Payload object:', payload);
        console.log('Payload JSON:', JSON.stringify(payload));
        console.log('Username in payload:', payload.username);
        console.log('Username type in payload:', typeof payload.username);

        try {
            console.log('Sending request to:', '/auth/register');
            const response = await axios.post('/auth/register', payload);
            console.log('Registration successful:', response.data);
            window.location.href = '/login?registered=true';
        } catch (error) {
            console.error('=== REGISTRATION ERROR ===');
            console.error('Full error object:', error);

            let errorMessage = '注册失败，请稍后再试';
            if (error.response) {
                console.error('Response data:', error.response.data);
                console.error('Response status:', error.response.status);
                console.error('Response headers:', error.response.headers);

                if (error.response.data && error.response.data.detail) {
                    if (Array.isArray(error.response.data.detail)) {
                        errorMessage = error.response.data.detail
                            .map(err => `${err.loc.join('.')} - ${err.msg}`)
                            .join('; ');
                    } else {
                        errorMessage = error.response.data.detail;
                    }
                }
            } else if (error.request) {
                console.error('Request made but no response:', error.request);
                errorMessage = '请求已发出但没有收到响应';
            } else {
                console.error('Request setup error:', error.message);
                errorMessage = `请求设置错误: ${error.message}`;
            }

            registerError.textContent = errorMessage;
            registerError.classList.remove('d-none');
        }

        console.log('=== FORM SUBMIT DEBUG END ===');
    });

    console.log('=== REGISTER.JS DEBUG END ===');
});
