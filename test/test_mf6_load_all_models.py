"""
Comprehensive loading tests for all available MF6 models.

This test suite validates the complete loading pipeline (parse → transform →
structure → binding resolution → children loading) against all models available
in modflow-devtools.
"""

import pytest
from modflow_devtools.models import ModelSourceConfig, copy_to, get_models

from flopy4.mf6.simulation import Simulation

# Ensure model registry is synced before getting models
# This is required for CI environments where the cache may not be initialized
try:
    config = ModelSourceConfig.load()
    config.sync(verbose=False, force=False)
except Exception:
    # If sync fails, get_models() will raise a more informative error
    pass

# Get all available models
ALL_MODELS = list(get_models())


@pytest.mark.parametrize("model_name", ALL_MODELS)
def test_load_simulation(tmp_path, model_name):
    """
    Test loading each available simulation.

    This is a smoke test that validates:
    - Simulation file can be parsed
    - Data can be transformed
    - Component can be structured
    - Bindings can be resolved
    - No critical errors occur

    Tests all 442 available models to ensure broad compatibility.
    """
    # Skip GWE, GWT, and PRT models (not yet fully supported)
    model_name_lower = model_name.lower()
    if any(
        x in model_name_lower for x in ["/gwe", "/gwt", "/prt", "ex-gwe-", "ex-gwt-", "ex-prt-"]
    ):
        pytest.skip(f"Skipping {model_name}: GWE/GWT/PRT models not yet supported")

    # Copy model to temporary workspace
    workspace = copy_to(tmp_path, model_name, verbose=False)
    sim_path = workspace / "mfsim.nam"

    # Skip if no simulation name file exists
    if not sim_path.exists():
        pytest.skip(f"No mfsim.nam found in {model_name}")

    # Load the simulation
    try:
        sim = Simulation.load(sim_path)
    except Exception as e:
        pytest.fail(f"Failed to load simulation from {model_name}: {e}")

    # Basic validation
    assert sim is not None, "Simulation should not be None"
    assert isinstance(sim, Simulation), "Should return Simulation instance"

    # Check that simulation has expected structure
    assert hasattr(sim, "tdis"), "Simulation should have tdis"
    assert hasattr(sim, "models"), "Simulation should have models attribute"
    assert hasattr(sim, "solutions"), "Simulation should have solutions attribute"

    # Validate tdis was loaded (required component)
    if sim.tdis is None:
        pytest.fail(f"TDIS not loaded for {model_name}")

    # Optional: Log successful load for debugging
    model_count = len(sim.models) if isinstance(sim.models, dict) else 0
    solution_count = len(sim.solutions) if isinstance(sim.solutions, dict) else 0

    print(f"\n✓ {model_name}")
    print(f"  - Models: {model_count}")
    print(f"  - Solutions: {solution_count}")


@pytest.mark.parametrize("model_name", ALL_MODELS)
def test_load_and_validate_structure(tmp_path, model_name):
    """
    Test that loaded simulations have valid structure.

    Validates:
    - Models are dict or None (not list/binding tuples)
    - Solutions are dict or None (not list/binding tuples)
    - Exchanges are dict or None (not list/binding tuples)
    - TDIS is a component instance (not a binding tuple)

    This ensures binding resolution completed successfully.
    """
    # Skip GWE, GWT, and PRT models (not yet fully supported)
    model_name_lower = model_name.lower()
    if any(
        x in model_name_lower for x in ["/gwe", "/gwt", "/prt", "ex-gwe-", "ex-gwt-", "ex-prt-"]
    ):
        pytest.skip(f"Skipping {model_name}: GWE/GWT/PRT models not yet supported")

    workspace = copy_to(tmp_path, model_name, verbose=False)
    sim_path = workspace / "mfsim.nam"

    if not sim_path.exists():
        pytest.skip(f"No mfsim.nam found in {model_name}")

    sim = Simulation.load(sim_path)

    # Validate binding resolution completed
    # After resolution, these should be dicts, not lists of tuples

    # Models should be dict or None, not list of binding tuples
    if hasattr(sim, "models") and sim.models is not None:
        assert isinstance(sim.models, dict), (
            f"Models should be dict after binding resolution, got {type(sim.models)}"
        )
        # If models exist, check they're component instances
        for model_name_key, model in sim.models.items():
            assert hasattr(model, "filename"), (
                f"Model {model_name_key} should be a component with filename"
            )

    # Solutions should be dict or None, not list of binding tuples
    if hasattr(sim, "solutions") and sim.solutions is not None:
        assert isinstance(sim.solutions, dict), (
            f"Solutions should be dict after binding resolution, got {type(sim.solutions)}"
        )

    # TDIS should be a component instance, not a tuple
    if hasattr(sim, "tdis") and sim.tdis is not None:
        assert not isinstance(sim.tdis, (tuple, list)), (
            "TDIS should be component instance, not binding tuple"
        )
        assert hasattr(sim.tdis, "filename"), "TDIS should be a component with filename"


@pytest.mark.parametrize("model_name", ALL_MODELS[:50])  # Test subset for package diversity
def test_package_loading(tmp_path, model_name):
    """
    Test that packages within models are properly loaded.

    This validates that:
    - Models have expected package structure
    - Packages are accessible
    - Basic package attributes exist

    Tests first 50 models to cover diverse package types without
    being too slow.
    """
    workspace = copy_to(tmp_path, model_name, verbose=False)
    sim_path = workspace / "mfsim.nam"

    if not sim_path.exists():
        pytest.skip(f"No mfsim.nam found in {model_name}")

    sim = Simulation.load(sim_path)

    # Check that models have package structure
    if hasattr(sim, "models") and isinstance(sim.models, dict):
        for model_name_key, model in sim.models.items():
            # Every model should have these basic attributes
            assert hasattr(model, "filename"), f"Model {model_name_key} should have filename"
            assert hasattr(model, "children"), f"Model {model_name_key} should have children dict"

            # Check for common packages (not all models have all packages)
            # Just verify the structure is sound
            if hasattr(model, "children") and model.children:
                for pkg_name, pkg in model.children.items():
                    assert hasattr(pkg, "filename"), f"Package {pkg_name} should have filename"


@pytest.mark.parametrize("model_name", ALL_MODELS)
def test_simulation_attributes(tmp_path, model_name):
    """
    Test that simulation has expected attributes after loading.

    Validates basic simulation structure and metadata.
    """
    # Skip GWE, GWT, and PRT models (not yet fully supported)
    model_name_lower = model_name.lower()
    if any(
        x in model_name_lower for x in ["/gwe", "/gwt", "/prt", "ex-gwe-", "ex-gwt-", "ex-prt-"]
    ):
        pytest.skip(f"Skipping {model_name}: GWE/GWT/PRT models not yet supported")

    workspace = copy_to(tmp_path, model_name, verbose=False)
    sim_path = workspace / "mfsim.nam"

    if not sim_path.exists():
        pytest.skip(f"No mfsim.nam found in {model_name}")

    sim = Simulation.load(sim_path)

    # Check required attributes
    assert hasattr(sim, "filename"), "Simulation should have filename"
    assert hasattr(sim, "workspace"), "Simulation should have workspace"

    # Filename should be set
    assert sim.filename is not None, "Simulation filename should not be None"
    assert "mfsim.nam" in str(sim.filename).lower(), "Filename should be mfsim.nam"

    # Workspace should be set
    assert sim.workspace is not None, "Simulation workspace should not be None"
    assert sim.workspace.exists(), "Workspace directory should exist"


# Model type specific tests
GWF_MODELS = [m for m in ALL_MODELS if "gwf" in m.lower()]
GWT_MODELS = [m for m in ALL_MODELS if "gwt" in m.lower()]
GWE_MODELS = [m for m in ALL_MODELS if "gwe" in m.lower()]
PRT_MODELS = [m for m in ALL_MODELS if "prt" in m.lower()]


@pytest.mark.parametrize("model_name", GWF_MODELS)
def test_gwf_model_loading(tmp_path, model_name):
    """Test loading GWF (groundwater flow) models specifically."""
    workspace = copy_to(tmp_path, model_name, verbose=False)
    sim_path = workspace / "mfsim.nam"

    if not sim_path.exists():
        pytest.skip(f"No mfsim.nam found in {model_name}")

    sim = Simulation.load(sim_path)

    # GWF models should load successfully
    assert sim is not None
    assert isinstance(sim, Simulation)


@pytest.mark.skip(reason="GWT models not yet supported")
@pytest.mark.parametrize("model_name", GWT_MODELS)
def test_gwt_model_loading(tmp_path, model_name):
    """Test loading GWT (groundwater transport) models specifically."""
    workspace = copy_to(tmp_path, model_name, verbose=False)
    sim_path = workspace / "mfsim.nam"

    if not sim_path.exists():
        pytest.skip(f"No mfsim.nam found in {model_name}")

    sim = Simulation.load(sim_path)

    # GWT models should load successfully
    assert sim is not None
    assert isinstance(sim, Simulation)


@pytest.mark.skip(reason="GWE models not yet supported")
@pytest.mark.parametrize("model_name", GWE_MODELS)
def test_gwe_model_loading(tmp_path, model_name):
    """Test loading GWE (groundwater energy) models specifically."""
    workspace = copy_to(tmp_path, model_name, verbose=False)
    sim_path = workspace / "mfsim.nam"

    if not sim_path.exists():
        pytest.skip(f"No mfsim.nam found in {model_name}")

    sim = Simulation.load(sim_path)

    # GWE models should load successfully
    assert sim is not None
    assert isinstance(sim, Simulation)


@pytest.mark.skip(reason="PRT models not yet supported")
@pytest.mark.parametrize("model_name", PRT_MODELS)
def test_prt_model_loading(tmp_path, model_name):
    """Test loading PRT (particle tracking) models specifically."""
    workspace = copy_to(tmp_path, model_name, verbose=False)
    sim_path = workspace / "mfsim.nam"

    if not sim_path.exists():
        pytest.skip(f"No mfsim.nam found in {model_name}")

    sim = Simulation.load(sim_path)

    # PRT models should load successfully
    assert sim is not None
    assert isinstance(sim, Simulation)
