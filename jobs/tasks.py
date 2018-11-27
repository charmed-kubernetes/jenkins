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
    c.run("jenkins-jobs --conf {} update . --worker 8".format(conf))


@task
def list_jobs(c, conf):
    """ list the Jenkins Job Builder definitions
    """
    c.run("jenkins-jobs --conf {} list".format(conf))

@task
def delete_jobs(c, conf, pattern):
    """ Delete jobs based on pattern
    """
    out = c.run("jenkins-jobs --conf {} list |grep '{}'".format(conf, pattern))
    for line in out.stdout.splitlines():
        c.run("jenkins-jobs --conf {} delete {}".format(conf, line.strip()))


@task
def create_nodes(c, apikey, apiuser, node, labels='runner'):
    """ Creates a jenkins slave node
    """
    j = jenkins.Jenkins('https://ci.kubernetes.juju.solutions',
                        username=apiuser, password=apikey)
    params = {
        'command': (
            'sudo -E sudo -u jenkins -E juju ssh -m jenkins-ci-google:agents '
            '{node}/0 -- "java -jar /home/ubuntu/slave.jar"'.format(
                node=node))
    }
    j.create_node(
        node,
        nodeDescription='juju generated slave node',
        remoteFS='/home/ubuntu',
        labels=labels,
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
    try:
        status = c.run(
            'sudo -E sudo -u jenkins -E juju status '
            '-m jenkins-ci-google:agents --format yaml')
        status = yaml.load(status.stdout)
    except:
        return

    if not status['applications']:
        return

    for node in status['applications'].keys():
        try:
            j.delete_node(node)
        except jenkins.JenkinsException as e:
            print(e)
            continue

@task
def set_node_ips(c):
    """ Returns a list of current nodes ip addresses to populate for ansible
    """
    status = c.run('sudo -E sudo -u jenkins -E juju status '
                   '-m jenkins-ci-google:agents --format yaml')
    status = yaml.load(status.stdout)
    ip_addresses = ['[jenkins-nodes]']
    if status['applications']:
        for node, properties in status['applications'].items():
            addr = properties['units']['{}/0'.format(node)]['public-address']
            ip_addresses.append(addr)
    print("Writing {}".format(ip_addresses))
    with open('infra/hosts', 'w') as hosts_f:
        hosts_f.write("\n".join(ip_addresses))
