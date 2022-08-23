from dotenv import load_dotenv
from invoke import task
import yaml

load_dotenv()


@task
def update_deps(c):
    """Syncs package dependencies"""
    c.run("pip-compile")


@task
def build_docs(c):
    c.run("rm -rf site")
    c.run("cp README.md docs/index.md")
    c.run("mkdocs build")


@task(pre=[build_docs])
def upload_docs(c):
    c.run("aws s3 sync site/ s3://jenkaas/docs")


@task
def format(c):
    """Formats py code"""
    c.run("black jobs cilib tests")


@task
def black_check(c):
    """Checks black format"""
    c.run("black --check jobs cilib tests")


@task
def flake8(c):
    """Runs flake8 against project"""
    c.run(
        "flake8 --ignore=E501,W503 jobs/integration jobs/build-charms jobs/build-snaps tests"
    )


@task(pre=[flake8, black_check])
def test(c):
    """Run unittest suite"""
    c.run("pytest -W error:UserWarning cilib tests")


@task
def test_jobs(c, conf):
    """Tests the Jenkins Job Builder definitions"""
    c.run("jenkins-jobs --conf {} test jobs/.".format(conf))


@task
def update_jobs(c, conf):
    """Uploads the Jenkins Job Builder definitions"""
    c.run("jenkins-jobs --conf {} update jobs/. --worker 8".format(conf))


@task
def list_jobs(c, conf):
    """list the Jenkins Job Builder definitions"""
    c.run("jenkins-jobs --conf {} list".format(conf))


@task
def delete_jobs(c, conf, pattern):
    """Delete jobs based on pattern"""
    out = c.run("jenkins-jobs --conf {} list |grep '{}'".format(conf, pattern))
    for line in out.stdout.splitlines():
        c.run("jenkins-jobs --conf {} delete {}".format(conf, line.strip()))
