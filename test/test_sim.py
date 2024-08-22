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
        f.write("END GRIDDATA\nn\\n")

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
        # f.write("  inner_rclose  1.00000000E-06\n")
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

    # test resolve
    with open(sim_fpth, "r") as f:
        s = MFSimulation.load(f)
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
