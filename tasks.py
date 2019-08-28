from dotenv import load_dotenv
from invoke import task
import yaml

load_dotenv()


@task
def test(c):
    c.run("pytest jobs/**/*/tests")


@task
def build_docs(c):
    c.run("ogc --spec maintainer-spec.yml --debug -t build-docs")


@task
def upload_docs(c):
    c.run("/snap/bin/aws s3 sync site/ s3://jenkaas/docs")


@task
def format(c):
    """ Formats py code
    """
    c.run("black .")


@task
def flake8(c):
    """ Runs flake8 against project
    """
    c.run("flake8 --ignore=E501,W503 jobs/integration")


@task
def test_jobs(c, conf):
    """ Tests the Jenkins Job Builder definitions
    """
    c.run("jenkins-jobs --conf {} test jobs/.".format(conf))


@task
def update_jobs(c, conf):
    """ Uploads the Jenkins Job Builder definitions
    """
    c.run("jenkins-jobs --conf {} update jobs/. --worker 8".format(conf))


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
