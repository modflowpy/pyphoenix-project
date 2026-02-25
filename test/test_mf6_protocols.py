"""Unit tests for dimension resolution protocols and mixins."""

from typing import Optional

from attrs import define, field

from flopy4.mf6.mixins import DimensionRegistryMixin

# Test fixtures: simple test components


@define
class MockDimensionProvider:
    """Mock component that provides dimensions."""

    nlay: int
    nrow: int
    ncol: int

    def get_dimensions(self) -> dict[str, int]:
        """Return dimensions including computed ones."""
        return {
            "nlay": self.nlay,
            "nrow": self.nrow,
            "ncol": self.ncol,
            "nodes": self.nlay * self.nrow * self.ncol,
            "ncpl": self.nrow * self.ncol,
        }


@define
class MockContainer(DimensionRegistryMixin):
    """Mock container that uses the dimension registry mixin."""

    provider: Optional[MockDimensionProvider] = None
    parent: Optional["MockContainer"] = None


@define
class MockContainerWithDict(DimensionRegistryMixin):
    """Mock container with dict of providers."""

    providers: dict[str, MockDimensionProvider] = field(factory=dict)
    parent: Optional["MockContainerWithDict"] = None


@define
class MockContainerWithList(DimensionRegistryMixin):
    """Mock container with list of providers."""

    providers: list[MockDimensionProvider] = field(factory=list)
    parent: Optional["MockContainerWithList"] = None


# Tests for DimensionRegistryMixin


class TestDimensionRegistryMixin:
    """Tests for DimensionRegistryMixin functionality."""

    def test_resolve_dimension_from_direct_child(self):
        """Test resolving dimension from a direct child provider."""
        provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
        container = MockContainer(provider=provider)

        assert container.resolve_dimension("nlay") == 3
        assert container.resolve_dimension("nrow") == 10
        assert container.resolve_dimension("ncol") == 20

    def test_resolve_computed_dimension(self):
        """Test resolving computed dimensions."""
        provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
        container = MockContainer(provider=provider)

        assert container.resolve_dimension("nodes") == 600
        assert container.resolve_dimension("ncpl") == 200

    def test_resolve_dimension_not_found(self):
        """Test resolving dimension that doesn't exist returns None."""
        provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
        container = MockContainer(provider=provider)

        assert container.resolve_dimension("nonexistent") is None

    def test_resolve_dimension_from_dict_child(self):
        """Test resolving dimension from children in a dict."""
        provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
        container = MockContainerWithDict(providers={"dis": provider})

        assert container.resolve_dimension("nlay") == 3
        assert container.resolve_dimension("nodes") == 600

    def test_resolve_dimension_from_list_child(self):
        """Test resolving dimension from children in a list."""
        provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
        container = MockContainerWithList(providers=[provider])

        assert container.resolve_dimension("nlay") == 3
        assert container.resolve_dimension("nodes") == 600

    def test_resolve_dimension_delegates_to_parent(self):
        """Test that dimension resolution delegates to parent when not found locally."""
        provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
        parent = MockContainer(provider=provider)
        child = MockContainer(parent=parent)

        # Child doesn't have a provider, so should delegate to parent
        assert child.resolve_dimension("nlay") == 3
        assert child.resolve_dimension("nodes") == 600

    def test_resolve_dimension_caching(self):
        """Test that resolved dimensions are cached."""
        provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
        container = MockContainer(provider=provider)

        # First resolution
        result1 = container.resolve_dimension("nlay")
        # Check cache was populated
        assert "nlay" in container._dimension_cache
        assert container._dimension_cache["nlay"] == 3

        # Second resolution should use cache
        result2 = container.resolve_dimension("nlay")
        assert result1 == result2 == 3

    def test_get_all_dimensions_direct_child(self):
        """Test getting all dimensions from direct child."""
        provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
        container = MockContainer(provider=provider)

        dims = container.get_all_dimensions()
        assert dims == {
            "nlay": 3,
            "nrow": 10,
            "ncol": 20,
            "nodes": 600,
            "ncpl": 200,
        }

    def test_get_all_dimensions_dict_children(self):
        """Test getting all dimensions from dict of children."""
        provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
        container = MockContainerWithDict(providers={"dis": provider})

        dims = container.get_all_dimensions()
        assert dims == {
            "nlay": 3,
            "nrow": 10,
            "ncol": 20,
            "nodes": 600,
            "ncpl": 200,
        }

    def test_get_all_dimensions_list_children(self):
        """Test getting all dimensions from list of children."""
        provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
        container = MockContainerWithList(providers=[provider])

        dims = container.get_all_dimensions()
        assert dims == {
            "nlay": 3,
            "nrow": 10,
            "ncol": 20,
            "nodes": 600,
            "ncpl": 200,
        }

    def test_get_all_dimensions_no_parent_delegation(self):
        """Test that get_all_dimensions does not delegate to parent."""
        provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
        parent = MockContainer(provider=provider)
        child = MockContainer(parent=parent)

        # Child has no provider, should return empty dict (not delegate to parent)
        dims = child.get_all_dimensions()
        assert dims == {}

    def test_get_all_dimensions_none_fields(self):
        """Test that None fields don't break dimension collection."""
        container = MockContainer(provider=None)

        dims = container.get_all_dimensions()
        assert dims == {}

    def test_hierarchical_resolution(self):
        """Test dimension resolution through multiple levels of hierarchy."""
        # Create a 3-level hierarchy
        provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
        grandparent = MockContainer(provider=provider)
        parent = MockContainer(parent=grandparent)
        child = MockContainer(parent=parent)

        # Child should be able to resolve from grandparent
        assert child.resolve_dimension("nlay") == 3
        assert child.resolve_dimension("nodes") == 600

    def test_parent_overrides_grandparent(self):
        """Test that parent dimensions override grandparent dimensions."""
        grandparent_provider = MockDimensionProvider(nlay=3, nrow=10, ncol=20)
        parent_provider = MockDimensionProvider(nlay=5, nrow=15, ncol=25)

        grandparent = MockContainer(provider=grandparent_provider)
        parent = MockContainer(provider=parent_provider, parent=grandparent)
        child = MockContainer(parent=parent)

        # Child should see parent's dimensions, not grandparent's
        assert child.resolve_dimension("nlay") == 5
        assert child.resolve_dimension("nodes") == 5 * 15 * 25


class TestDisDimensionProvider:
    """Tests for Dis.get_dimensions() implementation."""

    def test_dis_get_dimensions(self):
        """Test that Dis returns all expected dimensions."""
        from flopy4.mf6.gwf.dis import Dis

        dis = Dis(nlay=3, nrow=10, ncol=20)

        dims = dis.get_dimensions()

        assert dims == {
            "nlay": 3,
            "nrow": 10,
            "ncol": 20,
            "nodes": 600,
            "ncpl": 200,
        }

    def test_dis_computed_dimensions(self):
        """Test that Dis correctly computes nodes and ncpl."""
        from flopy4.mf6.gwf.dis import Dis

        dis = Dis(nlay=5, nrow=15, ncol=25)

        dims = dis.get_dimensions()

        assert dims["nodes"] == 5 * 15 * 25
        assert dims["ncpl"] == 15 * 25

    def test_dis_single_layer(self):
        """Test Dis dimensions with a single layer."""
        from flopy4.mf6.gwf.dis import Dis

        dis = Dis(nlay=1, nrow=10, ncol=10)

        dims = dis.get_dimensions()

        assert dims["nlay"] == 1
        assert dims["nodes"] == 100
        assert dims["ncpl"] == 100


class TestTdisDimensionProvider:
    """Tests for Tdis.get_dimensions() implementation."""

    def test_tdis_get_dimensions(self):
        """Test that Tdis returns nper dimension."""
        from flopy4.mf6.tdis import Tdis

        tdis = Tdis(nper=5)

        dims = tdis.get_dimensions()

        assert dims == {"nper": 5}

    def test_tdis_single_period(self):
        """Test Tdis with single stress period."""
        from flopy4.mf6.tdis import Tdis

        tdis = Tdis(nper=1)

        dims = tdis.get_dimensions()

        assert dims["nper"] == 1

    def test_tdis_many_periods(self):
        """Test Tdis with many stress periods."""
        from flopy4.mf6.tdis import Tdis

        tdis = Tdis(nper=100)

        dims = tdis.get_dimensions()

        assert dims["nper"] == 100
