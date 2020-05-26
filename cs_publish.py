import argparse
import datetime
import os
from pathlib import Path
import random
import subprocess
import tempfile
import time

import httpx
import yaml

CS_URL = os.environ.get("CS_URL", "https://compute.studio")
GH_PRS = "https://api.github.com/repos/compute-tooling/compute-studio-publish/pulls?state=open"


def run(cmd):
    print(f"Running: {cmd}\n")
    s = time.time()
    res = subprocess.run(cmd, shell=True, check=True)
    f = time.time()
    print(f"\n\tFinished in {f-s} seconds.\n")
    return res

def exists(project_name):
    resp = httpx.get(f"{CS_URL}/{project_name}/")
    return resp.status_code == 200

def open_pr_ref(owner, title):
    resp = httpx.get(GH_PRS)
    assert resp.status_code == 200, f"Got code: {resp.status_code}"
    for pr in resp.json():
        if f"{owner}/{title}" in pr["title"]:
            return pr["head"]["ref"]
    return None


def pub(args: argparse.Namespace):
    assert exists(args.name), f"{args.name} does not exist on {CS_URL}."
    start = os.path.abspath(Path("."))
    try:
        with tempfile.TemporaryDirectory(prefix="update-") as td:
            run(
                f"git clone git@github.com:compute-tooling/compute-studio-publish.git {td}"
            )
            os.chdir(Path(td))
            o, t = args.name.split("/")

            now = datetime.datetime.now()

            ref = open_pr_ref(o, t)
            if ref is not None:
                run(f"git fetch origin {ref} && git checkout {ref}")
                create = False
            else:
                ref = (
                    "update-"
                    + str(now.strftime("%Y-%m-%d"))
                    + "-"
                    + str(random.randint(1111, 9999))
                )
                run(f"git checkout -b {ref}")
                create = True

            config_dir_path = Path("config") / o / f"{t}.yaml"
            if not config_dir_path.exists():
                os.mkdir(config_dir_path)
            config_file_path = config_dir_path / f"{t}.yaml"
            with open(config_file_path, "w") as f:
                f.write(yaml.dump({"owner": o, "title": t, "timestamp": str(now.strftime("%Y-%m-%d %H:%M"))}))

            commit_message = f"Update {o}/{t} - {str(now.strftime('%Y-%m-%d %H:%M'))}"
            if args.skip_test:
                commit_message = f"[skip test] {commit_message}"
            run(f"git add '{config_file_path}' && git commit -m '{commit_message}'")

            # same for now
            if create:
                run(f"git push origin {ref}")
            else:
                run(f"git push origin {ref}")
    finally:
        os.chdir(start)


def cli():
    parser = argparse.ArgumentParser("Modify model config file and open GH PR.")
    parser.add_argument("--name", "-n", required=True)
    parser.add_argument("--skip-test", action="store_true")
    parser.set_defaults(func=pub)
    args = parser.parse_args()
    args.func(args)
