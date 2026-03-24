document.addEventListener('DOMContentLoaded', function () {
    const tbody = document.getElementById('users-body');

    async function loadUsers() {
        const res = await axios.get('/users/');
        tbody.innerHTML = '';
        res.data.forEach(u => {
            const row = document.createElement('tr');
            row.innerHTML = `<td>${u.id}</td><td>${u.username}</td><td>${u.email}</td><td>${u.is_active ? '是' : '否'}</td>`;
            tbody.appendChild(row);
        });
    }

    loadUsers();
});
