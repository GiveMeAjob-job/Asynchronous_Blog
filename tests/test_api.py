from pathlib import Path


def test_readme_contains_project_name():
    readme = Path('README.md').read_text(encoding='utf-8')
    assert 'Async Blog' in readme
