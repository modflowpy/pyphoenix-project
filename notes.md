# todo
- maybe store scalars as xarray attrs?
- quickstart notebook with readme example
- demo notebook explaining how it works
    - compare/contrast implementations
    - attrs vs xarray access pattern
- translate more examples to new pattern
    - emphasize friction points
    - inspiration from imod examples
- component access patterns 
    - dict style: subcomponents by name, e.g. `gwf["chd1"]`
    - attr style: subcomponents by type, e.g. `gwf.chd` as list of CHD packages
- define base component types as dfns?
    - distinguish abstract vs concrete dfn
    - some concept of dfn inheritance
        - e.g. models and exchanges have their own variables
          which all concrete model and exchanges types should
          inherit, not so for simulations and packages though
