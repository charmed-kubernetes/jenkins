import traceback
import click


def log(msg):
    click.echo(f"  {msg}")


def function_call_str(f, args, kwargs):
    top_module = f.__module__.split(".")[-1]
    function_name = top_module + "." + f.__name__
    arg_strs = [str(x) for x in args]
    kwarg_strs = ["%s=%s" % (k, v) for k, v in kwargs.items()]
    combined_arg_str = " ".join(arg_strs + kwarg_strs)
    return function_name + " " + combined_arg_str


logged_exception = None


def log_exception_once(e):
    global logged_exception
    if e != logged_exception:
        traceback.print_exc()
        logged_exception = e


def log_calls(f):
    def wrapper(*args, **kwargs):
        f_str = function_call_str(f, args, kwargs)
        log("START " + f_str)
        try:
            result = f(*args, **kwargs)
            log("END   " + f_str)
            return result
        except Exception as e:
            log_exception_once(e)
            log("RAISE " + f_str)
            raise

    return wrapper


def log_calls_async(f):
    async def wrapper(*args, **kwargs):
        f_str = function_call_str(f, args, kwargs)
        log("START " + f_str)
        try:
            result = await f(*args, **kwargs)
            log("END   " + f_str)
            return result
        except Exception as e:
            log_exception_once(e)
            log("RAISE " + f_str)
            raise

    return wrapper
