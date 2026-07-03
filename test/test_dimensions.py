"""Tests for dimension resolution protocols and mixins."""

from typing import Optional

from attrs import define, field

from flopy4.dimensions import DimensionResolverMixin


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

def test_resolve_dimension_caching():
    """Test that resolved dimensions are cached."""
    provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
    container = MockContainer(provider=provider)

    # First resolution
    result1 = container.resolve_dims("nlay")
    # Check cache was populated
    assert "nlay" in container._dimension_cache
    assert container._dimension_cache["nlay"] == 3

    # Second resolution should use cache
    result2 = container.resolve_dims("nlay")
    assert result1 == result2 == {"nlay": 3}

def test_resolve_multiple_dimensions_uses_cache():
    """Test that cache is used when resolving multiple dimensions."""
    provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
    container = MockContainer(provider=provider)

    # First, resolve one dimension to populate cache
    container.resolve_dims("nlay")
    assert "nlay" in container._dimension_cache

    # Now resolve multiple including the cached one
    result = container.resolve_dims("nlay", "nrow")
    assert result == {"nlay": 3, "nrow": 10}
    # Both should now be cached
    assert "nlay" in container._dimension_cache
    assert "nrow" in container._dimension_cache

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
