import os
import re

import requests
from celery import Celery
from celery.signals import task_postrun
from celery.result import AsyncResult


CS_URL = os.environ.get("CS_URL")

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://redis-master/0")
CELERY_RESULT_BACKEND = os.environ.get(
    "CELERY_RESULT_BACKEND", "redis://redis-master/0"
)


def get_task_routes():
    def clean(name):
        return re.sub("[^0-9a-zA-Z]+", "", name).lower()

    print(f"getting config from: {CS_URL}/publish/api/")
    resp = requests.get(f"{CS_URL}/publish/api/")
    if resp.status_code != 200:
        raise Exception(f"Response status code: {resp.status_code}")
    data = resp.json()
    task_routes = {}
    for project in data:
        owner = clean(project["owner"])
        title = clean(project["title"])
        model = f"{owner}_{title}"

        # all apps use celery workers for handling their inputs.
        routes = {
            f"{model}_tasks.inputs_get": {"queue": f"{model}_inputs_queue"},
            f"{model}_tasks.inputs_parse": {"queue": f"{model}_inputs_queue"},
            f"{model}_tasks.inputs_version": {"queue": f"{model}_inputs_queue"},
        }

        # only add sim routes for models that use celery workers.
        if project["cluster_type"] == "single-core":
            routes[f"{model}_tasks.sim"] = {"queue": f"{model}_queue"}

        task_routes.update(routes)
    return task_routes


task_routes = get_task_routes()


def get_app():
    app = Celery("app", broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)
    app.conf.update(
        task_serializer="json",
        accept_content=["msgpack", "json"],
        task_routes=task_routes,
        worker_prefetch_multiplier=1,
        task_acks_late=True,
    )
    return app


@task_postrun.connect
def post_results(sender=None, headers=None, body=None, **kwargs):
    print(f'task_id: {kwargs["task_id"]}')
    print(f'task: {kwargs["task"]} {kwargs["task"].name}')
    print(f'is sim: {kwargs["task"].name.endswith("sim")}')
    print(f'state: {kwargs["state"]}')
    result = kwargs["retval"]
    result["job_id"] = kwargs["task_id"]

    if kwargs["task"].name.endswith("sim"):
        task_type = "sim"
    elif kwargs["task"].name.endswith("parse"):
        task_type = "parse"
    else:
        return None

    get_app().signature(
        "outputs_processor.push_to_cs", args=(task_type, result)
    ).delay()
