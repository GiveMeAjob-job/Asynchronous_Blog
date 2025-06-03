document.addEventListener('DOMContentLoaded', function () {
    const tbody = document.getElementById('categories-body');
    const form = document.getElementById('category-form');

    async function loadCategories() {
        const res = await axios.get('/api/v1/categories/');
        tbody.innerHTML = '';
        res.data.forEach(cat => {
            const row = document.createElement('tr');
            row.innerHTML = `<td>${cat.name}</td><td>${cat.description || ''}</td><td>${cat.post_count || 0}</td>`;
            tbody.appendChild(row);
        });
    }

    if (form) {
        form.addEventListener('submit', async function (e) {
            e.preventDefault();
            const name = form.querySelector('[name="name"]').value;
            const description = form.querySelector('[name="description"]').value;
            await axios.post('/api/v1/categories/', { name, description });
            form.reset();
            loadCategories();
        });
    }

    loadCategories();
});
