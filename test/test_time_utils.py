from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from flopy4.mf6.utils.time import Time, to_timedeltas


def test_to_deltas_regular_intervals():
    # daily
    times = pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-04"])
    durations = to_timedeltas(times.values)
    assert len(durations) == 3
    assert durations == [timedelta(days=1), timedelta(days=1), timedelta(days=1)]

    # hourly
    times = pd.to_datetime(
        ["2020-01-01 00:00:00", "2020-01-01 01:00:00", "2020-01-01 02:00:00", "2020-01-01 03:00:00"]
    )
    durations = to_timedeltas(times.values)
    assert len(durations) == 3
    assert durations == [pd.Timedelta(hours=1), pd.Timedelta(hours=1), pd.Timedelta(hours=1)]


def test_to_deltas_varying_intervals():
    times = pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-05", "2020-01-10"])
    durations = to_timedeltas(times.values)
    assert len(durations) == 3
    assert durations == [pd.Timedelta(days=1), pd.Timedelta(days=3), pd.Timedelta(days=5)]

    times = pd.to_datetime(
        [
            "2020-01-01 00:00:00",
            "2020-01-01 12:30:45",
            "2020-01-02 00:00:00",
        ]
    )
    durations = to_timedeltas(times.values)
    assert len(durations) == 2
    expected_first = pd.Timedelta(hours=12, minutes=30, seconds=45)
    expected_second = pd.Timedelta(hours=11, minutes=29, seconds=15)
    assert durations == [expected_first, expected_second]


def test_to_deltas_cross_month_boundaries():
    times = pd.to_datetime(
        [
            "2020-01-31",
            "2020-02-01",
            "2020-02-29",
            "2020-03-01",
        ]
    )
    durations = to_timedeltas(times.values)
    assert len(durations) == 3
    assert durations == [pd.Timedelta(days=1), pd.Timedelta(days=28), pd.Timedelta(days=1)]


def test_leap_year_vs_regular_year():
    # Leap year
    times_leap = pd.to_datetime(["2020-02-01", "2020-03-01"])
    durations_leap = to_timedeltas(times_leap.values)

    # Regular year
    times_regular = pd.to_datetime(["2021-02-01", "2021-03-01"])
    durations_regular = to_timedeltas(times_regular.values)

    assert durations_leap[0] == pd.Timedelta(days=29)
    assert durations_regular[0] == pd.Timedelta(days=28)


def test_to_deltas_empty_with_less_than_2_items():
    times = pd.to_datetime(["2020-01-01"])
    assert not any(to_timedeltas(times.values))

    times = pd.to_datetime([])
    assert not any(to_timedeltas(times.values))


def test_time_from_timestamps_basic():
    times = pd.to_datetime(["2020-01-01", "2020-01-05", "2020-01-15", "2020-02-01"])
    time = Time.from_timestamps(times)

    assert time.nper == 3
    assert time.time_units == "days"
    assert time.start_datetime == pd.Timestamp("2020-01-01").to_pydatetime()
    np.testing.assert_array_equal(time.perlen, [4.0, 10.0, 17.0])
    np.testing.assert_array_equal(time.nstp, [1, 1, 1])
    np.testing.assert_array_equal(time.tsmult, [1.0, 1.0, 1.0])


def test_time_from_timestamps_with_duplicates():
    times = np.array(["2020-01-01", "2020-01-05", "2020-01-01", "2020-01-10", "2020-01-05"])
    time = Time.from_timestamps(times)

    assert time.nper == 2
    np.testing.assert_array_equal(time.perlen, [4.0, 5.0])


def test_time_from_timestamps_single_timestamp():
    times = pd.to_datetime(["2020-01-01"])

    with pytest.raises(ValueError, match="at least two timestamps"):
        Time.from_timestamps(times)


def test_time_from_timestamps_realistic_scenario():
    times = np.hstack(
        [
            pd.date_range("2020-01-01", periods=12, freq="MS"),
            pd.to_datetime(["2020-03-15", "2020-06-15", "2020-09-15"]),
        ]
    )
    time = Time.from_timestamps(times)

    assert time.nper == 14  # 12 months + 3 mid-month splits - 1
    assert time.time_units == "days"
    assert time.start_datetime.year == 2020
    assert time.start_datetime.month == 1
    assert time.start_datetime.day == 1


def test_time_from_timestamps_with_nstp_scalar():
    times = pd.to_datetime(["2020-01-01", "2020-01-05", "2020-01-15"])
    time = Time.from_timestamps(times, nstp=10)

    assert time.nper == 2
    np.testing.assert_array_equal(time.nstp, [10, 10])
    np.testing.assert_array_equal(time.tsmult, [1.0, 1.0])


def test_time_from_timestamps_with_nstp_array():
    times = pd.to_datetime(["2020-01-01", "2020-01-05", "2020-01-15", "2020-02-01"])
    time = Time.from_timestamps(times, nstp=[5, 10, 20])

    assert time.nper == 3
    np.testing.assert_array_equal(time.nstp, [5, 10, 20])
    np.testing.assert_array_equal(time.tsmult, [1.0, 1.0, 1.0])


def test_time_from_timestamps_with_tsmult_scalar():
    times = pd.to_datetime(["2020-01-01", "2020-01-05", "2020-01-15"])
    time = Time.from_timestamps(times, nstp=10, tsmult=1.5)

    assert time.nper == 2
    np.testing.assert_array_equal(time.nstp, [10, 10])
    np.testing.assert_array_equal(time.tsmult, [1.5, 1.5])


def test_time_from_timestamps_with_tsmult_array():
    times = pd.to_datetime(["2020-01-01", "2020-01-05", "2020-01-15", "2020-02-01"])
    time = Time.from_timestamps(times, tsmult=[1.0, 1.2, 1.5])

    assert time.nper == 3
    np.testing.assert_array_equal(time.nstp, [1, 1, 1])
    np.testing.assert_array_equal(time.tsmult, [1.0, 1.2, 1.5])


def test_time_from_timestamps_with_both_arrays():
    times = pd.to_datetime(["2020-01-01", "2020-01-05", "2020-01-15", "2020-02-01"])
    time = Time.from_timestamps(times, nstp=[5, 10, 20], tsmult=[1.0, 1.2, 1.5])

    assert time.nper == 3
    np.testing.assert_array_equal(time.nstp, [5, 10, 20])
    np.testing.assert_array_equal(time.tsmult, [1.0, 1.2, 1.5])


def test_time_from_timestamps_nstp_length_mismatch():
    times = pd.to_datetime(["2020-01-01", "2020-01-05", "2020-01-15"])

    with pytest.raises(ValueError, match="nstp length"):
        Time.from_timestamps(times, nstp=[5, 10, 20])


def test_time_from_timestamps_tsmult_length_mismatch():
    timestamps = pd.to_datetime(["2020-01-01", "2020-01-05", "2020-01-15"])

    with pytest.raises(ValueError, match="tsmult length"):
        Time.from_timestamps(timestamps, tsmult=[1.0, 1.2, 1.5])
