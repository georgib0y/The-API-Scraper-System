import os
import shutil
import subprocess
import logging
from contextlib import contextmanager

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("fetch_repos")

# TODO make these args
REPO_DIR = "repos"
PATCHES_DIR = "patches"

TASS_GIT_URL = "https://github.com/TheAlphaSchoolSystemPTYLTD/"
TASS_REPOS = [
    "IdM",
    "accounts-payable-integration",
    "assessment",
    "boarding",
    "data-upload-utility",
    "deep-linking",
    "employee-hr",
    "general-ledger-analytics",
    "library-integration",
    "lms-integration",
    "mobile-app",
    "online-enrolments",
    "payroll",
    "public-calendar-and-notices",
    "school-calendar-and-notices",
    "student-academic-analytics",
    "student-details",
]


@contextmanager
def in_dir(dir: str):
    curr = os.getcwd()
    try:
        os.chdir(dir)
        yield
    finally:
        os.chdir(curr)


def fetch_git_repos():
    for repo in TASS_REPOS:
        path = os.path.join(REPO_DIR, repo)
        url = TASS_GIT_URL+repo
        res = subprocess.run(["git", "clone", url, path])
        res.check_returncode()


def apply_patches(patch_dir: str, repo_dir: str):
    patches = sorted(os.listdir(patch_dir))
    rel_patch_dir = os.path.relpath(patch_dir, repo_dir)

    with in_dir(repo_dir):
        for p in patches:
            patch_path = os.path.join(rel_patch_dir, p)
            res = subprocess.run(["git", "apply", patch_path])
            res.check_returncode()


def patch_repos():
    for dir in os.listdir(PATCHES_DIR):
        if dir not in TASS_REPOS:
            logger.error(f"unknown patch dir: {dir}")

        logger.info(f"patching {dir}")
        patch_dir = os.path.join(PATCHES_DIR, dir)
        repo_dir = os.path.join(REPO_DIR, dir)

        apply_patches(patch_dir, repo_dir)


def main():
    if os.path.exists(REPO_DIR):
        logger.info("repo dir already exists, removing")
        shutil.rmtree(REPO_DIR)

    logger.info("creating repo dir")
    os.mkdir(REPO_DIR)

    logger.info("fetching repos")
    fetch_git_repos()
    logger.info("done fetching repos")

    logger.info("patching repos")
    if not os.path.exists(PATCHES_DIR):
        logger.err("patches dir does not exist, the parsing will likely fail")
    else:
        patch_repos()
    logger.info("done patching repos")

    logger.info("fetch finished successfully")


if __name__ == "__main__":
    main()
