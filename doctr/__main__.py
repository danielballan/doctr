"""
doctr

A tool to automatically deploy docs to GitHub pages from Travis CI.

The doctr command is two commands in one. To use, first run

doctr

on your local machine. This will prompt for your GitHub credentials and the
name of the repo you want to deploy docs for. This will generate a secure key,
which you should insert into your .travis.yml.

Then, on Travis, for the build where you build your docs, add

    - doctr

to the end of the build to deploy the docs to GitHub pages.  This will only
run on the master branch, and won't run on pull requests.

For more information, see https://gforsyth.github.io/doctr/docs/
"""

import sys
import os
import argparse

from .local import generate_GitHub_token, encrypt_variable
from .travis import setup_GitHub_push, commit_docs, push_docs, get_repo
from . import __version__

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('-V', '--version', action='version', version='doctr ' + __version__)
    location = parser.add_mutually_exclusive_group()
    location.add_argument('--travis', action='store_true', default=None,
    help="Run as if on Travis. The default is to detect automatically.")
    location.add_argument('--local', action='store_true', default=None,
    help="Run as if local (not on Travis). The default is to detect automatically.")

    args = parser.parse_args()

    if args.local == args.travis == None:
        on_travis = os.environ.get("TRAVIS_JOB_NUMBER", '')
    else:
        on_travis = args.travis

    if on_travis:
        repo = get_repo()
        if setup_GitHub_push(repo):
            commit_docs()
            push_docs()
    else:
        username = input("What is your GitHub username? ")
        token = generate_GitHub_token(username)

        repo = input("What repo to you want to build the docs for? ")
        encrypted_variable = encrypt_variable("GH_TOKEN={token}".format(token=token).encode('utf-8'), repo=repo)
        travis_content = """
env:
  global:
    secure: "{encrypted_variable}"

""".format(encrypted_variable=encrypted_variable.decode('utf-8'))

        print("Put\n", travis_content, "in your .travis.yml.\n")

if __name__ == '__main__':
    sys.exit(main())
