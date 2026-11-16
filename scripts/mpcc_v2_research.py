# ruff: noqa: ANN001, ANN201
"""Local research adapter, never selected by production config."""

from lsy_drone_racing.control import mpcc_v2_core as core


def controller_factory(settings, geometry):
    """Bind validated complete records without mutating module globals."""
    values, shape = core.validated_settings(settings, geometry)

    class ResearchMPCCV2(core.MPCCV2Core):
        def __init__(self, obs, info, config):
            super().__init__(obs, info, config, settings=values, geometry=shape)

    return ResearchMPCCV2
