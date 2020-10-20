"""Provides interface to querying snap revisions and grabbing version information"""


class SnapModel:
    def __init__(self, track):
        """
        track: Snap channel track to query
        """
        self.track = track
        self.snap = None
