""" Launchpad module
"""

from launchpadlib.launchpad import Launchpad
import os

class ClientError(Exception):
    pass


class Client:
    """ Launchpad client
    """

    def __init__(self, stage='production', version='devel'):
        _env = os.environ.copy()
        self._client = None
        self.cache = _env.get('WORKSPACE', '/tmp') + '/cache'
        self.creds = _env.get('LPCREDS', None)
        self.stage = stage
        self.version = version


    def login(self):
        if self._client:
            return self._client

        self._client = Launchpad.login_with(
            application_name='k8s-jenkaas-bot',
            service_root=self.stage,
            launchpadlib_dir=self.cache,
            version=self.version,
            credentials_file=self.creds)

    def owner(self, name):
        """ Returns LP owner object
        """
        return self._client.people[name]

    @property
    def snaps(self):
        """ Gets snaps collection
        """
        return self._client.snaps

    def create_snap_builder(self, name, owner, branch, track):
        """ Creates a new LP builder for snap with a specific git branch to build from
        """
        _current_working_snap = self.snaps.getByName(name=name, owner=owner)
        _new_name = f'{name}-{branch}'
        return self.snaps.new(
            name=_new_name,
            owner=owner,
            distro_series=_current_working_snap.distro_series,
            git_repository=_current_working_snap.git_repository,
            git_path=branch,
            store_upload=_current_working_snap.store_upload,
            store_name=_current_working_snap.store_name,
            store_series=_current_working_snap.store_series,
            store_channels=track,
            processors=['/+processors/amd64',
                        '/+processors/s390x',
                        '/+processors/ppc64el',
                        '/+processors/arm64'],
            auto_build=_current_working_snap.auto_build,
            auto_build_archive=_current_working_snap.auto_build_archive,
            auto_build_pocket='Updates'
        )
