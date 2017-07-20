#!/usr/bin/env python

from __future__ import print_function
import numpy as np
import pandas as pd
import os

__version__ = "2016-11-09"
__author__ = "Stef Smeets"
__email__ = "stef.smeets@mmk.su.se"


def kendalltau(x, y, initial_lexsort=True):
    """
    Calculates Kendall's tau, a correlation measure for ordinal data.
    Kendall's tau is a measure of the correspondence between two rankings.
    Values close to 1 indicate strong agreement, values close to -1 indicate
    strong disagreement.  This is the tau-b version of Kendall's tau which
    accounts for ties.

    Adapted from SciPy 0.15.1 stats module:
    https://github.com/scipy/scipy/blob/v0.15.1/scipy/stats/stats.py#L2827
    """

    x = np.asarray(x).ravel()
    y = np.asarray(y).ravel()

    if not x.size or not y.size:
        return (np.nan, np.nan)  # Return NaN if arrays are empty

    n = np.int64(len(x))
    temp = list(range(n))  # support structure used by mergesort
    # this closure recursively sorts sections of perm[] by comparing
    # elements of y[perm[]] using temp[] as support
    # returns the number of swaps required by an equivalent bubble sort

    def mergesort(offs, length):
        exchcnt = 0
        if length == 1:
            return 0
        if length == 2:
            if y[perm[offs]] <= y[perm[offs+1]]:
                return 0
            t = perm[offs]
            perm[offs] = perm[offs+1]
            perm[offs+1] = t
            return 1
        length0 = length // 2
        length1 = length - length0
        middle = offs + length0
        exchcnt += mergesort(offs, length0)
        exchcnt += mergesort(middle, length1)
        if y[perm[middle - 1]] < y[perm[middle]]:
            return exchcnt
        # merging
        i = j = k = 0
        while j < length0 or k < length1:
            if k >= length1 or (j < length0 and y[perm[offs + j]] <=
                                                y[perm[middle + k]]):
                temp[i] = perm[offs + j]
                d = i - j
                j += 1
            else:
                temp[i] = perm[middle + k]
                d = (offs + i) - (middle + k)
                k += 1
            if d > 0:
                exchcnt += d
            i += 1
        perm[offs:offs+length] = temp[0:length]
        return exchcnt

    # initial sort on values of x and, if tied, on values of y
    if initial_lexsort:
        # sort implemented as mergesort, worst case: O(n log(n))
        perm = np.lexsort((y, x))
    else:
        # sort implemented as quicksort, 30% faster but with worst case: O(n^2)
        perm = list(range(n))
        perm.sort(key=lambda a: (x[a], y[a]))

    # compute joint ties
    first = 0
    t = 0
    for i in xrange(1, n):
        if x[perm[first]] != x[perm[i]] or y[perm[first]] != y[perm[i]]:
            t += ((i - first) * (i - first - 1)) // 2
            first = i
    t += ((n - first) * (n - first - 1)) // 2

    # compute ties in x
    first = 0
    u = 0
    for i in xrange(1,n):
        if x[perm[first]] != x[perm[i]]:
            u += ((i - first) * (i - first - 1)) // 2
            first = i
    u += ((n - first) * (n - first - 1)) // 2

    # count exchanges
    exchanges = mergesort(0, n)
    # compute ties in y after mergesort with counting
    first = 0
    v = 0
    for i in xrange(1,n):
        if y[perm[first]] != y[perm[i]]:
            v += ((i - first) * (i - first - 1)) // 2
            first = i
    v += ((n - first) * (n - first - 1)) // 2

    tot = (n * (n - 1)) // 2
    if tot == u or tot == v:
        return (np.nan, np.nan)    # Special case for all ties in both ranks

    # Prevent overflow; equal to np.sqrt((tot - u) * (tot - v))
    denom = np.exp(0.5 * (np.log(tot - u) + np.log(tot - v)))
    tau = ((tot - (v + u - t)) - 2.0 * exchanges) / denom

    return tau


def pearsonr(x, y):
    """Pearson correlation coefficient"""
    assert len(x) == len(y)
    assert len(x) > 0

    xdiff = x - np.mean(x)
    ydiff = y - np.mean(y)

    return np.sum(xdiff * ydiff) / (np.sum(xdiff * xdiff) * np.sum(ydiff * ydiff))**0.5


def serialmerge(df, kind="mean", digitize_threshold=None, key="val", verbose=False):
    """Implementation based on SerialRank algorithm
    http://arxiv.org/abs/1406.5370
    http://www.di.ens.fr/~fogel/SerialRank/tutorial.html"""

    if kind == "max":
        merged = df.groupby(df.index).max()
    elif kind == "mean":
        merged = df.groupby(df.index).mean()
    elif kind == "median":
        merged = df.groupby(df.index).median()
    elif kind == "first":
        merged = df.groupby(df.index).first()
    else:
        raise ValueError("serialmerge - kind =", kind)

    merged["Nobs"] = df.groupby(df.index).size()

    # setup
    refs = df.index.drop_duplicates()          # get unique set of indices
    C = np.eye(refs.size, dtype=np.float32)    # initializing the comparison matrix
    counter = np.eye(refs.size)                # matrix to keep track of number of observations

    # Prepare comparison matrix
    for frame, subdf in df.groupby("frame"):
        subdf = subdf.groupby(subdf.index)[key].first()      # Check for duplicate reflections from a single frame
        tri = np.tri(subdf.size, dtype=int)                  # We know that an ordered ranking produces a triangular matrix
                                                             # So we can make use of that here (for speed reasons)
        idx = [refs.get_loc(ref) for ref in subdf.sort_values().index]
        ix, jx = np.meshgrid(idx, idx)                       # Generate indices for the triangular matrix
        C[ix,jx] += tri                                      # The C matrix is mirrored around the diagonal
        C[ix,jx] -= (1-tri)
        counter[ix,jx] += 1                                  # Keep track of how many comparisons are made
    
    np.divide(C, counter, out=C, where=counter!=0)  # Normalize to number of observations
                                                    # use np.divide to avoid ZeroDivideWarning
    if digitize_threshold:                # digitize to only give values of -1, 0, or 1
        bins = (-digitize_threshold, digitize_threshold)
        C = np.digitize(C, bins)

    # Calculate similarity matrix Sim
    Sim = np.dot(C, C.T)
    # subtract minimum of S in order to keep S non negative
    Sim = Sim - Sim.min()

    # Compute the Laplacian matrix and its second eigenvector
    L = np.diag(np.sum(Sim,1)) - Sim
    D, V = np.linalg.eigh(L)
    argD = np.argsort(D)
    D = D[argD]
    V = V[:,argD]
    fiedler = V[:,1]

    # get new index
    retrievedPerm = np.argsort(fiedler)
    index = pd.Index(refs[retrievedPerm])

    # update dataframe
    merged.sort_values(key, ascending=False, inplace=True)    # sort the values by intensity
    merged.index = index                                      # overwrite index with new ranking

    if verbose:
        print("Array shape: {}".format(C.shape))
        print("Memory usage: {} MB".format(C.nbytes / (1024*1024)))
        nfilled = np.sum(counter!=0)
        print("Completeness: {}/{}={:.2%}".format(nfilled, C.size, float(nfilled)/C.size))
        print("Reflection redundancy: {:.2f}".format(float(len(df)) / len(merged)))
        print("Pair redundancy: {:.3f}".format(((counter.sum() - refs.size)) / ((nfilled - refs.size))))
        # print("R(serialmerge): {:.3f}".format(np.sum((np.ceil(np.abs(C)) - np.abs(C))**2) / nfilled))

    return merged


def get_files_in_dir(ext, drc="."):
    """Grab all files with extension 'ext' in directory 'drc'"""
    for fn in os.listdir(drc):
        if fn.endswith(ext):
            yield os.path.join(drc, fn)


def load_hkl_files(fns=[]):
    """Load hkl files using pandas, and setup dataframe"""
    for i, fn in enumerate(fns):
        try:
            dfn = pd.read_table(fn, sep="\s*", engine="python", index_col=[0,1,2], header=None, names="h k l val sigma".split())
        except Exception:
            print("Problem reading file {} {}".format(i, fn))
            continue
        dfn.index = pd.Index(dfn.index)
        
        dfn["frame"] = i
    
        try:
            dfx = dfx.append(dfn)
        except NameError:
            dfx = dfn
    
    return dfx


def serialmerge_fns(fns, remove_0_reflections=True, fout="merged.hkl", verbose=False):
    dfx = load_hkl_files(fns)

    print("Observed reflections: {}".format(len(dfx)))

    if remove_0_reflections:
        print("Ignore {} reflections with I=0".format(np.sum(dfx["val"] == 0)))
        sel = dfx["val"] > 0
        dfx = dfx[sel]
        print("Remaining reflections: {}".format(len(dfx)))

    print("Unique reflections:", len(dfx.groupby(dfx.index)))
    print("Number of frames:", max(dfx["frame"]+1))

    m = serialmerge(dfx, verbose=verbose)
    
    merged = dfx.groupby(dfx.index).mean()
    
    # calculate kendall tau to see whether order should be reversed
    t = kendalltau(np.argsort(m["val"]), np.argsort(merged.loc[m.index, "val"]))
    if t < 0:
        m.index = reversed(m.index)
        t = kendalltau(np.argsort(m["val"]), np.argsort(merged.loc[m.index, "val"]))

    print("Kendall's tau: {:.3f}".format(t))
    
    if verbose:
        print("\nMost common reflections:")
        print(m.sort_values("Nobs", ascending=False)["Nobs"][0:10])
    
    fout = open(fout, "w")
    for i, row in m.iterrows():
        h,k,l = i
        print("{:4d}{:4d}{:4d}{:8.1f}{:8.1f}".format(h, k, l, row.val, 1.0), file=fout)
    print("\n >> Wrote {} reflections to file {}".format(len(m), fout.name))


def serialmerge_entry():
    import argparse

    description = """
SerialMerge: A program to merge HKL files using rank aggregation

    usage: "serialmerge arg1 [arg2 ...]"

arguments can be a filename (i.e. data.hkl), a directory, or any combination.
In case a directory is given, SerialMerge will load all the hkl files in that directory.
hkl files should be in free format (space separated) with 5 columns: h k l I/F esd"""

    epilog = 'Updated: {}'.format(__version__)

    parser = argparse.ArgumentParser(description=description,
                                     epilog=epilog,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)

    parser = argparse.ArgumentParser()

    parser.add_argument("args",
                        type=str, metavar="FN", nargs='*',
                        help="File or directory name")

    parser.set_defaults()

    options = parser.parse_args()
    args = options.args

    fns = []
    for fn in args:
        if os.path.isdir(fn):
            fns.extend(list(get_files_in_dir(".hkl", drc=fn)))
        else:
            fns.append(fn)

    if not fns:
        print(description)
        exit()

    serialmerge_fns(fns)




if __name__ == '__main__':
    serialmerge_entry()
