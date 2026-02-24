Dimension Resolution Refactor: Implementation Plan

  Design Decisions

  Key Approach: Lazy runtime resolution instead of eager registration
  - No pre-registration of dimension providers
  - Resolution by walking object graph on-demand when dimensions are needed
  - Parent references enable walking up the hierarchy
  - Results cached after first resolution for performance

  Rationale:
  - Supports both cattrs (top-down) and interactive (bottom-up) construction
  - Simpler implementation without global state or registration lists
  - Construction order agnostic - works regardless of when children are added
  - Dimensions are runtime data; static validation wouldn't prevent runtime errors

  Migration Approach: Wrapper Pattern

  This refactor uses a WRAPPER PATTERN to add dimension resolution infrastructure
  while minimizing scope and risk:

  1. New protocols and mixin wrap existing xattree features (.parent)
  2. Implementation is incremental: 5 small PRs, each independently testable
  3. Dimension resolution works on top of xattree's parent management
  4. Later (Phase 3/Issue #167): swap parent implementation, dimension code unchanged
  5. Clean separation: this refactor = dimension resolution, future = parent management

  This keeps the current effort focused on dimension resolution while enabling
  future parent management migration without rework.

  Coexistence with xattree

  This refactor uses a WRAPPER PATTERN: new dimension resolution infrastructure wraps
  existing xattree features (like .parent), then we swap the implementation later.

  Phases 1-2 (This refactor - Dimension resolution only):
  - Components keep @xattree decorator
  - DimensionRegistryMixin is @define, Component stays @xattree (xattree wraps attrs)
  - New infrastructure (DimensionProvider, resolve_dimension()) wraps xattree's .parent
  - Mixin accesses self.parent generically - doesn't care where it comes from
  - _set_child_parents() is a no-op during coexistence (xattree already sets parents)
  - _resolve_dimensions() tries parent.get_all_dimensions() FIRST, falls back to xattree
  - Both resolution systems work simultaneously
  - All tests pass with fallback path active

  Phase 3 (Parent management migration - See issue #167):
  - Remove @xattree decorator from Component
  - Add explicit _parent field and @property to Component
  - Enable _set_child_parents() to actually set parent references
  - Enable ParentSettingDict for interactive construction
  - Remove xattree dimension fallback from _resolve_dimensions()
  - Mixin code doesn't change - still accesses self.parent the same way

  Key insights:
  - Dimension resolution refactor stays focused - doesn't also migrate parent management
  - New dimension API works with existing parent infrastructure (xattree now, ours later)
  - Protocols are structural typing - can implement protocol while decorated with @xattree
  - Clean separation: dimension resolution (Phases 1-2) vs parent management (Phase 3)

  Core Protocols

  Define two protocols in flopy4/mf6/protocols.py:

  class DimensionProvider(Protocol):
      """Components that provide dimensions to consumers."""

      def get_dimensions(self) -> dict[str, int]:
          """Return all dimensions this component provides.

          This is the single source of truth for what dimensions a component
          provides and their current values. Computed dimensions (like nodes)
          should be calculated here.
          """

  class DimensionRegistry(Protocol):
      """Containers that resolve dimensions from child providers."""

      def resolve_dimension(self, dim_name: str) -> int | None:
          """Resolve dimension by lazily walking object graph.

          Resolution order:
          1. Check cache
          2. Walk child fields/collections for DimensionProviders
          3. If not found, delegate to parent
          4. Cache result
          """

      def get_all_dimensions(self) -> dict[str, int]:
          """Get all dimensions from current children (no parent delegation)."""

  Component Implementations

  1. Implement DimensionProvider on grid/time components:

  Each component implements get_dimensions() to return its dimensions:

  - Dis: Provides nlay, nrow, ncol, nodes (nlay * nrow * ncol), ncpl (nrow * ncol)
  - Disv: Provides nlay, ncpl, nvert, nodes (nlay * ncpl)
  - Disu: Provides nodes, nvert (both explicit, no computation)
  - Tdis: Provides nper

  Example implementation:

  @xattree  # Keeps @xattree during Phases 1-2
  class Dis(Package):  # Package inherits from Component
      nlay: int
      nrow: int
      ncol: int
      # parent comes from xattree decorator (Phases 1-2)
      # will come from Component base class (Phase 3)

      def get_dimensions(self) -> dict[str, int]:
          """Provide grid dimensions including computed nodes and ncpl."""
          return {
              'nlay': self.nlay,
              'nrow': self.nrow,
              'ncol': self.ncol,
              'nodes': self.nlay * self.nrow * self.ncol,
              'ncpl': self.nrow * self.ncol,
          }

  2. Implement DimensionRegistryMixin:

  Create flopy4/mf6/mixins.py with lazy resolution logic:

  IMPORTANT: The mixin must be an attrs class (@define) so it can define its own fields.
  Attrs handles multiple @define classes in inheritance chains properly.

  @define
  class DimensionRegistryMixin:
      """Mixin for containers that resolve dimensions from children via lazy tree walking."""
      _dimension_cache: dict[str, int] = field(init=False, factory=dict, repr=False)

      def __attrs_post_init__(self):
          """Set parent references on all children after construction."""
          if hasattr(super(), '__attrs_post_init__'):
              super().__attrs_post_init__()
          self._set_child_parents()

      def _set_child_parents(self):
          """Walk all fields and set parent references on children.

          NOTE: During Phases 1-2 (xattree coexistence), this is a no-op since
          xattree already sets parent references. This method will be enabled
          in Phase 3 when we migrate parent management.

          Handles:
          - Direct children (single component fields)
          - Collections (dict/list of components)
          """
          # TODO Phase 3: Enable this when we remove @xattree
          # For now, xattree handles parent setting
          pass

          # Implementation to enable in Phase 3:
          # for field in attrs.fields(type(self)):
          #     value = getattr(self, field.name, None)
          #     if value is None:
          #         continue
          #     if hasattr(value, 'parent'):
          #         value.parent = self
          #     elif isinstance(value, dict):
          #         for child in value.values():
          #             if hasattr(child, 'parent'):
          #                 child.parent = self
          #     elif isinstance(value, list):
          #         for child in value:
          #             if hasattr(child, 'parent'):
          #                 child.parent = self

      def resolve_dimension(self, dim_name: str) -> int | None:
          """Resolve dimension by walking current object graph.

          Resolution order:
          1. Check cache
          2. Walk fields looking for DimensionProviders
          3. Check each provider's get_dimensions()
          4. If not found, delegate to parent
          5. Cache result
          """
          # Check cache first
          if dim_name in self._dimension_cache:
              return self._dimension_cache[dim_name]

          # Walk current children
          result = self._find_dimension_in_children(dim_name)

          if result is not None:
              self._dimension_cache[dim_name] = result
              return result

          # Delegate to parent
          if hasattr(self, 'parent') and self.parent is not None:
              if hasattr(self.parent, 'resolve_dimension'):
                  result = self.parent.resolve_dimension(dim_name)
                  if result is not None:
                      self._dimension_cache[dim_name] = result
                  return result

          return None

      def _find_dimension_in_children(self, dim_name: str) -> int | None:
          """Walk fields and check dimension providers for the requested dimension."""
          for field in attrs.fields(type(self)):
              value = getattr(self, field.name, None)
              if value is None:
                  continue

              # Check direct provider
              if isinstance(value, DimensionProvider):
                  dims = value.get_dimensions()
                  if dim_name in dims:
                      return dims[dim_name]

              # Check collections
              elif isinstance(value, dict):
                  for child in value.values():
                      if isinstance(child, DimensionProvider):
                          dims = child.get_dimensions()
                          if dim_name in dims:
                              return dims[dim_name]

              elif isinstance(value, list):
                  for child in value:
                      if isinstance(child, DimensionProvider):
                          dims = child.get_dimensions()
                          if dim_name in dims:
                              return dims[dim_name]

          return None

      def get_all_dimensions(self) -> dict[str, int]:
          """Get all dimensions from current children (no parent delegation)."""
          all_dims = {}

          for field in attrs.fields(type(self)):
              value = getattr(self, field.name, None)
              if value is None:
                  continue

              # Collect from direct providers
              if isinstance(value, DimensionProvider):
                  all_dims.update(value.get_dimensions())

              # Collect from collections
              elif isinstance(value, dict):
                  for child in value.values():
                      if isinstance(child, DimensionProvider):
                          all_dims.update(child.get_dimensions())

              elif isinstance(value, list):
                  for child in value:
                      if isinstance(child, DimensionProvider):
                          all_dims.update(child.get_dimensions())

          return all_dims

  3. Apply mixin to base Component class:

  DECISION: Make ALL components dimension registries by applying mixin to Component.

  During Phases 1-2 (xattree coexistence):

  @xattree  # Keep @xattree decorator
  class Component(DimensionRegistryMixin, ABC, MutableMapping):
      """Base class for all MF6 components."""
      # Inherits _dimension_cache and all dimension resolution methods from mixin
      # parent comes from @xattree decorator (not our own field yet)
      # ... existing Component fields and methods

  In Phase 3 (parent management migration):

  @define  # Replace @xattree with @define
  class Component(DimensionRegistryMixin):
      """Base class for all MF6 components."""
      _parent: Optional['Component'] = field(default=None, init=False, repr=False)
      # Inherits _dimension_cache and all dimension resolution methods from mixin

      @property
      def parent(self) -> Optional['Component']:
          return self._parent

      @parent.setter
      def parent(self, value: Optional['Component']):
          self._parent = value
          self._dimension_cache.clear()  # Invalidate cache when parent changes

  Benefits:
  - Simple, uniform: all components work the same way
  - No need to track which components "should" be registries
  - Future-proof: any component can aggregate dimensions if needed
  - Minimal overhead: empty _dimension_cache dict
  - Mixin code works with both xattree's parent (Phases 1-2) and our own (Phase 3)

  This means:
  - Gwf automatically resolves from Dis/Disv/Disu children, delegates to Simulation parent
  - Simulation automatically resolves from Tdis, model children
  - Even leaf packages like Ic get registry behavior (unused but harmless)
  - parent type is simply Component (not DimensionRegistry protocol type)

  Implementation Notes

  Attrs Multi-Class Inheritance:
  - DimensionRegistryMixin is @define (provides _dimension_cache field)
  - Component is @xattree during Phases 1-2 (xattree wraps attrs)
  - Since xattree uses attrs internally, Component can inherit from @define mixin
  - Attrs collects fields from both classes and chains __attrs_post_init__ calls
  - In Phase 3: Component becomes @define, cleaner multi-class @define inheritance

  Parent Property During Coexistence:
  - Phases 1-2: parent comes from @xattree decorator (xattree manages it)
  - Mixin accesses self.parent generically - doesn't know/care where it comes from
  - No cache invalidation on parent changes during coexistence (acceptable trade-off)
  - Phase 3: Add explicit _parent field with @property setter that clears cache
  - Type is Component (not protocol type) for simplicity

  Integration Points

  1. Parent reference setting:

  Phases 1-2: xattree automatically sets parent references during construction.
  The mixin's _set_child_parents() is a no-op.

  Phase 3: The DimensionRegistryMixin.__attrs_post_init__ method will set parent
  references on all children after construction (both cattrs and manual). The
  _set_child_parents() implementation will be enabled.

  2. Interactive construction support - Auto-registering dict class:

  DECISION: Use custom dict class that auto-sets parent on item assignment (Phase 3)

  Implementation using collections.UserDict for cleaner behavior:

  from collections import UserDict

  class ParentSettingDict(UserDict):
      """Dict that automatically sets parent reference on item assignment.

      Uses UserDict instead of dict subclass to avoid issues with dict's
      internal optimizations that sometimes bypass __setitem__.
      """

      def __init__(self, parent, initial_dict=None):
          super().__init__(initial_dict or {})
          self._parent = parent
          # Set parent on any items already in dict
          for value in self.data.values():
              if hasattr(value, 'parent'):
                  value.parent = self._parent

      def __setitem__(self, key, value):
          super().__setitem__(key, value)
          if hasattr(value, 'parent'):
              value.parent = self._parent

      def update(self, *args, **kwargs):
          super().update(*args, **kwargs)
          # Set parent on newly added items
          for value in self.data.values():
              if hasattr(value, 'parent'):
                  value.parent = self._parent

  NOTE: ParentSettingDict will be implemented but not used until Phase 3.
  During Phases 1-2, xattree handles interactive construction.

  Usage in specific component classes (Phase 3 only):

  @define  # After removing @xattree
  class Gwf(Model):
      packages: dict[str, Package] = field(factory=dict)

      def __attrs_post_init__(self):
          super().__attrs_post_init__()  # Sets parent on existing children
          # Wrap packages dict for future assignments
          self.packages = ParentSettingDict(self, self.packages)

  Similarly for Simulation:

  @define  # After removing @xattree
  class Simulation(Context):
      models: dict[str, Model] = field(factory=dict)

      def __attrs_post_init__(self):
          super().__attrs_post_init__()  # Sets parent on existing children
          # Wrap models dict for future assignments
          self.models = ParentSettingDict(self, self.models)

  This allows natural interactive construction:

  ic = Ic(strt=...)
  gwf = Gwf(dis=Dis(...))
  gwf.packages['ic'] = ic  # parent is automatically set to gwf

  Note: Only container classes with dict fields need to wrap them. Most classes
  don't need to override __attrs_post_init__ at all.

  3. Update _resolve_dimensions() (structure.py):

  Change dimension resolution to use parent hierarchy:

  def _resolve_dimensions(self_, field, *, dims=None):
      dim_dict = {}

      # Priority 1: Explicit dims parameter (highest priority)
      if dims:
          dim_dict.update(dims)

      # Priority 2: Parent's dimension resolution
      if hasattr(self_, 'parent') and self_.parent is not None:
          if hasattr(self_.parent, 'get_all_dimensions'):
              dim_dict.update(self_.parent.get_all_dimensions())

      # Priority 3: Structuring context (TEMPORARY fallback during migration)
      context_dims = get_structuring_dims()
      if context_dims:
          dim_dict.update(context_dims)

      # Priority 4: Self attributes (dimension fields already set)
      for dim_name in field.dims:
          if hasattr(self_, dim_name):
              dim_value = getattr(self_, dim_name)
              if isinstance(dim_value, int):
                  dim_dict[dim_name] = dim_value

      # TEMPORARY: Computed dimensions fallback during migration
      # TODO: Remove after all DimensionProviders implement get_dimensions()
      if "nodes" not in dim_dict and {"nlay", "nrow", "ncol"} <= dim_dict.keys():
          dim_dict["nodes"] = dim_dict["nlay"] * dim_dict["nrow"] * dim_dict["ncol"]

      # ... rest of function

  Note: After migration completes, Priority 3 (context) and computed dimension
  fallbacks can be removed.

  Dimension Conflict Detection

  DECISION: Check for conflicts in get_all_dimensions() and raise error on first access

  def get_all_dimensions(self) -> dict[str, int]:
      all_dims = {}
      for field in attrs.fields(type(self)):
          value = getattr(self, field.name, None)
          if value is None:
              continue

          if isinstance(value, DimensionProvider):
              dims = value.get_dimensions()
              # Check for conflicts
              conflicts = set(dims.keys()) & set(all_dims.keys())
              if conflicts:
                  raise ValueError(
                      f"{type(self).__name__} has multiple providers for dimensions: {conflicts}. "
                      f"Field {field.name} provides {dims.keys()}, already provided by another child."
                  )
              all_dims.update(dims)

          # Similar for collections...

      return all_dims

  This catches configuration errors early (on first dimension access) without
  requiring import-time analysis.

  Optional Validation Tool

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

  Usage in tests:
  sim = load_simulation(path)
  errors = validate_dimension_resolution(sim)
  assert not errors, f"Dimension resolution failures: {errors}"

  Migration Strategy

  This refactor is broken into small, testable PRs covering Phases 1-2 (dimension
  resolution). Phase 3 (parent management migration) is deferred to issue #167.

  PR1: Add Protocol and Mixin Infrastructure
  - Add flopy4/mf6/protocols.py with DimensionProvider and DimensionRegistry protocols
  - Add flopy4/mf6/mixins.py with:
    - DimensionRegistryMixin (@define class with _dimension_cache field)
    - ParentSettingDict (for Phase 3, implemented but not used yet)
  - Unit tests for mixin in isolation (create test component classes)
  - Zero changes to existing Component or packages
  - Tests: New unit tests only, all existing tests unchanged

  PR2: Implement DimensionProvider on Dis
  - Add get_dimensions() method to Dis class
  - Returns {nlay, nrow, ncol, nodes, ncpl} with computed dimensions
  - Dis now structurally implements DimensionProvider protocol
  - Unit tests verifying correct dimension values including computed ones
  - Tests: New tests for get_dimensions(), all existing tests pass

  PR3: Implement DimensionProvider on Tdis
  - Add get_dimensions() method to Tdis class
  - Returns {nper}
  - Unit tests
  - Tests: New tests for get_dimensions(), all existing tests pass

  PR4: Apply Mixin to Component Base Class
  - Component inherits from DimensionRegistryMixin while keeping @xattree
  - Component gains _dimension_cache field and resolution methods
  - All components now have resolve_dimension() and get_all_dimensions()
  - Integration tests showing dimension resolution works via parent hierarchy
  - Tests: New integration tests, all existing tests pass

  PR5: Integrate with _resolve_dimensions
  - Update _resolve_dimensions() in structure.py:
    - Try parent.get_all_dimensions() FIRST (new path)
    - Fall back to xattree's parent.data.dims (compatibility)
    - Keep computed dimension fallback (temporary)
  - All tests pass using both new and fallback paths
  - Tests: All existing tests pass (proving coexistence works)

  Phase 3 (Separate effort - Issue #167): Parent Management Migration
  - Remove @xattree decorator from Component
  - Add explicit _parent field and @property to Component
  - Enable _set_child_parents() implementation in mixin
  - Update Gwf/Simulation to use ParentSettingDict
  - Remove xattree fallback from _resolve_dimensions()
  - Remove computed dimension fallback
  - All tests must pass without xattree

  Optional Future Work:
  - Add conflict detection in get_all_dimensions()
  - Add optional validate_dimension_resolution() tool
  - Add logging/debugging for resolution paths
  - Document interactive construction pattern in user guide

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

  Testing Requirements

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

  Benefits Achieved

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

  Key Implementation Details (Summary)

  1. Wrapper pattern for xattree coexistence
     - DimensionRegistryMixin is @define (provides _dimension_cache)
     - Component is @xattree during Phases 1-2 (xattree wraps attrs internally)
     - Mixin accesses self.parent generically - works with both sources
     - Phase 3: Component becomes @define with explicit _parent field

  2. All components are dimension registries
     - Component inherits from DimensionRegistryMixin
     - Every component (containers and leaves) gets registry behavior
     - Minimal overhead: empty _dimension_cache dict
     - Mixin methods work regardless of parent source (xattree vs our own)

  3. Parent management deferred to Phase 3
     - Phases 1-2: Use xattree's .parent property as-is
     - _set_child_parents() is no-op during coexistence
     - Phase 3: Add _parent field, enable _set_child_parents()
     - No cache invalidation during coexistence (acceptable trade-off)

  4. ParentSettingDict implemented but unused until Phase 3
     - Uses collections.UserDict (not dict) for reliable __setitem__
     - Will be used in container classes (Gwf, Simulation) in Phase 3
     - Sets parent automatically on assignment: gwf.packages['ic'] = ic

  5. Clean separation of concerns
     - Phases 1-2 (PRs 1-5): Dimension resolution only
     - Phase 3 (Issue #167): Parent management migration
     - New dimension API doesn't depend on xattree specifics
     - Protocols provide clean abstraction boundary
