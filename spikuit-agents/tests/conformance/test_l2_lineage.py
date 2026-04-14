"""Re-export L2 lineage conformance tests for the local pytest run."""

import pytest

from amkb.conformance.test_l2_lineage import *  # noqa: F401,F403
from amkb.conformance.test_l2_lineage import (  # noqa: F401
    test_L2_merge_02_kind_mismatch_rejected as _orig_merge_02,
)


@pytest.mark.skip(
    reason="Spikuit v0.7.1 does not support KIND_CATEGORY; merge kind-mismatch "
    "validation tested upstream via DictStore.",
)
def test_L2_merge_02_kind_mismatch_rejected(store, actor):  # type: ignore[no-redef]
    pass
