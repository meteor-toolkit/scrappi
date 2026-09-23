"""Pytest configuration shared across every scrappi test suite.

Force a non-interactive matplotlib backend before any test (or scrappi module)
imports ``pyplot``, so the tests that exercise plotting code
(:py:meth:`scrappi.product.ProductItem.plot_geometry` /
:py:meth:`~scrappi.product.ProductItemSet.plot_geometries`) never open a window
or block on ``plt.show()`` -- locally or in the GitLab pipeline.
"""

import matplotlib

matplotlib.use("Agg", force=True)
