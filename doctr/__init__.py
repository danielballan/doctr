from .local import encrypt_variable, generate_GitHub_token
from .travis import (get_token, run, setup_GitHub_push, gh_pages_exists,
                     create_gh_pages, commit_docs, push_docs, get_repo,
                     find_doc_dir)

__all__ = [
    'encrypt_variable', 'generate_GitHub_token',

    'get_token', 'run', 'setup_GitHub_push', 'gh_pages_exists',
    'create_gh_pages', 'commit_docs', 'push_docs', 'get_repo',
    'find_doc_dir',
]

from ._version import get_versions
__version__ = get_versions()['version']
del get_versions
