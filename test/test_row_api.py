"""Tests for the typed Row construction API on generated packages.

Period block Row API:
  - ``Pkg.Row`` — nested @attrs.define class with typed fields + __iter__
  - ``PkgRow`` — module-level alias for clean imports

Row instances are accepted anywhere nested lists are accepted in
``stress_period_data``.  They are coerced to np.recarray in
``__attrs_post_init__``; the stored type is always ``dict[int, np.recarray]``.

Static list block Row API:
  - ``Pkg.PackagedataRow``, ``Pkg.ConnectiondataRow``, etc. — one per block
  - ``PkgPackagedataRow`` — module-level alias

Row instances for static blocks are accepted anywhere nested lists are accepted
in the block field (``lak.packagedata = [Lak.PackagedataRow(...)]``).  They are
coerced to np.recarray in ``_init_block_dtype`` via ``_coerce_to_recarray``.

``Row.__iter__`` always yields every schema column in declaration order,
yielding ``None`` for optional fields that are absent.  The coercion loop
reads only as many values as the dtype has names, so trailing ``None``
values from absent optional columns are harmlessly ignored when the package
does not have ``boundnames=True``.

Tests cover:
  - Row construction and field access
  - __iter__ yields values in schema column order (including None for absent optionals)
  - All three input styles (nested list, Row, recarray) produce the same result
  - Multiple rows per stress period (the common real-world case)
  - Optional boundname with and without boundnames=True
  - Rows with and without boundname mixed in the same period
  - time_series field accepts both float and str
  - Module-level alias importable
  - Multi-value packages (DRN)
  - Keystring packages (LAK)
"""

import numpy as np
import pytest

from flopy4.mf6.gwf.chd import Chd, ChdRow
from flopy4.mf6.gwf.drn import Drn, DrnRow
from flopy4.mf6.gwf.lak import (
    Lak,
    LakConnectiondataRow,
    LakOutletsRow,
    LakPackagedataRow,
    LakRow,
)
from flopy4.mf6.gwf.wel import Wel, WelRow
from flopy4.mf6.utl.ats import Ats, AtsPerioddataRow


class TestRowConstruction:
    def test_chd_row_fields(self):
        row = Chd.Row(cellid=(0, 0, 0), head=1.0)
        assert row.cellid == (0, 0, 0)
        assert row.head == 1.0
        assert row.boundname is None

    def test_chd_row_with_boundname(self):
        row = Chd.Row(cellid=(0, 0, 0), head=1.0, boundname="left-bc")
        assert row.boundname == "left-bc"

    def test_drn_row_fields(self):
        row = Drn.Row(cellid=(0, 0, 5), elev=10.0, cond=100.0)
        assert row.cellid == (0, 0, 5)
        assert row.elev == 10.0
        assert row.cond == 100.0
        assert row.boundname is None

    def test_wel_row_fields(self):
        row = Wel.Row(cellid=(0, 0, 4), q=-500.0)
        assert row.cellid == (0, 0, 4)
        assert row.q == -500.0

    def test_lak_row_fields(self):
        row = Lak.Row(number=0, keyword="STATUS", value="ACTIVE")
        assert row.number == 0
        assert row.keyword == "STATUS"
        assert row.value == "ACTIVE"


class TestRowIter:
    def test_chd_row_iter_no_aux_no_boundname(self):
        row = Chd.Row(cellid=(0, 0, 0), head=1.0)
        # required, (no aux), boundname=None
        assert list(row) == [(0, 0, 0), 1.0, None]

    def test_chd_row_iter_with_aux(self):
        row = Chd.Row(cellid=(0, 0, 0), head=1.0, aux=(5.0,))
        assert list(row) == [(0, 0, 0), 1.0, 5.0, None]

    def test_chd_row_iter_with_multi_aux(self):
        row = Chd.Row(cellid=(0, 0, 0), head=1.0, aux=(5.0, 3.0))
        assert list(row) == [(0, 0, 0), 1.0, 5.0, 3.0, None]

    def test_chd_row_iter_with_aux_and_boundname(self):
        row = Chd.Row(cellid=(0, 0, 0), head=1.0, aux=(5.0,), boundname="bc")
        assert list(row) == [(0, 0, 0), 1.0, 5.0, "bc"]

    def test_chd_row_iter_with_boundname_no_aux(self):
        row = Chd.Row(cellid=(0, 0, 0), head=1.0, boundname="bc")
        assert list(row) == [(0, 0, 0), 1.0, "bc"]

    def test_drn_row_iter_no_aux(self):
        row = Drn.Row(cellid=(0, 0, 5), elev=10.0, cond=100.0)
        assert list(row) == [(0, 0, 5), 10.0, 100.0, None]

    def test_drn_row_iter_with_boundname(self):
        row = Drn.Row(cellid=(0, 0, 5), elev=10.0, cond=100.0, boundname="drain")
        assert list(row) == [(0, 0, 5), 10.0, 100.0, "drain"]

    def test_lak_row_iter_no_aux_field(self):
        # LAK is keystring — no positional aux
        row = Lak.Row(number=0, keyword="STATUS", value="ACTIVE")
        assert list(row) == [0, "STATUS", "ACTIVE"]
        assert not hasattr(Lak.Row, "__attrs_attrs__") or "aux" not in [
            a.name for a in Lak.Row.__attrs_attrs__
        ]


class TestAllInputStyles:
    """Every accepted input form for stress_period_data.

    The coercion in Package._coerce_to_recarray accepts six distinct forms.
    All produce the same dict[int, np.recarray] internal state.

    Style 1 — list of lists (row-oriented, positional)
    Style 2 — list of tuples (row-oriented, positional)
    Style 3 — list of Row objects (typed, positional via __iter__)
    Style 4 — list of dicts (row-oriented, named columns)
    Style 5 — dict of lists (column-oriented)
    Style 6 — np.recarray (direct, zero coercion cost)
    """

    CELLID = (0, 0, 0)
    HEAD = 2.5

    def _make_ref(self):
        """Canonical recarray to compare all styles against."""
        chd = Chd(stress_period_data={0: [[self.CELLID, self.HEAD]]})
        return chd.stress_period_data[0]

    def _assert_matches_ref(self, spd, ref):
        assert isinstance(spd, np.recarray)
        assert spd["head"][0] == pytest.approx(ref["head"][0])
        assert tuple(spd["cellid"][0]) == tuple(ref["cellid"][0])

    def test_style1_list_of_lists(self):
        chd = Chd(stress_period_data={0: [[self.CELLID, self.HEAD]]})
        self._assert_matches_ref(chd.stress_period_data[0], self._make_ref())

    def test_style2_list_of_tuples(self):
        chd = Chd(stress_period_data={0: [(self.CELLID, self.HEAD)]})
        self._assert_matches_ref(chd.stress_period_data[0], self._make_ref())

    def test_style3_list_of_row_objects(self):
        chd = Chd(stress_period_data={0: [Chd.Row(cellid=self.CELLID, head=self.HEAD)]})
        self._assert_matches_ref(chd.stress_period_data[0], self._make_ref())

    def test_style4_list_of_dicts(self):
        chd = Chd(stress_period_data={0: [{"cellid": self.CELLID, "head": self.HEAD}]})
        self._assert_matches_ref(chd.stress_period_data[0], self._make_ref())

    def test_style5_column_oriented_dict(self):
        chd = Chd(stress_period_data={0: {"cellid": [self.CELLID], "head": [self.HEAD]}})
        self._assert_matches_ref(chd.stress_period_data[0], self._make_ref())

    def test_style6_recarray(self):
        ref = self._make_ref()
        chd = Chd(stress_period_data={0: ref})
        self._assert_matches_ref(chd.stress_period_data[0], ref)

    def test_all_styles_produce_identical_result(self):
        ref = self._make_ref()
        inputs = [
            [[self.CELLID, self.HEAD]],  # style 1
            [(self.CELLID, self.HEAD)],  # style 2
            [Chd.Row(cellid=self.CELLID, head=self.HEAD)],  # style 3
            [{"cellid": self.CELLID, "head": self.HEAD}],  # style 4
            {"cellid": [self.CELLID], "head": [self.HEAD]},  # style 5
            ref,  # style 6
        ]
        for spd_input in inputs:
            chd = Chd(stress_period_data={0: spd_input})
            self._assert_matches_ref(chd.stress_period_data[0], ref)

    def test_storage_is_always_recarray(self):
        for spd_input in [
            [[self.CELLID, self.HEAD]],
            [Chd.Row(cellid=self.CELLID, head=self.HEAD)],
        ]:
            chd = Chd(stress_period_data={0: spd_input})
            assert isinstance(chd.stress_period_data, dict)
            assert isinstance(chd.stress_period_data[0], np.recarray)

    def test_multi_row_list_of_dicts(self):
        rows = [
            {"cellid": (0, 0, 0), "head": 1.0},
            {"cellid": (0, 0, 1), "head": 2.0},
            {"cellid": (0, 0, 2), "head": 3.0},
        ]
        chd = Chd(stress_period_data={0: rows})
        spd = chd.stress_period_data[0]
        assert len(spd) == 3
        assert spd["head"][2] == pytest.approx(3.0)

    def test_multi_row_column_oriented_dict(self):
        chd = Chd(
            stress_period_data={
                0: {
                    "cellid": [(0, 0, 0), (0, 0, 1), (0, 0, 2)],
                    "head": [1.0, 2.0, 3.0],
                }
            }
        )
        spd = chd.stress_period_data[0]
        assert len(spd) == 3
        assert spd["head"][2] == pytest.approx(3.0)


class TestInputStyleEquivalence:
    """Spot-checks for specific package types across input styles."""

    def test_drn_nested_list_vs_row(self):
        drn_list = Drn(stress_period_data={0: [[(0, 0, 5), 10.0, 100.0]]})
        drn_row = Drn(stress_period_data={0: [Drn.Row(cellid=(0, 0, 5), elev=10.0, cond=100.0)]})

        for field in ("elev", "cond"):
            assert drn_list.stress_period_data[0][field][0] == pytest.approx(
                drn_row.stress_period_data[0][field][0]
            )


class TestAux:
    """Auxiliary variables — standard stress packages only.

    Row.aux is a tuple of values matching the package's ``auxiliary`` option
    in declaration order.  The coercion inserts them positionally between the
    last required value column and boundname, matching the DFN recarray layout:
    ``cellid ... values  aux0 aux1 …  boundname``.

    Keystring packages (LAK, SFR) use a different AUXILIARY keyword mechanism
    and do not have a positional aux field on Row.
    """

    def test_chd_row_has_aux_field(self):
        assert hasattr(Chd.Row, "__attrs_attrs__")
        names = [a.name for a in Chd.Row.__attrs_attrs__]
        assert "aux" in names

    def test_lak_row_has_no_aux_field(self):
        names = [a.name for a in Lak.Row.__attrs_attrs__]
        assert "aux" not in names

    def test_chd_aux_default_is_empty_tuple(self):
        row = Chd.Row(cellid=(0, 0, 0), head=1.0)
        assert row.aux == ()

    def test_chd_single_aux_stored(self):
        chd = Chd(
            auxiliary=["conc"],
            stress_period_data={0: [Chd.Row(cellid=(0, 0, 0), head=1.0, aux=(5.0,))]},
        )
        spd = chd.stress_period_data[0]
        assert "aux0" in spd.dtype.names
        assert spd["aux0"][0] == pytest.approx(5.0)

    def test_chd_multi_aux_stored(self):
        chd = Chd(
            auxiliary=["conc", "density"],
            stress_period_data={0: [Chd.Row(cellid=(0, 0, 0), head=1.0, aux=(5.0, 1025.0))]},
        )
        spd = chd.stress_period_data[0]
        assert "aux0" in spd.dtype.names
        assert "aux1" in spd.dtype.names
        assert spd["aux0"][0] == pytest.approx(5.0)
        assert spd["aux1"][0] == pytest.approx(1025.0)

    def test_chd_multi_row_with_aux(self):
        rows = [
            Chd.Row(cellid=(0, 0, 0), head=1.0, aux=(10.0,)),
            Chd.Row(cellid=(0, 0, 1), head=2.0, aux=(20.0,)),
            Chd.Row(cellid=(0, 0, 2), head=3.0, aux=(30.0,)),
        ]
        chd = Chd(auxiliary=["conc"], stress_period_data={0: rows})
        spd = chd.stress_period_data[0]
        assert len(spd) == 3
        assert spd["aux0"][1] == pytest.approx(20.0)

    def test_chd_aux_with_boundname(self):
        chd = Chd(
            auxiliary=["conc"],
            boundnames=True,
            stress_period_data={
                0: [
                    Chd.Row(cellid=(0, 0, 0), head=1.0, aux=(5.0,), boundname="left"),
                    Chd.Row(cellid=(0, 0, 1), head=2.0, aux=(6.0,)),
                ]
            },
        )
        spd = chd.stress_period_data[0]
        assert spd["aux0"][0] == pytest.approx(5.0)
        assert spd["boundname"][0] == "left"
        assert spd["aux0"][1] == pytest.approx(6.0)

    def test_chd_no_aux_without_auxiliary_option(self):
        # Without auxiliary=, dtype has no aux columns
        chd = Chd(stress_period_data={0: [Chd.Row(cellid=(0, 0, 0), head=1.0)]})
        spd = chd.stress_period_data[0]
        assert "aux0" not in spd.dtype.names

    def test_drn_single_aux(self):
        drn = Drn(
            auxiliary=["tracer"],
            stress_period_data={0: [Drn.Row(cellid=(0, 0, 0), elev=10.0, cond=100.0, aux=(99.0,))]},
        )
        spd = drn.stress_period_data[0]
        assert spd["aux0"][0] == pytest.approx(99.0)


class TestTimeSeries:
    def test_chd_row_head_accepts_float(self):
        chd = Chd(stress_period_data={0: [Chd.Row(cellid=(0, 0, 0), head=5.0)]})
        assert chd.stress_period_data[0]["head"][0] == 5.0

    def test_chd_row_head_accepts_ts_name(self):
        chd = Chd(stress_period_data={0: [Chd.Row(cellid=(0, 0, 0), head="ts_head")]})
        assert chd.stress_period_data[0]["head"][0] == "ts_head"


class TestModuleAlias:
    def test_chdrow_is_chd_row(self):
        assert ChdRow is Chd.Row

    def test_drnrow_is_drn_row(self):
        assert DrnRow is Drn.Row

    def test_welrow_is_wel_row(self):
        assert WelRow is Wel.Row

    def test_lakrow_is_lak_row(self):
        assert LakRow is Lak.Row

    def test_chdrow_constructible(self):
        row = ChdRow(cellid=(0, 0, 0), head=1.0)
        assert row.head == 1.0

    def test_chdrow_usable_in_spd(self):
        chd = Chd(stress_period_data={0: [ChdRow(cellid=(0, 0, 0), head=3.0)]})
        assert chd.stress_period_data[0]["head"][0] == pytest.approx(3.0)


class TestMultiRowPerPeriod:
    """The common real-world case: many rows per stress period."""

    def test_chd_multiple_rows_single_period(self):
        rows = [
            Chd.Row(cellid=(0, 0, 0), head=1.0),
            Chd.Row(cellid=(0, 0, 1), head=2.0),
            Chd.Row(cellid=(0, 0, 2), head=3.0),
        ]
        chd = Chd(stress_period_data={0: rows})
        spd = chd.stress_period_data[0]
        assert isinstance(spd, np.recarray)
        assert len(spd) == 3
        assert spd["head"][0] == pytest.approx(1.0)
        assert spd["head"][1] == pytest.approx(2.0)
        assert spd["head"][2] == pytest.approx(3.0)

    def test_chd_cellids_preserved_multi_row(self):
        rows = [
            Chd.Row(cellid=(0, 0, 0), head=1.0),
            Chd.Row(cellid=(0, 1, 5), head=2.0),
            Chd.Row(cellid=(2, 3, 4), head=3.0),
        ]
        chd = Chd(stress_period_data={0: rows})
        spd = chd.stress_period_data[0]
        assert tuple(spd["cellid"][0]) == (0, 0, 0)
        assert tuple(spd["cellid"][1]) == (0, 1, 5)
        assert tuple(spd["cellid"][2]) == (2, 3, 4)

    def test_drn_multiple_rows(self):
        rows = [
            Drn.Row(cellid=(0, 0, 0), elev=10.0, cond=100.0),
            Drn.Row(cellid=(0, 0, 1), elev=20.0, cond=200.0),
        ]
        drn = Drn(stress_period_data={0: rows})
        spd = drn.stress_period_data[0]
        assert len(spd) == 2
        assert spd["elev"][0] == pytest.approx(10.0)
        assert spd["cond"][1] == pytest.approx(200.0)

    def test_multi_row_vs_equivalent_nested_list(self):
        row_data = [
            Chd.Row(cellid=(0, 0, 0), head=1.0),
            Chd.Row(cellid=(0, 0, 1), head=2.0),
        ]
        list_data = [[(0, 0, 0), 1.0], [(0, 0, 1), 2.0]]
        chd_row = Chd(stress_period_data={0: row_data})
        chd_list = Chd(stress_period_data={0: list_data})
        for i in range(2):
            assert chd_row.stress_period_data[0]["head"][i] == pytest.approx(
                chd_list.stress_period_data[0]["head"][i]
            )

    def test_maxbound_reflects_row_count(self):
        rows = [Chd.Row(cellid=(0, 0, i), head=float(i)) for i in range(10)]
        chd = Chd(stress_period_data={0: rows})
        assert len(chd.stress_period_data[0]) == 10
        assert chd.maxbound == 10


class TestBoundnames:
    """boundnames=True widens the dtype to include a boundname column.
    Rows without a boundname must still coerce correctly (None assigned).
    """

    def test_chd_boundnames_row_with_name(self):
        chd = Chd(
            boundnames=True,
            stress_period_data={0: [Chd.Row(cellid=(0, 0, 0), head=1.0, boundname="left")]},
        )
        spd = chd.stress_period_data[0]
        assert "boundname" in spd.dtype.names
        assert spd["boundname"][0] == "left"

    def test_chd_boundnames_row_without_name(self):
        # Row without boundname must not IndexError when boundnames=True
        chd = Chd(
            boundnames=True,
            stress_period_data={0: [Chd.Row(cellid=(0, 0, 0), head=1.0)]},
        )
        spd = chd.stress_period_data[0]
        assert "boundname" in spd.dtype.names
        assert spd["head"][0] == pytest.approx(1.0)

    def test_chd_boundnames_mixed_rows(self):
        # Some rows with boundname, some without — all must coerce without error
        rows = [
            Chd.Row(cellid=(0, 0, 0), head=1.0, boundname="left"),
            Chd.Row(cellid=(0, 0, 1), head=2.0),
            Chd.Row(cellid=(0, 0, 2), head=3.0, boundname="right"),
        ]
        chd = Chd(boundnames=True, stress_period_data={0: rows})
        spd = chd.stress_period_data[0]
        assert len(spd) == 3
        assert spd["boundname"][0] == "left"
        assert spd["head"][1] == pytest.approx(2.0)
        assert spd["boundname"][2] == "right"

    def test_chd_no_boundnames_option_excludes_column(self):
        # Without boundnames=True, the dtype should not contain boundname
        chd = Chd(stress_period_data={0: [Chd.Row(cellid=(0, 0, 0), head=1.0)]})
        spd = chd.stress_period_data[0]
        assert "boundname" not in spd.dtype.names


class TestMultiPeriod:
    def test_chd_row_multi_period(self):
        chd = Chd(
            stress_period_data={
                0: [Chd.Row(cellid=(0, 0, 0), head=1.0)],
                1: [Chd.Row(cellid=(0, 0, 0), head=2.0)],
            }
        )
        assert chd.stress_period_data[0]["head"][0] == pytest.approx(1.0)
        assert chd.stress_period_data[1]["head"][0] == pytest.approx(2.0)

    def test_chd_multi_period_multi_row(self):
        chd = Chd(
            stress_period_data={
                0: [Chd.Row(cellid=(0, 0, i), head=float(i)) for i in range(5)],
                1: [Chd.Row(cellid=(0, 0, i), head=float(i) * 2) for i in range(3)],
            }
        )
        assert len(chd.stress_period_data[0]) == 5
        assert len(chd.stress_period_data[1]) == 3
        assert chd.stress_period_data[0]["head"][4] == pytest.approx(4.0)
        assert chd.stress_period_data[1]["head"][2] == pytest.approx(4.0)

    def test_mixed_styles_across_periods(self):
        chd = Chd(
            stress_period_data={
                0: [[(0, 0, 0), 1.0]],
                1: [Chd.Row(cellid=(0, 0, 0), head=2.0)],
            }
        )
        assert chd.stress_period_data[0]["head"][0] == pytest.approx(1.0)
        assert chd.stress_period_data[1]["head"][0] == pytest.approx(2.0)


class TestStaticBlockRows:
    """Row construction API for static (non-repeating) list blocks."""

    # --- LAK PackagedataRow ---

    def test_lak_packagedata_row_fields(self):
        row = Lak.PackagedataRow(ifno=0, strt=320.0, nlakeconn=9)
        assert row.ifno == 0
        assert row.strt == pytest.approx(320.0)
        assert row.nlakeconn == 9
        assert row.boundname is None

    def test_lak_packagedata_row_with_boundname(self):
        row = Lak.PackagedataRow(ifno=0, strt=320.0, nlakeconn=9, boundname="lake-1")
        assert row.boundname == "lake-1"

    def test_lak_packagedata_row_iter(self):
        row = Lak.PackagedataRow(ifno=0, strt=320.0, nlakeconn=9)
        assert list(row) == [0, 320.0, 9, None]

    def test_lak_packagedata_row_iter_with_boundname(self):
        row = Lak.PackagedataRow(ifno=2, strt=305.0, nlakeconn=3, boundname="lake-3")
        assert list(row) == [2, 305.0, 3, "lake-3"]

    def test_lak_packagedata_row_alias(self):
        assert LakPackagedataRow is Lak.PackagedataRow

    def test_lak_packagedata_accepts_rows(self):
        lak = Lak(
            nlakes=1,
            noutlets=0,
            packagedata=[
                Lak.PackagedataRow(ifno=0, strt=320.0, nlakeconn=9),
            ],
            connectiondata=[
                Lak.ConnectiondataRow(
                    ifno=0,
                    iconn=0,
                    cellid=(0, 2, 3),
                    claktype="HORIZONTAL",
                    bedleak="NONE",
                    belev=305.0,
                    telev=320.0,
                    connlen=50.0,
                    connwidth=10.0,
                ),
            ],
        )
        assert lak.packagedata is not None
        assert isinstance(lak.packagedata, np.recarray)
        assert lak.packagedata["strt"][0] == pytest.approx(320.0)

    # --- LAK ConnectiondataRow (9 columns — the ergonomic win case) ---

    def test_lak_connectiondata_row_fields(self):
        row = Lak.ConnectiondataRow(
            ifno=0,
            iconn=0,
            cellid=(0, 2, 3),
            claktype="HORIZONTAL",
            bedleak="NONE",
            belev=305.0,
            telev=320.0,
            connlen=50.0,
            connwidth=10.0,
        )
        assert row.ifno == 0
        assert row.iconn == 0
        assert row.cellid == (0, 2, 3)
        assert row.claktype == "HORIZONTAL"
        assert row.bedleak == "NONE"
        assert row.belev == pytest.approx(305.0)
        assert row.connwidth == pytest.approx(10.0)

    def test_lak_connectiondata_row_iter(self):
        row = Lak.ConnectiondataRow(
            ifno=1,
            iconn=2,
            cellid=(0, 0, 5),
            claktype="VERTICAL",
            bedleak="0.01",
            belev=290.0,
            telev=310.0,
            connlen=25.0,
            connwidth=5.0,
        )
        assert list(row) == [1, 2, (0, 0, 5), "VERTICAL", "0.01", 290.0, 310.0, 25.0, 5.0]

    def test_lak_connectiondata_alias(self):
        assert LakConnectiondataRow is Lak.ConnectiondataRow

    def test_lak_connectiondata_coerced_to_recarray(self):
        lak = Lak(
            nlakes=1,
            noutlets=0,
            packagedata=[[0, 320.0, 2]],
            connectiondata=[
                Lak.ConnectiondataRow(
                    ifno=0,
                    iconn=0,
                    cellid=(0, 0, 3),
                    claktype="HORIZONTAL",
                    bedleak="NONE",
                    belev=305.0,
                    telev=320.0,
                    connlen=50.0,
                    connwidth=10.0,
                ),
                Lak.ConnectiondataRow(
                    ifno=0,
                    iconn=1,
                    cellid=(0, 0, 4),
                    claktype="HORIZONTAL",
                    bedleak="NONE",
                    belev=305.0,
                    telev=320.0,
                    connlen=40.0,
                    connwidth=10.0,
                ),
            ],
        )
        assert isinstance(lak.connectiondata, np.recarray)
        assert len(lak.connectiondata) == 2
        assert lak.connectiondata["connlen"][0] == pytest.approx(50.0)
        assert lak.connectiondata["connlen"][1] == pytest.approx(40.0)
        assert tuple(lak.connectiondata["cellid"][1]) == (0, 0, 4)

    # --- LAK OutletsRow ---

    def test_lak_outlets_row_fields(self):
        row = Lak.OutletsRow(
            outletno=0,
            lakein=0,
            lakeout=-1,
            couttype="MANNING",
            invert=310.0,
            width=5.0,
            rough=0.03,
            slope=0.001,
        )
        assert row.outletno == 0
        assert row.couttype == "MANNING"
        assert row.rough == pytest.approx(0.03)

    def test_lak_outlets_row_iter(self):
        row = Lak.OutletsRow(
            outletno=0,
            lakein=0,
            lakeout=-1,
            couttype="MANNING",
            invert=310.0,
            width=5.0,
            rough=0.03,
            slope=0.001,
        )
        assert list(row) == [0, 0, -1, "MANNING", 310.0, 5.0, 0.03, 0.001]

    def test_lak_outlets_alias(self):
        assert LakOutletsRow is Lak.OutletsRow

    # --- ATS PerioddataRow (package with only a static block, no period schema) ---

    def test_ats_perioddata_row_fields(self):
        row = Ats.PerioddataRow(
            iperats=0, dt0=1.0, dtmin=0.001, dtmax=10.0, dtadj=2.0, dtfailadj=5.0
        )
        assert row.iperats == 0
        assert row.dt0 == pytest.approx(1.0)
        assert row.dtfailadj == pytest.approx(5.0)

    def test_ats_perioddata_row_iter(self):
        row = Ats.PerioddataRow(
            iperats=1, dt0=0.5, dtmin=0.001, dtmax=5.0, dtadj=1.5, dtfailadj=3.0
        )
        assert list(row) == [1, 0.5, 0.001, 5.0, 1.5, 3.0]

    def test_ats_perioddata_alias(self):
        assert AtsPerioddataRow is Ats.PerioddataRow

    def test_ats_perioddata_accepts_rows(self):
        ats = Ats(
            perioddata=[
                Ats.PerioddataRow(
                    iperats=0, dt0=1.0, dtmin=0.001, dtmax=10.0, dtadj=2.0, dtfailadj=5.0
                ),
                Ats.PerioddataRow(
                    iperats=1, dt0=0.5, dtmin=0.001, dtmax=5.0, dtadj=1.5, dtfailadj=3.0
                ),
            ]
        )
        assert isinstance(ats.perioddata, np.recarray)
        assert len(ats.perioddata) == 2
        assert ats.perioddata["dt0"][0] == pytest.approx(1.0)
        assert ats.perioddata["dt0"][1] == pytest.approx(0.5)
