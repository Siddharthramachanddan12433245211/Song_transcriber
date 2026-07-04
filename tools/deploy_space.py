"""Deploy the Shabd web app to a Hugging Face Space (free CPU tier).

Usage:
    set HF_TOKEN=hf_xxx            (a WRITE token from hf.co/settings/tokens)
    .venv\\Scripts\\python tools\\deploy_space.py [--space owner/name]

Stages only the files the Space needs (no tests, no venv, no git history),
creates the Space if it doesn't exist, and uploads. Idempotent: run again to
redeploy after changes.
"""

import argparse
import os
import shutil
import sys
import tempfile

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_SPACE = "Siddharth7021/shabd"

# (source relative to project root, destination relative to Space root)
FILES = [
    ("requirements.txt", "requirements.txt"),
    ("Dockerfile", "Dockerfile"),
    ("deploy/space_README.md", "README.md"),
    ("templates/index.html", "templates/index.html"),
]
PACKAGE_MODULES = ["__init__.py", "web.py", "web_static.py", "engine.py",
                   "cues.py", "hardware.py", "cli.py"]  # gui.py excluded: desktop-only


def stage(staging):
    for src, dest in FILES:
        dest_path = os.path.join(staging, dest)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.copy2(os.path.join(PROJECT_ROOT, src), dest_path)
    pkg_dir = os.path.join(staging, "shabd")
    os.makedirs(pkg_dir, exist_ok=True)
    for name in PACKAGE_MODULES:
        shutil.copy2(os.path.join(PROJECT_ROOT, "shabd", name),
                     os.path.join(pkg_dir, name))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--space", default=DEFAULT_SPACE,
                        help="Space id, e.g. Siddharth7021/shabd")
    args = parser.parse_args()

    token = os.environ.get("HF_TOKEN")
    if not token:
        print("ERROR: set the HF_TOKEN environment variable first.\n"
              "Create a WRITE token at https://huggingface.co/settings/tokens")
        return 1

    from huggingface_hub import HfApi
    api = HfApi(token=token)
    who = api.whoami()
    print("Logged in as: %s" % who.get("name"))

    staging = tempfile.mkdtemp(prefix="shabd_space_")
    try:
        stage(staging)
        print("Staged %d files for upload." %
              sum(len(fs) for _, _, fs in os.walk(staging)))
        api.create_repo(repo_id=args.space, repo_type="space",
                        space_sdk="docker", exist_ok=True)
        api.upload_folder(folder_path=staging, repo_id=args.space,
                          repo_type="space",
                          commit_message="Deploy Shabd web app")
        print("\nDeployed. The Space is building now (first build ~5-10 min).")
        print("Live URL: https://huggingface.co/spaces/%s" % args.space)
        return 0
    finally:
        shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
