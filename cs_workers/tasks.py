import time
import os

from cs_workers import app, task_wrapper

try:
    from cs_config import functions
except ImportError as ie:
    if os.environ.get("IS_FLASK", "False") == "True":
        functions = None
    else:
        raise ie


APP_NAME = os.environ.get("APP_NAME")
SIM_TIME_LIMIT = os.environ.get("SIM_TIME_LIMIT")

@app.task(
    name=f"{APP_NAME}.inputs_version", soft_time_limit=10, bind=True, acks_late=True
)
@task_wrapper
def inputs_version(self):
    return {"version": functions.get_version()}


@app.task(
    name=f"{APP_NAME}.inputs_get", soft_time_limit=10, bind=True, acks_late=True
)
@task_wrapper
def inputs_get(self, meta_param_dict):
    return functions.get_inputs(meta_param_dict)


@app.task(
    name=f"{APP_NAME}.inputs_parse", soft_time_limit=10, bind=True, acks_late=True
)
@task_wrapper
def inputs_parse(self, meta_param_dict, adjustment, errors_warnings):
    return functions.validate_inputs(meta_param_dict, adjustment, errors_warnings)


@app.task(
    name=f"{APP_NAME}.sim",
    soft_time_limit=int(SIM_TIME_LIMIT),
    bind=True,
    acks_late=True,
)
@task_wrapper
def sim(self, meta_param_dict, adjustment):
    if os.environ.get("DASK_SCHEDULER_ADDRESS") is not None:
        from distributed import Client
        from dask import delayed

        print("submitting data")
        with Client() as c:
            print("c", c)
            fut = c.submit(functions.run_model, meta_param_dict, adjustment)
            print("waiting on result", fut)
            return fut.result()

    return functions.run_model(meta_param_dict, adjustment)

