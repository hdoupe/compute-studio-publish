import argparse
import copy
import json
import yaml
import os
import sys
from pathlib import Path

from git import Repo

from cs_publish.utils import clean, run
from cs_publish.secrets import Secrets

TAG = os.environ.get("TAG", "")
PROJECT = os.environ.get("PROJECT", "cs-workers-dev")
CURR_PATH = Path(os.path.abspath(os.path.dirname(__file__)))
BASE_PATH = CURR_PATH / ".."


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

    def __init__(
        self,
        tag,
        project,
        models=None,
        base_branch="origin/master",
        quiet=False,
        kubernetes_target=None,
    ):
        self.tag = tag
        self.project = project
        self.models = models if models and models[0] else None
        self.base_branch = base_branch
        self.quiet = quiet

        self.kubernetes_target = kubernetes_target or self.kubernetes_target

        if self.kubernetes_target == "-":
            self.quiet = True
        elif not self.kubernetes_target.exists():
            os.mkdir(self.kubernetes_target)

        self.config = self.get_config()

        with open(
            CURR_PATH
            / Path("..")
            / Path("templates")
            / Path("sc-deployment.template.yaml"),
            "r",
        ) as f:
            self.app_template = yaml.safe_load(f.read())

        with open(
            CURR_PATH / Path("..") / Path("templates") / Path("job.template.yaml"), "r"
        ) as f:
            self.job_template = yaml.safe_load(f.read())

        with open(
            CURR_PATH / Path("..") / Path("templates") / Path("secret.template.yaml"),
            "r",
        ) as f:
            self.secret_template = yaml.safe_load(f.read())

        self.errored = set()

    def get_config(self):
        r = Repo()
        config = {}
        files_with_diff = r.index.diff(r.commit(self.base_branch), paths="config")
        for config_file in files_with_diff:
            if config_file.a_path in (
                "config/worker_config.dev.yaml",
                "config/secret.yaml",
            ):
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
                    config_file = (
                        BASE_PATH / Path("config") / Path(owner) / Path(f"{title}.yaml")
                    )
                    with open(config_file, "r") as f:
                        c = yaml.safe_load(f.read())
                    config[(c["owner"], c["title"])] = c
        if not self.quiet and config:
            print("# Updating:")
            print("\n#".join(f"  {o}/{t}" for o, t in config.keys()))
        elif not self.quiet:
            print("# No changes detected.")
        return config

    def build(self):
        self.apply_method_to_apps(method=self.build_app_image)

    def test(self):
        self.apply_method_to_apps(method=self.test_app_image)

    def push(self):
        self.apply_method_to_apps(method=self.push_app_image)

    def write_app_config(self):
        self.apply_method_to_apps(method=self.write_secrets)
        self.apply_method_to_apps(method=self._write_app_inputs_procesess)

    def write_job_config(self):
        self.apply_method_to_apps(method=self._write_job_config)

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
                print(
                    f"There was an error building: "
                    f"{app['owner']}/{app['title']}:{self.tag}"
                )
                import traceback as tb

                tb.print_exc()
                self.errored.add((app["owner"], app["title"]))
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

        buildargs_str = " ".join(
            [f"--build-arg {arg}={value}" for arg, value in buildargs.items()]
        )
        cmd = f"docker build {buildargs_str} -t {img_name}:{self.tag} ./"
        run(cmd)

        run(
            f"docker tag {img_name}:{self.tag} {self.cr}/{self.project}/{img_name}:{self.tag}"
        )

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

    def write_secrets(self, app):
        secret_config = copy.deepcopy(self.secret_template)
        safeowner = clean(app["owner"])
        safetitle = clean(app["title"])
        name = f"{safeowner}-{safetitle}-secret"

        secret_config["metadata"]["name"] = name

        for name, value in self._list_secrets(app).items():
            secret_config["stringData"][name] = value

        if self.kubernetes_target == "-":
            sys.stdout.write(yaml.dump(secret_config))
            sys.stdout.write("---")
            sys.stdout.write("\n")
        else:
            with open(self.kubernetes_target / Path(f"{name}.yaml"), "w") as f:
                f.write(yaml.dump(secret_config))

        return secret_config

    def _write_app_inputs_procesess(self, app):
        app_deployment = copy.deepcopy(self.app_template)
        safeowner = clean(app["owner"])
        safetitle = clean(app["title"])
        action = "io"
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
        container_config["env"].append(
            {"name": "SIM_TIME_LIMIT", "value": str(app["sim_time_limit"])}
        )
        container_config["env"].append(
            {"name": "APP_NAME", "value": f"{safeowner}_{safetitle}_tasks"}
        )
        self._set_secrets(app, container_config)

        if self.kubernetes_target == "-":
            sys.stdout.write(yaml.dump(app_deployment))
            sys.stdout.write("---")
            sys.stdout.write("\n")
        else:
            with open(
                self.kubernetes_target / Path(f"{name}-deployment.yaml"), "w"
            ) as f:
                f.write(yaml.dump(app_deployment))

        return app_deployment

    def _write_job_config(self, app):
        job = self.job_config(app)
        safeowner = clean(app["owner"])
        safetitle = clean(app["title"])
        name = f"{safeowner}-{safetitle}-job"

        if self.kubernetes_target == "-":
            sys.stdout.write(yaml.dump(job))
            sys.stdout.write("---")
            sys.stdout.write("\n")
        else:
            with open(self.kubernetes_target / Path(f"{name}.yaml"), "w") as f:
                f.write(yaml.dump(job))

        return job

    def job_config(self, app, tag=None):
        tag = tag or self.tag
        app_deployment = copy.deepcopy(self.job_template)
        safeowner = clean(app["owner"])
        safetitle = clean(app["title"])
        name = f"{safeowner}-{safetitle}-job"

        resources = self._resources(app)

        app_deployment["metadata"]["name"] = name
        app_deployment["spec"]["template"]["metadata"]["labels"]["app"] = name

        container_config = app_deployment["spec"]["template"]["spec"]["containers"][0]

        container_config.update(
            {
                "name": name,
                "image": f"{self.cr}/{self.project}/{safeowner}_{safetitle}_tasks:{self.tag}",
                "command": [
                    "cs-job",
                    "-t",
                    "1234",
                    "-a",
                    '{"Policy": {}, "Tax Information": {}}',
                    "-m",
                    '{"year": 2022}',
                ],
                "resources": resources,
            }
        )

        container_config["env"].append({"name": "TITLE", "value": app["title"]})
        container_config["env"].append({"name": "OWNER", "value": app["owner"]})
        container_config["env"].append(
            {"name": "SIM_TIME_LIMIT", "value": str(app["sim_time_limit"])}
        )
        container_config["env"].append(
            {"name": "APP_NAME", "value": f"{safeowner}_{safetitle}_tasks"}
        )
        self._set_secrets(app, container_config)

        return app_deployment

    def _resources(self, app, action=None):
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
        safeowner = clean(app["owner"])
        safetitle = clean(app["title"])
        name = f"{safeowner}-{safetitle}-secret"
        for key in self._list_secrets(app):
            config["env"].append(
                {"name": key, "valueFrom": {"secretKeyRef": {"name": name, "key": key}}}
            )

    def _list_secrets(self, app):
        secret = Secrets(app["owner"], app["title"], self.project)
        return secret.list_secrets()


def main():
    parser = argparse.ArgumentParser(description="Deploy C/S compute cluster.")
    parser.add_argument("--tag", required=False, default=TAG)
    parser.add_argument("--project", required=False, default=PROJECT)
    parser.add_argument("--models", nargs="+", type=str, required=False, default=None)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--app-config", action="store_true")
    parser.add_argument("--job-config", action="store_true")
    parser.add_argument("--base-branch", default="origin/master")
    parser.add_argument("--quiet", "-q", default=False)
    parser.add_argument("--config-out", "-o", default=None)

    args = parser.parse_args()

    publisher = Publisher(
        tag=args.tag,
        project=args.project,
        models=args.models,
        base_branch=args.base_branch,
        quiet=args.quiet,
        kubernetes_target=args.config_out,
    )
    if args.build:
        publisher.build()
    if args.test:
        publisher.test()
    if args.push:
        publisher.push()
    if args.app_config:
        publisher.write_app_config()
    if args.job_config:
        publisher.write_job_config()


if __name__ == "__main__":
    main()
