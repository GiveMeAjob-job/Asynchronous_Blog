let currentUser = null;
let isAuthenticated = false;
let refreshPromise = null;
let logoutInProgress = false;

axios.defaults.baseURL = "/api/v1";
axios.defaults.withCredentials = true;

function clearSession() {
    currentUser = null;
    isAuthenticated = false;
}

function updateAuthUI() {
    const authButtons = document.getElementById("auth-buttons");
    const userMenu = document.getElementById("user-menu");
    const navUsername = document.getElementById("navUsername");
    const navAvatar = document.getElementById("navAvatar");

    if (isAuthenticated && currentUser) {
        authButtons?.classList.add("d-none");
        userMenu?.classList.remove("d-none");

        const displayName = currentUser.full_name || currentUser.username || "用户";
        if (navUsername) {
            navUsername.textContent = displayName;
        }
        if (navAvatar) {
            navAvatar.textContent = displayName.charAt(0).toUpperCase();
        }
        return;
    }

    authButtons?.classList.remove("d-none");
    userMenu?.classList.add("d-none");
}

async function refreshSession() {
    if (refreshPromise) {
        return refreshPromise;
    }

    refreshPromise = axios.post("/auth/refresh-token", null, {
        _skipAuthRefresh: true,
        _silentAuthFailure: true
    }).then(() => true).catch(() => {
        clearSession();
        return false;
    }).finally(() => {
        refreshPromise = null;
    });

    return refreshPromise;
}

async function checkAuthStatus() {
    try {
        const response = await axios.get("/users/me", {_silentAuthFailure: true});
        currentUser = response.data;
        isAuthenticated = true;
        updateAuthUI();
        return true;
    } catch (error) {
        clearSession();
        updateAuthUI();
        return false;
    }
}

function getCurrentUser() {
    return currentUser;
}

function getAuthStatus() {
    return isAuthenticated;
}

async function logout() {
    if (logoutInProgress) {
        return;
    }

    logoutInProgress = true;
    try {
        await axios.post("/auth/logout", null, {
            _skipAuthRefresh: true,
            _silentAuthFailure: true
        });
    } catch (error) {
        console.warn("Logout request failed", error);
    } finally {
        clearSession();
        updateAuthUI();
        logoutInProgress = false;
        window.location.href = "/";
    }
}

function bindLogout() {
    const logoutBtn = document.getElementById("logout-btn");
    if (!logoutBtn || logoutBtn.dataset.bound === "true") {
        return;
    }
    logoutBtn.dataset.bound = "true";
    logoutBtn.addEventListener("click", async function (event) {
        event.preventDefault();
        await logout();
    });
}

function bindNavbarToggle() {
    const toggle = document.getElementById("navbarToggle");
    const menu = document.getElementById("navbarNav");
    const backdrop = document.getElementById("navbarBackdrop");

    if (!toggle || !menu) {
        return;
    }

    const closeMenu = () => {
        menu.classList.remove("show");
        backdrop?.classList.remove("show");
        toggle.setAttribute("aria-expanded", "false");
        document.body.classList.remove("nav-open");
    };

    const openMenu = () => {
        menu.classList.add("show");
        backdrop?.classList.add("show");
        toggle.setAttribute("aria-expanded", "true");
        document.body.classList.add("nav-open");
    };

    toggle.addEventListener("click", function () {
        const isOpen = menu.classList.contains("show");
        if (isOpen) {
            closeMenu();
        } else {
            openMenu();
        }
    });

    backdrop?.addEventListener("click", closeMenu);
    menu.querySelectorAll(".nav-link, .btn").forEach((link) => {
        link.addEventListener("click", () => {
            if (window.innerWidth <= 820) {
                closeMenu();
            }
        });
    });

    window.addEventListener("resize", () => {
        if (window.innerWidth > 820) {
            closeMenu();
        }
    });
}

function guardDashboardRoute() {
    if (!window.location.pathname.startsWith("/dashboard")) {
        return;
    }

    if (!isAuthenticated) {
        const redirectUrl = encodeURIComponent(window.location.pathname + window.location.search);
        window.location.href = `/login?redirect=${redirectUrl}`;
    }
}

axios.interceptors.response.use(
    (response) => response,
    async (error) => {
        const originalRequest = error.config || {};
        if (error.response?.status === 401) {
            const safePaths = ["/login", "/register", "/forgot-password", "/reset-password"];
            const shouldRefresh = !originalRequest._retry && !originalRequest._skipAuthRefresh;
            if (shouldRefresh) {
                originalRequest._retry = true;
                const refreshed = await refreshSession();
                if (refreshed) {
                    return axios(originalRequest);
                }
            }

            clearSession();
            updateAuthUI();

            if (!originalRequest._silentAuthFailure && !safePaths.includes(window.location.pathname)) {
                const redirectUrl = encodeURIComponent(window.location.pathname + window.location.search);
                window.location.href = `/login?session_expired=true&redirect=${redirectUrl}`;
            }
        }
        return Promise.reject(error);
    }
);

document.addEventListener("DOMContentLoaded", async function () {
    await checkAuthStatus();
    bindNavbarToggle();
    bindLogout();
    guardDashboardRoute();
});

window.checkAuthStatus = checkAuthStatus;
window.getCurrentUser = getCurrentUser;
window.getAuthStatus = getAuthStatus;
window.logout = logout;
