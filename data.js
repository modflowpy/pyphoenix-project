window.BENCHMARK_DATA = {
  "lastUpdate": 1793136987280,
  "repoUrl": "https://github.com/modflowpy/pyphoenix-project",
  "entries": {
    "flopy4 benchmarks": [
      {
        "commit": {
          "author": {
            "name": "wpbonelli",
            "username": "wpbonelli",
            "email": "wbonelli@ucar.edu"
          },
          "committer": {
            "name": "GitHub",
            "username": "web-flow",
            "email": "noreply@github.com"
          },
          "id": "c045de0424241604c0d2cc3a67eee76bd7d621cb",
          "message": "refactoring binary file loader, follow MF6 IDM (#514)\n\nSome refactoring\n\n* build the external binary file list row spec from the same column classification the text reader uses, instead of a separate field walk, so the two paths can't disagree on field order or kind\n* read the file with one np.frombuffer call instead of a loop\n\nAnd follow MF6, specifically IDM's StructArray%read_from_binary, on some things:\n\n* reject binary input when BOUNDNAMES puts a text column in the row\n* drop a partial trailing row rather than raising\n* don't require a cellid column\n\nFollowup to #511 and #512",
          "timestamp": "2026-10-27T21:34:03Z",
          "url": "https://github.com/modflowpy/pyphoenix-project/commit/c045de0424241604c0d2cc3a67eee76bd7d621cb"
        },
        "date": 1793136985278,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "load (smoke): flopy4",
            "value": 0.06331237499999531,
            "unit": "s",
            "extra": "AMD EPYC 9V74 80-Core Processor, Linux, Python 3.11.16"
          },
          {
            "name": "load (smoke): flopy4 / flopy3",
            "value": 0.2874419867716803,
            "unit": "ratio",
            "extra": "AMD EPYC 9V74 80-Core Processor, Linux, Python 3.11.16"
          },
          {
            "name": "load (standard): flopy4",
            "value": 0.2957782649999956,
            "unit": "s",
            "extra": "AMD EPYC 9V74 80-Core Processor, Linux, Python 3.11.16"
          },
          {
            "name": "load (standard): flopy4 / flopy3",
            "value": 0.2847417101970213,
            "unit": "ratio",
            "extra": "AMD EPYC 9V74 80-Core Processor, Linux, Python 3.11.16"
          },
          {
            "name": "load (large): flopy4",
            "value": 6.4553199179999865,
            "unit": "s",
            "extra": "AMD EPYC 9V74 80-Core Processor, Linux, Python 3.11.16"
          },
          {
            "name": "load (large): flopy4 / flopy3",
            "value": 0.2739360585245829,
            "unit": "ratio",
            "extra": "AMD EPYC 9V74 80-Core Processor, Linux, Python 3.11.16"
          },
          {
            "name": "load-materialize (smoke): flopy4",
            "value": 0.06957334000000515,
            "unit": "s",
            "extra": "AMD EPYC 9V74 80-Core Processor, Linux, Python 3.11.16"
          },
          {
            "name": "load-materialize (smoke): flopy4 / flopy3",
            "value": 0.2945820830356303,
            "unit": "ratio",
            "extra": "AMD EPYC 9V74 80-Core Processor, Linux, Python 3.11.16"
          },
          {
            "name": "load-materialize (standard): flopy4",
            "value": 0.36265457300000037,
            "unit": "s",
            "extra": "AMD EPYC 9V74 80-Core Processor, Linux, Python 3.11.16"
          },
          {
            "name": "load-materialize (standard): flopy4 / flopy3",
            "value": 0.23985015409538235,
            "unit": "ratio",
            "extra": "AMD EPYC 9V74 80-Core Processor, Linux, Python 3.11.16"
          },
          {
            "name": "load-materialize (large): flopy4",
            "value": 8.480395589000011,
            "unit": "s",
            "extra": "AMD EPYC 9V74 80-Core Processor, Linux, Python 3.11.16"
          },
          {
            "name": "load-materialize (large): flopy4 / flopy3",
            "value": 0.32738824406952866,
            "unit": "ratio",
            "extra": "AMD EPYC 9V74 80-Core Processor, Linux, Python 3.11.16"
          },
          {
            "name": "write (smoke): flopy4",
            "value": 0.09616814799998963,
            "unit": "s",
            "extra": "AMD EPYC 9V74 80-Core Processor, Linux, Python 3.11.16"
          },
          {
            "name": "write (smoke): flopy4 / flopy3",
            "value": 0.47410534347366734,
            "unit": "ratio",
            "extra": "AMD EPYC 9V74 80-Core Processor, Linux, Python 3.11.16"
          },
          {
            "name": "write (standard): flopy4",
            "value": 0.7625356850000173,
            "unit": "s",
            "extra": "AMD EPYC 9V74 80-Core Processor, Linux, Python 3.11.16"
          },
          {
            "name": "write (standard): flopy4 / flopy3",
            "value": 0.2899661302326354,
            "unit": "ratio",
            "extra": "AMD EPYC 9V74 80-Core Processor, Linux, Python 3.11.16"
          },
          {
            "name": "write (large): flopy4",
            "value": 10.713131043999965,
            "unit": "s",
            "extra": "AMD EPYC 9V74 80-Core Processor, Linux, Python 3.11.16"
          },
          {
            "name": "write (large): flopy4 / flopy3",
            "value": 0.37727099146418286,
            "unit": "ratio",
            "extra": "AMD EPYC 9V74 80-Core Processor, Linux, Python 3.11.16"
          },
          {
            "name": "cold start: flopy4",
            "value": 1.0416458579999954,
            "unit": "s",
            "extra": "AMD EPYC 9V74 80-Core Processor, Linux, Python 3.11.16"
          }
        ]
      }
    ]
  }
}