""" Charm, layer, interface service object """

from cilib.log import DebugMixin
from urllib.parse import urlparse
import dataclasses
import json
import subprocess
import tempfile
from pathlib import Path
from functools import cached_property
from typing import FrozenSet


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


@dataclasses.dataclass(frozen=True)
class CharmBase:
    name: str
    channel: str

    def __str__(self) -> str:
        return f"{self.name}@{self.channel}"

    def __contains__(self, item: str) -> bool:
        return item in self.name or item in self.channel


@dataclasses.dataclass(frozen=True)
class CharmRev:
    name: str
    track: str
    risk: str
    revision: int
    version: str
    size: str
    architectures: FrozenSet[str]
    bases: FrozenSet[CharmBase]

    @property
    def channel(self) -> str:
        return f"{self.track}/{self.risk}"

    @property
    def archs(self) -> str:
        return ", ".join(sorted(self.architectures))

    @property
    def base(self) -> str:
        return ", ".join(sorted(map(str, self.bases)))

    @classmethod
    def from_dict(cls, **kwargs) -> "CharmRev":
        names = set([f.name for f in dataclasses.fields(cls)])
        kwargs["architectures"] = frozenset(kwargs["architectures"])
        kwargs["bases"] = frozenset(CharmBase(**b) for b in kwargs["bases"])
        return cls(**{k: v for k, v in kwargs.items() if k in names})


class CharmInfo(DebugMixin):
    def __init__(self, name: str) -> None:
        self.name = name

    @cached_property
    def _fetched(self):
        try:
            out = subprocess.check_output(
                ["juju", "info", self.name, "--format", "json"]
            )
        except subprocess.CalledProcessError:
            return {}
        return json.loads(out)

    def at(self, track: str, risk: str) -> FrozenSet[CharmRev]:
        p = self._fetched
        if track not in p["tracks"]:
            return set()
        return frozenset(
            CharmRev.from_dict(name=self.name, **r)
            for revlist in p["channels"][track].values()
            for r in revlist
            if r["risk"] == risk
        )

    def unreleased(self, track: str) -> FrozenSet[CharmRev]:
        unreleased_risks = [
            "beta",
            "candidate",
        ]  # look in these tracks for unreleased charms
        stable_revisions = self.at(track, "stable")
        unreleased_revisions = set()
        for risk in unreleased_risks:
            for rev in self.at(track, risk):
                match = next(
                    (
                        r
                        for r in stable_revisions
                        if r.architectures == rev.architectures
                    ),
                    None,
                )
                if match and rev.revision > match.revision:
                    unreleased_revisions |= {rev}
        return unreleased_revisions
