"""Tests for WriteContext functionality."""

import textwrap
import threading

import pytest

from flopy4.mf6.gwf import Chd, Dis, Gwf, Ic, Npf, Oc
from flopy4.mf6.ims import Ims
from flopy4.mf6.simulation import Simulation
from flopy4.mf6.utils.time import Time
from flopy4.mf6.write_context import ArrayIO, WriteContext


def test_write_context_default():
    """Every setting starts unset; resolving fills in the defaults."""
    ctx = WriteContext()
    assert ctx.use_netcdf is None
    assert ctx.binary_threshold is None
    assert ctx.float_precision is None
    assert ctx.array_format is None
    assert ctx.arrays == {}

    resolved = WriteContext.resolve()
    assert resolved.strict is False
    assert resolved.use_netcdf is False
    assert resolved.float_precision == "lossless"
    assert resolved.array_format is None
    assert WriteContext.default() == resolved


def test_write_context_custom():
    """Test WriteContext with custom settings."""
    ctx = WriteContext(array_format="binary", float_precision=8)
    assert ctx.array_format == "binary"
    assert ctx.float_precision == 8


def test_write_context_to_numpy_printoptions():
    """Test conversion to numpy printoptions."""
    ctx = WriteContext(float_precision=4)
    opts = ctx.to_numpy_printoptions()

    assert opts["precision"] == 4
    assert "linewidth" in opts
    assert "threshold" in opts


def test_write_context_to_numpy_printoptions_lossless():
    """Without a precision, numpy prints floats losslessly."""
    opts = WriteContext().to_numpy_printoptions()

    assert "precision" not in opts
    assert opts["floatmode"] == "unique"


def test_write_context_manager():
    """Test WriteContext as context manager."""
    # Default context
    default_ctx = WriteContext.current()
    assert default_ctx.float_precision is None

    # Enter context manager
    with WriteContext(float_precision=10):
        current = WriteContext.current()
        assert current.float_precision == 10

    # After exiting, should return to default
    after = WriteContext.current()
    assert after.float_precision is None


def test_write_context_manager_nesting():
    """Test nested WriteContext managers."""
    with WriteContext(float_precision=4):
        assert WriteContext.current().float_precision == 4

        with WriteContext(float_precision=6):
            assert WriteContext.current().float_precision == 6

        # Should return to outer context
        assert WriteContext.current().float_precision == 4

    # Should return to default
    assert WriteContext.current().float_precision is None


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
        solutiongroup=[ims],
    )

    gwf = Gwf(parent=sim, name="gwf", dis=dis)
    ic = Ic(parent=gwf, strt=1.0)
    npf = Npf(parent=gwf, k=1.0)
    chd = Chd(parent=gwf, stress_period_data={0: [[(0, 0, 0), 1.0]]})
    oc = Oc(parent=gwf, head_file="gwf.hds", budget_file="gwf.bud")

    # Write with custom context
    ctx = WriteContext(float_precision=8)
    sim.write(context=ctx)

    # Check that files were written
    assert (function_tmpdir / "mfsim.nam").exists()
    assert (function_tmpdir / "gwf.dis.dis").exists()


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
        solutiongroup=[ims],
    )

    gwf = Gwf(parent=sim, name="gwf", dis=dis)
    ic = Ic(parent=gwf, strt=1.0)
    npf = Npf(parent=gwf, k=1.0)

    # Use context manager
    with WriteContext(float_precision=10):
        sim.write()

    # Check that files were written
    assert (function_tmpdir / "mfsim.nam").exists()
    assert (function_tmpdir / "gwf.dis.dis").exists()


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


def test_write_floats_lossless_by_default(function_tmpdir):
    """By default, floats are written as the shortest string that reads back
    as the same value."""
    dis = Dis(
        nlay=1,
        nrow=1,
        ncol=3,
        delr=[11.09305553, 0.1, 3e30],
        delc=100.58491653,
        top=1.123456789012345,
        botm=0.0,
    )
    dis.filename = str(function_tmpdir / "gwf.dis")
    dis.write()

    content = (function_tmpdir / "gwf.dis").read_text()
    assert "11.09305553 0.1 3e+30" in content
    assert "CONSTANT 100.58491653" in content
    assert "CONSTANT 1.123456789012345" in content


def test_resolve_takes_highest_set_setting():
    """Each setting comes from the highest-ranked context setting it; None
    contexts are skipped."""
    high = WriteContext(float_precision=4)
    low = WriteContext(float_precision=8, use_netcdf=True)
    resolved = WriteContext.resolve(None, high, low)
    assert resolved.float_precision == 4
    assert resolved.use_netcdf is True
    # an explicit False beats a lower True
    assert WriteContext.resolve(WriteContext(use_netcdf=False), low).use_netcdf is False


def test_resolve_merges_array_entries():
    """Array entries from several contexts are all kept; for one key, the
    higher context's settings win."""
    high = WriteContext(arrays={"k": ArrayIO(iprn=1)})
    low = WriteContext(arrays={"k": ArrayIO(iprn=2), "k33": ArrayIO(iprn=3)})
    resolved = WriteContext.resolve(high, low)
    assert resolved.arrays == {"k": ArrayIO(iprn=1), "k33": ArrayIO(iprn=3)}
    assert ArrayIO().over(ArrayIO(iprn=2)) == ArrayIO(iprn=2)


def test_array_io_falls_back_to_containing_array():
    """A layer of a period's array falls back to the period's entry, then
    the field's."""
    ctx = WriteContext(arrays={"recharge": ArrayIO(iprn=1), ("recharge", 3): ArrayIO(iprn=2)})
    assert ctx.array_io("recharge", 3, 0).iprn == 2
    assert ctx.array_io("recharge", 4, 0).iprn == 1
    assert ctx.array_io("recharge").iprn == 1
    assert ctx.array_io("other").iprn is None


def _dis(**kwargs):
    return Dis(nlay=1, nrow=1, ncol=1, delr=1.0, delc=1.0, top=1.123456789, botm=0.0, **kwargs)


def test_component_write_context_precedence(function_tmpdir):
    """The write() argument beats the context manager, which beats the
    component's own write_context, which beats its ancestors'."""
    sim = Simulation(name="test", workspace=function_tmpdir, tdis=Time(perlen=[1.0], nstp=[1]))
    gwf = Gwf(parent=sim, name="gwf", dis=_dis())
    gwf.write_context = WriteContext(float_precision=2)
    dis = gwf.dis
    dis.filename = "gwf.dis"
    path = function_tmpdir / "gwf.dis"

    def top():
        dis.write()
        return next(ln for ln in path.read_text().splitlines() if "CONSTANT 1.1" in ln)

    assert top().endswith("1.12e+00")  # ancestor
    dis.write_context = WriteContext(float_precision=4)
    assert top().endswith("1.1235e+00")  # own beats ancestor
    with WriteContext(float_precision=6):
        assert top().endswith("1.123457e+00")  # context manager beats own
        dis.write(context=WriteContext(float_precision="lossless"))
        assert "CONSTANT 1.123456789" in path.read_text()  # argument beats all


def test_ancestor_arrays_do_not_apply(function_tmpdir):
    """An ancestor's array entries key its own fields, so they don't apply
    to a child's same-named fields."""
    sim = Simulation(name="test", workspace=function_tmpdir, tdis=Time(perlen=[1.0], nstp=[1]))
    gwf = Gwf(
        parent=sim,
        name="gwf",
        dis=Dis(nlay=1, nrow=1, ncol=2, delr=[1.0, 2.0], delc=1.0, top=1.0, botm=0.0),
    )
    gwf.write_context = WriteContext(arrays={"delr": ArrayIO(iprn=5)})
    gwf.dis.filename = "gwf.dis"
    gwf.dis.write()
    assert "IPRN" not in (function_tmpdir / "gwf.dis").read_text()


def test_write_context_not_model_data():
    """write_context is left out of equality and to_dict()."""
    a, b = _dis(), _dis(write_context=WriteContext(float_precision=4))
    assert a == b
    assert "write_context" not in b.to_dict()


@pytest.fixture
def iprn_dis(function_tmpdir):
    path = function_tmpdir / "in.dis"
    path.write_text(
        textwrap.dedent("""\
            BEGIN DIMENSIONS
              NLAY 2
              NROW 1
              NCOL 3
            END DIMENSIONS
            BEGIN GRIDDATA
              DELR
                INTERNAL IPRN 3
                  1.0 2.0 3.0
              DELC
                CONSTANT 1.0
              TOP
                CONSTANT 1.0
              BOTM LAYERED
                INTERNAL IPRN 1
                  0.0 -1.0 0.5
                INTERNAL IPRN 2
                  -2.0 -3.0 -4.0
            END GRIDDATA
        """)
    )
    dis = Dis.load(path)
    dis.filename = str(function_tmpdir / "out.dis")
    return dis


def _iprn_lines(dis):
    dis.write()
    return [
        ln.strip() for ln in dis.path.read_text().splitlines() if ln.strip().startswith("INTERNAL")
    ]


def test_load_keeps_iprn(iprn_dis):
    """A loaded array's IPRN, per layer for a LAYERED one, is written back."""
    assert iprn_dis.write_context.arrays == {
        "delr": ArrayIO(iprn=3, format="internal", layered=False),
        "delc": ArrayIO(format="constant", layered=False),
        "top": ArrayIO(format="constant", layered=False),
        "botm": ArrayIO(layered=True),
        ("botm", 0): ArrayIO(iprn=1, format="internal"),
        ("botm", 1): ArrayIO(iprn=2, format="internal"),
    }
    assert _iprn_lines(iprn_dis) == ["INTERNAL IPRN 3", "INTERNAL IPRN 1", "INTERNAL IPRN 2"]


def test_loaded_iprn_overridden_or_dropped(iprn_dis):
    """A context manager's entry beats the loaded one; clearing
    write_context drops them all."""
    with WriteContext(arrays={"delr": ArrayIO(iprn=9)}):
        assert _iprn_lines(iprn_dis)[0] == "INTERNAL IPRN 9"
    iprn_dis.write_context = None
    assert _iprn_lines(iprn_dis) == ["INTERNAL"] * 3


def test_load_keeps_period_iprn(function_tmpdir):
    """A READARRAY period array's IPRN is kept by (field, kper)."""
    from flopy4.mf6.gwf.rcha import Rcha

    path = function_tmpdir / "in.rcha"
    values = " ".join(str(i) for i in range(4))
    path.write_text(
        textwrap.dedent(f"""\
            BEGIN OPTIONS
              READASARRAYS
            END OPTIONS
            BEGIN PERIOD 2
             RECHARGE
              INTERNAL IPRN 4
                {values}
            END PERIOD 2
        """)
    )
    rcha = Rcha.load(path, dims={"nlay": 1, "nodes": 4})
    assert rcha.write_context.arrays == {
        ("recharge", 1): ArrayIO(iprn=4, format="internal", layered=False)
    }
    rcha.filename = str(function_tmpdir / "out.rcha")
    rcha.write()
    assert "INTERNAL IPRN 4" in rcha.path.read_text()


@pytest.fixture
def form_dis(function_tmpdir):
    """A DIS whose arrays' forms the writer wouldn't choose: a uniform
    INTERNAL array, a non-LAYERED INTERNAL one of a layered field, and a
    LAYERED one whose layers are CONSTANT and a uniform INTERNAL."""
    path = function_tmpdir / "in.dis"
    path.write_text(
        textwrap.dedent("""\
            BEGIN DIMENSIONS
              NLAY 2
              NROW 1
              NCOL 2
            END DIMENSIONS
            BEGIN GRIDDATA
              DELR
                INTERNAL
                  1.0 1.0
              DELC
                CONSTANT 1.0
              TOP
                CONSTANT 1.0
              BOTM
                INTERNAL
                  0.0 0.5
                  -1.0 -2.0
              IDOMAIN LAYERED
                CONSTANT 1
                INTERNAL
                  1 1
            END GRIDDATA
        """)
    )
    dis = Dis.load(path)
    dis.filename = str(function_tmpdir / "out.dis")
    return dis


def _griddata(dis) -> list[str]:
    dis.write()
    text = dis.path.read_text()
    block = text[text.index("BEGIN GRIDDATA") : text.index("END GRIDDATA")]
    return [ln.strip() for ln in block.splitlines()[1:] if ln.strip()]


def test_load_keeps_array_forms(form_dis):
    assert _griddata(form_dis) == [
        "DELR",
        "INTERNAL",
        "1.0 1.0",
        "DELC",
        "CONSTANT 1.0",
        "TOP",
        "CONSTANT 1.0",
        "BOTM",
        "INTERNAL",
        "0.0 0.5",
        "-1.0 -2.0",
        "IDOMAIN LAYERED",
        "CONSTANT 1",
        "INTERNAL",
        "1 1",
    ]


def test_without_forms_writer_chooses(form_dis):
    form_dis.write_context = None
    assert _griddata(form_dis) == [
        "DELR",
        "CONSTANT 1.0",
        "DELC",
        "CONSTANT 1.0",
        "TOP",
        "CONSTANT 1.0",
        "BOTM LAYERED",
        "INTERNAL",
        "0.0 0.5",
        "INTERNAL",
        "-1.0 -2.0",
        "IDOMAIN",
        "CONSTANT 1",
    ]


def test_form_needs_its_values(form_dis):
    """A form the values no longer allow is ignored: an edited uniform
    INTERNAL layer stays INTERNAL, but a CONSTANT one that isn't uniform
    anymore is written INTERNAL."""
    form_dis.idomain.flat[0] = 0
    assert _griddata(form_dis)[-5:] == ["IDOMAIN LAYERED", "INTERNAL", "0 1", "INTERNAL", "1 1"]
