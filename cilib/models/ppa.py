"""Launchpad PPA model"""
from cilib import lp
import semver

class PPA:
    def __init__(self, collection):
        self.collection = collection

    @property
    def sources(self):
        """Return the published sources for PPA collection"""
        return [{
            "name": pkg.source_package_name,
            "version": pkg.source_package_version,
            "status": pkg.status
        } for pkg in self.collection.getPublishedSources()]

    @property
    def published(self):
        """Get published sources from collection"""
        return [pkg for pkg in self.sources if pkg["status"] == "Published"]

    def get_latest_source(self, name):
        """Gets the latest published package by name"""
        for pkg in self.published:
            if pkg["name"] == name:
                return pkg
        return None

    def get_source_semver(self, name):
        """Get semver for latest published package"""
        source = self.get_latest_source(name)
        if source:
            return semver.VersionInfo.parse(source["version"])
        return None
