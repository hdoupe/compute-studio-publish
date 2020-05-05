import argparse
import json

from cs_publish.task_wrapper import kubernetes_task_wrapper
from cs_publish.celery import get_app


app = get_app()


@kubernetes_task_wrapper(celery_app=app)
def run(*args, **kwargs):
    print("run", args, kwargs)
    from cs_config import functions

    result = functions.run_model(*args, **kwargs)
    print("success")
    return result


def main():
    parser = argparse.ArgumentParser(description="CLI for C/S jobs.")
    parser.add_argument("--task-id", "-t", required=True)
    parser.add_argument("--meta-param-dict", "-m", required=True)
    parser.add_argument("--adjustment", "-a", required=True)
    args = parser.parse_args()

    print(args.adjustment)
    adjustment = json.loads(args.adjustment)
    mp_dict = json.loads(args.meta_param_dict)

    run(args.task_id, mp_dict, adjustment)
