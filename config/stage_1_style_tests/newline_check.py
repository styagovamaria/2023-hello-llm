"""
Checks newline at the end
"""
import sys

from config.constants import PROJECT_ROOT


def get_paths() -> list:
    """
    Returns list of paths to non-python files
    """
    paths_to_exclude = {
        'venv',
        '.git',
        '.idea',
        '.coverage',
        '.mypy_cache',
        '.pytest_cache',
        '__pycache__',
        'build',
        '_build',
        'intersphinx',
    }

    only_sources = [file for file in PROJECT_ROOT.iterdir() if file.name not in paths_to_exclude]

    list_with_paths = []
    for source_file in only_sources:
        if not source_file.is_dir():
            list_with_paths.append(source_file)
            continue

        list_with_paths.extend([
            file
            for file in source_file.rglob('*')
            if not set(i.name for i in file.parents) & paths_to_exclude
        ])
    return list_with_paths


def check_paths(list_with_paths: list) -> list:
    """
    Checks if the path is correct
    """
    paths_to_exclude = [
        '1_raw.txt',
        '__init__.cpython-310.pyc',
        'test_params.cpython-310.pyc'
    ]
    bad_endings = ['.jpg', '.png', '.pkl']
    paths = []
    for path in sorted(list_with_paths):
        is_file = path.is_file() and path.stat().st_size != 0
        is_ok_file = (
                path.name not in paths_to_exclude and
                '__pycache__' not in str(path) and
                'assets' not in str(path) and
                path.suffix not in bad_endings
        )
        if is_file and is_ok_file:
            paths.append(path)
    return paths


def has_newline(paths: list) -> bool:
    """
    Checks for a newline at the end
    """
    bad_paths = []
    check_is_good = True
    for path in paths:
        print(f'Analyzing {path}')
        with open(path, encoding='utf-8') as file:
            lines = file.readlines()
        if lines[-1][-1] != '\n':
            bad_paths.append(path)
            check_is_good = False
    if check_is_good:
        print('All files conform to the template.')
    else:
        for bad_path in bad_paths:
            print(f'No newline at the end of the {bad_path}')
    return check_is_good


def main() -> None:
    """
    Entrypoint for module
    """
    list_with_paths = get_paths()
    paths = check_paths(list_with_paths)
    result = has_newline(paths)
    sys.exit(not result)


if __name__ == '__main__':
    main()