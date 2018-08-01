Running JJB

# Prereqs

  - Needs `pipenv` installed
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
> pipenv shell
```

# Update jobs in jenkins

```
> jenkins-jobs --conf jobs/jjb-conf.ini update jobs/
```

# References

- https://jenkins.io/doc/book/pipeline/jenkinsfile/
- http://jenkins-job-builder.readthedocs.io/en/latest/project_pipeline.html
