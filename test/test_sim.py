import os
import shutil
import subprocess
from pathlib import Path

import numpy as np

from flopy4.simulation import MFSimulation


def test_load_sim(tmp_path):
    name = "gwf_1"

    nlay = 3
    nrow = 10
    ncol = 10
    dis_fpth = tmp_path / f"{name}.dis"
    with open(dis_fpth, "w") as f:
        f.write("BEGIN OPTIONS\n")
        f.write("END OPTIONS\n\n")
        f.write("BEGIN DIMENSIONS\n")
        f.write(f"  NLAY  {nlay}\n")
        f.write(f"  NROW  {nrow}\n")
        f.write(f"  NCOL  {ncol}\n")
        f.write("END DIMENSIONS\n\n")
        f.write("BEGIN GRIDDATA\n")
        f.write("  DELR\n    CONSTANT  1000.00000000\n")
        f.write("  DELC\n    CONSTANT  2000.00000000\n")
        f.write("  TOP\n    CONSTANT  0.00000000\n")
        f.write("  BOTM    LAYERED\n")
        f.write("    CONSTANT  -100.00000000\n")
        f.write("    CONSTANT  -150.00000000\n")
        f.write("    CONSTANT  -350.00000000\n")
        f.write("END GRIDDATA\n")

    ic_fpth = tmp_path / f"{name}.ic"
    strt = np.linspace(0.0, 30.0, num=300)
    array = " ".join(str(x) for x in strt)
    with open(ic_fpth, "w") as f:
        f.write("BEGIN OPTIONS\n")
        f.write("  EXPORT_ARRAY_ASCII\n")
        f.write("END OPTIONS\n")
        f.write("\n")
        f.write("BEGIN GRIDDATA\n")
        f.write(f"  STRT\n    INTERNAL\n      {array}\n")
        f.write("END GRIDDATA\n")

    nam_fpth = tmp_path / f"{name}.nam"
    with open(nam_fpth, "w") as f:
        f.write("BEGIN OPTIONS\n")
        f.write("END OPTIONS\n")
        f.write("\n")
        f.write("BEGIN PACKAGES\n")
        f.write(f"  DIS6  {tmp_path}/{name}.dis  dis\n")
        f.write(f"  IC6  {tmp_path}/{name}.ic  ic\n")
        f.write("END PACKAGES\n")

    tdis_fpth = tmp_path / "sim.tdis"
    with open(tdis_fpth, "w") as f:
        f.write("BEGIN OPTIONS\n")
        f.write("  TIME_UNITS  days\n")
        f.write("  START_DATE_TIME  2041-01-01t00:00:00-05:00\n")
        f.write("END OPTIONS\n\n")
        f.write("BEGIN DIMENSIONS\n")
        f.write("  NPER  31\n")
        f.write("END DIMENSIONS\n\n")
        f.write("BEGIN PERIODDATA\n")
        f.write("    1.00000000  1       1.00000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("  365.25000000  6       1.30000000\n")
        f.write("END PERIODDATA\n\n")

    ims_fpth = tmp_path / f"{name}.ims"
    with open(ims_fpth, "w") as f:
        f.write("BEGIN OPTIONS\n")
        f.write("  PRINT_OPTION  summary\n")
        f.write("END OPTIONS\n\n")
        f.write("BEGIN NONLINEAR\n")
        f.write("  OUTER_DVCLOSE  1.00000000E-09\n")
        f.write("  OUTER_MAXIMUM  500\n")
        f.write("  UNDER_RELAXATION  none\n")
        f.write("END NONLINEAR\n\n")
        f.write("BEGIN LINEAR\n")
        f.write("  INNER_MAXIMUM  300\n")
        f.write("  INNER_DVCLOSE  1.00000000E-09\n")
        # TODO: fails
        # f.write("  INNER_RCLOSE  1.00000000E-06\n")
        f.write("  LINEAR_ACCELERATION  bicgstab\n")
        f.write("  RELAXATION_FACTOR       1.00000000\n")
        f.write("  SCALING_METHOD  none\n")
        f.write("  REORDERING_METHOD  none\n")
        f.write("END LINEAR\n\n")

    sim_fpth = tmp_path / "mfsim.nam"
    with open(sim_fpth, "w") as f:
        f.write("BEGIN OPTIONS\n")
        f.write("END OPTIONS\n\n")
        f.write("BEGIN TIMING\n")
        f.write(f"  TDIS6  {tmp_path}/sim.tdis\n")
        f.write("END TIMING\n\n")
        f.write("BEGIN MODELS\n")
        f.write(f"  GWF6  {tmp_path}/{name}.nam  {name}\n")
        f.write("END MODELS\n\n")
        f.write("BEGIN EXCHANGES\n")
        f.write("END EXCHANGES\n\n")
        f.write("BEGIN SOLUTIONGROUP 1\n")
        f.write(f"  ims6  {tmp_path}/{name}.ims  {name}\n")
        f.write("END SOLUTIONGROUP 1\n\n")

    s = None
    with open(sim_fpth, "r") as f:
        s = MFSimulation.load(f)

    # mfsim.nam
    assert "options" in s.nam
    assert "timing" in s.nam
    assert "models" in s.nam
    assert "exchanges" in s.nam
    assert "solutiongroup" in s.nam
    assert "tdis6" in s.nam["timing"]
    assert "mtype" in s.nam["models"].params["models"]
    assert "mfname" in s.nam["models"].params["models"]
    assert "mname" in s.nam["models"].params["models"]
    assert s.nam["models"].params["models"]["mtype"][0] == "GWF6"
    assert s.nam["models"].params["models"]["mname"][0] == f"{name}"
    assert "slntype" in s.nam["solutiongroup"].params["solutiongroup"]
    assert "slnfname" in s.nam["solutiongroup"].params["solutiongroup"]
    assert "slnmnames" in s.nam["solutiongroup"].params["solutiongroup"]
    assert (
        s.nam["solutiongroup"].params["solutiongroup"]["slntype"][0] == "ims6"
    )
    assert (
        s.nam["solutiongroup"].params["solutiongroup"]["slnmnames"][0]
        == f"{name}"
    )

    # models
    assert "dis" in s.models["gwf_1"].packages
    assert "options" in s.models["gwf_1"].packages["dis"]
    assert "dimensions" in s.models["gwf_1"].packages["dis"]
    assert "griddata" in s.models["gwf_1"].packages["dis"]
    assert "ic" in s.models["gwf_1"].packages
    assert "options" in s.models["gwf_1"].packages["ic"]
    assert "griddata" in s.models["gwf_1"].packages["ic"]

    # tdis
    assert "time_units" in s.tdis.params
    assert "start_date_time" in s.tdis.params
    assert "nper" in s.tdis.params
    assert "perioddata" in s.tdis.params
    assert "perlen" in s.tdis.params["perioddata"]
    assert "nstp" in s.tdis.params["perioddata"]
    assert "tsmult" in s.tdis.params["perioddata"]
    assert s.tdis.params["time_units"] == "days"
    assert s.tdis.params["start_date_time"] == "2041-01-01t00:00:00-05:00"
    assert s.tdis.params["nper"] == 31
    assert np.allclose(
        [float(f) for f in s.tdis.params["perioddata"]["perlen"]],
        np.array(
            [
                1.0,
                365.25,
                365.25,
                365.25,
                365.25,
                365.25,
                365.25,
                365.25,
                365.25,
                365.25,
                365.25,
                365.25,
                365.25,
                365.25,
                365.25,
                365.25,
                365.25,
                365.25,
                365.25,
                365.25,
                365.25,
                365.25,
                365.25,
                365.25,
                365.25,
                365.25,
                365.25,
                365.25,
                365.25,
                365.25,
                365.25,
            ]
        ),
    )
    assert np.allclose(
        s.tdis.params["perioddata"]["nstp"],
        np.array(
            [
                1,
                6,
                6,
                6,
                6,
                6,
                6,
                6,
                6,
                6,
                6,
                6,
                6,
                6,
                6,
                6,
                6,
                6,
                6,
                6,
                6,
                6,
                6,
                6,
                6,
                6,
                6,
                6,
                6,
                6,
                6,
            ]
        ),
    )
    assert np.allclose(
        [float(f) for f in s.tdis.params["perioddata"]["tsmult"]],
        np.array(
            [
                1.0,
                1.3,
                1.3,
                1.3,
                1.3,
                1.3,
                1.3,
                1.3,
                1.3,
                1.3,
                1.3,
                1.3,
                1.3,
                1.3,
                1.3,
                1.3,
                1.3,
                1.3,
                1.3,
                1.3,
                1.3,
                1.3,
                1.3,
                1.3,
                1.3,
                1.3,
                1.3,
                1.3,
                1.3,
                1.3,
                1.3,
            ]
        ),
    )

    # ims
    assert "ims_0" in s.solvers
    assert "print_option" in s.solvers["ims_0"].params
    assert "outer_dvclose" in s.solvers["ims_0"].params
    assert "outer_maximum" in s.solvers["ims_0"].params
    assert "under_relaxation" in s.solvers["ims_0"].params
    assert "inner_maximum" in s.solvers["ims_0"].params
    assert "inner_dvclose" in s.solvers["ims_0"].params
    assert "linear_acceleration" in s.solvers["ims_0"].params
    assert "relaxation_factor" in s.solvers["ims_0"].params
    assert "scaling_method" in s.solvers["ims_0"].params
    assert "reordering_method" in s.solvers["ims_0"].params
    assert s.solvers["ims_0"].params["print_option"] == "summary"
    assert float(s.solvers["ims_0"].params["outer_dvclose"]) == 1.00000000e-09
    assert s.solvers["ims_0"].params["outer_maximum"] == 500
    assert s.solvers["ims_0"].params["under_relaxation"] == "none"
    assert s.solvers["ims_0"].params["inner_maximum"] == 300
    assert float(s.solvers["ims_0"].params["inner_dvclose"]) == 1.00000000e-09
    assert s.solvers["ims_0"].params["linear_acceleration"] == "bicgstab"
    assert s.solvers["ims_0"].params["relaxation_factor"] == 1.00000000
    assert s.solvers["ims_0"].params["scaling_method"] == "none"
    assert s.solvers["ims_0"].params["reordering_method"] == "none"

    # test resolve
    assert np.allclose(
        strt, s.models[f"{name}"].resolve(f"sim/{name}/ic/griddata/strt")
    )
    assert nlay == s.models[f"{name}"].resolve(
        f"sim/{name}/dis/dimensions/nlay"
    )
    assert nrow == s.models[f"{name}"].resolve(
        f"sim/{name}/dis/dimensions/nrow"
    )
    assert ncol == s.models[f"{name}"].resolve(
        f"sim/{name}/dis/dimensions/ncol"
    )

    write_dir = tmp_path / "write"
    os.makedirs(write_dir)
    s.write(write_dir)


def test_gwf_chd01(tmp_path):
    name = "gwf_chd01"

    data_fpth = Path(__file__).parent / "data" / "test_gwf_chd01"
    shutil.copytree(data_fpth, tmp_path / "gwf_chd01")
    sim_fpth = Path(tmp_path / "gwf_chd01" / "mfsim.nam")

    sim = None
    with open(sim_fpth, "r") as f:
        sim = MFSimulation.load(f)

    write_dir = tmp_path / "write"
    os.makedirs(write_dir)
    sim.write(write_dir)

    w = subprocess.run(["which", "mf6"])
    if w.returncode == 0:
        os.chdir(tmp_path / "gwf_chd01")
        subprocess.run(["mf6"])
        os.chdir(write_dir)
        subprocess.run(["mf6"])
        diff = subprocess.run(
            ["diff", f"./{name}.lst", f"../gwf_chd01/{name}.lst"]
        )
        if diff.stderr:
            print(diff.stderr)
        else:
            print(f"\nmodel lst file diffs: {diff.stdout}")


def test_gwf_disv(tmp_path):
    name = "disv01a"

    data_fpth = Path(__file__).parent / "data" / "test_mf6model_0-disv01a_0"
    shutil.copytree(data_fpth, tmp_path / "disv01a")
    sim_fpth = Path(tmp_path / "disv01a" / "mfsim.nam")

    sim = None
    with open(sim_fpth, "r") as f:
        sim = MFSimulation.load(f)

    write_dir = tmp_path / "write"
    os.makedirs(write_dir)
    sim.write(write_dir)

    w = subprocess.run(["which", "mf6"])
    if w.returncode == 0:
        os.chdir(tmp_path / "disv01a")
        subprocess.run(["mf6"])
        os.chdir(write_dir)
        subprocess.run(["mf6"])
        diff = subprocess.run(
            ["diff", f"./{name}.lst", f"../disv01a/{name}.lst"]
        )
        if diff.stderr:
            print(diff.stderr)
        else:
            print(f"\nmodel lst file diffs: {diff.stdout}")


def test_gwf_disu(tmp_path):
    name = "disu01a"

    data_fpth = Path(__file__).parent / "data" / "test_mf6model_0-disu01a_0"
    shutil.copytree(data_fpth, tmp_path / "disu01a")
    sim_fpth = Path(tmp_path / "disu01a" / "mfsim.nam")

    sim = None
    with open(sim_fpth, "r") as f:
        sim = MFSimulation.load(f)

    write_dir = tmp_path / "write"
    os.makedirs(write_dir)
    sim.write(write_dir)

    w = subprocess.run(["which", "mf6"])
    if w.returncode == 0:
        os.chdir(tmp_path / "disu01a")
        subprocess.run(["mf6"])
        os.chdir(write_dir)
        subprocess.run(["mf6"])
        diff = subprocess.run(
            ["diff", f"./{name}.lst", f"../disu01a/{name}.lst"]
        )
        if diff.stderr:
            print(diff.stderr)
        else:
            print(f"\nmodel lst file diffs: {diff.stdout}")
