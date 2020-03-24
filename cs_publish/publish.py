import argparse
import yaml
import os
import re
import subprocess
import time
from pathlib import Path


TAG = os.environ.get("TAG", "")
PROJECT = os.environ.get("PROJECT", "cs-workers-dev")


def clean(word):
    return re.sub("[^0-9a-zA-Z]+", "", word).lower()


def run(cmd):
    print(f"Running: {cmd}\n")
    s = time.time()
    res = subprocess.run(cmd, shell=True, check=True)
    f = time.time()
    print(f"\n\tFinished in {f-s} seconds.\n")
    return res


class Publisher:
    """
    Build, test, and publish docker images for Compute Studio:

    args:
        - config: configuration for the apps powering C/S.
        - tag: image version, defined as [c/s version].[mm][dd].[n]
        - project: GCP project that the compute cluster is under.
        - models (optional): only build a subset of the models in
        the config.

    """

    cr = "gcr.io"

    def __init__(self, config, tag, project, models=None):
        self.tag = tag
        self.project = project
        self.models = models if models and models[0] else None

        with open(config, "r") as f:
            self.config = yaml.safe_load(f.read())

    def build(self):
        self.apply_method_to_apps(method=self.build_app_image)

    def test(self):
        self.apply_method_to_apps(method=self.test_app_image)

    def push(self):
        self.apply_method_to_apps(method=self.push_app_image)

    def apply_method_to_apps(self, method):
        """
        Build, tag, and push images and write k8s config files
        for all apps in config. Filters out those not in models
        list, if applicable.
        """
        for app in self.config:
            if self.models and app["title"] not in self.models[0]:
                continue
            try:
                method(app)
            except Exception as e:
                print(
                    f"There was an error building: "
                    f"{app['title']}/{app['owner']}:{self.tag}"
                )
                print(e)
                continue

    def build_app_image(self, app):
        """
        Build, tag, and pus the image for a single app.
        """
        safeowner = clean(app["owner"])
        safetitle = clean(app["title"])
        img_name = f"{safeowner}_{safetitle}_tasks"

        reg_url = "https://github.com"
        raw_url = "https://raw.githubusercontent.com"

        buildargs = dict(
            OWNER=app["owner"],
            TITLE=app["title"],
            BRANCH=app["branch"],
            SAFEOWNER=safeowner,
            SAFETITLE=safetitle,
            SIM_TIME_LIMIT=app["sim_time_limit"],
            REPO_URL=app["repo_url"],
            RAW_REPO_URL=app["repo_url"].replace(reg_url, raw_url),
            **app["env"],
        )

        buildargs_str = " ".join(
            [f"--build-arg {arg}={value}" for arg, value in buildargs.items()]
        )
        cmd = (
            f"docker build {buildargs_str} -t {img_name}:{self.tag} ./"
        )
        run(cmd)

        run(
            f"docker tag {img_name}:{self.tag} {self.cr}/{self.project}/{img_name}:{self.tag}"
        )

    def test_app_image(self, app):
        safeowner = clean(app["owner"])
        safetitle = clean(app["title"])
        img_name = f"{safeowner}_{safetitle}_tasks"
        run(f"docker run {self.cr}/{self.project}/{img_name}:{self.tag} py.test /home/test_functions.py -v -s")

    def push_app_image(self, app):
        safeowner = clean(app["owner"])
        safetitle = clean(app["title"])
        img_name = f"{safeowner}_{safetitle}_tasks"
        run(f"docker push {self.cr}/{self.project}/{img_name}:{self.tag}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy C/S compute cluster.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--tag", required=False, default=TAG)
    parser.add_argument("--project", required=False, default=PROJECT)
    parser.add_argument("--models", nargs="+", type=str, required=False, default=None)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--push", action="store_true")

    args = parser.parse_args()

    publisher = Publisher(
        config=args.config, tag=args.tag, project=args.project, models=args.models
    )
    if args.build:
        publisher.build()
    if args.test:
        publisher.test()
    if args.push:
        publisher.push()
