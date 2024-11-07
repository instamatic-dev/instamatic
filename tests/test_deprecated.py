from __future__ import annotations

import pytest

from instamatic.utils.deprecated import VisibleDeprecationWarning, deprecated


def test_basic():
    @deprecated(since='2.0', alternative='bar')
    def foo() -> int:
        return 1

    with pytest.warns(
        VisibleDeprecationWarning,
        match='Function foo is deprecated since 2.0, use bar instead.',
    ):
        assert foo() == 1


def test_with_removed():
    @deprecated(since='2.0', alternative='bar', removed='3.0')
    def foo() -> int:
        return 1

    with pytest.warns(
        VisibleDeprecationWarning,
        match='Function foo is deprecated since 2.0, use bar instead. Will be removed in version 3.0.',
    ):
        assert foo() == 1


def test_on_member_method():
    class Foo:
        @deprecated(since='2.0', alternative='baz')
        def bar(self) -> int:
            return 1

    with pytest.warns(
        VisibleDeprecationWarning,
        match='Function bar is deprecated since 2.0, use baz instead.',
    ):
        foo = Foo()
        assert foo.bar() == 1


def test_on_class_method():
    class Foo:
        @classmethod
        @deprecated(since='2.0', alternative='baz')
        def bar(cls) -> int:
            return 1

    with pytest.warns(
        VisibleDeprecationWarning,
        match='Function bar is deprecated since 2.0, use baz instead.',
    ):
        foo = Foo()
        assert foo.bar() == 1
        assert Foo.bar() == 1


def test_on_static_method():
    class Foo:
        @staticmethod
        @deprecated(since='2.0', alternative='baz')
        def bar() -> int:
            return 1

    foo = Foo()

    with pytest.warns(
        VisibleDeprecationWarning,
        match='Function bar is deprecated since 2.0, use baz instead.',
    ):
        assert foo.bar() == 1
        assert Foo.bar() == 1
