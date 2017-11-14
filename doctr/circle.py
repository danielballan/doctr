"""
The code that should be run on Circle-CI
"""

import os
import shlex
import shutil
import subprocess
import sys
import glob
import re
import pathlib
import tempfile
import time

from cryptography.fernet import Fernet

from .utils import (red, blue, decrypt_file, setup_deploy_key,
                    run_command_hiding_token, get_token, run, push_docs,
                    set_git_user_email, copy_to_tmp, checkout_deploy_branch,
                    deploy_branch_exists, create_deploy_branch,
                    create_working_branch, find_sphinx_build_dir,
                    sync_from_log, find_sphinx_build_dir)


DOCTR_WORKING_BRANCH = '__doctr_working_branch'


def get_current_repo():
    """
    Get the GitHub repo name for the current directory.

    Assumes that the repo is in the ``origin`` remote.
    """
    remote_url = subprocess.check_output(['git', 'config', '--get',
        'remote.origin.url']).decode('utf-8')

    # TODO Does circle use the https clone url also? If so, use shared version
    # in utils.
    # Travis uses the https clone url
    _, org, git_repo = remote_url.rsplit('.git', 1)[0].rsplit('/', 2)
    return (org + '/' + git_repo)

def get_circle_branch():
    """Get the name of the branch that the PR is from.

    TODO: Does the complication belowed (copied from get_travis_branch)
    apply to Circle?

    Note that this is not simply ``$TRAVIS_BRANCH``. the ``push`` build will
    use the correct branch (the branch that the PR is from) but the ``pr``
    build will use the _target_ of the PR (usually master). So instead, we ask
    for ``$TRAVIS_PULL_REQUEST_BRANCH`` if it's a PR build, and
    ``$TRAVIS_BRANCH`` if it's a push build.
    """
    # if os.environ.get("TRAVIS_PULL_REQUEST", "") == "true":
    #     return os.environ.get("TRAVIS_PULL_REQUEST_BRANCH", "")
    # else:
    #     return os.environ.get("TRAVIS_BRANCH", "")
    return os.environ.get("CIRCLE_BRANCH", "")


def setup_GitHub_push(deploy_repo, auth_type='deploy_key', full_key_path='github_deploy_key.enc', branch_whitelist=None, deploy_branch='gh-pages'):
    """
    Setup the remote to push to GitHub (to be run on Circle).

    ``auth_type`` should be either ``'deploy_key'`` or ``'token'``.

    For ``auth_type='token'``, this sets up the remote with the token and
    checks out the gh-pages branch. The token to push to GitHub is assumed to be in the ``GH_TOKEN`` environment
    variable.

    For ``auth_type='deploy_key'``, this sets up the remote with ssh access.
    """

    if not branch_whitelist:
        branch_whitelist={'master'}

    if auth_type not in ['deploy_key', 'token']:
        raise ValueError("auth_type must be 'deploy_key' or 'token'")

    CIRCLE_BRANCH = os.environ.get("CIRCLE_BRANCH", "")
    CIRCLE_PULL_REQUEST = os.environ.get("CIRCLE_PULL_REQUESTS", "")

    canpush = determine_push_rights(branch_whitelist, CIRCLE_BRANCH,
                                    CIRCLE_PULL_REQUESTS)

    print("Setting git attributes")
    set_git_user_email()

    remotes = subprocess.check_output(['git', 'remote']).decode('utf-8').split('\n')
    if 'doctr_remote' in remotes:
        print("doctr_remote already exists, removing")
        run(['git', 'remote', 'remove', 'doctr_remote'])
    print("Adding doctr remote")
    if canpush:
        if auth_type == 'token':
            token = get_token()
            run(['git', 'remote', 'add', 'doctr_remote',
                'https://{token}@github.com/{deploy_repo}.git'.format(token=token.decode('utf-8'),
                    deploy_repo=deploy_repo)])
        else:
            keypath, key_ext = full_key_path.rsplit('.', 1)
            key_ext = '.' + key_ext
            setup_deploy_key(keypath=keypath, key_ext=key_ext)
            run(['git', 'remote', 'add', 'doctr_remote',
                'git@github.com:{deploy_repo}.git'.format(deploy_repo=deploy_repo)])
    else:
        print('setting a read-only GitHub doctr_remote')
        run(['git', 'remote', 'add', 'doctr_remote',
                'https://github.com/{deploy_repo}.git'.format(deploy_repo=deploy_repo)])


    print("Fetching doctr remote")
    run(['git', 'fetch', 'doctr_remote'])

    return canpush


def commit_docs(*, added, removed):
    """
    Commit the docs to the current branch

    Assumes that :func:`setup_GitHub_push`, which sets up the ``doctr_remote``
    remote, has been run.

    Returns True if changes were committed and False if no changes were
    committed.
    """
    CIRCLE_BUILD_NUM = os.environ.get("CIRCLE_BUILD_NUM", "<unknown>")
    CIRCLE_BRANCH = os.environ.get("CIRCLE_BRANCH", "<unknown>")
    CIRCLE_SHA1 = os.environ.get("CIRCLE_SHA1", "<unknown>")
    CIRCLE_PROJECT_REPONAME = os.environ.get("CIRCLE_PROJECT_REPONAME", "<unknown>")
    CIRCLE_PROJECT_USERNAME = os.environ.get("CIRCLE_PROJECT_USERNAME", "<unknown>")
    DOCTR_COMMAND = ' '.join(map(shlex.quote, sys.argv))

    for f in added:
        run(['git', 'add', f])
    for f in removed:
        run(['git', 'rm', f])

    commit_message = """\
Update docs after building Circle build {CIRCLE_BUILD_NUM} of
{CIRCLE_PROJECT_REPONAME}

The docs were built from the branch '{CIRCLE_BRANCH}' against the commit
{CIRCLE_SHA1}.

The Circle build that generated this commit is at
https://circleci.com/gh/{CIRCLE_PROJECT_USERNAME/CIRCLE_PROJECT_REPONAME}/{CIRCLE_BUILD_NUM}.

The doctr command that was run is

    {DOCTR_COMMAND}
""".format(
    CIRCLE_BUILD_NUM=CIRCLE_BUILD_NUM,
    CIRCLE_BRANCH=CIRCLE_BRANCH,
    CIRCLE_SHA1=CIRCLE_SHA1,
    CIRCLE_PROJECT_REPONAME=CIRCLE_PROJECT_REPONAME,
    CIRCLE_PROJECT_USERNAME=CIRCLE_PROJECT_USERNAME,
    DOCTR_COMMAND=DOCTR_COMMAND,
    )

    # Only commit if there were changes
    if subprocess.run(['git', 'diff-index', '--quiet', 'HEAD', '--'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode != 0:
        print("Committing")
        run(['git', 'commit', '-am', commit_message])
        return True

    return False

def determine_push_rights(branch_whitelist, CIRCLE_BRANCH, CIRCLE_PULL_REQUESTS):
    """Check if Circle is running on ``master`` (or a whitelisted branch) to
    determine if we can/should push the docs to the deploy repo
    """
    canpush = True

    if not any([re.compile(x).match(CIRCLE_BRANCH) for x in branch_whitelist]):
        print("The docs are only pushed to gh-pages from master. To allow pushing from "
        "a non-master branch, use the --no-require-master flag", file=sys.stderr)
        print("This is the {CIRCLE_BRANCH} branch".format(CIRCLE_BRANCH=CIRCLE_BRANCH), file=sys.stderr)
        canpush = False

    if CIRCLE_PULL_REQUEST:
        print("The website and docs are not pushed to gh-pages on pull requests", file=sys.stderr)
        canpush = False

    return canpush
