import argparse
import functools
import json
import os
import uuid

import redis

from cs_publish.executors.task_wrapper import handle_sim_task
from cs_publish.executors.celery import get_app


REDIS = os.environ.get("REDIS")


app = get_app()


def kubernetes_task_wrapper(celery_app):
    def _task_wrapper(func):
        @functools.wraps(func)
        def f(task, *args, **kwargs):
            print("kubernetes wrapper", task, func, args, kwargs)
            with redis.Redis.from_url(REDIS) as rclient:
                result = rclient.get(task)
            if result is None:
                raise KeyError(f"No value found for job id: {task}")
            kwargs = json.loads(result.decode())
            result = handle_sim_task(celery_app, task, func, *args, **kwargs)
            print("result from handle_sim_task", result)
            celery_app.signature(
                "outputs_processor.push_to_cs", args=("sim", result)
            ).delay()
            return result

        return f

    return _task_wrapper


@kubernetes_task_wrapper(celery_app=app)
def run(job_id=None, meta_param_dict=None, adjustment=None):
    print("run", job_id, meta_param_dict, adjustment)
    from cs_config import functions

    result = functions.run_model(meta_param_dict, adjustment)
    print("success")
    return result


def main():
    parser = argparse.ArgumentParser(description="CLI for C/S jobs.")
    parser.add_argument("--job-id", "-t", required=True)
    args = parser.parse_args()

    run(args.job_id)
