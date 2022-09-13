import pytest
import cilib.version as version


@pytest.mark.parametrize(
    "a, b",
    [
        ("2.15/edge", "2.14/EDGE"),
        ("0.15/stable", "0.15/candidate"),
        ("0.15/candidate", "0.15/beta"),
        ("0.15/beta", "0.15/edge"),
        ("0.15/edge", "0.15"),
    ],
)
def test_release_comparitors(a, b):
    a, b = map(version.Release.mk, (a, b))
    assert a > b
    assert b < a
    assert a != b


@pytest.mark.parametrize(
    "channel",
    [
        "2.15/edge",
        "0.15/stable",
        "0.15/candidate",
        "0.15/beta",
    ],
)
def test_channel_comparitor(channel):
    # latest/<anything> is excluded from channel range comparison
    assert "latest/banana" in version.ChannelRange("0.15/edge", "0.15/edge")

    # all channels are excluded from channel range comparison without min or max
    assert channel in version.ChannelRange(None, None)

    # all channel params are greater than 0.14 and 0.14/stable
    assert channel in version.ChannelRange("0.14", None)
    assert channel in version.ChannelRange("0.14/stable", None)

    # all channel params are less than 2.15/edge and 2.16
    assert channel in version.ChannelRange(None, "2.15/edge")
    assert channel in version.ChannelRange(None, "2.16")

    # all channel params fall outside the range starting at 2.15/candidate
    assert channel not in version.ChannelRange("2.15/candidate", None)

    # all channel params fall outside the range ending at 0.15/edge
    assert channel not in version.ChannelRange(None, "0.15/edge")
