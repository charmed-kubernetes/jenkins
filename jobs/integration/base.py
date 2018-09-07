from sh import juju_wait


def _juju_wait(controller, model):
    juju_wait('-e', "{}:{}".format(controller, model), '-w')
