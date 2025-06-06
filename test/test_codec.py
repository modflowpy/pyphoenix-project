from flopy4.mf6.codec import dumps


def test_dumps_ic():
    from flopy4.mf6.gwf import Dis, Gwf, Ic

    dis = Dis()
    gwf = Gwf(dis=dis)
    ic = Ic(
        parent=gwf,
        export_array_ascii=True,
        export_array_netcdf=True,
    )

    result = dumps(ic)
    print(result)
    assert result


def test_dumps_oc():
    from flopy4.mf6.gwf import Oc

    oc = Oc(
        budget_file="test.bud",
        head_file="test.hds",
        save_head={"*": "all"},
        save_budget={"*": "all"},
        dims={"nper": 1},
    )

    result = dumps(oc)
    print(result)
    assert result


def test_dumps_dis():
    from flopy4.mf6.gwf import Dis

    dis = Dis(
        nlay=1,
        nrow=10,
        ncol=10,
        delr=100.0,
        delc=100.0,
        idomain=1,
        length_units="feet",
    )

    result = dumps(dis)
    print(result)
    assert result


def test_dumps_tdis():
    from flopy.discretization.modeltime import ModelTime

    from flopy4.mf6.tdis import Tdis

    tdis = Tdis.from_time(ModelTime(perlen=[1.0, 2.0], nstp=[1, 2]))
    tdis.time_units = "days"

    result = dumps(tdis)
    print(result)
    assert result


def test_dumps_chd():
    from flopy4.mf6.gwf import Chd, Dis, Gwf

    dis = Dis(nrow=10, ncol=10)
    gwf = Gwf(dis=dis)
    chd = Chd(
        parent=gwf,
        head={
            0: {
                (0, 0, 0): 10.0,
                (0, 9, 9): 20.0,
            }
        },
        save_flows=True,
        print_input=True,
        dims={"nper": 1},
    )

    result = dumps(chd)
    print(result)
    assert result
