"""Test IO plumbing for classmethod load/write operations."""

from pathlib import Path

from xattree import xattree

from flopy4.mf6.component import Component
from flopy4.mf6.constants import MF6
from flopy4.uio import DEFAULT_REGISTRY, IO, Loader, Registry, Writer


def test_io_descriptor_access_from_class():
    @xattree
    class MockComponent(Component):
        name: str = "test"

    loader = MockComponent._load
    writer = MockComponent._write

    assert isinstance(loader, Loader)
    assert isinstance(writer, Writer)
    assert loader._cls is MockComponent
    assert writer._cls is MockComponent
    assert loader._instance is None
    assert writer._instance is None
    assert callable(loader)
    assert callable(writer)


def test_io_descriptor_access_from_instance():
    @xattree
    class MockComponent(Component):
        name: str = "test"

    component = MockComponent()
    loader = component._load
    writer = component._write

    assert isinstance(loader, Loader)
    assert isinstance(writer, Writer)
    assert loader._cls is MockComponent
    assert writer._cls is MockComponent
    assert loader._instance is component
    assert writer._instance is component


def test_loader_registry_lookup():
    @xattree
    class MockComponent(Component):
        name: str = "test"

    test_registry = Registry()

    def loader_fn(cls, path, format=MF6):
        return cls()

    test_registry.register_loader(MockComponent, MF6, loader_fn)
    found_loader = test_registry.get_loader(MockComponent, format=MF6)
    assert found_loader is loader_fn


def test_loader_registry_subclass_lookup():
    @xattree
    class MockComponent(Component):
        name: str = "test"

    @xattree
    class SubComponent(MockComponent):
        pass

    test_registry = Registry()

    def base_loader(cls, path, format=MF6):
        return cls()

    test_registry.register_loader(MockComponent, MF6, base_loader)
    found_loader = test_registry.get_loader(SubComponent, format=MF6)
    assert found_loader is base_loader


def test_classmethod_load_signature():
    import inspect

    @xattree
    class MockComponent(Component):
        name: str = "test"

    load_method = MockComponent.load
    assert isinstance(inspect.getattr_static(MockComponent, "load"), classmethod)

    sig = inspect.signature(load_method)
    params = list(sig.parameters.keys())
    assert "path" in params
    assert "format" in params


def test_load_and_write():
    @xattree
    class MockComponent(Component):
        name: str = "test"

    test_registry = Registry()
    load_called = {"value": False, "cls": None, "path": None, "format": None}
    write_called = {"value": False, "instance": None, "format": None}

    def mock_loader(cls, path, format=MF6):
        load_called["value"] = True
        load_called["cls"] = cls
        load_called["path"] = path
        load_called["format"] = format
        return cls(name="loaded")

    def mock_writer(instance, format=MF6, context=None):
        write_called["value"] = True
        write_called["instance"] = instance
        write_called["format"] = format

    test_registry.register_loader(MockComponent, MF6, mock_loader)
    test_registry.register_writer(MockComponent, MF6, mock_writer)

    original_load = MockComponent._load
    MockComponent._load = IO(lambda instance, cls: Loader(instance, cls))

    component = MockComponent(name="test")
    loader = Loader(None, MockComponent)
    writer = Writer(component, MockComponent)
    loader._registry = test_registry
    writer._registry = test_registry

    test_path = Path("/test/path.txt")
    result = loader(test_path, format=MF6)
    assert load_called["value"]
    assert load_called["cls"] is MockComponent
    assert load_called["path"] == test_path
    assert load_called["format"] == MF6
    assert result.name == "loaded"
    assert isinstance(result, MockComponent)
    assert result.name == "loaded"

    writer(format=MF6)
    assert write_called["value"]
    assert write_called["instance"] is component
    assert write_called["format"] == MF6

    MockComponent._load = original_load


def test_multiple_format_registrations():
    @xattree
    class MockComponent(Component):
        name: str = "test"

    test_registry = Registry()

    format1_called = {"value": False}
    format2_called = {"value": False}

    def loader_fmt1(cls, path, format=None):
        format1_called["value"] = True
        return cls()

    def loader_fmt2(cls, path, format=None):
        format2_called["value"] = True
        return cls()

    test_registry.register_loader(MockComponent, "format1", loader_fmt1)
    test_registry.register_loader(MockComponent, "format2", loader_fmt2)

    loader1 = test_registry.get_loader(MockComponent, format="format1")
    loader2 = test_registry.get_loader(MockComponent, format="format2")

    assert loader1 is loader_fmt1
    assert loader2 is loader_fmt2


def test_component_load():
    """
    Test that Component.load() classmethod actually works end-to-end.

    Note: This test verifies the plumbing works by checking that
    the registered loader is called. Since Component already has
    loaders registered, we temporarily replace one to test.
    """
    original_loader = DEFAULT_REGISTRY._loaders.get((Component, MF6))
    loader_calls = []

    def mock_loader(cls, path, format=MF6):
        loader_calls.append({"cls": cls, "path": path, "format": format})
        return cls(name="loaded_component")

    # Temporarily replace the Component loader
    DEFAULT_REGISTRY._loaders[(Component, MF6)] = mock_loader

    try:
        test_path = Path("/test/component.txt")
        Component.load(test_path, format=MF6)

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
