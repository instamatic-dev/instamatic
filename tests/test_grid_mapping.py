from __future__ import annotations


def test_grid_mapping(ctrl):
    gm = ctrl.grid_montage()
    gm.setup(3, 3)
    gm.start()

    montage = gm.to_montage()
