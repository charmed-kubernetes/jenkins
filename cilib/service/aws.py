""" AWS session
"""

import boto3
import botocore.exceptions


class AWSSessionException(Exception):
    pass


class AWSSession:
    def __init__(self, region="us-east-1", resource=None):
        self.session = boto3.Session(region_name=region)
        if resource is None:
            raise AWSSessionException("Must have a resource defined.")
        self.resource = self.session.resource(resource)


class Store(AWSSession):
    def __init__(self, table):
        super().__init__(resource="dynamodb")
        self.table = self.resource.Table(table)

    def get_item(self, *args, **kwargs):
        try:
            return self.table.get_item(*args, **kwargs)
        except botocore.exceptions.NoCredentialsError:
            return None

    def put_item(self, *args, **kwargs):
        return self.table.put_item(*args, **kwargs)
