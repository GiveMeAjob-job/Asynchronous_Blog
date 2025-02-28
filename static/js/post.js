document.addEventListener('DOMContentLoaded', function() {
    const submitCommentBtn = document.getElementById('submit-comment');
    const commentContent = document.getElementById('comment-content');
    const commentError = document.getElementById('comment-error');
    const commentList = document.getElementById('comment-list');
    const relatedPostsContainer = document.getElementById('related-posts');

    // 提交评论
    if (submitCommentBtn) {
        submitCommentBtn.addEventListener('click', async function() {
            const postId = this.dataset.postId;
            const content = commentContent.value.trim();

            if (!content) {
                commentError.textContent = '评论内容不能为空';
                commentError.classList.remove('d-none');
                return;
            }

            commentError.classList.add('d-none');

            try {
                const response = await axios.post(`/api/v1/posts/${postId}/comments`, {
                    content: content,
                    post_id: postId
                });

                // 评论成功后清空输入框
                commentContent.value = '';

                // 添加新评论到列表
                const comment = response.data;
                const commentElement = document.createElement('div');
                commentElement.className = 'card mb-3';
                commentElement.innerHTML = `
                    <div class="card-body">
                        <h5 class="card-title">${comment.author}</h5>
                        <h6 class="card-subtitle mb-2 text-muted">刚刚</h6>
                        <p class="card-text">${comment.content}</p>
                    </div>
                `;

                // 将新评论添加到列表顶部
                commentList.insertBefore(commentElement, commentList.firstChild);

                // 检查是否有"暂无评论"提示，如果有则移除
                const noCommentsAlert = commentList.querySelector('.alert');
                if (noCommentsAlert) {
                    noCommentsAlert.remove();
                }

            } catch (error) {
                console.error('提交评论失败', error);

                let errorMessage = '提交评论失败，请稍后再试';
                if (error.response && error.response.data && error.response.data.detail) {
                    errorMessage = error.response.data.detail;
                } else if (error.response && error.response.status === 401) {
                    errorMessage = '请先登录后再发表评论';
                }

                commentError.textContent = errorMessage;
                commentError.classList.remove('d-none');
            }
        });
    }

    // 加载相关文章
    if (relatedPostsContainer) {
        const loadRelatedPosts = async () => {
            try {
                const postSlug = window.location.pathname.split('/').pop();
                const response = await axios.get(`/api/v1/posts/${postSlug}/related`);

                const relatedPosts = response.data;
                if (relatedPosts.length === 0) {
                    relatedPostsContainer.innerHTML = '<p class="text-center">暂无相关文章</p>';
                    return;
                }

                let postsHtml = '<ul class="list-group list-group-flush">';
                relatedPosts.forEach(post => {
                    postsHtml += `
                        <li class="list-group-item">
                            <a href="/post/${post.slug}" class="text-decoration-none">
                                ${post.title}
                            </a>
                        </li>
                    `;
                });
                postsHtml += '</ul>';

                relatedPostsContainer.innerHTML = postsHtml;

            } catch (error) {
                console.error('加载相关文章失败', error);
                relatedPostsContainer.innerHTML = '<p class="text-center text-muted">加载相关文章失败</p>';
            }
        };

        // 延迟加载相关文章，优先渲染主要内容
        setTimeout(loadRelatedPosts, 500);
    }
});
