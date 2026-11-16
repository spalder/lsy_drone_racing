"""Fixed baseline facade for MPCC v2; research records use a separate adapter."""

from lsy_drone_racing.control import mpcc_v2_core as core


class AttitudeMPCCV2(core.MPCCV2Core):
    """Use embedded baseline settings and reject research TOML overrides."""
