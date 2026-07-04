"""Unit tests for flopy4.mf6.schema — Column and Schema."""

import dataclasses

import pytest

from flopy4.mf6.schema import Column, Schema


class TestColumn:
    def test_required_fields(self):
        col = Column("head", role="value")
        assert col.name == "head"
        assert col.role == "value"

    def test_defaults(self):
        col = Column("head", role="value")
        assert col.dfn_type == "double"
        assert col.optional is False
        assert col.shape is None
        assert col.time_series is False
        assert col.dtype is None
        assert col.prefix is None

    def test_explicit_fields(self):
        col = Column(
            "cellid",
            role="cellid",
            dfn_type="integer",
            optional=True,
            shape="(ncelldim)",
            time_series=False,
            dtype="np.int64",
            prefix="cell",
        )
        assert col.role == "cellid"
        assert col.dfn_type == "integer"
        assert col.optional is True
        assert col.shape == "(ncelldim)"
        assert col.dtype == "np.int64"
        assert col.prefix == "cell"

    def test_immutable(self):
        col = Column("head", role="value")
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            col.name = "other"  # type: ignore[misc]

    def test_equality(self):
        a = Column("head", role="value", dfn_type="double")
        b = Column("head", role="value", dfn_type="double")
        assert a == b

    def test_inequality(self):
        a = Column("head", role="value")
        b = Column("head", role="cellid")
        assert a != b


class TestSchema:
    def test_columns_preserves_declaration_order(self):
        class MySchema(Schema):
            a = Column("a", role="value")
            b = Column("b", role="cellid")
            c = Column("c", role="feature_id")

        names = [col.name for col in MySchema.columns()]
        assert names == ["a", "b", "c"]

    def test_columns_only_returns_column_instances(self):
        class MySchema(Schema):
            a = Column("a", role="value")
            note = "not a column"
            count = 42
            b = Column("b", role="value")

        cols = MySchema.columns()
        assert len(cols) == 2
        assert all(isinstance(c, Column) for c in cols)

    def test_empty_schema_returns_empty_list(self):
        class EmptySchema(Schema):
            pass

        assert EmptySchema.columns() == []

    def test_subclass_isolation(self):
        class SchemaA(Schema):
            x = Column("x", role="value")

        class SchemaB(Schema):
            y = Column("y", role="cellid")

        assert [c.name for c in SchemaA.columns()] == ["x"]
        assert [c.name for c in SchemaB.columns()] == ["y"]

    def test_columns_not_inherited_from_sibling(self):
        class Base(Schema):
            pass

        class Child1(Base):
            a = Column("a", role="value")

        class Child2(Base):
            b = Column("b", role="value")

        assert [c.name for c in Child1.columns()] == ["a"]
        assert [c.name for c in Child2.columns()] == ["b"]

    def test_all_roles_accepted(self):
        class RolesSchema(Schema):
            c1 = Column("c1", role="cellid")
            c2 = Column("c2", role="feature_id")
            c3 = Column("c3", role="value")
            c4 = Column("c4", role="boundname")
            c5 = Column("c5", role="keyword")
            c6 = Column("c6", role="inline_keyword")

        roles = [col.role for col in RolesSchema.columns()]
        assert roles == ["cellid", "feature_id", "value", "boundname", "keyword", "inline_keyword"]
