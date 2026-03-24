document.addEventListener("DOMContentLoaded", function () {
    const registerForm = document.getElementById("register-form");
    const registerError = document.getElementById("register-error");

    function showError(message) {
        registerError.textContent = message;
        registerError.classList.remove("d-none");
    }

    registerForm?.addEventListener("submit", async function (e) {
        e.preventDefault();
        registerError.classList.add("d-none");

        const username = document.getElementById("registerUsername").value.trim();
        const email = document.getElementById("email").value.trim();
        const password = document.getElementById("password").value;
        const confirmPassword = document.getElementById("confirm-password").value;
        const agreeTerms = document.getElementById("agree-terms").checked;

        if (password !== confirmPassword) {
            showError("两次输入的密码不一致。");
            return;
        }

        if (!agreeTerms) {
            showError("请先同意服务条款和隐私政策。");
            return;
        }

        try {
            await axios.post("/auth/register", {
                username,
                email,
                password,
                is_active: true,
                is_superuser: false,
            });
            window.location.href = "/login?registered=true";
        } catch (error) {
            const detail = error.response?.data?.detail;
            const message = Array.isArray(detail)
                ? detail.map((item) => `${item.loc.join(".")} - ${item.msg}`).join("; ")
                : (detail || "注册失败，请稍后再试。");
            showError(message);
        }
    });
});
