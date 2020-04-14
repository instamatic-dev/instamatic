def test_get_image(ctrl):
    bin1 = 1
    bin2 = 2
    bin4 = 4

    img, h = ctrl.get_image(binsize=bin1)
    x1, y1 = img.shape

    img, h = ctrl.get_image(binsize=bin2)
    x2, y2 = img.shape

    img, h = ctrl.get_image(binsize=bin4)
    x4, y4 = img.shape

    assert x1 == bin2 * x2
    assert y1 == bin2 * y2
    assert x1 == bin4 * x4
    assert y1 == bin4 * y4


def test_functions(ctrl):
    dims = ctrl.cam.getImageDimensions()
    assert isinstance(dims, tuple)
    assert len(dims) == 2
