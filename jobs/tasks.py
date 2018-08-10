from invoke import task
import jenkins
import yaml


@task
def test_jobs(c, conf):
    """ Tests the Jenkins Job Builder definitions
    """
    c.run("jenkins-jobs --conf {} test .".format(conf))


@task
def update_jobs(c, conf):
    """ Uploads the Jenkins Job Builder definitions
    """
    c.run("jenkins-jobs --conf {} update .".format(conf))


@task
def create_nodes(c, apikey, apiuser, node):
    """ Creates a jenkins slave node
    """
    j = jenkins.Jenkins('https://ci.kubernetes.juju.solutions',
                        username=apiuser, password=apikey)
    params = {
        'command': ('sudo -E sudo -u jenkins -E juju ssh -m jenkins-ci:agents '
                    '{node}/0 -- "java -jar /home/ubuntu/slave.jar"'.format(
                        node=node))
    }
    j.create_node(
        node,
        nodeDescription='juju generated slave node',
        remoteFS='/home/ubuntu',
        labels='runner',
        exclusive=False,
        numExecutors=1,
        launcher=jenkins.LAUNCHER_COMMAND,
        launcher_params=params
    )


@task
def delete_nodes(c, apikey, apiuser):
    """ Creates a jenkins slave node
    """
    j = jenkins.Jenkins('https://ci.kubernetes.juju.solutions',
                        username=apiuser, password=apikey)
    status = c.run('sudo -E sudo -u jenkins -E juju status --format yaml')
    status = yaml.load(status.stdout)
    if not status['applications']:
        return

    for node in status['applications'].keys():
        j.delete_node(node)
