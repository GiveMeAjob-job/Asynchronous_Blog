from pathlib import Path
import tomllib


def test_pyproject_has_project_name():
    pyproject = tomllib.loads(Path('pyproject.toml').read_text(encoding='utf-8'))
    assert pyproject['tool']['poetry']['name'] == 'async-blog'


def test_dockerfile_exists():
    assert Path('Dockerfile').exists()
