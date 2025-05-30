import pytest

from flopy4.mf6.codec import JINJA_ENV, JINJA_TEMPLATE_NAME
from flopy4.mf6.gwf import Dis, Gwf, Ic, Oc


@pytest.fixture
def template():
    return JINJA_ENV.get_template(JINJA_TEMPLATE_NAME)


def test_render_ic(template):
    dis = Dis()
    gwf = Gwf(dis=dis)
    ic = Ic(
        parent=gwf,
        export_array_ascii=True,
        export_array_netcdf=True,
    )

    result = template.render(dfn=Ic.dfn, data=ic)
    print(result)
    assert result


def test_render_oc(template):
    oc = Oc(
        budget_file="test.bud",
        head_file="test.hds",
        save_head={"*": "all"},
        save_budget={"*": "all"},
        dims={"nper": 1},
    )

    result = template.render(dfn=Oc.dfn, data=oc)
    print(result)
    assert result
