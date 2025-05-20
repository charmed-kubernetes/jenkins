from dataclasses import dataclass
from typing import Optional, Mapping, Union
import semver
from cilib import log


def normalize(version):
    """Normalizes a version string"""
    return version.lstrip("v")


def parse(version):
    """Returns semver.parse"""
    return semver.VersionInfo.parse(normalize(version))


def compare(version_a, version_b):
    """Compares 2 sem versions"""

    def _cmp(x, y):
        return (x > y) - (x < y)

    def _from(ver):
        ver = normalize(ver)
        try:
            return semver.VersionInfo.parse(ver)
        except ValueError:
            return tuple(map(int, ver.split(".")))
        except Exception:
            log.error(f"Unable to parse {ver} into semver")
            raise

    return _cmp(_from(version_a), _from(version_b))


def greater(version_a, version_b):
    """Check that version_a > version_b"""
    return compare(version_a, version_b) >= 0


def lesser(version_a, version_b):
    """Check that version_a < version_b"""
    return compare(version_a, version_b) <= 0


RISKS = ["stable", "candidate", "beta", "edge"]


@dataclass
class Release:
    """Representation of Charm or Snap Release version."""

    major: int
    minor: int
    risk: Optional[str]

    def __str__(self):
        risk = ""
        if self.risk:
            risk = f"/{self.risk}" if self.risk.lower() in RISKS else ""
        return f"{self.major}.{self.minor}{risk}"

    def _as_cmp(self):
        return (
            self.major,
            self.minor,
            RISKS[::-1].index(self.risk.lower()) + 1 if self.risk else 0,
        )

    @classmethod
    def mk(cls, rel: str) -> "Release":
        has_risk = rel.split("/")
        if len(has_risk) == 2:
            track, risk = has_risk
        else:
            track, risk = has_risk[0], None
        return cls(*map(int, track.split(".")), risk)

    def __eq__(self, other: "Release") -> bool:
        return self._as_cmp() == other._as_cmp()

    def __gt__(self, other: "Release") -> bool:
        return self._as_cmp() > other._as_cmp()

    def __lt__(self, other: "Release") -> bool:
        return self._as_cmp() < other._as_cmp()


@dataclass
class ChannelRange:
    """Determine if channel is within a channel range.

    Usage:
        assert "latest/edge" in ChannelRange("1.18", "1.25/stable") # latest/<anything> is ignored
        assert "1.24/edge" in ChannelRange("1.18", "1.25/stable")   # within bounds inclusively
        assert "1.24/edge" in ChannelRange("1.18", None)            # No upper bound
        assert "1.24/edge" in ChannelRange(None, "1.25/stable")     # No lower bound
        assert "1.24/edge" in ChannelRange(None, None)              # No bounds
    """

    _min: Optional[str] = None
    _max: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Mapping[str, Optional[str]]) -> "ChannelRange":
        range_def = d.get("channel-range", {})
        definitions = range_def.get("min"), range_def.get("max")
        assert all(isinstance(_, (str, type(None))) for _ in definitions)
        return cls(*definitions)

    @property
    def min(self) -> Optional[Release]:
        """Release object representing the minimum."""
        return self._min and Release.mk(self._min)

    @property
    def max(self) -> Optional[Release]:
        """Release object representing the maximum."""
        return self._max and Release.mk(self._max)

    def __contains__(self, other: Union[str, Release]) -> bool:
        """Implements comparitor."""
        if isinstance(other, str) and other.startswith("latest"):
            return True
        if not isinstance(other, Release):
            other = Release.mk(str(other))
        if self.min and other < self.min:
            return False
        if self.max and other > self.max:
            return False
        return True
