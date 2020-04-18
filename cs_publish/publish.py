import argparse
import copy
import yaml
import os
import re
import subprocess
import time
from pathlib import Path

from git import Repo

TAG = os.environ.get("TAG", "")
PROJECT = os.environ.get("PROJECT", "cs-workers-dev")
CURR_PATH = Path(os.path.abspath(os.path.dirname(__file__)))
BASE_PATH = CURR_PATH / ".."


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
    kubernetes_target = CURR_PATH / Path("..") / Path("kubernetes")

    def __init__(self, tag, project, models=None, base_branch="origin/master"):
        self.tag = tag
        self.project = project
        self.models = models if models and models[0] else None
        self.base_branch = base_branch

        self.config = self.get_config()

        with open(
            CURR_PATH / Path("..") / Path("templates") / Path("sc-deployment.template.yaml"), "r",
        ) as f:
            self.sc_template = yaml.safe_load(f.read())

    def get_config(self):
        r = Repo()
        config = {}
        files_with_diff = r.index.diff(r.commit(self.base_branch), paths="config")
        for config_file in files_with_diff:
            if config_file.a_path in ("config/worker_config.dev.yaml", "config/secret.yaml"):
                continue
            with open(config_file.a_path, "r") as f:
                c = yaml.safe_load(f.read())
            config[(c["owner"], c["title"])] = c
        if self.models:
            for owner_title in self.models:
                owner, title = owner_title.split("/")
                if (owner, title) in config:
                    continue
                else:
                    config_file = BASE_PATH / Path("config") / Path(owner) / Path(f"{title}.yaml")
                    with open(config_file, "r") as f:
                        c = yaml.safe_load(f.read())
                    config[(c["owner"], c["title"])] = c
        if config:
            print("Updating:\n", "\n\t".join(f"{o}/{t}" for o, t in config.keys()))
        else:
            print("No changes detected.")
        return config

    def build(self):
        self.apply_method_to_apps(method=self.build_app_image)

    def test(self):
        self.apply_method_to_apps(method=self.test_app_image)

    def push(self):
        self.apply_method_to_apps(method=self.push_app_image)

    def make_config(self):
        self.apply_method_to_apps(method=self.write_sc_app)

    def apply_method_to_apps(self, method):
        """
        Build, tag, and push images and write k8s config files
        for all apps in config. Filters out those not in models
        list, if applicable.
        """
        for name, app in self.config.items():
            if self.models and f"{name[0]}/{name[1]}" not in self.models:
                continue
            try:
                method(app)
            except Exception:
                print(f"There was an error building: " f"{app['title']}/{app['owner']}:{self.tag}")
                import traceback as tb

                tb.print_exc()
                continue

    def build_app_image(self, app):
        """
        Build, tag, and pus the image for a single app.
        """
        print(app)
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

        buildargs_str = " ".join([f"--build-arg {arg}={value}" for arg, value in buildargs.items()])
        cmd = f"docker build {buildargs_str} -t {img_name}:{self.tag} ./"
        run(cmd)

        run(f"docker tag {img_name}:{self.tag} {self.cr}/{self.project}/{img_name}:{self.tag}")

    def test_app_image(self, app):
        safeowner = clean(app["owner"])
        safetitle = clean(app["title"])
        img_name = f"{safeowner}_{safetitle}_tasks"
        run(
            f"docker run {self.cr}/{self.project}/{img_name}:{self.tag} py.test /home/test_functions.py -v -s"
        )

    def push_app_image(self, app):
        safeowner = clean(app["owner"])
        safetitle = clean(app["title"])
        img_name = f"{safeowner}_{safetitle}_tasks"
        run(f"docker push {self.cr}/{self.project}/{img_name}:{self.tag}")

    def write_sc_app(self, app):
        for action in ["io", "sim"]:
            self._write_sc_app(app, action)

    def _write_sc_app(self, app, action):
        app_deployment = copy.deepcopy(self.sc_template)
        safeowner = clean(app["owner"])
        safetitle = clean(app["title"])
        name = f"{safeowner}-{safetitle}-{action}"

        resources = self._resources(app, action)

        app_deployment["metadata"]["name"] = name
        app_deployment["spec"]["selector"]["matchLabels"]["app"] = name
        app_deployment["spec"]["template"]["metadata"]["labels"]["app"] = name

        container_config = app_deployment["spec"]["template"]["spec"]["containers"][0]

        container_config.update(
            {
                "name": name,
                "image": f"{self.cr}/{self.project}/{safeowner}_{safetitle}_tasks:{self.tag}",
                "command": [f"./celery_{action}.sh"],
                "args": [
                    app["owner"],
                    app["title"],
                ],  # TODO: pass safe names to docker file at build and run time
                "resources": resources,
            }
        )

        container_config["env"].append({"name": "TITLE", "value": app["title"]})
        container_config["env"].append({"name": "OWNER", "value": app["owner"]})

        self._set_secrets(app, container_config)

        with open(self.kubernetes_target / Path(f"{name}-deployment.yaml"), "w") as f:
            f.write(yaml.dump(app_deployment))

        return app_deployment

    def _resources(self, app, action):
        if action == "io":
            resources = {
                "requests": {"cpu": 0.7, "memory": "0.25G"},
                "limits": {"cpu": 1, "memory": "0.7G"},
            }
        else:
            resources = {"requests": {"memory": "1G", "cpu": 1}}
            resources = dict(resources, **copy.deepcopy(app["resources"]))
        return resources

    def _set_secrets(self, app, config):
        # TODO: write secrets to secret config files instead of env.
        if app.get("secret"):
            for var, val in app["secret"].items():
                config["env"].append({"name": var.upper(), "value": val})


def main():
    parser = argparse.ArgumentParser(description="Deploy C/S compute cluster.")
    parser.add_argument("--tag", required=False, default=TAG)
    parser.add_argument("--project", required=False, default=PROJECT)
    parser.add_argument("--models", nargs="+", type=str, required=False, default=None)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--make-config", action="store_true")

    args = parser.parse_args()

    publisher = Publisher(tag=args.tag, project=args.project, models=args.models)
    if args.build:
        publisher.build()
    if args.test:
        publisher.test()
    if args.push:
        publisher.push()
    if args.make_config:
        publisher.make_config()


if __name__ == "__main__":
    main()
