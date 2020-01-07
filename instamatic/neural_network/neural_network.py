import pickle
from pathlib import Path

import numpy as np

with open(Path(__file__).parent / 'weights-py3.p', 'rb') as p_file:
    weights = pickle.load(p_file)


def conv_layer(in_layer, weight, offset):
    first_layer = np.ones([(in_layer.shape[0] - 2) * (in_layer.shape[1] - 2), in_layer.shape[2], 3, 3])
    q = 0
    for n in range(in_layer.shape[0] - 2):
        for p in range(in_layer.shape[1] - 2):
            first_layer[q] = np.transpose(in_layer[n:n + 3, p:p + 3], [2, 0, 1])
            q += 1
    convoluted = np.tensordot(first_layer, weight, axes=(((2, 3, 1), (0, 1, 2))))
    convoluted_reshaped = convoluted.reshape([in_layer.shape[0] - 2, in_layer.shape[1] - 2, 64])
    convoluted_reshaped += offset

    return convoluted_reshaped


def relu(convoluted):
    convoluted[convoluted < 0] = 0
    return convoluted


def max_pooling(convoluted):
    pooled = np.ones((convoluted.shape[0] // 2, convoluted.shape[1] // 2, convoluted.shape[2]))
    for n in range(convoluted.shape[0] // 2):
        for p in range(convoluted.shape[1] // 2):
            pooled[n, p] = np.amax(convoluted[n * 2:n * 2 + 2, p * 2:p * 2 + 2], axis=(0, 1))
    return pooled


def logistic(x):
    return 1 / (1 + np.exp(-x))


def predict(image, weights=weights):
    convoluted1 = relu(conv_layer(image, weights[0], weights[1]))
    pooled1 = max_pooling(convoluted1)
    convoluted2 = relu(conv_layer(pooled1, weights[2], weights[3]))
    pooled2 = max_pooling(convoluted2)
    convoluted3 = relu(conv_layer(pooled2, weights[4], weights[5]))
    pooled3 = max_pooling(convoluted3)
    convoluted4 = relu(conv_layer(pooled3, weights[6], weights[7]))
    pooled4 = max_pooling(convoluted4)
    convoluted5 = relu(conv_layer(pooled4, weights[8], weights[9]))
    flattened = convoluted5.reshape((1, 1600))
    dense1 = relu(np.tensordot(flattened, weights[10], axes=(1, 0)) + weights[11])
    dense2 = relu(np.tensordot(dense1, weights[12], axes=(1, 0)) + weights[13])
    dense3 = np.tensordot(dense2, weights[14], axes=(1, 0)) + weights[15]
    return logistic(dense3)[0][0]
