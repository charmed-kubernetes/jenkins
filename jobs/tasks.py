from invoke import task

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
