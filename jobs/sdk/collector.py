""" collection utilities
"""

from datetime import datetime
from pathlib import Path
import boto3
import click
import os
import sh
import yaml
import json
from pprint import pformat


class CollectionException(Exception):
    pass


class Collect:
    def __init__(self, identifier, dynamodb_table="CIBuilds"):
        """ Initialize

        identifier: unique key for this collection
        """
        self.identifier = identifier
        self.cache_db = {}
        self.session = boto3.Session(profile_name="default", region_name="us-east-1")
        self.dynamodb = session.resource("dynamodb")
        self.dynamodb_table = dynamodb_table
        self.s3 = session.client("s3")
        self.s3_bucket = "jenkaas"

    def upload_file(self, name, src, dst):
        """ Upload file to s3

        Arguments:
        name: friendly name to reference
        src: Path obj to local file
        dst: Path obj to s3 destination

        Return None
        """
        if not src.exists():
            raise CollectionException(f"Unable to locate file {src}")
        if "files" in self.cache_db:
            self.cache_db["files"].append({"name": name, "path": str(dst)})
        else:
            self.cache_db["files"] = [{"name": name, "path": str(dst)}]
        self.s3.upload_file(str(src), str(dst))

    def start(self):
        """ Timestamps start of a collection
        """
        env = os.environ.copy()
        self.cache_db["build_datetime"] = str(datetime.utcnow().isoformat())
        self.cache_db["identifier"] = self.identifier
        self.cache_db["job_name"] = env["JOB_NAME"]
        self.cache_db["build_number"] = env["BUILD_NUMBER"]
        self.cache_db["node_name"] = env["NODE_NAME"]
        self.cache_db["build_tag"] = env["BUILD_TAG"]
        self.cache_db["workspace"] = env["WORKSPACE"]

    def result(self, passed=False):
        """ Result of the collection, typically a ci run end result
        """
        self.cache_db["test_result"] = passed

    def end(self):
        """ Timestamps end of a collection
        """
        self.cache_db["build_endtime"] = str(datetime.utcnow().isoformat())
        self.__save()

    def set_kv(self, key, value):
        """ General setter
        """
        self.cache_db[key] = value

    def save(self):
        """ Saves collected data to dynamodb
        """
        table = self.dynamodb.Table(self.dynamodb_table)
        table.put_item(Item=json.dumps(self.cache_db))
