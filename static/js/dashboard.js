function parseApiError(error, fallbackMessage) {
    const detail = error.response?.data?.detail;
    if (Array.isArray(detail)) {
        return detail.map((item) => `${item.loc.join(".")} - ${item.msg}`).join("; ");
    }
    return detail || fallbackMessage;
}

function showFormMessage(target, message) {
    if (!target) {
        return;
    }
    target.textContent = message;
    target.classList.remove("d-none");
}

function hideFormMessages(...targets) {
    targets.forEach((target) => target?.classList.add("d-none"));
}

function slugify(value) {
    return value
        .trim()
        .toLowerCase()
        .replace(/\s+/g, "-")
        .replace(/[^a-z0-9\u4e00-\u9fa5-]/g, "")
        .replace(/-+/g, "-")
        .replace(/^-|-$/g, "");
}

function debounce(callback, wait) {
    let timeoutId = null;
    return (...args) => {
        clearTimeout(timeoutId);
        timeoutId = window.setTimeout(() => callback(...args), wait);
    };
}

function bindDeletePostButtons() {
    document.querySelectorAll(".delete-post").forEach((button) => {
        if (button.dataset.bound === "true") {
            return;
        }

        button.dataset.bound = "true";
        button.addEventListener("click", async function () {
            const postId = this.dataset.id;
            const postTitle = this.dataset.title;
            if (!confirm(`确定要删除文章《${postTitle}》吗？此操作不可恢复。`)) {
                return;
            }

            try {
                await axios.delete(`/posts/${postId}`);
                window.location.reload();
            } catch (error) {
                alert(parseApiError(error, "删除失败，请稍后再试。"));
            }
        });
    });
}

async function copyTextToClipboard(value) {
    if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
        return;
    }

    const helper = document.createElement("textarea");
    helper.value = value;
    helper.setAttribute("readonly", "readonly");
    helper.style.position = "absolute";
    helper.style.left = "-9999px";
    document.body.appendChild(helper);
    helper.select();
    document.execCommand("copy");
    document.body.removeChild(helper);
}

function showPreviewFeedback(message, kind = "success") {
    const feedbackNode = document.getElementById("post-preview-feedback");
    if (!feedbackNode) {
        alert(message);
        return;
    }

    feedbackNode.textContent = message;
    feedbackNode.classList.remove("d-none", "success", "warning", "error");
    feedbackNode.classList.add(kind);
}

function bindPreviewLinkButtons() {
    document.querySelectorAll(".generate-preview-link").forEach((button) => {
        if (button.dataset.bound === "true") {
            return;
        }

        button.dataset.bound = "true";
        button.addEventListener("click", async function () {
            const postId = this.dataset.postId;
            const originalLabel = this.dataset.originalLabel || this.textContent.trim();
            this.dataset.originalLabel = originalLabel;
            this.disabled = true;

            try {
                const response = await axios.post(`/posts/${postId}/preview-link`);
                const previewUrl = response.data.preview_url;
                const expiresAt = response.data.expires_at ? new Date(response.data.expires_at) : null;

                await copyTextToClipboard(previewUrl);
                this.textContent = "已复制预览链接";

                const message = expiresAt
                    ? `草稿预览链接已复制，可分享给协作者查看。链接将于 ${expiresAt.toLocaleString()} 失效。`
                    : "草稿预览链接已复制。";
                showPreviewFeedback(message, "warning");

                window.setTimeout(() => {
                    this.textContent = originalLabel;
                }, 2200);
            } catch (error) {
                showPreviewFeedback(parseApiError(error, "生成预览链接失败，请稍后再试。"), "error");
            } finally {
                this.disabled = false;
            }
        });
    });
}

function collectPostPayload() {
    return {
        title: document.getElementById("title")?.value.trim(),
        summary: document.getElementById("summary")?.value.trim() || null,
        slug: document.getElementById("slug")?.value.trim() || undefined,
        content: document.getElementById("content")?.value || "",
        featured_image: document.getElementById("featured-image")?.value.trim() || null,
        category_id: parseInt(document.getElementById("category")?.value, 10) || null,
        tags: (document.getElementById("tags-input")?.value || "")
            .split(",")
            .map((tag) => tag.trim())
            .filter(Boolean),
        published: document.getElementById("published")?.checked || false,
        is_featured: document.getElementById("is-featured")?.checked || false,
        allow_comments: document.getElementById("allow-comments")?.checked ?? true,
        meta_title: document.getElementById("meta-title")?.value.trim() || null,
        meta_description: document.getElementById("meta-description")?.value.trim() || null,
        meta_keywords: document.getElementById("meta-keywords")?.value.trim() || null,
    };
}

function bindPostEditorForm() {
    const form = document.getElementById("post-editor-form");
    if (!form) {
        return;
    }

    const titleInput = document.getElementById("title");
    const slugInput = document.getElementById("slug");
    const tagsInput = document.getElementById("tags-input");
    const contentInput = document.getElementById("content");
    const previewPane = document.getElementById("editor-preview");
    const errorDiv = document.getElementById("post-error");
    const successDiv = document.getElementById("post-success");

    titleInput?.addEventListener("input", function () {
        if (slugInput && slugInput.dataset.touched !== "true") {
            slugInput.value = slugify(this.value);
        }
    });

    slugInput?.addEventListener("input", function () {
        slugInput.dataset.touched = "true";
    });

    document.querySelectorAll(".tag-button").forEach((button) => {
        button.addEventListener("click", function () {
            if (!tagsInput) {
                return;
            }

            const tagName = this.dataset.tagName;
            const tags = tagsInput.value.split(",").map((tag) => tag.trim()).filter(Boolean);
            if (!tags.includes(tagName)) {
                tags.push(tagName);
                tagsInput.value = tags.join(", ");
            }
        });
    });

    const renderPreview = debounce(async () => {
        if (!previewPane || !contentInput) {
            return;
        }

        const content = contentInput.value.trim();
        if (!content) {
            previewPane.innerHTML = '<p class="muted">开始输入正文后，这里会同步显示渲染结果。</p>';
            return;
        }

        previewPane.innerHTML = '<p class="muted">正在生成预览...</p>';
        try {
            const response = await axios.post("/posts/preview-markdown", { content: contentInput.value });
            previewPane.innerHTML = response.data.html || '<p class="muted">当前内容暂无预览。</p>';
        } catch (error) {
            previewPane.innerHTML = `<p class="muted">${parseApiError(error, "预览生成失败，请稍后再试。")}</p>`;
        }
    }, 260);

    contentInput?.addEventListener("input", renderPreview);
    renderPreview();

    form.addEventListener("submit", async function (event) {
        event.preventDefault();
        hideFormMessages(errorDiv, successDiv);

        const mode = form.dataset.mode;
        const postId = form.dataset.postId;
        const payload = collectPostPayload();

        try {
            const response = mode === "edit"
                ? await axios.put(`/posts/${postId}`, payload)
                : await axios.post("/posts", payload);

            showFormMessage(
                successDiv,
                mode === "edit"
                    ? (payload.published ? "文章更新成功，正在跳转..." : "草稿已保存，可以继续编辑或生成私密预览链接。")
                    : (payload.published ? "文章创建成功，正在跳转..." : "草稿已创建，正在前往编辑页...")
            );

            const redirectUrl = payload.published && response.data?.slug
                ? `/post/${response.data.slug}`
                : `/dashboard/posts/edit/${response.data?.id || postId}`;

            setTimeout(() => {
                window.location.href = redirectUrl;
            }, 900);
        } catch (error) {
            showFormMessage(errorDiv, parseApiError(error, "保存文章失败，请稍后再试。"));
        }
    });
}

function bindProfileEditForm() {
    const form = document.getElementById("profile-edit-form");
    if (!form) {
        return;
    }

    const errorDiv = document.getElementById("profile-update-error");
    const successDiv = document.getElementById("profile-update-success");

    form.addEventListener("submit", async function (event) {
        event.preventDefault();
        hideFormMessages(errorDiv, successDiv);

        const password = document.getElementById("editPassword")?.value || "";
        const confirmPassword = document.getElementById("editConfirmPassword")?.value || "";
        if (password && password !== confirmPassword) {
            showFormMessage(errorDiv, "两次输入的新密码不一致。");
            return;
        }

        const payload = {
            username: document.getElementById("editUsername")?.value.trim(),
            email: document.getElementById("editEmail")?.value.trim(),
            full_name: document.getElementById("editFullName")?.value.trim() || null,
            location: document.getElementById("editLocation")?.value.trim() || null,
            avatar_url: document.getElementById("editAvatarUrl")?.value.trim() || null,
            website: document.getElementById("editWebsite")?.value.trim() || null,
            bio: document.getElementById("editBio")?.value.trim() || null,
        };

        if (password) {
            payload.password = password;
        }

        try {
            const response = await axios.put("/users/me", payload);
            showFormMessage(successDiv, "个人资料已更新。");

            const navUsername = document.getElementById("navUsername");
            const navAvatar = document.getElementById("navAvatar");
            const displayName = response.data.full_name || response.data.username;

            if (navUsername) {
                navUsername.textContent = displayName;
            }
            if (navAvatar) {
                navAvatar.textContent = displayName.charAt(0).toUpperCase();
            }

            setTimeout(() => {
                window.location.href = "/dashboard/profile";
            }, 800);
        } catch (error) {
            showFormMessage(errorDiv, parseApiError(error, "更新资料失败，请稍后再试。"));
        }
    });
}

function updateModerationCounter(id, delta) {
    const node = document.getElementById(id);
    if (!node) {
        return;
    }
    const current = parseInt(node.textContent, 10) || 0;
    node.textContent = String(Math.max(0, current + delta));
}

function renderModerationEmptyState() {
    const list = document.querySelector(".moderation-list");
    if (!list || list.querySelector(".moderation-card")) {
        return;
    }
    list.innerHTML = `
        <div class="empty-state">
            <h3>当前筛选下没有评论</h3>
            <p>等读者开始留言后，这里会成为你维护讨论氛围的主控台。</p>
        </div>
    `;
}

function getModerationStatusLabel(status) {
    if (status === "approved") {
        return "已展示";
    }
    if (status === "pending") {
        return "待审核";
    }
    return "已隐藏";
}

function updateModerationCardState(card, status) {
    const statusNode = card.querySelector("[data-comment-status-label]");
    const approveButton = card.querySelector('[data-action="approve"]');
    const hideButton = card.querySelector('[data-action="hide"]');

    card.dataset.commentStatus = status;
    if (statusNode) {
        statusNode.textContent = getModerationStatusLabel(status);
        statusNode.classList.toggle("status-published", status === "approved");
        statusNode.classList.toggle("status-draft", status === "pending");
        statusNode.classList.toggle("status-hidden", status === "hidden");
    }
    if (approveButton) {
        approveButton.disabled = status === "approved";
        approveButton.textContent = status === "pending" ? "通过审核" : "恢复展示";
    }
    if (hideButton) {
        hideButton.disabled = status === "hidden";
    }
}

function bindModerationActions() {
    document.querySelectorAll(".moderation-action").forEach((button) => {
        if (button.dataset.bound === "true") {
            return;
        }

        button.dataset.bound = "true";
        button.addEventListener("click", async function () {
            const action = this.dataset.action;
            const commentId = this.dataset.commentId;
            const card = this.closest(".moderation-card");
            const statusFilter = new URLSearchParams(window.location.search).get("status") || "all";

            if (action === "delete" && !confirm("确定要删除这条评论吗？它的回复也会一并删除。")) {
                return;
            }

            try {
                if (action === "approve") {
                    const response = await axios.post(`/comments/${commentId}/approve`);
                    updateModerationCounter("comment-stat-visible", 1);
                    if (response.data.previous_status === "pending") {
                        updateModerationCounter("comment-stat-pending", -1);
                    } else if (response.data.previous_status === "hidden") {
                        updateModerationCounter("comment-stat-hidden", -1);
                    }
                    if (statusFilter === "hidden" || statusFilter === "pending") {
                        card?.remove();
                    } else if (card) {
                        updateModerationCardState(card, "approved");
                    }
                } else if (action === "hide") {
                    const response = await axios.post(`/comments/${commentId}/hide`);
                    updateModerationCounter("comment-stat-hidden", response.data.changed_ids?.length ? response.data.changed_ids.length : 1);
                    updateModerationCounter("comment-stat-visible", -(response.data.approved_changed_count || 0));
                    updateModerationCounter("comment-stat-pending", -(response.data.pending_changed_count || 0));

                    const changedIds = response.data.changed_ids || [parseInt(commentId, 10)];
                    changedIds.forEach((changedId) => {
                        const changedCard = document.querySelector(`.moderation-card[data-comment-id="${changedId}"]`);
                        if (!changedCard) {
                            return;
                        }
                        if (statusFilter === "visible" || statusFilter === "pending") {
                            changedCard.remove();
                        } else {
                            updateModerationCardState(changedCard, "hidden");
                        }
                    });
                    if (statusFilter === "all" && card && !changedIds.includes(parseInt(commentId, 10))) {
                        updateModerationCardState(card, "hidden");
                    }
                } else if (action === "delete") {
                    const response = await axios.delete(`/comments/${commentId}`);
                    const deletedIds = response.data.deleted_ids || [parseInt(commentId, 10)];
                    deletedIds.forEach((deletedId) => {
                        document.querySelector(`.moderation-card[data-comment-id="${deletedId}"]`)?.remove();
                    });
                    updateModerationCounter("comment-stat-total", -(response.data.deleted_count || 1));
                    updateModerationCounter("comment-stat-visible", -(response.data.approved_deleted_count || 0));
                    updateModerationCounter("comment-stat-pending", -(response.data.pending_deleted_count || 0));
                    updateModerationCounter("comment-stat-hidden", -(response.data.hidden_deleted_count || 0));
                }

                renderModerationEmptyState();
            } catch (error) {
                alert(parseApiError(error, "评论操作失败，请稍后再试。"));
            }
        });
    });
}

document.addEventListener("DOMContentLoaded", function () {
    bindDeletePostButtons();
    bindPreviewLinkButtons();
    bindPostEditorForm();
    bindProfileEditForm();
    bindModerationActions();
});
