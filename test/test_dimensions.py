"""Tests for dimension resolution protocols and mixins."""

from typing import Optional

import pytest
from attrs import define, field

from flopy4.dimensions import DerivedDim, DimensionResolverMixin


@define
class MockDimensionProvider:
    """Mock component that provides dimensions."""

    nlay: int
    nrow: int
    ncol: int

    def get_dims(self) -> dict[str, int]:
        """Return dimensions including computed ones."""
        return {
            "nlay": self.nlay,
            "nrow": self.nrow,
            "ncol": self.ncol,
            "nodes": self.nlay * self.nrow * self.ncol,
            "ncpl": self.nrow * self.ncol,
        }


@define
class MockContainer(DimensionResolverMixin):
    """Mock container that uses the dimension registry mixin."""

    provider: Optional[MockDimensionProvider] = None


@define
class MockContainerWithDict(DimensionResolverMixin):
    """Mock container with dict of providers."""

    providers: dict[str, MockDimensionProvider] = field(factory=dict)


@define
class MockContainerWithList(DimensionResolverMixin):
    """Mock container with list of providers."""

    providers: list[MockDimensionProvider] = field(factory=list)


def test_resolve_dimension_from_direct_child():
    """Test resolving dimension from a direct child provider."""
    provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
    container = MockContainer(provider=provider)

    assert container.resolve_dims("nlay") == {"nlay": 3}
    assert container.resolve_dims("nrow") == {"nrow": 10}
    assert container.resolve_dims("ncol") == {"ncol": 20}


def test_resolve_computed_dimension():
    """Test resolving computed dimensions."""
    provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
    container = MockContainer(provider=provider)

    assert container.resolve_dims("nodes") == {"nodes": 600}
    assert container.resolve_dims("ncpl") == {"ncpl": 200}


def test_resolve_dimension_not_found():
    """Test resolving dimension that doesn't exist returns None."""
    provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
    container = MockContainer(provider=provider)

    assert container.resolve_dims("nonexistent") == {}


def test_resolve_dimension_from_dict_child():
    """Test resolving dimension from children in a dict."""
    provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
    container = MockContainerWithDict(providers={"dis": provider})

    assert container.resolve_dims("nlay") == {"nlay": 3}
    assert container.resolve_dims("nodes") == {"nodes": 600}


def test_resolve_dimension_from_list_child():
    """Test resolving dimension from children in a list."""
    provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
    container = MockContainerWithList(providers=[provider])

    assert container.resolve_dims("nlay") == {"nlay": 3}
    assert container.resolve_dims("nodes") == {"nodes": 600}


def test_resolve_multiple_dimensions():
    """Test resolving multiple dimensions at once."""
    provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
    container = MockContainer(provider=provider)

    result = container.resolve_dims("nlay", "nrow", "ncol")
    assert result == {"nlay": 3, "nrow": 10, "ncol": 20}


def test_resolve_multiple_with_computed():
    """Test resolving multiple dimensions including computed ones."""
    provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
    container = MockContainer(provider=provider)

    result = container.resolve_dims("nlay", "nodes", "ncpl")
    assert result == {"nlay": 3, "nodes": 600, "ncpl": 200}


def test_resolve_multiple_computed_dimensions():
    """Test resolving only computed dimensions."""
    provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
    container = MockContainer(provider=provider)

    result = container.resolve_dims("nodes", "ncpl")
    assert result == {"nodes": 600, "ncpl": 200}


def test_resolve_multiple_mix_valid_invalid():
    """Test resolving mix of valid and invalid dimensions."""
    provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
    container = MockContainer(provider=provider)

    # Request mix of valid and nonexistent dimensions
    result = container.resolve_dims("nlay", "nonexistent", "nrow")
    # Should only return the valid ones
    assert result == {"nlay": 3, "nrow": 10}
    assert "nonexistent" not in result


def test_resolve_multiple_all_invalid():
    """Test resolving multiple dimensions that all don't exist."""
    provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
    container = MockContainer(provider=provider)

    result = container.resolve_dims("invalid1", "invalid2", "invalid3")
    assert result == {}


def test_resolve_duplicate_dimensions():
    """Test resolving with duplicate dimension names."""
    provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
    container = MockContainer(provider=provider)

    # Request same dimension multiple times
    result = container.resolve_dims("nlay", "nlay", "nlay")
    # Should handle duplicates gracefully and return it once
    assert result == {"nlay": 3}


def test_resolve_dimension_sees_provider_changes():
    """Test that resolution isn't cached: a provider's dimensions can change."""
    provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
    container = MockContainer(provider=provider)

    assert container.resolve_dims("nlay") == {"nlay": 3}
    provider.nlay = 4
    assert container.resolve_dims("nlay") == {"nlay": 4}


def test_get_all_dimensions_direct_child():
    """Test getting all dimensions from direct child."""
    provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
    container = MockContainer(provider=provider)

    dims = container.resolve_dims()
    assert dims == {
        "nlay": 3,
        "nrow": 10,
        "ncol": 20,
        "nodes": 600,
        "ncpl": 200,
    }


def test_get_all_dimensions_dict_children():
    """Test getting all dimensions from dict of children."""
    provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
    container = MockContainerWithDict(providers={"dis": provider})

    dims = container.resolve_dims()
    assert dims == {
        "nlay": 3,
        "nrow": 10,
        "ncol": 20,
        "nodes": 600,
        "ncpl": 200,
    }


def test_get_all_dimensions_list_children():
    """Test getting all dimensions from list of children."""
    provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
    container = MockContainerWithList(providers=[provider])

    dims = container.resolve_dims()
    assert dims == {
        "nlay": 3,
        "nrow": 10,
        "ncol": 20,
        "nodes": 600,
        "ncpl": 200,
    }


def test_get_all_dimensions_none_fields():
    """Test that None fields don't break dimension collection."""
    container = MockContainer(provider=None)

    dims = container.resolve_dims()
    assert dims == {}


@pytest.mark.parametrize(
    "expr,expected",
    [
        ("3", 3),
        ("nrow * ncol", 200),
        ("nlay * nrow * ncol", 600),
        ("(nja - nodes) / 2", 3),
    ],
)
def test_derived_dim_expr(expr, expected):
    @define
    class Dims:
        nlay: int = 3
        nrow: int = 10
        ncol: int = 20
        nja: int = 10
        nodes: int = 4
        derived = DerivedDim(expr)

    assert Dims().derived == expected


@pytest.mark.parametrize("expr", ["nrow ** 2", "1.5", "nrow *"])
def test_derived_dim_rejects(expr):
    with pytest.raises(ValueError):
        DerivedDim(expr)


def test_derived_dim():
    @define
    class Grid:
        nrow: Optional[int] = None
        ncol: Optional[int] = None
        ncpl = DerivedDim("nrow * ncol")

    assert Grid().ncpl is None
    grid = Grid(nrow=2, ncol=3)
    assert grid.ncpl == 6
    with pytest.raises(AttributeError, match="derived"):
        grid.ncpl = 7
