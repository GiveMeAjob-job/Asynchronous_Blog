document.addEventListener("DOMContentLoaded", function () {
    const loginForm = document.getElementById("login-form");
    const loginError = document.getElementById("login-error");

    function showError(message) {
        loginError.textContent = message;
        loginError.classList.remove("d-none");
    }

    function showSuccess(message) {
        const success = document.createElement("div");
        success.className = "form-message success";
        success.textContent = message;
        loginError.parentNode.insertBefore(success, loginError);
    }

    loginForm?.addEventListener("submit", async function (e) {
        e.preventDefault();
        loginError.classList.add("d-none");

        const email = document.getElementById("email").value;
        const password = document.getElementById("password").value;
        const rememberMe = document.getElementById("remember-me").checked;

        try {
            const response = await axios.post(
                "/auth/login",
                new URLSearchParams({
                    username: email,
                    password,
                    remember_me: rememberMe ? "true" : "false"
                }),
                {headers: {"Content-Type": "application/x-www-form-urlencoded"}}
            );

            await window.checkAuthStatus?.();
            showSuccess("登录成功，正在跳转...");

            const redirect = new URLSearchParams(window.location.search).get("redirect") || "/dashboard";
            setTimeout(() => {
                window.location.href = redirect;
            }, 800);
        } catch (error) {
            if (error.response?.status === 401) {
                showError("邮箱或密码错误。");
                return;
            }
            if (error.response?.status === 422) {
                showError("请检查邮箱和密码格式。");
                return;
            }
            if (error.response?.status === 400 && error.response?.data?.detail) {
                showError(error.response.data.detail);
                return;
            }
            showError(error.response?.data?.detail || "登录失败，请稍后再试。");
        }
    });

    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get("registered") === "true") {
        showSuccess("注册成功，现在可以直接登录。");
    }
    if (urlParams.get("session_expired") === "true") {
        const warning = document.createElement("div");
        warning.className = "form-message warning";
        warning.textContent = "会话已过期，请重新登录。";
        loginError.parentNode.insertBefore(warning, loginError);
    }
});
