document.addEventListener("DOMContentLoaded", function () {
    const commentInput = document.getElementById("comment-content");
    const commentError = document.getElementById("comment-error");
    const commentFeedback = document.getElementById("comment-feedback");
    const commentList = document.getElementById("comment-list");
    const submitCommentBtn = document.getElementById("submit-comment");
    const postLikeButton = document.getElementById("post-like-button");
    const sharePostButton = document.getElementById("share-post");
    const commentsCount = document.querySelector(".comments-count");

    function showError(message) {
        if (!commentError) {
            return;
        }
        clearFeedback();
        commentError.textContent = message;
        commentError.classList.remove("d-none");
    }

    function clearError() {
        commentError?.classList.add("d-none");
    }

    function showFeedback(message, kind = "warning") {
        if (!commentFeedback) {
            return;
        }
        clearError();
        commentFeedback.classList.remove("warning", "success");
        commentFeedback.classList.add(kind);
        commentFeedback.textContent = message;
        commentFeedback.classList.remove("d-none");
    }

    function clearFeedback() {
        if (!commentFeedback) {
            return;
        }
        commentFeedback.classList.add("d-none");
        commentFeedback.classList.remove("warning", "success");
    }

    function parseApiError(error, fallbackMessage) {
        const detail = error.response?.data?.detail;
        if (Array.isArray(detail)) {
            return detail.map((item) => `${item.loc.join(".")} - ${item.msg}`).join("; ");
        }
        return detail || fallbackMessage;
    }

    function bumpCommentCount(delta) {
        if (!commentsCount) {
            return;
        }
        const current = parseInt(commentsCount.textContent, 10) || 0;
        commentsCount.textContent = `${Math.max(0, current + delta)} 条`;
    }

    function canEditComment(comment) {
        const currentUser = window.getCurrentUser?.();
        if (!currentUser) {
            return false;
        }
        return currentUser.id === comment.author_id || currentUser.is_superuser;
    }

    function canDeleteComment(comment) {
        const currentUser = window.getCurrentUser?.();
        if (!currentUser) {
            return false;
        }
        const postAuthorId = parseInt(commentList?.dataset.postAuthorId || "0", 10);
        return currentUser.id === comment.author_id || currentUser.is_superuser || currentUser.id === postAuthorId;
    }

    function buildManageActions(comment) {
        const actions = [];
        if (canEditComment(comment)) {
            actions.push(`<button class="link-button comment-edit-trigger" type="button" data-comment-id="${comment.id}">编辑</button>`);
        }
        if (canDeleteComment(comment)) {
            actions.push(`<button class="link-button comment-delete-button" type="button" data-comment-id="${comment.id}">删除</button>`);
        }
        if (!actions.length) {
            return "";
        }
        return actions.join("");
    }

    function buildEditForm(comment) {
        if (!canEditComment(comment)) {
            return "";
        }

        return `
            <div class="reply-form d-none comment-edit-form" id="edit-form-${comment.id}">
                <textarea class="form-control edit-comment-content" rows="3">${comment.content}</textarea>
                <div class="reply-form__actions">
                    <button type="button" class="btn btn-secondary btn-sm cancel-comment-edit" data-comment-id="${comment.id}">取消</button>
                    <button type="button" class="btn btn-primary btn-sm submit-comment-edit" data-comment-id="${comment.id}">保存修改</button>
                </div>
            </div>
        `;
    }

    function renderComment(comment, isReply = false) {
        const article = document.createElement("article");
        article.className = isReply ? "comment-card comment-card--reply" : "comment-card";
        article.dataset.commentId = comment.id;

        const authorName = comment.author?.full_name || comment.author?.username || "匿名用户";
        const authorInitial = authorName.charAt(0).toUpperCase();
        const createdAt = new Date(comment.created_at).toLocaleString("zh-CN", {
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
        });
        const editedText = comment.is_edited ? " · 已编辑" : "";

        article.innerHTML = `
            <div class="comment-card__avatar">${authorInitial}</div>
            <div class="comment-card__body">
                <div class="comment-card__header">
                    <strong>${authorName}</strong>
                    <span>${createdAt}${editedText}</span>
                </div>
                <p class="comment-card__text"></p>
                <div class="comment-card__actions">
                    ${!isReply ? `<button class="link-button reply-trigger" type="button" data-parent-id="${comment.id}">回复</button>` : ""}
                    <button class="link-button comment-like-button" type="button" data-comment-id="${comment.id}" data-liked="${comment.is_liked ? "true" : "false"}">
                        ${comment.is_liked ? "已点赞" : "点赞"} · <span>${comment.like_count || 0}</span>
                    </button>
                    ${buildManageActions(comment)}
                </div>
                ${buildEditForm(comment)}
                ${!isReply ? `
                <div class="reply-form d-none" id="reply-form-${comment.id}">
                    <textarea class="form-control reply-content" rows="3" placeholder="回复这条评论..."></textarea>
                    <div class="reply-form__actions">
                        <button type="button" class="btn btn-secondary btn-sm cancel-reply" data-parent-id="${comment.id}">取消</button>
                        <button type="button" class="btn btn-primary btn-sm submit-reply" data-post-id="${comment.post_id}" data-parent-id="${comment.id}">提交回复</button>
                    </div>
                </div>
                <div class="reply-list"></div>` : ""}
            </div>
        `;
        article.querySelector(".comment-card__text").textContent = comment.content;
        return article;
    }

    async function submitComment({ postId, parentId = null, content }) {
        const payload = { content, post_id: parseInt(postId, 10) };
        if (parentId) {
            payload.parent_id = parseInt(parentId, 10);
        }
        const response = await axios.post("/comments", payload);
        return response.data;
    }

    async function updateComment(commentId, content) {
        const response = await axios.patch(`/comments/${commentId}`, { content });
        return response.data;
    }

    async function deleteComment(commentId) {
        const response = await axios.delete(`/comments/${commentId}`);
        return response.data;
    }

    async function togglePostLike() {
        if (!postLikeButton) {
            return;
        }

        const postId = postLikeButton.dataset.postId;
        const liked = postLikeButton.dataset.liked === "true";

        try {
            const response = liked
                ? await axios.delete(`/posts/${postId}/like`)
                : await axios.post(`/posts/${postId}/like`);

            postLikeButton.dataset.liked = String(response.data.liked);
            document.getElementById("post-like-label").textContent = response.data.liked ? "已点赞" : "点赞文章";
            document.getElementById("post-like-count").textContent = response.data.like_count;
            postLikeButton.classList.toggle("btn-primary", response.data.liked);
            postLikeButton.classList.toggle("btn-secondary", !response.data.liked);
        } catch (error) {
            showError(parseApiError(error, "点赞失败，请先登录后重试。"));
        }
    }

    async function toggleCommentLike(button) {
        const commentId = button.dataset.commentId;
        const liked = button.dataset.liked === "true";

        try {
            const response = liked
                ? await axios.delete(`/comments/${commentId}/like`)
                : await axios.post(`/comments/${commentId}/like`);
            button.dataset.liked = String(response.data.liked);
            button.innerHTML = `${response.data.liked ? "已点赞" : "点赞"} · <span>${response.data.like_count}</span>`;
        } catch (error) {
            showError(parseApiError(error, "评论点赞失败，请先登录后重试。"));
        }
    }

    submitCommentBtn?.addEventListener("click", async function () {
        const postId = this.dataset.postId;
        const content = commentInput.value.trim();
        if (!content) {
            showError("评论内容不能为空。");
            return;
        }

        clearError();
        clearFeedback();
        try {
            const comment = await submitComment({ postId, content });
            commentInput.value = "";
            if (comment.moderation_status === "approved") {
                commentList.querySelector(".empty-state")?.remove();
                commentList.prepend(renderComment(comment));
                bumpCommentCount(1);
                showFeedback("评论已发布。", "success");
            } else {
                showFeedback("评论已提交，待审核通过后才会公开显示。", "warning");
            }
        } catch (error) {
            showError(parseApiError(error, "提交评论失败，请稍后再试。"));
        }
    });

    postLikeButton?.addEventListener("click", togglePostLike);

    sharePostButton?.addEventListener("click", async function () {
        const shareUrl = this.dataset.shareUrl;
        try {
            await navigator.clipboard.writeText(shareUrl);
            this.textContent = "链接已复制";
            setTimeout(() => {
                this.textContent = "复制文章链接";
            }, 1200);
        } catch (error) {
            showError("复制链接失败，请手动复制浏览器地址栏。");
        }
    });

    document.addEventListener("click", async function (event) {
        const replyTrigger = event.target.closest(".reply-trigger");
        if (replyTrigger) {
            document.getElementById(`reply-form-${replyTrigger.dataset.parentId}`)?.classList.toggle("d-none");
            return;
        }

        const cancelReply = event.target.closest(".cancel-reply");
        if (cancelReply) {
            document.getElementById(`reply-form-${cancelReply.dataset.parentId}`)?.classList.add("d-none");
            return;
        }

        const submitReply = event.target.closest(".submit-reply");
        if (submitReply) {
            const postId = submitReply.dataset.postId;
            const parentId = submitReply.dataset.parentId;
            const form = document.getElementById(`reply-form-${parentId}`);
            const textarea = form?.querySelector(".reply-content");
            const content = textarea?.value.trim();
            if (!content) {
                showError("回复内容不能为空。");
                return;
            }

            clearError();
            clearFeedback();
            try {
                const reply = await submitComment({ postId, parentId, content });
                if (reply.moderation_status === "approved") {
                    const commentCard = submitReply.closest(".comment-card");
                    let replyList = commentCard?.querySelector(".reply-list");
                    if (!replyList && commentCard) {
                        replyList = document.createElement("div");
                        replyList.className = "reply-list";
                        commentCard.querySelector(".comment-card__body")?.append(replyList);
                    }
                    replyList?.append(renderComment(reply, true));
                    bumpCommentCount(1);
                    showFeedback("回复已发布。", "success");
                } else {
                    showFeedback("回复已提交，待审核通过后才会公开显示。", "warning");
                }
                if (textarea) {
                    textarea.value = "";
                }
                form?.classList.add("d-none");
            } catch (error) {
                showError(parseApiError(error, "回复失败，请稍后再试。"));
            }
            return;
        }

        const commentLikeButton = event.target.closest(".comment-like-button");
        if (commentLikeButton) {
            await toggleCommentLike(commentLikeButton);
            return;
        }

        const editTrigger = event.target.closest(".comment-edit-trigger");
        if (editTrigger) {
            document.getElementById(`edit-form-${editTrigger.dataset.commentId}`)?.classList.toggle("d-none");
            return;
        }

        const cancelEdit = event.target.closest(".cancel-comment-edit");
        if (cancelEdit) {
            document.getElementById(`edit-form-${cancelEdit.dataset.commentId}`)?.classList.add("d-none");
            return;
        }

        const submitEdit = event.target.closest(".submit-comment-edit");
        if (submitEdit) {
            const commentId = submitEdit.dataset.commentId;
            const form = document.getElementById(`edit-form-${commentId}`);
            const textarea = form?.querySelector(".edit-comment-content");
            const content = textarea?.value.trim();
            if (!content) {
                showError("评论内容不能为空。");
                return;
            }

            clearError();
            try {
                const updated = await updateComment(commentId, content);
                const card = submitEdit.closest(".comment-card");
                const textNode = card?.querySelector(".comment-card__text");
                const metaNode = card?.querySelector(".comment-card__header span");
                if (textNode) {
                    textNode.textContent = updated.content;
                }
                if (metaNode && !metaNode.textContent.includes("已编辑")) {
                    metaNode.textContent = `${metaNode.textContent} · 已编辑`;
                }
                form?.classList.add("d-none");
            } catch (error) {
                showError(parseApiError(error, "更新评论失败，请稍后再试。"));
            }
            return;
        }

        const deleteButton = event.target.closest(".comment-delete-button");
        if (deleteButton) {
            const commentId = deleteButton.dataset.commentId;
            if (!confirm("确定要删除这条评论吗？相关回复也会一并删除。")) {
                return;
            }

            clearError();
            clearFeedback();
            try {
                const payload = await deleteComment(commentId);
                const deletedIds = payload.deleted_ids || [parseInt(commentId, 10)];
                deletedIds.forEach((deletedId) => {
                    document.querySelector(`.comment-card[data-comment-id="${deletedId}"]`)?.remove();
                });
                bumpCommentCount(-(payload.approved_deleted_count || 0));
                if (!commentList.querySelector(".comment-card")) {
                    commentList.innerHTML = `
                        <div class="empty-state">
                            <h3>还没有评论</h3>
                            <p>第一条评论，往往决定这里的气氛。</p>
                        </div>
                    `;
                }
            } catch (error) {
                showError(parseApiError(error, "删除评论失败，请稍后再试。"));
            }
        }
    });
});
