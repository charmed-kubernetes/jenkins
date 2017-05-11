#!/usr/bin/python

import sys
import yaml


# argv[1] is the path to the downloaded bundle
# argv[2] is the snap channel we want to use

file_name = '{}/bundle.yaml'.format(sys.argv[1])

stream = open(file_name, 'r')
data = yaml.load(stream)

channel = {'channel': sys.argv[2]}
data['services']['kubernetes-master']['options'] = channel
data['services']['kubernetes-worker']['options'] = channel

yaml.Dumper.ignore_aliases = lambda *args : True
with open(file_name, 'w') as yaml_file:
    yaml_file.write( yaml.dump(data, default_flow_style=False))
