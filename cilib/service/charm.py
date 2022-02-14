""" Charm, layer, interface service object """

from cilib.log import DebugMixin
from urllib.parse import urlparse
import tempfile
from pathlib import Path


class CharmService(DebugMixin):
    def __init__(self, repo):
        self.repo = repo
        self.name = repo.name

        self.upstream_normalized = str(
            Path(urlparse(self.repo.upstream).path.lstrip("/")).with_suffix("")
        )
        self.downstream_normalized = str(Path(self.repo.downstream).with_suffix(""))

    @property
    def is_upstream_eq_downstream(self):
        """checks if upstream equals downstream"""
        return self.upstream_normalized == self.downstream_normalized

    def sync(self):
        """Syncs all charm, layers, interfaces repositories with their downstream counterparts"""
        if self.is_upstream_eq_downstream:
            self.log(
                f"Skipping {self.repo.name} ({self.upstream_normalized} == {self.downstream_normalized})"
            )
            return

        self.log(f"Syncing {self.upstream_normalized} -> {self.downstream_normalized}")
        upstream_ref = self.repo.default_gh_branch(self.upstream_normalized)
        downstream_ref = self.repo.default_gh_branch(self.downstream_normalized)
        with tempfile.TemporaryDirectory() as tmpdir:
            src_path = Path(tmpdir) / self.repo.src
            self.repo.base.clone(cwd=tmpdir)
            self.repo.base.remote_add(
                origin="upstream", url=self.repo.upstream, cwd=str(src_path)
            )
            self.repo.base.fetch(origin="upstream", cwd=str(src_path))
            self.repo.base.checkout(ref=downstream_ref, cwd=str(src_path))
            self.repo.base.merge(origin="upstream", ref=upstream_ref, cwd=str(src_path))
            self.repo.base.push(origin="origin", ref=downstream_ref, cwd=str(src_path))
