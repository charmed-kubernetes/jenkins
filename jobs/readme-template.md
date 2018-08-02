# Name

- **Job**: `JOBFILE.YAML`
- **Project Name**: `PROJECT NAME`

# Description

_Description of project_

# Parameters

- **parameter_a**: Description of parameter_a

# Usage

Example of modifying, changing job

```
 - job-group:
     name: '{name}-tests'
     jobs:
       - '{name}-tests-{k8sver}':
           k8sver: 'v1.11.x'
           bundle_revision: '218'
           cloud: ['aws', 'google']
       - '{name}-tests-{k8sver}':
           k8sver: 'v1.12.x'
           bundle_revision: '2xx'
           cloud: ['aws', 'google']
```

# References

- https://example.com
