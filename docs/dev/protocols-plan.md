# Dimension Resolution Refactor Plan

## Design

Lazy runtime resolution instead of eager registration. No pre-registration of dimension providers. Resolution by walking object graph on-demand when dimensions are needed. Parent references enable walking up the hierarchy. Results cached after resolution.

This supports both cattrs (top-down) and interactive (bottom-up) construction. It's simpler than xattree, no global state to manage. It's construction order agnostic, it works regardless when children are added.

## Migration

The new dimension stuff doesn't depend on xattree specifics. Protocols provide a clean abstraction boundary. Protocols and mixins can wrap existing xattree features (e.g. .parent) and implement dimension resolution on top of xattree's parent management. Later, we can swap the parent implementation.

At first, components can keep @xattree decorator. DimensionRegistryMixin can use @define, Component can stay @xattree.

Later, when migrating parent management:
- Remove @xattree decorator from Component
- Add explicit _parent field and @property to Component
- Enable _set_child_parents() to actually set parent references
- Enable ParentSettingDict for interactive construction
- Remove xattree dimension fallback from _resolve_dimensions()

## Implementation

Dimension resolution works via two protocols:

- DimensionProvider: Components that provide dimensions to consumers
- DimensionRegistry: Components that store dimensions from providers

**Note**: The mixin must be an attrs class (@define) so it can define its own fields.

On first use, registries resolve dimensions by lazily walking the object graph.

The resolution order is:
1. Check cache
2. Walk children, find DimensionProviders
3. If not found, delegate to parent
4. Cache result
          
Grid and time discretization package implement `DimensionProvider` for both explicit (defined in DFNs, e.g. `nlay`) and derived (e.g. referenced in DFNs but not explicitly defined, e.g. `nodes`) dimensions

The base `Component` class implements `DimensionRegistry`.

During migration, component classes inherits dimension resolution methods from the mixin. At first, parent continues to come from the @xattree decorator. Eventually we can migrate the parent management and other xattree features and switch `Component` to @define. At that point the component could manage its own parent, with a custom setter to invalidate the dimension cache when the parent is modified.

Making all components dimension registries is simple and uniform: all components work the same way. No need to track which components "should" be registries. Any component can resolve dimensions.

Concretely, this means Gwf automatically resolves from Dis/Disv/Disu children, delegates to Simulation parent. Simulation automatically resolves from Tdis, model children. Packages get registry behavior, where it it's unused but harmless.

After we've migrated parent management, the DimensionRegistryMixin.__attrs_post_init__ method will set parent references on all children after construction (both cattrs and manual). Interactive construction via dict syntax can be supported with a custom dict that attaches parents to children. This can be used to wrap the packages dict in model subclasses' post init hook. Similarly for Simulation and models.

This allows natural interactive construction:

  ic = Ic(strt=...)
  gwf = Gwf(dis=Dis(...))
  gwf.packages['ic'] = ic  # parent is automatically set to gwf

**Note**: Only container classes with dict fields need to wrap them. Leaf classes don't need to override __attrs_post_init__ at all.

There is potential for dimension conflicts if multiple providers declare the same dimensions.

We check for conflicts eagerly and raise error on first access.
This catches configuration errors early.

For development/testing, provide an optional validation function:

  def validate_dimension_resolution(component: Component) -> list[str]:
      """Validate that all array fields can resolve their required dimensions.

      Returns list of error messages for dimensions that cannot be resolved.
      Use in tests or CI to catch missing dimension providers.
      """
      errors = []

      for field in attrs.fields(type(component)):
          if hasattr(field.metadata, 'get') and 'dims' in field.metadata:
              for dim in field.metadata['dims']:
                  if hasattr(component, 'parent') and component.parent:
                      if component.parent.resolve_dimension(dim) is None:
                          errors.append(
                              f"{type(component).__name__}.{field.name} needs dimension '{dim}' "
                              f"but it's not available in parent hierarchy"
                          )

      # Recursively validate children
      for field in attrs.fields(type(component)):
          value = getattr(component, field.name, None)
          if isinstance(value, Component):
              errors.extend(validate_dimension_resolution(value))
          elif isinstance(value, dict):
              for child in value.values():
                  if isinstance(child, Component):
                      errors.extend(validate_dimension_resolution(child))

      return errors

## Progress

### Phase 1-2: Complete

  **Add Protocols and Mixins** - DONE
  - Created flopy4/mf6/dimensions.py with:
    - DimensionProvider protocol
    - DimensionRegistry protocol
    - DimensionRegistryMixin (@xattree class with _dimension_cache field)
    - _set_child_parents() stubbed for Phase 3
  - Unit tests in test/test_mf6_dimensions.py
  - Zero changes to existing code outside of new functionality

  **Apply Mixin to Component** - DONE
  - Component inherits from DimensionRegistryMixin while keeping @xattree
  - Component gains _dimension_cache field and resolution methods
  - All components now have resolve_dimension() and get_all_dimensions()
  - Integration tests show dimension resolution works via parent hierarchy
  - All existing tests pass

  **Implement Dimension Providers** - DONE
  - Dis.get_dimensions() returns nlay, nrow, ncol, nodes, ncpl
  - Tdis.get_dimensions() returns nper
  - Both compute derived dimensions correctly

  **Comprehensive Testing** - DONE
  - Unit tests for DimensionRegistryMixin in isolation (mock components)
  - Unit tests for Dis and Tdis get_dimensions()
  - Integration tests for Gwf → Dis dimension resolution
  - Integration tests for Simulation → Tdis dimension resolution
  - Integration tests for Model accessing both grid and time dimensions
  - Caching tests
  - All tests passing

### Phase 3: Complete ✅

  **Integrate with _resolve_dimensions** - DONE ✅
  - Updated _resolve_dimensions() in structure.py:
    - Uses parent.resolve_dims() (new path)
    - Removed xattree fallback - cleaner, simpler code
  - Updated resolve_dims() to include parent dimensions (walks up hierarchy)
  - Tests: All 207 non-integration tests pass

  **Validation** - DONE ✅
  - Added conflict detection in resolve_dims()
    - Detects conflicts among children at same level
    - Allows children to override parent dimensions
  - Added validate_dimension_resolution() validation tool in dimensions.py

  **Implement Disv DimensionProvider** - DONE ✅
  - Added get_dims() to Disv class
  - Returns nlay, ncpl, nvert, and computed nodes dimension
  - All Disv-related tests now pass

  **API Refinements** - DONE ✅
  - Renamed: DimensionRegistry → DimensionResolver
  - Renamed: DimensionRegistryMixin → DimensionResolverMixin
  - Renamed: get_dimensions() → get_dims()
  - Unified API: resolve_dimension() + get_all_dimensions() → resolve_dims()
  - resolve_dims() always returns dict for consistency:
    - `resolve_dims()` → all available dimensions
    - `resolve_dims('nlay')` → `{'nlay': 3}`
    - `resolve_dims('nlay', 'nrow')` → `{'nlay': 3, 'nrow': 10}`

  **ParentSettingDict** - NOT DONE
  - Not yet implemented
  - Deferred to Phase 4 (parent management migration)

### Phase 4: Future Work

  **Parent Management Migration**
  - Remove @xattree decorator from Component
  - Add explicit _parent field and @property to Component
  - Enable _set_child_parents() implementation in mixin
  - Update Gwf/Simulation to use ParentSettingDict
  - Remove xattree fallback from _resolve_dimensions()
  - Remove computed dimension fallback
  - All tests must pass without xattree

  **Optional Future Work:**
  - Add logging/debugging for resolution paths
  - Document interactive construction pattern in user guide

## Testing

  Unit tests:
  - Test each DimensionProvider.get_dimensions() returns correct dims
  - Test computed dimensions (nodes, etc.) calculated correctly
  - Test DimensionRegistry.resolve_dimension() walks tree correctly
  - Test DimensionRegistry.get_all_dimensions() aggregates children
  - Test hierarchical resolution (IC needs nlay → checks Gwf → finds Dis)
  - Test caching: second resolution doesn't re-walk tree
  - Test parent setting in __attrs_post_init__ (cattrs path)

  Integration tests:
  - Load real simulations with structured grids (Dis)
  - Load real simulations with unstructured grids (Disu)
  - Load real simulations with vertex grids (Disv)
  - Verify packages can resolve dimensions from parent model
  - Verify transient packages can access nper from Tdis through Simulation
  - Test interactive construction (bottom-up):
    - Create components separately
    - Assemble into hierarchy
    - Set parent references manually
    - Verify dimension resolution works

  Edge cases:
  - Unstructured grid (Disu): provides nodes but not nrow/ncol
  - Multiple models: Each model's packages see only their model's grid dims, not sibling models
  - Missing dimensions: Clear error messages indicating which component should provide them
  - Dimension conflicts: Error if multiple providers at same level provide same dimension
  - None fields: Fields that are None don't break parent setting or resolution
  - Empty collections: Empty packages dict doesn't break resolution

  Error Message Quality:

  When dimension not found:
  "Package IC.strt needs dimension 'nlay' but it's not available in parent hierarchy.
   Parent Gwf provides: []
   Expected: Gwf should contain one of: Dis (nlay/nrow/ncol), Disv (nlay/ncpl), Disu (nodes)"

  When dimension conflict detected:
  "Gwf has multiple providers for dimensions: {'nlay', 'nrow'}.
   Field 'dis' provides nlay/nrow/ncol, already provided by field 'disv'."

## Motivations

  - No global state: Dimension resolution purely through object graph
  - Type-safe: Protocols enable static type checking of dimension provider/consumer contracts
  - Debuggable: Clear ownership and resolution path, can log resolution walk
  - Extensible: New dimension providers just implement DimensionProvider protocol
  - Construction-order agnostic: Works regardless of child construction order
  - Supports both construction patterns: cattrs (top-down) and interactive (bottom-up)
  - Performance: Caching prevents repeated tree walking
  - Simple implementation: No metaclasses, decorators, or global registries
  - Framework agnostic: Works with attrs, pydantic, dataclasses
  - Testable: Can validate dimension resolution in tests without static analysis

## Notes

Computed Dimensions

  Computed dimensions are those referenced in dims=(...) but not explicitly defined
  as dimension fields in grid components. These must be calculated in get_dimensions().

  From analyzing existing flopy4 components:

  Dis (structured grid) computes:
  - nodes = nlay * nrow * ncol
  - ncpl = nrow * ncol

  Disv (vertex grid) will compute:
  - nodes = nlay * ncpl
  (ncpl is explicit in Disv)

  Disu (unstructured grid):
  - nodes is explicit, not computed

  These computed dimensions appear frequently in package dims:
  - nodes: Used in IC, NPF, STO, and most packages for grid-based arrays
  - ncpl: Used for 2D arrays on a single layer

  Implementation note: Each grid component's get_dimensions() must return both
  explicit dimensions (nlay, nrow, ncol, nper) and computed dimensions (nodes, ncpl).
