""" Launchpad module
"""

from lazr.restfulclient.errors import NotFound
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

    def snap_git_repo(self, owner, project):
        """ Returns a git repository link for project

        Usage:
        snap_git_repo('k8s-jenkaas-admins, 'snap-kubectl')
        """
        return self._client.git_repositories.getByPath(
            path=f'~{owner.name}/{project}')

    def archive(self, reference='ubuntu'):
        """ Returns archive for reference
        """
        return self._client.archives.getByReference(reference=reference)

    def distro_series(self, distribution='ubuntu', series='xenial'):
        """ Returns distributions
        """
        return self._client.distributions[distribution].getSeries(name_or_version=series)

    def snappy_series(self, name='16'):
        """ Returns current snappy_series
        """
        return self._client.snappy_serieses.getByName(name=name)

    def create_or_update_snap_builder(self, name, owner, version, repo, branch, track):
        """ Creates a new LP builder for snap with a specific git branch to build from
        """
        lp_snap_name = f'{name}-{version}'
        lp_snap_project_name = f'snap-{name}'
        lp_owner = self.owner(owner)

        if not isinstance(track, list):
            track = [track]

        try:
            _current_working_snap = self.snaps.getByName(name=lp_snap_name, owner=lp_owner)
            _current_working_snap.git_path = branch
            _current_working_snap.auto_build = True
            _current_working_snap.auto_build_pocket= 'Updates'
            _current_working_snap.auto_build_archive = self.archive()
            _current_working_snap.store_upload = True
            _current_working_snap.store_name = name
            _current_working_snap.store_series = self.snappy_series()
            _current_working_snap.store_channels = track
            _current_working_snap.lp_save()
        except NotFound:
            return self.snaps.new(
                name=lp_snap_name,
                owner=lp_owner,
                distro_series=self.distro_series(),
                git_repository=self.snap_git_repo(lp_owner, lp_snap_project_name),
                git_path=branch,
                store_upload=True,
                store_name=name,
                store_series=self.snappy_series(),
                store_channels=track,
                processors=['/+processors/amd64',
                            '/+processors/s390x',
                            '/+processors/ppc64el',
                            '/+processors/arm64'],
                auto_build=True,
                auto_build_pocket='Updates',
                auto_build_archive=self.archive()
            )
