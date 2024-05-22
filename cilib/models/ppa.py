"""Launchpad PPA model"""

from cilib import lp, version


class PPA:
    def __init__(self, collection):
        self.collection = collection

    @property
    def sources(self):
        """Return the published sources for PPA collection"""
        return [
            {
                "name": pkg.source_package_name,
                "version": pkg.source_package_version,
                "status": pkg.status,
            }
            for pkg in self.collection.getPublishedSources()
        ]

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
            return version.parse(source["version"])
        return None


class PPACollection:
    def __init__(self, ppas):
        self.ppas = ppas

    def get_ppa_by_major_minor(self, major_minor):
        """Returns the ppa archive by name which is major.minor"""
        for _ppa in self.ppas:
            if _ppa.name == major_minor:
                return PPA(_ppa)
        return None

    @property
    def names(self):
        """Returns a list of all ppas in collection by name"""
        return [_ppa.name for _ppa in self.ppas]
