"""Deprecation decorator."""

from __future__ import annotations


class VisibleDeprecationWarning(UserWarning):
    """Numpy-inspired deprecation warning which will be shown by default.

    The default `DeprecationWarning` does not show by default.
    """


def deprecated(since: str, alternative: str, removed: str = None):
    """Mark a function as deprecated, printing a warning whenever it is used.

    Parameters
    ----------
    since : str
        Version that the deprecation was introduced
    alternative : str
        Name of alternative function
    removed : str, optional
        Planned version to remove the function

    Notes
    -----
    Does not work on entire classes, but works on member methods, classmethods and staticmethods.
    If used in a chain with classmethod/staticmethod, place the deprecation decorator underneath those
    """
    import warnings
    from functools import wraps

    def decorator(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            msg = f'Function {func.__name__} is deprecated since {since}, use {alternative} instead.'
            if removed is not None:
                msg += f' Will be removed in version {removed}.'
            warnings.warn(msg, VisibleDeprecationWarning, stacklevel=2)
            return func(*args, **kwargs)

        return wrapped

    return decorator
