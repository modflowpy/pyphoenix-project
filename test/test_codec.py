import pytest

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

    # TODO figure out how to adapt simulation_data
    # and get this working, then compare results?
    # old_gwf = Flopy3Model(model=gwf)
    # old_ic = ModflowGwfic(
    #     old_gwf,
    #     save_flows=True,
    #     save_initial_conditions=True,
    #     export_array_ascii=True,
    #     export_array_netcdf=True,
    # )

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


@pytest.mark.skip(reason="TODO 3D arrays")
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
