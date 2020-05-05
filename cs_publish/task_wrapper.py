import functools
import os
import re
import time
import traceback

import requests
from celery import Task
import cs_storage


try:
    from cs_config import functions
except ImportError as ie:
    # if os.environ.get("IS_FLASK", "False") == "True":
    #     functions = None
    # else:
    #     raise ie
    pass


OUTPUTS_VERSION = os.environ.get("OUTPUTS_VERSION")


def handle_inputs_task(celery_app, task_id, func, *args, **kwargs):
    start = time.time()
    traceback_str = None
    res = {}
    try:
        outputs = func(*args, **kwargs)
        res.update(outputs)
    except Exception:
        traceback_str = traceback.format_exc()
    finish = time.time()
    if "meta" not in res:
        res["meta"] = {}
    res["meta"]["task_times"] = [finish - start]
    if traceback_str is None:
        res["status"] = "SUCCESS"
    else:
        res["status"] = "FAIL"
        res["traceback"] = traceback_str
    return res


def handle_sim_task(celery_app, task_id, func, *args, **kwargs):
    print("sim task", celery_app, task_id, func, args, kwargs)
    start = time.time()
    traceback_str = None
    res = {}
    try:
        outputs = func(*args, **kwargs)
        version = outputs.pop("version", OUTPUTS_VERSION)
        outputs = cs_storage.serialize_to_json(outputs)
        outputs = (
            celery_app.signature(
                "outputs_processor.write_to_storage", args=(task_id, outputs)
            )
            .delay()
            .get(
                # danger: by default cannot run sync tasks
                # from within a task.
                disable_sync_subtasks=False
            )
        )
        res.update(
            {
                "model_version": functions.get_version(),
                "outputs": outputs,
                "version": version,
            }
        )
    except Exception:
        traceback_str = traceback.format_exc()
    finish = time.time()
    if "meta" not in res:
        res["meta"] = {}
    res["meta"]["task_times"] = [finish - start]
    if traceback_str is None:
        res["status"] = "SUCCESS"
    else:
        res["status"] = "FAIL"
        res["traceback"] = traceback_str
    return res


def celery_task_wrapper(celery_app):
    def _task_wrapper(func):
        @functools.wraps(func)
        def f(task, *args, **kwargs):
            return handle_inputs_task(
                celery_app, task.request.id, func, *args, **kwargs
            )

        return f


def kubernetes_task_wrapper(celery_app):
    def _task_wrapper(func):
        @functools.wraps(func)
        def f(task, *args, **kwargs):
            print("kubernetes wrapper", task, func, args, kwargs)
            result = handle_sim_task(celery_app, task, func, *args, **kwargs)
            celery_app.signature(
                "outputs_processor.push_to_cs", args=("sim", result)
            ).delay()
            return result

        return f
