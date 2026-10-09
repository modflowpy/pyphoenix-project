import attrs
import pytest


def _maw_strt_takes_ts() -> bool:
    from flopy4.mf6.gwf.maw import Maw

    return bool(attrs.fields_dict(Maw.Packagedata)["strt"].metadata.get("time_series"))


# Models that MF6 runs but whose input some released DFNs don't describe,
# with a check of the synced classes for what each model needs. Checked
# against the classes, not the MF6 version, so a model runs again once a
# release's DFNs describe it.
SPEC_GAPS = {
    "mf6/test/test020_NevilleTonkinTransient_constantMAW": (
        _maw_strt_takes_ts,
        "MAW strt is a time series, which DFNs before MF6 #2748 don't declare",
    ),
}


def pytest_collection_modifyitems(items):
    unmet = {model: reason for model, (check, reason) in SPEC_GAPS.items() if not check()}
    for item in items:
        callspec = getattr(item, "callspec", None)
        model = callspec.params.get("model_name") if callspec else None
        if model in unmet:
            item.add_marker(pytest.mark.skip(reason=unmet[model]))
