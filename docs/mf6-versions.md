# MF6 versions

`flopy4.mf6`'s classes are generated from MF6's definition (DFN) files, so
each set of classes matches one MF6 version. `flopy4.mf6.MF6_VERSION` says
which, and `flopy4/mf6/_contract.py` also records the DFN commit and the
generated files.

## Supported versions

flopy4 is tested against the latest MF6 release and MF6's `develop` branch
(the nightly build). A flopy4 release ships classes synced to a tagged MF6
release. Older MF6 versions usually work if you sync to them, but aren't
tested.

## Checking

`Simulation.run` warns if the MF6 executable it runs doesn't match the
synced version. To check by hand:

```
flopy4 mf6 status
```

## Syncing

To regenerate the classes for another MF6 version:

```
flopy4 mf6 sync 6.8.1              # a release
flopy4 mf6 sync develop            # the develop branch
flopy4 mf6 sync path/to/dfn        # a local DFN directory
flopy4 mf6 sync 6.8.1 --install    # also install that release's mf6
```

Or from Python, `flopy4.mf6.sync("6.8.1")`.

Sync writes into the installed `flopy4` package, so install flopy4 into a
virtual environment. A failed sync leaves the previous classes in place.
`pip install --upgrade flopy4` restores the release's classes; sync again
afterwards if you need a different MF6 version.
