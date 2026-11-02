import warnings
from unittest import TestCase

import jax.numpy as jp
import numpy as np
from mujoco.mjx._src import mesh
from mujoco.mjx._src.collision_types import ConvexInfo, GeomInfo

from lsy_drone_racing.envs.mjx_compat import _box_box


class TestBoxContacts(TestCase):
    """Check contact signs and float32 sentinel conversion without hiding warnings."""

    def test_separated_and_overlapping_boxes(self):
        """Separation stays finite and overlap retains negative penetration depth."""

        def box(x: float) -> ConvexInfo:
            result = mesh.box(
                GeomInfo(
                    pos=jp.array([x, 0, 0], dtype=jp.float32),
                    mat=jp.eye(3, dtype=jp.float32),
                    size=jp.full((1, 3), 0.1, dtype=jp.float32),
                )
            )
            return result.replace(vert=result.vert[0], face=result.face[0])

        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            separated, _, _ = _box_box(box(0), box(1))
            overlapping, _, _ = _box_box(box(0), box(0.15))
            self.assertTrue(np.all(np.isfinite(separated)))
            self.assertTrue(np.all(np.asarray(separated) > 0))
            self.assertLess(float(overlapping.min()), 0)
