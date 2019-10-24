""" AWS session
"""
import boto3


class AWSSession:
    def __init__(self, region="us-east-1", resource):
        self.session = boto3.Session(region_name=region)
        self.resource = session.resource(resource)


class Store(AWSSession):
    def __init__(self, table):
        super().__init__(resource="dynamodb")
        self.table = self.resource.Table(table)

    def get_item(self, *args, **kwargs):
        return self.table.get_item(*args, **kwargs)

    def put_item(self, *args, **kwargs):
        return self.table.put_item(*args, **kwargs)
