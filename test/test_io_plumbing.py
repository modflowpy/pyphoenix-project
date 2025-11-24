"""Test IO plumbing for classmethod load/write operations."""

from pathlib import Path

from xattree import xattree

from flopy4.mf6.component import Component
from flopy4.mf6.constants import MF6
from flopy4.mf6.context import Context
from flopy4.uio import DEFAULT_REGISTRY, IO, Loader, Registry, Writer


@xattree
class MockComponent(Component):
    """Minimal test component for IO testing."""

    name: str = "test"


def test_io_descriptor_access_from_class():
    """Test that IO descriptors can be accessed from a class (not instance)."""
    # Access the descriptor from the class
    loader = MockComponent._load

    # Should return a Loader instance
    assert isinstance(loader, Loader)
    assert loader._cls is MockComponent
    assert loader._instance is None  # No instance in classmethod context


def test_io_descriptor_access_from_instance():
    """Test that IO descriptors can still be accessed from an instance."""
    component = MockComponent()
    loader = component._load

    # Should return a Loader instance
    assert isinstance(loader, Loader)
    assert loader._cls is MockComponent
    assert loader._instance is component


def test_classmethod_load_with_mock_loader():
    """Test that Component.load() classmethod can invoke a registered loader."""
    # Create a separate registry for testing to avoid polluting the global one
    test_registry = Registry()

    # Track whether the loader was called
    load_called = {"value": False, "cls": None, "path": None, "format": None}

    def mock_loader(cls, path, format=MF6):
        """Mock loader function that tracks invocation."""
        load_called["value"] = True
        load_called["cls"] = cls
        load_called["path"] = path
        load_called["format"] = format
        # Return a new instance
        return cls(name="loaded")

    # Register the mock loader
    test_registry.register_loader(MockComponent, MF6, mock_loader)

    # Replace the descriptor's registry temporarily
    original_load = MockComponent._load
    MockComponent._load = IO(lambda instance, cls: Loader(instance, cls))

    # Manually create a loader with the test registry
    loader = Loader(None, MockComponent)
    loader._registry = test_registry

    # Call the loader
    test_path = Path("/test/path.txt")
    result = loader(test_path, format=MF6)

    # Verify the mock loader was called correctly
    assert load_called["value"]
    assert load_called["cls"] is MockComponent
    assert load_called["path"] == test_path
    assert load_called["format"] == MF6
    assert result.name == "loaded"

    # Restore original
    MockComponent._load = original_load


def test_loader_registry_lookup():
    """Test that the registry can look up the correct loader function."""
    test_registry = Registry()

    def loader_fn(cls, path, format=MF6):
        return cls()

    # Register loader
    test_registry.register_loader(MockComponent, MF6, loader_fn)

    # Lookup loader
    found_loader = test_registry.get_loader(MockComponent, format=MF6)
    assert found_loader is loader_fn


def test_loader_registry_subclass_lookup():
    """Test that registry correctly finds loaders for subclasses."""
    test_registry = Registry()

    @xattree
    class SubComponent(MockComponent):
        """Subclass of MockComponent."""

        pass

    def base_loader(cls, path, format=MF6):
        return cls()

    # Register loader for base class
    test_registry.register_loader(MockComponent, MF6, base_loader)

    # Should find loader for subclass via issubclass check
    found_loader = test_registry.get_loader(SubComponent, format=MF6)
    assert found_loader is base_loader


def test_writer_descriptor_requires_instance():
    """Test that Writer descriptor works with instances."""
    component = MockComponent(name="test_write")
    writer = component._write

    # Should return a Writer instance with the component instance
    assert isinstance(writer, Writer)
    assert writer._cls is MockComponent
    assert writer._instance is component


def test_classmethod_load_signature():
    """Test that the load classmethod has the expected signature."""
    import inspect

    # Get the load method
    load_method = MockComponent.load

    # Check it's a classmethod
    assert isinstance(inspect.getattr_static(MockComponent, "load"), classmethod)

    # Check signature
    sig = inspect.signature(load_method)
    params = list(sig.parameters.keys())

    # Should have: cls (implicit), path, format
    assert "path" in params
    assert "format" in params


def test_io_descriptor_callable():
    """Test that the Loader descriptor returns a callable object."""
    loader = MockComponent._load

    # Should be callable
    assert callable(loader)


def test_registry_write_with_mock_writer():
    """Test that the Writer can invoke a registered writer function."""
    test_registry = Registry()

    # Track whether the writer was called
    write_called = {"value": False, "instance": None, "format": None}

    def mock_writer(instance, format=MF6, context=None):
        """Mock writer function that tracks invocation."""
        write_called["value"] = True
        write_called["instance"] = instance
        write_called["format"] = format

    # Register the mock writer
    test_registry.register_writer(MockComponent, MF6, mock_writer)

    # Create instance and writer
    component = MockComponent(name="test")
    writer = Writer(component, MockComponent)
    writer._registry = test_registry

    # Call the writer
    writer(format=MF6)

    # Verify the mock writer was called correctly
    assert write_called["value"]
    assert write_called["instance"] is component
    assert write_called["format"] == MF6


def test_load_return_type():
    """Test that load method returns the correct type hint."""
    import inspect

    sig = inspect.signature(MockComponent.load)
    return_annotation = sig.return_annotation

    # Check the return annotation - should be None (the value)
    assert return_annotation is None


def test_multiple_format_registrations():
    """Test that different loaders can be registered for different formats."""
    test_registry = Registry()

    format1_called = {"value": False}
    format2_called = {"value": False}

    def loader_fmt1(cls, path, format=None):
        format1_called["value"] = True
        return cls()

    def loader_fmt2(cls, path, format=None):
        format2_called["value"] = True
        return cls()

    # Register different loaders for different formats
    test_registry.register_loader(MockComponent, "format1", loader_fmt1)
    test_registry.register_loader(MockComponent, "format2", loader_fmt2)

    # Get format1 loader
    loader1 = test_registry.get_loader(MockComponent, format="format1")
    assert loader1 is loader_fmt1

    # Get format2 loader
    loader2 = test_registry.get_loader(MockComponent, format="format2")
    assert loader2 is loader_fmt2


def test_classmethod_load_should_return_instance():
    """
    Test that demonstrates the expected behavior for load() as a classmethod.

    The current implementation has a bug at component.py:140 where it uses
    `self.children` in a classmethod context. This test shows the expected
    pattern: load() should return an instance so that children can be accessed.
    """
    test_registry = Registry()

    def mock_loader(cls, path, format=MF6):
        """Mock loader that returns a new instance."""
        return cls(name="loaded_from_file")

    # Register the loader
    test_registry.register_loader(MockComponent, MF6, mock_loader)

    # Create a loader with the test registry
    loader = Loader(None, MockComponent)
    loader._registry = test_registry

    # Call the loader - should return an instance
    test_path = Path("/test/path.txt")
    result = loader(test_path, format=MF6)

    # Verify we got an instance back
    assert isinstance(result, MockComponent)
    assert result.name == "loaded_from_file"

    # This is what load() should do: return the instance
    # so that code like `component = Component.load(path)` works
    # and children can be accessed via `component.children`


def test_loader_can_be_called_directly_from_class():
    """
    Test that the loader can be accessed and called directly from a class.
    This is the pattern that Component.load() uses.
    """
    test_registry = Registry()

    # Track calls
    calls = []

    def mock_loader(cls, path, format=MF6):
        calls.append({"cls": cls, "path": path, "format": format})
        return cls(name="loaded")

    # Register loader
    test_registry.register_loader(MockComponent, MF6, mock_loader)

    # Simulate what Component.load() does: access descriptor from class
    loader = MockComponent._load
    loader._registry = test_registry

    # Call it with a path
    result = loader(Path("/test/file.txt"), format=MF6)

    # Verify the loader was called correctly
    assert len(calls) == 1
    assert calls[0]["cls"] is MockComponent
    assert calls[0]["path"] == Path("/test/file.txt")
    assert calls[0]["format"] == MF6
    assert isinstance(result, MockComponent)


def test_component_load_classmethod_calls_loader():
    """
    Test that Component.load() classmethod actually works end-to-end.
    This verifies the fix for the bug at component.py:139-140.

    Note: This test verifies the plumbing works by checking that
    the registered loader is called. Since Component already has
    loaders registered, we temporarily replace one to test.
    """
    # Save the original loader
    original_loader = DEFAULT_REGISTRY._loaders.get((Component, MF6))

    # Track whether the loader was called
    loader_calls = []

    def mock_loader(cls, path, format=MF6):
        """Mock loader that returns an instance with no children."""
        loader_calls.append({"cls": cls, "path": path, "format": format})
        # Return an instance (simulating a loaded component)
        instance = cls(name="loaded_component")
        return instance

    # Temporarily replace the Component loader
    DEFAULT_REGISTRY._loaders[(Component, MF6)] = mock_loader

    try:
        # Call Component.load() classmethod
        test_path = Path("/test/component.txt")
        Component.load(test_path, format=MF6)

        # Verify the loader was called
        assert len(loader_calls) == 1
        assert loader_calls[0]["cls"] is Component
        assert loader_calls[0]["path"] == test_path
        assert loader_calls[0]["format"] == MF6

    finally:
        # Restore the original loader
        if original_loader:
            DEFAULT_REGISTRY._loaders[(Component, MF6)] = original_loader
        else:
            del DEFAULT_REGISTRY._loaders[(Component, MF6)]


def test_component_load_with_children():
    """
    Test that Component.load() correctly loads children.
    This ensures the fix allows accessing self.children in the classmethod.
    """
    # Save original loader
    original_loader = DEFAULT_REGISTRY._loaders.get((Component, MF6))

    # Track all load calls
    all_loads = []

    def mock_loader(cls, path, format=MF6):
        """Mock loader that tracks calls."""
        all_loads.append({"cls": cls, "path": str(path), "format": format})

        # Create instance
        instance = cls(name=f"loaded_{cls.__name__}")

        # Simulate children only for the parent component
        if "parent" in str(path):
            # Add mock children that have paths
            @xattree
            class ChildComponent(Component):
                name: str = "child"

                def default_filename(self):
                    return "child.txt"

            # Attach a child with a path
            child = ChildComponent(name="child1", filename="child1.txt")
            # Children dict should exist from xattree
            instance.children["child1"] = child

        return instance

    # Temporarily replace the Component loader
    DEFAULT_REGISTRY._loaders[(Component, MF6)] = mock_loader

    try:
        # Load a component with children
        Component.load(Path("/test/parent.txt"), format=MF6)

        # Should have called loader for parent AND child
        assert len(all_loads) == 2, f"Expected 2 loads (parent + child), got {len(all_loads)}"

        # First call should be for parent
        assert "/test/parent.txt" in all_loads[0]["path"].replace("\\", "/")
        assert all_loads[0]["format"] == MF6

        # Second call should be for child (with its relative path)
        # Note: child path is relative to cwd, not parent's directory
        assert "child1.txt" in all_loads[1]["path"].replace("\\", "/")
        assert all_loads[1]["format"] == MF6

    finally:
        # Restore original loader
        if original_loader:
            DEFAULT_REGISTRY._loaders[(Component, MF6)] = original_loader
        else:
            del DEFAULT_REGISTRY._loaders[(Component, MF6)]


def test_context_load_with_workspace():
    """
    Test that Context.load() uses workspace for loading children.

    Context components have a workspace attribute, and children should
    be loaded relative to that workspace, not the current directory.
    """
    import tempfile

    # Create a test Context subclass
    @xattree
    class TestContext(Context):
        """Test context component with workspace."""

        name: str = "test_context"

    # Save original loader
    original_loader = DEFAULT_REGISTRY._loaders.get((Context, MF6))

    # Track all load calls with their working directory
    all_loads = []

    # Create a temporary workspace directory
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_dir = Path(tmpdir) / "workspace"
        workspace_dir.mkdir()

        def mock_loader(cls, path, format=MF6):
            """Mock loader that tracks calls and current directory."""
            all_loads.append(
                {"cls": cls, "path": str(path), "format": format, "cwd": str(Path.cwd())}
            )

            # Create instance
            instance = cls(name=f"loaded_{cls.__name__}")

            # Set workspace for parent
            if "parent" in str(path):
                instance.workspace = workspace_dir

                # Add mock child
                @xattree
                class ChildComponent(Component):
                    name: str = "child"

                child = ChildComponent(name="child1", filename="child1.txt")
                instance.children["child1"] = child

            return instance

        # Register loader for Context (will match TestContext via subclass)
        DEFAULT_REGISTRY._loaders[(Context, MF6)] = mock_loader
        # Also register for Component (for the child)
        DEFAULT_REGISTRY._loaders[(Component, MF6)] = mock_loader

        try:
            # Load a context component with children
            TestContext.load(Path("/test/parent.txt"), format=MF6)

            # Should have called loader for parent AND child
            assert len(all_loads) == 2, f"Expected 2 loads (parent + child), got {len(all_loads)}"

            # First call should be for parent
            assert "/test/parent.txt" in all_loads[0]["path"].replace("\\", "/")
            assert all_loads[0]["format"] == MF6

            # Second call should be for child
            assert "child1.txt" in all_loads[1]["path"].replace("\\", "/")
            assert all_loads[1]["format"] == MF6

            # IMPORTANT: Child should be loaded with cwd = parent's workspace
            # This is the key feature of Context.load()
            # Resolve both paths to handle symlinks (e.g., /private/var vs /var on macOS)
            actual_cwd = Path(all_loads[1]["cwd"]).resolve()
            expected_cwd = workspace_dir.resolve()
            assert actual_cwd == expected_cwd, (
                f"Child should be loaded in parent's workspace {expected_cwd}, "
                f"but was loaded in {actual_cwd}"
            )

        finally:
            # Restore original loaders
            if original_loader:
                DEFAULT_REGISTRY._loaders[(Context, MF6)] = original_loader
            else:
                if (Context, MF6) in DEFAULT_REGISTRY._loaders:
                    del DEFAULT_REGISTRY._loaders[(Context, MF6)]

            # Clean up Component loader
            if (Component, MF6) in DEFAULT_REGISTRY._loaders:
                del DEFAULT_REGISTRY._loaders[(Component, MF6)]
