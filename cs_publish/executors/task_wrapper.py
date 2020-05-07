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
    res = {"job_id": task_id}
    try:
        print("calling func", func, args, kwargs)
        outputs = func(*args, **kwargs)
        print("got result")
        outputs = cs_storage.serialize_to_json(outputs)
        resp = requests.post(
            "http://outputs-processor/write/",
            json={"task_id": task_id, "outputs": outputs},
        )
        assert resp.status_code == 200, f"Got code: {resp.status_code}"
        outputs = resp.json()
        res.update(
            {
                "model_version": functions.get_version(),
                "outputs": outputs,
                "version": "v1",
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
