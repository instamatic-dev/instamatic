from __future__ import annotations

import pickle

import numpy as np
import pytest
from pytest import TEST_DATA

from instamatic.camera.merlin_io import load_mib


@pytest.fixture
def raw_dataframe():
    # Directly from socket (`CameraMerlin.receive_data()`)
    with open(TEST_DATA / 'merlin_raw_dataframe.pickle', 'rb') as f:
        dataframe = pickle.load(f)
    return dataframe


@pytest.fixture
def expected_data():
    return np.load(TEST_DATA / 'merlin_expected_data.npy')


def test_load_mib(raw_dataframe, expected_data):
    dataframe = raw_dataframe[1:]

    array = load_mib(dataframe)

    array = array.squeeze()
    array = np.flipud(array)  # make it same orientation as QD Merlin software

    assert isinstance(array, np.ndarray)
    assert array.shape == expected_data.shape

    np.testing.assert_array_equal(array, expected_data)
