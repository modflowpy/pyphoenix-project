# Dimension Resolution Refactor Plan

> **Note**: The dimension resolution architecture has been consolidated into the main design document. See the **Object Model > Data Model** section in [`sdd.md`](./sdd.md) for the current architectural design. This document remains as an implementation plan and progress tracker.

---

## Context: Prototyping xattree v2

**This work is prototyping what will become xattree v2.0.** The current xattree library has fundamental architectural flaws (data hijacking, `__getattr__` proxying, can't use slots). Rather than rewrite xattree speculatively, we're proving the new design here in pyphoenix/flopy4 first.

**Strategy**: Build dimension resolution + translation layer in pyphoenix → prove it works with complex MF6 models → extract patterns back to xattree as a clean translation library.

**What pyphoenix proves**:
- Protocol-based dimension resolution (no global state, no magic)
- Hierarchical delegation (simpler than xattree's `scope=ROOT`)
- Translation layer (`to_datatree()` / `from_datatree()` instead of fusion)
- Works with normal attrs classes (no `__dict__` hijacking)

**Timeline**: Once pyphoenix removes xattree dependency (Phase 4), extract proven patterns to xattree v2.0 (Phase 5).

See `xattree/PIVOT_PLAN.md` for the full xattree v2 vision.

---

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

  **3c. Validation** - NOT DONE
  - Add conflict detection in get_all_dimensions()
  - Add optional validate_dimension_resolution() tool

### Phase 3.5: Hierarchy Infrastructure (Preparation for Phase 4)

  **Create flopy4/mf6/hierarchy.py module**
  - New module for parent/child relationship management
  - Consolidates tree structure utilities separate from dimension resolution

  **Implement ParentSettingDict**
  - Custom dict class that auto-sets parent references on assignment
  - Signature: `ParentSettingDict(parent: Component, data: dict[str, Component] = None)`
  - On `__setitem__`: sets `child._parent = parent` and invalidates parent's dimension cache
  - On `__delitem__`: sets `child._parent = None` and invalidates parent's dimension cache
  - Handles both initial construction (via data param) and interactive updates
  - Enables natural interactive construction: `gwf.packages['ic'] = ic`

  **Cache invalidation helpers**
  - `invalidate_dimension_cache(component: Component)`: Clear _dimension_cache
  - Start with aggressive invalidation (any parent/child change clears cache)
  - Later can refine to check if changed component is DimensionProvider

  **Child iteration strategy**
  - Add `_iter_children() -> Iterator[Component]` helper function
  - Walks attrs fields, yields Component instances
  - Handles both single Component fields and dict[str, Component] fields
  - Used by dimension resolution and MutableMapping implementation

  **Tests**:
  - Test ParentSettingDict sets parent on assignment
  - Test ParentSettingDict invalidates cache on add/delete
  - Test _iter_children() finds all child components
  - Test cache invalidation propagates correctly

### Phase 4: pyphoenix xattree Removal

  **4a. DataTree Conversion Layer**
  - Add DataTreeConvertible protocol in dimensions.py (or new module)
  - Protocol defines: `to_datatree() -> DataTree`, `from_datatree(dt: DataTree) -> Self`
  - Implement to_datatree() method on Component base class
  - Implement from_datatree() classmethod on Component base class
  - Replaces xattree's `.data` attribute and fusion model
  - Used exclusively for NetCDF I/O in Phase 4

  **4b. Replace MutableMapping Implementation**
  - Component currently implements MutableMapping via xattree's `self.children`
  - Replace with our own implementation using `_iter_children()`:
    - `__iter__`: yield from `_iter_children()`
    - `__getitem__`: search children by name, raise KeyError if not found
    - `__setitem__`: set child field, call ParentSettingDict logic for parent binding
    - `__delitem__`: delete child field, invalidate cache
    - `__len__`: count children from `_iter_children()`
  - Preserves existing MutableMapping API for backward compatibility
  - Note: Component.children dict concept goes away, replaced by field introspection

  **4c. Parent Management**
  - Remove @xattree decorator from Component
  - Switch Component to @define
  - Add explicit `_parent: Optional[Component] = None` field (private)
  - Add `@property parent` with custom setter:
    - Setter invalidates dimension cache when parent changes
    - Enables both cattrs construction and interactive assignment
  - Enable _set_child_parents() implementation in DimensionRegistryMixin
  - Update Gwf/Simulation.__attrs_post_init__ to wrap packages dict:
    - `self.packages = ParentSettingDict(parent=self, data=self.packages)`
  - Similarly for Simulation.models dict

  **4d. Final Cleanup**
  - Remove xattree imports from all files
  - Remove xattree fallback from _resolve_dimensions() (already done in Phase 3)
  - Remove computed dimension fallback (if any)
  - Delete xattree from pyproject.toml dependencies
  - Update Component docstring (remove "must be decorated with xattree" note)
  - **All tests must pass without xattree**

  **Success Criteria**:
  - No xattree imports anywhere in flopy4
  - All existing tests pass (unit + integration)
  - Can load/save complex MF6 models via NetCDF using to_datatree()/from_datatree()
  - Normal Python objects (data in `__dict__`, can use `slots=True`)
  - Dimension resolution works for both cattrs and interactive construction
  - Parent references maintained correctly in all scenarios

### Phase 5: Extract to xattree v2

  **Extract Proven Patterns** (Future)
  - Copy protocols from flopy4/mf6/dimensions.py to xattree
  - Copy conversion logic from DataTreeConvertible
  - Generalize (remove MF6-specific code)
  - Add multi-backend support (attrs, dataclasses, pydantic)
  - Add specification system from old xattree (metadata parsing)
  - Comprehensive tests (not MF6-specific)
  - Documentation and examples
  - Release xattree v2.0
  - pyphoenix becomes reference implementation

  **Optional Future Work:**
  - Add logging/debugging for resolution paths
  - Document interactive construction pattern in user guide
  - Array backends (numpy, jax, torch)?

## Testing

  Unit tests (Phases 1-3):
  - Test each DimensionProvider.get_dimensions() returns correct dims
  - Test computed dimensions (nodes, etc.) calculated correctly
  - Test DimensionRegistry.resolve_dimension() walks tree correctly
  - Test DimensionRegistry.get_all_dimensions() aggregates children
  - Test hierarchical resolution (IC needs nlay → checks Gwf → finds Dis)
  - Test caching: second resolution doesn't re-walk tree
  - Test parent setting in __attrs_post_init__ (cattrs path)

  Unit tests (Phase 3.5 - hierarchy.py):
  - Test ParentSettingDict sets parent reference on __setitem__
  - Test ParentSettingDict invalidates parent cache on __setitem__
  - Test ParentSettingDict invalidates parent cache on __delitem__
  - Test ParentSettingDict handles initial data dict in constructor
  - Test _iter_children() finds single Component fields
  - Test _iter_children() finds Component instances in dict fields
  - Test _iter_children() skips non-Component fields
  - Test _iter_children() handles None fields gracefully
  - Test invalidate_dimension_cache() clears cache
  - Test cache invalidation propagates up parent chain (future refinement)

  Unit tests (Phase 4 - xattree removal):
  - Test Component._parent field can be set and retrieved
  - Test Component.parent property setter invalidates cache
  - Test Component MutableMapping __iter__ iterates all children
  - Test Component MutableMapping __getitem__ finds child by name
  - Test Component MutableMapping __setitem__ sets parent reference
  - Test Component MutableMapping __delitem__ removes child and invalidates cache
  - Test Component MutableMapping __len__ counts children correctly
  - Test to_datatree() creates correct DataTree structure
  - Test from_datatree() reconstructs Component from DataTree
  - Test to_datatree() → from_datatree() roundtrip preserves data
  - Test _set_child_parents() walks all children and sets parent refs

  Integration tests:
  - Load real simulations with structured grids (Dis)
  - Load real simulations with unstructured grids (Disu)
  - Load real simulations with vertex grids (Disv)
  - Verify packages can resolve dimensions from parent model
  - Verify transient packages can access nper from Tdis through Simulation
  - Test interactive construction (bottom-up):
    - Create components separately
    - Assemble into hierarchy via ParentSettingDict
    - Verify dimension resolution works after assembly
    - Test: gwf.packages['ic'] = ic automatically sets ic.parent = gwf
  - Test cattrs construction (top-down):
    - Load from dict/file via cattrs
    - Verify parent references set in __attrs_post_init__
    - Verify dimension resolution works immediately after load
  - Test NetCDF I/O via to_datatree()/from_datatree():
    - Save model to NetCDF using to_datatree()
    - Load model from NetCDF using from_datatree()
    - Verify all data preserved (arrays, dimensions, metadata)

  Edge cases:
  - Unstructured grid (Disu): provides nodes but not nrow/ncol
  - Multiple models: Each model's packages see only their model's grid dims, not sibling models
  - Missing dimensions: Clear error messages indicating which component should provide them
  - Dimension conflicts: Error if multiple providers at same level provide same dimension
  - None fields: Fields that are None don't break parent setting or resolution
  - Empty collections: Empty packages dict doesn't break resolution
  - Orphan components: Components without parent don't crash when resolving dims
  - Reparenting: Moving component from one parent to another invalidates both caches
  - Dict field updates: Modifying packages dict after construction maintains parent refs

  Error Message Quality:

  When dimension not found:
  "Package IC.strt needs dimension 'nlay' but it's not available in parent hierarchy.
   Parent Gwf provides: []
   Expected: Gwf should contain one of: Dis (nlay/nrow/ncol), Disv (nlay/ncpl), Disu (nodes)"

  When dimension conflict detected:
  "Gwf has multiple providers for dimensions: {'nlay', 'nrow'}.
   Field 'dis' provides nlay/nrow/ncol, already provided by field 'disv'."

## Motivations

**For pyphoenix/flopy4**:
  - No global state: Dimension resolution purely through object graph
  - Type-safe: Protocols enable static type checking of dimension provider/consumer contracts
  - Debuggable: Clear ownership and resolution path, can log resolution walk
  - Extensible: New dimension providers just implement DimensionProvider protocol
  - Construction-order agnostic: Works regardless of child construction order
  - Supports both construction patterns: cattrs (top-down) and interactive (bottom-up)
  - Performance: Caching prevents repeated tree walking
  - Normal Python objects: Data in `__dict__`, fast attribute access, can use `slots=True`

**For xattree v2 (extraction target)**:
  - Simple implementation: No metaclasses, decorators, or global registries
  - Framework agnostic: Works with attrs, pydantic, dataclasses
  - Testable: Can validate dimension resolution in tests without static analysis
  - Explicit conversion: `to_datatree()` / `from_datatree()` instead of magic `.data`
  - Proven design: Validated by complex real-world use (MF6 models)

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

Child Iteration and MutableMapping

  **Current implementation** (with xattree):
  Component inherits from MutableMapping and delegates to xattree's `self.children` dict:
  - `__getitem__`, `__setitem__`, `__delitem__`, `__iter__`, `__len__`
  - xattree automatically populates `self.children` with child components
  - Works but requires xattree's magic field introspection

  **New implementation** (Phase 4, without xattree):
  Replace xattree's `self.children` with explicit field introspection:

  ```python
  def _iter_children(self) -> Iterator[tuple[str, Component]]:
      """Iterate over (name, child) pairs for all child components.

      Discovers children by walking attrs fields:
      - Single Component fields: yield (field_name, component)
      - Dict fields: yield (key, component) for each Component in dict
      - Skips None values and non-Component fields
      """
      for field in attrs.fields(type(self)):
          value = getattr(self, field.name, None)
          if value is None:
              continue
          if isinstance(value, Component):
              yield (field.name, value)
          elif isinstance(value, dict):
              for key, child in value.items():
                  if isinstance(child, Component):
                      yield (key, child)

  def __iter__(self):
      """Iterate over child component names."""
      return (name for name, _ in self._iter_children())

  def __getitem__(self, key: str) -> Component:
      """Get child component by name."""
      for name, child in self._iter_children():
          if name == key:
              return child
      raise KeyError(f"No child component named '{key}'")

  def __setitem__(self, key: str, value: Component):
      """Set child component, auto-setting parent reference."""
      # Find appropriate dict field to add to (e.g., packages)
      for field in attrs.fields(type(self)):
          field_value = getattr(self, field.name, None)
          if isinstance(field_value, dict):
              field_value[key] = value
              value._parent = self
              invalidate_dimension_cache(self)
              return
      raise AttributeError(f"No dict field available to add child '{key}'")

  def __delitem__(self, key: str):
      """Remove child component."""
      for field in attrs.fields(type(self)):
          value = getattr(self, field.name, None)
          if isinstance(value, dict) and key in value:
              child = value[key]
              del value[key]
              child._parent = None
              invalidate_dimension_cache(self)
              return
      raise KeyError(f"No child component named '{key}'")

  def __len__(self):
      """Count child components."""
      return sum(1 for _ in self._iter_children())
  ```

  **Key differences from xattree approach**:
  - No magic `self.children` dict maintained in parallel
  - Children discovered on-demand via field introspection
  - Works with normal attrs classes (no decorator needed)
  - Component.children attribute concept disappears
  - Explicit parent reference management via ParentSettingDict
  - Cache invalidation integrated into setters/deleters

  **Trade-offs**:
  - Slightly slower (field walk vs dict lookup) - acceptable for typical use
  - More explicit and debuggable (no hidden state)
  - Type-safe (can type hint fields properly)
  - Works with `slots=True` (no `__dict__` hijacking)

ParentSettingDict Details

  ParentSettingDict wraps dict fields (like `packages`, `models`) to automatically
  maintain parent references and cache consistency:

  ```python
  class ParentSettingDict(dict):
      """Dict that auto-sets parent refs and invalidates cache on mutation."""

      def __init__(self, parent: Component, data: dict[str, Component] | None = None):
          self._parent = parent
          super().__init__(data or {})
          # Set parent on any initial children
          for child in self.values():
              if isinstance(child, Component):
                  child._parent = parent

      def __setitem__(self, key: str, value: Component):
          super().__setitem__(key, value)
          if isinstance(value, Component):
              value._parent = self._parent
              invalidate_dimension_cache(self._parent)

      def __delitem__(self, key: str):
          child = self[key]
          super().__delitem__(key)
          if isinstance(child, Component):
              child._parent = None
              invalidate_dimension_cache(self._parent)
  ```

  **Usage in model classes**:
  ```python
  @define
  class Gwf(Component):
      packages: dict[str, Package] = field(factory=dict)

      def __attrs_post_init__(self):
          super().__attrs_post_init__()
          # Wrap packages dict for parent management
          self.packages = ParentSettingDict(parent=self, data=self.packages)
  ```

  This enables natural interactive construction:
  ```python
  gwf = Gwf(dis=Dis(...))
  ic = Ic(strt=...)
  gwf.packages['ic'] = ic  # ic._parent automatically set to gwf
  ```
