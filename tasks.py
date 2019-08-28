from dotenv import load_dotenv
from invoke import task

load_dotenv()


@task
def test(c):
    c.run("pytest **/*/tests")


@task
def build_docs(c):
    c.run("mkdocs build")


@task
def upload_docs(c):
    c.run("/snap/bin/aws s3 sync site/ s3://jenkaas/docs")
