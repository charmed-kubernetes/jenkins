Running JJB

# Prereqs

  - Python 3.6 or later
  - Needs `tox` installed
  - Needs Jenkins Job Builder config (**jjb-conf.ini**):

```ini
[job_builder]
ignore_cache=True
keep_descriptions=False
include_path=.:scripts:~/git/
recursive=False
exclude=.*:manual:./development
allow_duplicates=False

[jenkins]
user=jenkinsuser
password=password
url=https://jenkinsci.com
query_plugins_info=False
```

# Setup

First setup your python environment:

```
> cd jobs
```

# See a list of available job tasks
```
> tox --workdir .tox -e py36 -- invoke -l
```

# Update jobs in jenkins

```
> tox --workdir .tox -e py36 -- invoke update-jobs --conf jjb-conf.ini
```

# Adding new jobs

1. Create the job yaml in this `jobs/` directory.
2. Create a sub-directory of the same name as job.
3. Create a `Jenkinsfile` and any additional local libraries required for job to run.
4. Include a readme.md based on `readme-template.md`
5. Verify job syntax with: `tox --workdir .tox -e py36 -- invoke test-jobs --conf jobs/jjb-conf.ini`

# References

- https://jenkins.io/doc/book/pipeline/jenkinsfile/
- http://jenkins-job-builder.readthedocs.io/en/latest/project_pipeline.html
