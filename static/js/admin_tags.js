document.addEventListener('DOMContentLoaded', function () {
    const tbody = document.getElementById('tags-body');
    const form = document.getElementById('tag-form');

    async function loadTags() {
        const res = await axios.get('/api/v1/tags/');
        tbody.innerHTML = '';
        res.data.forEach(tag => {
            const row = document.createElement('tr');
            row.innerHTML = `<td>${tag.name}</td><td>${tag.description || ''}</td>`;
            tbody.appendChild(row);
        });
    }

    if (form) {
        form.addEventListener('submit', async function (e) {
            e.preventDefault();
            const name = form.querySelector('[name="name"]').value;
            const description = form.querySelector('[name="description"]').value;
            await axios.post('/api/v1/tags/', { name, description });
            form.reset();
            loadTags();
        });
    }

    loadTags();
});
