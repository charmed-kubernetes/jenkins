#!/usr/bin/python

import sys
import yaml


# argv[1] is the path to the downloaded bundle
# argv[2] is the snap channel we want to use

file_name = '{}/bundle.yaml'.format(sys.argv[1])

stream = open(file_name, 'r')
data = yaml.load(stream)

master_options = {'channel': sys.argv[2]}
worker_options = {'channel': sys.argv[2],
                  'labels': 'mylabel=thebest'}

data['services']['kubernetes-master']['options'] = master_options
data['services']['kubernetes-worker']['options'] = worker_options

yaml.Dumper.ignore_aliases = lambda *args : True
with open(file_name, 'w') as yaml_file:
    yaml_file.write( yaml.dump(data, default_flow_style=False))
