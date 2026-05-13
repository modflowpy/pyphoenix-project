"""Tests for WriteContext functionality."""

import threading

from flopy4.mf6.gwf import Chd, Dis, Gwf, Ic, Npf, Oc
from flopy4.mf6.ims import Ims
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.utils.time import Time
from flopy4.mf6.write_context import WriteContext


def test_write_context_default():
    """Test default WriteContext initialization."""
    ctx = WriteContext()
    assert ctx.use_binary is False
    assert ctx.use_netcdf is False
    assert ctx.binary_threshold is None
    assert ctx.float_precision == 8
    assert ctx.use_relative_paths is True
    assert ctx.array_format is None


def test_write_context_custom():
    """Test WriteContext with custom settings."""
    ctx = WriteContext(use_binary=True, float_precision=8, use_relative_paths=False)
    assert ctx.use_binary is True
    assert ctx.float_precision == 8
    assert ctx.use_relative_paths is False


def test_write_context_to_numpy_printoptions():
    """Test conversion to numpy printoptions."""
    ctx = WriteContext(float_precision=4)
    opts = ctx.to_numpy_printoptions()

    assert opts["precision"] == 4
    assert "linewidth" in opts
    assert "threshold" in opts


def test_write_context_get_float_format():
    """Test float format string generation."""
    ctx = WriteContext(float_precision=6)
    assert ctx.get_float_format() == "%.6e"

    ctx2 = WriteContext(float_precision=10)
    assert ctx2.get_float_format() == "%.10e"


def test_write_context_manager():
    """Test WriteContext as context manager."""
    # Default context
    default_ctx = WriteContext.current()
    assert default_ctx.float_precision == 8

    # Enter context manager
    with WriteContext(float_precision=10):
        current = WriteContext.current()
        assert current.float_precision == 10

    # After exiting, should return to default
    after = WriteContext.current()
    assert after.float_precision == 8


def test_write_context_manager_nesting():
    """Test nested WriteContext managers."""
    with WriteContext(float_precision=4):
        assert WriteContext.current().float_precision == 4

        with WriteContext(float_precision=6):
            assert WriteContext.current().float_precision == 6

        # Should return to outer context
        assert WriteContext.current().float_precision == 4

    # Should return to default
    assert WriteContext.current().float_precision == 8


def test_write_context_thread_local():
    """Test that WriteContext is thread-local."""
    results = {}

    def thread_func(precision):
        with WriteContext(float_precision=precision):
            results[threading.current_thread().name] = WriteContext.current().float_precision

    t1 = threading.Thread(target=thread_func, args=(4,), name="t1")
    t2 = threading.Thread(target=thread_func, args=(8,), name="t2")

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results["t1"] == 4
    assert results["t2"] == 8


def test_component_write_with_context(function_tmpdir):
    """Test writing component with explicit context."""
    time = Time(perlen=[1.0], nstp=[1])
    ims = Ims(
        models=["gwf"],
        outer_dvclose=1e-6,
        outer_maximum=100,
        inner_maximum=300,
        inner_dvclose=1e-6,
        linear_acceleration="cg",
    )
    dis = Dis(nlay=1, nrow=2, ncol=2, delr=1.0, delc=1.0, top=1.0, botm=0.0)

    sim = Simulation(
        name="test",
        workspace=function_tmpdir,
        tdis=time,
        solutions={"ims": ims},
    )

    gwf = Gwf(parent=sim, name="gwf", dis=dis)
    ic = Ic(parent=gwf, strt=1.0)
    npf = Npf(parent=gwf, k=1.0)
    chd = Chd(parent=gwf, head={0: {(0, 0, 0): 1.0}})
    oc = Oc(parent=gwf, head_file="gwf.hds", budget_file="gwf.bud")

    # Write with custom context
    ctx = WriteContext(float_precision=8)
    sim.write(context=ctx)

    # Check that files were written
    assert (function_tmpdir / "mfsim.nam").exists()
    assert (function_tmpdir / "gwf.dis").exists()


def test_write_context_manager_with_component(function_tmpdir):
    """Test using WriteContext as context manager with component write."""
    time = Time(perlen=[1.0], nstp=[1])
    ims = Ims(
        models=["gwf"],
        outer_dvclose=1e-6,
        outer_maximum=100,
        inner_maximum=300,
        inner_dvclose=1e-6,
        linear_acceleration="cg",
    )
    dis = Dis(nlay=1, nrow=2, ncol=2, delr=1.0, delc=1.0, top=1.0, botm=0.0)

    sim = Simulation(
        name="test",
        workspace=function_tmpdir,
        tdis=time,
        solutions={"ims": ims},
    )

    gwf = Gwf(parent=sim, name="gwf", dis=dis)
    ic = Ic(parent=gwf, strt=1.0)
    npf = Npf(parent=gwf, k=1.0)

    # Use context manager
    with WriteContext(float_precision=10):
        sim.write()

    # Check that files were written
    assert (function_tmpdir / "mfsim.nam").exists()
    assert (function_tmpdir / "gwf.dis").exists()


def test_nested_write_context_precision(function_tmpdir):
    """Test that nested WriteContext uses correct precision in actual writes."""

    # Create component with a float value that will show precision differences
    dis = Dis(
        nlay=1,
        nrow=1,
        ncol=1,
        delr=1.0,
        delc=1.0,
        top=1.123456789,  # Value with many decimals
        botm=0.0,
    )

    # Outer context: precision=4
    with WriteContext(float_precision=4):
        outer_file = function_tmpdir / "outer.dis"
        dis.filename = str(outer_file)
        dis.write()
        outer_content = outer_file.read_text()

        # Inner nested context: precision=10
        with WriteContext(float_precision=10):
            inner_file = function_tmpdir / "inner.dis"
            dis.filename = str(inner_file)
            dis.write()
            inner_content = inner_file.read_text()

        # Back to outer context: precision=4
        after_file = function_tmpdir / "after.dis"
        dis.filename = str(after_file)
        dis.write()
        after_content = after_file.read_text()

    # Verify precision is respected at each level
    # Outer: 4 decimals
    assert "1.1235" in outer_content  # Rounded to 4 decimals

    # Inner: 10 decimals
    assert "1.1234567890" in inner_content  # Full 10 decimals

    # After: back to 4 decimals
    assert "1.1235" in after_content
    assert after_content == outer_content
