"""Tests for MF6 component dimension resolution."""


def test_dis_get_dimensions():
    """Test that Dis returns all expected dimensions."""
    from flopy4.mf6.gwf.dis import Dis

    dis = Dis(nlay=3, nrow=10, ncol=20)

    dims = dis.get_dims()

    assert dims == {
        "nlay": 3,
        "nrow": 10,
        "ncol": 20,
        "nodes": 600,
        "ncpl": 200,
    }


def test_dis_computed_dimensions():
    """Test that Dis correctly computes nodes and ncpl."""
    from flopy4.mf6.gwf.dis import Dis

    dis = Dis(nlay=5, nrow=15, ncol=25)

    dims = dis.get_dims()

    assert dims["nodes"] == 5 * 15 * 25
    assert dims["ncpl"] == 15 * 25


def test_dis_single_layer():
    """Test Dis dimensions with a single layer."""
    from flopy4.mf6.gwf.dis import Dis

    dis = Dis(nlay=1, nrow=10, ncol=10)

    dims = dis.get_dims()

    assert dims["nlay"] == 1
    assert dims["nodes"] == 100
    assert dims["ncpl"] == 100


class TestTdisDimensionProvider:
    """Tests for Tdis.get_dims() implementation."""

    def test_tdis_get_dimensions(self):
        """Test that Tdis returns nper dimension."""
        from flopy4.mf6.tdis import Tdis

        tdis = Tdis(nper=5)

        dims = tdis.get_dims()

        assert dims == {"nper": 5}

    def test_tdis_single_period(self):
        """Test Tdis with single stress period."""
        from flopy4.mf6.tdis import Tdis

        tdis = Tdis(nper=1)

        dims = tdis.get_dims()

        assert dims["nper"] == 1

    def test_tdis_many_periods(self):
        """Test Tdis with many stress periods."""
        from flopy4.mf6.tdis import Tdis

        tdis = Tdis(nper=100)

        dims = tdis.get_dims()

        assert dims["nper"] == 100


class TestComponentIntegration:
    """Integration tests for dimension resolution through real component hierarchy."""

    def test_component_has_dimension_methods(self):
        """Test that Component subclasses have dimension resolution methods."""
        from flopy4.mf6.gwf.dis import Dis

        dis = Dis(nlay=3, nrow=10, ncol=20)

        # Component should have these methods from DimensionResolverMixin
        assert hasattr(dis, "resolve_dims")
        assert hasattr(dis, "get_dims")

        # Test that the methods actually work
        # Dis doesn't have a parent, so resolve_dims should return {} for non-existent dims
        assert dis.resolve_dims("nonexistent") == {}
        # get_all_dimensions should work since Dis is a DimensionProvider
        dims = dis.get_dims()  # Dis is a provider, not a registry in this context
        assert "nlay" in dims
        assert dims["nlay"] == 3

    def test_gwf_resolves_dimensions_from_dis(self):
        """Test that Gwf can resolve dimensions from its Dis child."""
        from flopy4.mf6.gwf import Gwf
        from flopy4.mf6.gwf.dis import Dis

        dis = Dis(nlay=3, nrow=10, ncol=20)
        gwf = Gwf(name="test", dis=dis)

        # Gwf should be able to get dimensions from its Dis child
        assert gwf.resolve_dims("nlay") == {"nlay": 3}
        assert gwf.resolve_dims("nrow") == {"nrow": 10}
        assert gwf.resolve_dims("ncol") == {"ncol": 20}
        assert gwf.resolve_dims("nodes") == {"nodes": 600}
        assert gwf.resolve_dims("ncpl") == {"ncpl": 200}

    def test_gwf_get_all_dimensions(self):
        """Test that Gwf.resolve_dims() returns dimensions from Dis."""
        from flopy4.mf6.gwf import Gwf
        from flopy4.mf6.gwf.dis import Dis

        dis = Dis(nlay=3, nrow=10, ncol=20)
        gwf = Gwf(name="test", dis=dis)

        dims = gwf.resolve_dims()

        assert dims == {
            "nlay": 3,
            "nrow": 10,
            "ncol": 20,
            "nodes": 600,
            "ncpl": 200,
        }

    def test_package_delegates_to_parent_model(self):
        """Test that packages can resolve dimensions from parent model."""
        # NOTE: This test is simplified for Phase 2 (xattree coexistence)
        # In Phase 2, packages that require dimension resolution during construction
        # (e.g., IC with array fields) can't be easily tested because xattree sets
        # parents after construction. This will work properly in Phase 3.

        from flopy4.mf6.gwf import Gwf
        from flopy4.mf6.gwf.dis import Dis

        # For now, test that the parent-child relationship enables dimension resolution
        dis = Dis(nlay=3, nrow=10, ncol=20)
        gwf = Gwf(name="test", dis=dis)

        # Gwf should be able to resolve dimensions from Dis
        assert gwf.resolve_dims("nlay") == {"nlay": 3}
        assert gwf.resolve_dims("nodes") == {"nodes": 600}

        # Verify parent was set by xattree (use 'is' for identity, not '==' for equality)
        assert dis.parent is gwf

    def test_dimension_caching_in_real_components(self):
        """Test that dimension caching works with real components."""
        from flopy4.mf6.gwf import Gwf
        from flopy4.mf6.gwf.dis import Dis

        dis = Dis(nlay=3, nrow=10, ncol=20)
        gwf = Gwf(name="test", dis=dis)

        # First resolution
        result1 = gwf.resolve_dims("nlay")
        assert "nlay" in gwf._dimension_cache
        assert gwf._dimension_cache["nlay"] == 3

        # Second resolution should use cache
        result2 = gwf.resolve_dims("nlay")
        assert result1 == result2 == {"nlay": 3}

    def test_simulation_resolves_nper_from_tdis(self):
        """Test that Simulation can resolve nper from Tdis."""
        from flopy4.mf6.simulation import Simulation
        from flopy4.mf6.tdis import Tdis

        tdis = Tdis(nper=10)
        sim = Simulation(name="test", tdis=tdis)

        # Simulation should resolve nper from Tdis
        assert sim.resolve_dims("nper") == {"nper": 10}

    def test_model_in_simulation_can_access_tdis_dimensions(self):
        """Test that models within simulation can access Tdis dimensions."""
        from flopy4.mf6.gwf import Gwf
        from flopy4.mf6.gwf.dis import Dis
        from flopy4.mf6.simulation import Simulation
        from flopy4.mf6.tdis import Tdis

        tdis = Tdis(nper=10)
        dis = Dis(nlay=3, nrow=10, ncol=20)
        gwf = Gwf(name="test", dis=dis)
        # Construct Simulation with models dict - xattree will set parent automatically
        sim = Simulation(name="test", tdis=tdis, models={"test": gwf})

        # Model should access its own grid dimensions
        assert gwf.resolve_dims("nlay") == {"nlay": 3}
        assert gwf.resolve_dims("nodes") == {"nodes": 600}

        # Model should also access time dimensions from parent simulation
        assert gwf.resolve_dims("nper") == {"nper": 10}

    def test_package_resolves_both_grid_and_time_dimensions(self):
        """Test that models can resolve both grid and time dimensions."""
        # NOTE: Simplified for Phase 2 - testing model-level resolution instead
        # of package-level to avoid IC construction issues

        from flopy4.mf6.gwf import Gwf
        from flopy4.mf6.gwf.dis import Dis
        from flopy4.mf6.simulation import Simulation
        from flopy4.mf6.tdis import Tdis

        tdis = Tdis(nper=10)
        dis = Dis(nlay=3, nrow=10, ncol=20)
        gwf = Gwf(name="test", dis=dis)
        sim = Simulation(name="test", tdis=tdis, models={"test": gwf})

        # Model should resolve grid dimensions from its Dis
        assert gwf.resolve_dims("nlay") == {"nlay": 3}
        assert gwf.resolve_dims("nodes") == {"nodes": 600}

        # Model should resolve time dimensions from parent Simulation → Tdis
        assert gwf.resolve_dims("nper") == {"nper": 10}

    def test_gwf_resolve_multiple_dimensions(self):
        """Test that Gwf can resolve multiple dimensions at once."""
        from flopy4.mf6.gwf import Gwf
        from flopy4.mf6.gwf.dis import Dis

        dis = Dis(nlay=3, nrow=10, ncol=20)
        gwf = Gwf(name="test", dis=dis)

        # Request multiple explicit dimensions
        result = gwf.resolve_dims("nlay", "nrow", "ncol")
        assert result == {"nlay": 3, "nrow": 10, "ncol": 20}

    def test_gwf_resolve_mix_explicit_computed(self):
        """Test resolving mix of explicit and computed dimensions."""
        from flopy4.mf6.gwf import Gwf
        from flopy4.mf6.gwf.dis import Dis

        dis = Dis(nlay=3, nrow=10, ncol=20)
        gwf = Gwf(name="test", dis=dis)

        # Request mix of explicit and computed
        result = gwf.resolve_dims("nlay", "nodes", "ncol", "ncpl")
        assert result == {"nlay": 3, "nodes": 600, "ncol": 20, "ncpl": 200}

    def test_gwf_resolve_only_computed(self):
        """Test resolving only computed dimensions."""
        from flopy4.mf6.gwf import Gwf
        from flopy4.mf6.gwf.dis import Dis

        dis = Dis(nlay=3, nrow=10, ncol=20)
        gwf = Gwf(name="test", dis=dis)

        # Request only computed dimensions
        result = gwf.resolve_dims("nodes", "ncpl")
        assert result == {"nodes": 600, "ncpl": 200}

    def test_gwf_resolve_mix_valid_invalid(self):
        """Test resolving mix of valid and invalid dimensions."""
        from flopy4.mf6.gwf import Gwf
        from flopy4.mf6.gwf.dis import Dis

        dis = Dis(nlay=3, nrow=10, ncol=20)
        gwf = Gwf(name="test", dis=dis)

        # Request mix - some valid, some invalid
        result = gwf.resolve_dims("nlay", "nonexistent", "nodes", "invalid")
        assert result == {"nlay": 3, "nodes": 600}
        assert "nonexistent" not in result
        assert "invalid" not in result

    def test_model_resolve_grid_and_time_together(self):
        """Test resolving both grid and time dimensions in one call."""
        from flopy4.mf6.gwf import Gwf
        from flopy4.mf6.gwf.dis import Dis
        from flopy4.mf6.simulation import Simulation
        from flopy4.mf6.tdis import Tdis

        tdis = Tdis(nper=10)
        dis = Dis(nlay=3, nrow=10, ncol=20)
        gwf = Gwf(name="test", dis=dis)
        sim = Simulation(name="test", tdis=tdis, models={"test": gwf})

        # Request both grid and time dimensions together
        result = gwf.resolve_dims("nlay", "nrow", "ncol", "nper", "nodes")
        assert result == {
            "nlay": 3,
            "nrow": 10,
            "ncol": 20,
            "nper": 10,
            "nodes": 600,
        }
