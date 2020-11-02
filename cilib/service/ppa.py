"""PPA service object

Keeps ppas maintained
"""

from cilib import enums
from cilib.models.ppa import PPACollection
from cilib.log import DebugMixin
from drypy.patterns import sham


class PPAService(DebugMixin):
    def __init__(self, owner):
        self.owner = owner
        self.ppas = PPACollection(owner.ppas)

    @property
    def missing_ppas(self):
        """Returns any missing ppas"""
        upstream_ppas = self.ppas.names
        supported_ppas = list(enums.DEB_K8S_TRACK_MAP.keys())
        return list(set(supported_ppas) - set(upstream_ppas))

    def sync(self):
        """Syncs and creates missing upstream ppas"""
        if not self.missing_ppas:
            self.log(f"All ppas are synced, nothing to do here.")
            return

        for _ppa in self.missing_ppas:
            self.log(f"Creating ppa {_ppa} at {enums.DEB_K8S_TRACK_MAP[_ppa]}")
            self.owner.createPPA(name=_ppa, displayname=f"Kubernetes {_ppa}")
