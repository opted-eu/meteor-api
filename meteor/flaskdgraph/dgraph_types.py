"""
Classes to represent DGraph objects in Python
These are helper classes to automatically generate
nquad statements from dictionaries
May later be used for automatic query building
"""

from typing import Union, Any, Literal, get_args
import datetime
import json
from copy import deepcopy

# external utils
from slugify import slugify
import secrets
from dateutil import parser as dateparser


from meteor import dgraph

from .schema import Schema
from .customformfields import NullableDateField, TomSelectField, TomSelectMultipleField
from .utils import validate_uid, strip_query
from .dql import *
from meteor.errors import InventoryPermissionError, InventoryValidationError
from meteor.add.external import geocode, reverse_geocode
from meteor.users.constants import USER_ROLES

from wtforms import (
    StringField,
    SelectField,
    SelectMultipleField,
    DateField,
    BooleanField,
    TextAreaField,
    RadioField,
    IntegerField,
    PasswordField,
)
from wtforms.validators import DataRequired, Optional


"""
    Type Hints
"""

AvailableOperators = Union[eq, gt, lt, ge, le, has, type_, between, regexp]
operator_conversion = {
    "eq": eq,
    "gt": gt,
    "lt": lt,
    "ge": ge,
    "le": le,
    "has": has,
    "type": type_,
    "between": between,
    "regexp": regexp,
}

AvailableConnectors = Literal["AND", "OR", "NOT"]

"""
    DGraph Primitives
"""


class UID:
    def __init__(self, uid, facets=None):
        self.uid = uid.strip()
        self.facets = facets

    def __str__(self) -> str:
        return f"{self.uid}"

    def __repr__(self) -> str:
        return f"<{self.uid}>"

    def update_facets(self, facets: dict) -> None:
        if self.facets:
            self.facets.update(facets)
        else:
            self.facets = facets

    @property
    def nquad(self) -> str:
        return f"<{self.uid}>"

    @property
    def query(self) -> str:
        return f"{self.uid}"


class NewID:
    def __init__(self, newid=None, facets=None, suffix=None):
        if newid is None:
            newid = "_:newentry"
        if newid.startswith("_:"):
            self.newid = newid.strip()
        else:
            self.newid = f'_:{slugify(newid, separator="_", lowercase=False)}'

        if suffix:
            self.newid += f"_{suffix}"
        else:
            self.newid += secrets.token_urlsafe(4)

        self.facets = facets

        self.original_value = newid.strip()

    def __str__(self) -> str:
        return self.newid

    def __repr__(self) -> str:
        return f"{self.newid}"

    def update_facets(self, facets: dict) -> None:
        if self.facets:
            self.facets.update(facets)
        else:
            self.facets = facets

    @property
    def nquad(self) -> str:
        return f"{self.newid}"


class Facet:
    """
    Base class for facets. Use simple coercion.
    Facet keys are strings and values can be string, bool, int, float and dateTime.
    """

    predicate = None
    default_operator = eq
    is_list_predicate = False

    def __init__(
        self,
        key: str,
        dtype: Union[str, bool, int, float, datetime.datetime] = str,
        queryable=False,
        coerce=None,
        query_label=None,
        description=None,
        example=None,
        comparison_operators=None,
        render_kw=None,
        choices=None,
    ) -> None:
        self.key = key
        self.type = dtype
        self.queryable = queryable
        self._query_label = query_label
        if isinstance(comparison_operators, dict):
            comparison_operators = [(k, v) for k, v in comparison_operators.items()]
            comparison_operators.insert(0, ("", ""))

        self.description = description or ""
        self.example = example or "some string"
        self.operators = comparison_operators
        self.render_kw = render_kw or {}

        if isinstance(choices, dict):
            choices = [(k, v) for k, v in choices.items()]

        self.choices = choices

    def __repr__(self) -> str:
        if self.predicate:
            return f'<{self.type.__name__} Facet "{self.key}" of "{self.predicate}">'
        else:
            return f'<Unbound {self.type.__name__} Facet "{self.key}">'

    def __str__(self) -> str:
        if self.predicate:
            return f"{self.predicate}|{self.key}"
        else:
            return f"{self.key}"

    def corece(self, val) -> Any:
        if self.type == bool:
            return self._coerce_bool(val)
        elif self.type == datetime.datetime:
            try:
                return self._coerce_datetime(val)
            except:
                return None
        else:
            try:
                return self.type(val)
            except:
                return None

    def query_filter(
        self,
        vals: Union[str, list],
        operator: AvailableOperators = None,
        predicate=None,
        **kwargs,
    ) -> str:
        if vals is None:
            return None

        if not predicate:
            predicate = self.predicate

        if not operator:
            operator = self.default_operator

        if isinstance(operator, str):
            try:
                operator = operator_conversion[operator]
            except:
                operator = self.default_operator

        if not isinstance(vals, list):
            vals = [vals]

        if len(vals) == 0:
            return None

        vals = [self.corece(val) for val in vals]
        if self.type == datetime.datetime:
            if operator == between:
                left = ge(self.key, vals[0].strftime("%Y-%m-%d"))
                right = lt(self.key, vals[1].strftime("%Y-%m-%d"))
                return f"{left} AND {right}"
            else:
                val1 = vals[0]
                val2 = val1 + datetime.timedelta(days=1)
                left = ge(self.key, val1.strftime("%Y-%m-%d"))
                right = lt(self.key, val2.strftime("%Y-%m-%d"))
                return f"{left} AND {right}"

        if operator == between:
            left = ge(self.key, vals[0])
            right = lt(self.key, vals[1])
            return f"{left} AND {right}"
        else:
            filters = [str(operator(self.key, val)) for val in vals]
            if len(filters) > 1:
                filter_string = " OR ".join(filters)
                return f"({filter_string})"
            else:
                return filters[0]

    @staticmethod
    def _coerce_bool(val) -> bool:
        if isinstance(val, bool):
            return bool(val)
        elif isinstance(val, str):
            return val.lower() in ("yes", "true", "t", "1", "y")
        elif isinstance(val, int):
            return val > 0
        else:
            return False

    @staticmethod
    def _coerce_datetime(val):
        if isinstance(val, (datetime.date, datetime.datetime)):
            return val
        elif isinstance(val, int):
            try:
                return datetime.date(year=val, month=1, day=1)
            except:
                pass
        return dateparser.parse(val)

    @property
    def query_label(self) -> str:
        if self._query_label:
            return self._query_label
        else:
            return f'{self.predicate.replace("_", " ").title()}: {self.key.replace("_", " ").title()}'

    @property
    def query_field(self) -> StringField:
        self.render_kw.update(
            {"data-entities": ",".join(Schema.__predicates_types__[self.predicate])}
        )
        if self.type == bool:
            return BooleanField(label=self.query_label, render_kw=self.render_kw)
        elif self.type == int:
            return IntegerField(label=self.query_label, render_kw=self.render_kw)
        elif self.choices:
            return TomSelectMultipleField(
                label=self.query_label, render_kw=self.render_kw, choices=self.choices
            )
        else:
            return StringField(label=self.query_label, render_kw=self.render_kw)

    @property
    def openapi_query_parameter(self) -> dict:
        qp = {
            "name": self.__str__(),
            "in": "query",
            "description": self.description,
            "required": False,
            "schema": {"type": "array", "items": {"type": "string"}},
            "example": self.example,
        }
        connector = {
            "name": self.__str__() + "*connector",
            "in": "query",
            "description": "Logical connectors for combining an array",
            "required": False,
            "schema": {
                "type": "string",
                "enum": [c.func for c in get_args(AvailableOperators)],
                "default": self.default_operator.func,
            },
        }
        return {
            self.__str__().replace("|", "_") + "QueryParam": qp,
            self.__str__().replace("|", "_") + "QueryConnector": connector,
        }


class _PrimitivePredicate:
    """
    Private Class to resolve inheritance conflicts
    Base class for constructing Predicate Classes
    """

    dgraph_predicate_type = "string"
    _type = str
    dgraph_directives = None
    is_list_predicate = False
    default_operator = eq
    default_connector = "OR"
    bound_dgraph_type = None

    def __init__(
        self,
        label: str = None,
        default: Any = None,
        required=False,
        overwrite=False,
        facets=None,
        new=True,
        edit=True,
        queryable=False,
        permission=USER_ROLES.Contributor,
        read_only=False,
        hidden=False,
        description="",
        example=None,
        query_label=None,
        query_description=None,
        tom_select=False,
        render_kw: dict = None,
        predicate_alias: list = None,
        comparison_operators: str = None,
        directives: list = None,
    ) -> None:
        """
        Contruct a new Primitive Predicate
        """

        self.predicate = None
        self._label = label
        self.read_only = read_only
        self.hidden = hidden
        self.new = new
        self.edit = edit

        self.example = example or "some string"
        self.queryable = queryable
        self.query_label = query_label or label
        self.query_description = query_description
        self.permission = permission
        self.operators = comparison_operators

        if directives:
            if self.dgraph_directives:
                self.dgraph_directives += directives
            else:
                self.dgraph_directives = directives

        # Facets: parameter should accept lists and single Facet objects
        if isinstance(facets, Facet):
            facets = [facets]

        if facets:
            self.facets = {facet.key: facet for facet in facets}
        else:
            self.facets = None

        if isinstance(comparison_operators, dict):
            comparison_operators = [(k, v) for k, v in comparison_operators.items()]
            comparison_operators.insert(0, ("", ""))
        self.operators = comparison_operators

        # WTF Forms
        self.required = required
        self.description = description
        self.form_description = description
        self.tom_select = tom_select
        self.render_kw = render_kw or {}

        if hidden:
            self.render_kw.update(hidden=hidden)

        if read_only:
            self.render_kw.update(readonly=read_only)

        # default value applied when nothing is specified
        if callable(default):
            self._default = default
        elif (
            isinstance(default, (Scalar, UID, NewID, list, tuple, set))
            or default is None
        ):
            self._default = default
        else:
            self._default = Scalar(default)

        # delete all values first before writing new ones
        self.overwrite = overwrite

        # other references to this predicate
        # this is used for querying several predicates at once
        # but they also have different creation logics
        self.predicate_alias = predicate_alias

    def __str__(self) -> str:
        return f"{self.predicate}"

    def __repr__(self) -> str:
        if self.predicate:
            return f'<Primitive "{self.predicate}">'
        else:
            return f"<Unbound Primitive>"

    @classmethod
    def from_key(cls, key):
        cls_ = cls()
        cls_.predicate = key
        return cls_

    @property
    def default(self):
        try:
            # check if default value is result of a function
            return self._default()
        except:
            return self._default

    @property
    def label(self) -> str:
        if self._label:
            return self._label
        else:
            return self.predicate.replace("_", " ").title()

    @property
    def nquad(self) -> str:
        if self.predicate == "*":
            return "*"
        else:
            return f"<{self.predicate}>"

    @property
    def query(self) -> str:
        return f"{self.predicate}"

    def validation_hook(self, data):
        # this method is called in validation by default
        # when custom validation is required, overwriting this hook
        # is the preferred way.
        return data

    def validate(self, data, facets: dict = None, **kwargs):
        # Validation method that is called by data sanitizer
        # When overwriting this method make sure to accept
        # `facets` as keyword argument
        # preferably this method should return a Scalar object

        if not self.overwrite and data is None:
            raise InventoryValidationError(
                f"Tried to delete predicate <{self.predicate}> by supplying null value."
            )

        data = self.validation_hook(data)

        if isinstance(data, (list, set, tuple)):
            _data = []
            for item in data:
                if isinstance(item, (str, int, datetime.datetime, datetime.date)):
                    _data.append(Scalar(item))
                else:
                    _data.append(item)

            if facets:
                assert isinstance(facets, dict), InventoryValidationError(
                    f"Error in <{self.predicate}>: Facets provided in wrong format!"
                )
                for key, val in facets.items():
                    assert isinstance(val, dict), InventoryValidationError(
                        f"Error in <{self.predicate}>: Facets provided in wrong format!"
                    )
                    for counter, subval in val.items():
                        _data[int(counter)].update_facets({key: subval})

            return _data

            # return [Scalar(item, facets=facets) if isinstance(item, (str, int, datetime.datetime, datetime.date)) else item for item in data]
        elif isinstance(data, (str, int, datetime.datetime, datetime.date)):
            return Scalar(data, facets=facets)
        else:
            return data

    def query_filter(
        self,
        vals: Union[str, list],
        predicate=None,
        operator: AvailableOperators = None,
        connector: AvailableConnectors = None,
        **kwargs,
    ) -> str:
        if not predicate:
            predicate = self.predicate

        if vals is None:
            return f"{has(predicate)}"

        if not operator:
            operator = self.default_operator

        if isinstance(operator, str):
            try:
                operator = operator_conversion[operator]
            except:
                operator = self.default_operator

        if not connector:
            connector = self.default_connector

        if not isinstance(vals, list):
            vals = [vals]

        if "uid" in self.dgraph_predicate_type:
            vals = [validate_uid(v) for v in vals if validate_uid(v)]

        if len(vals) == 0:
            return f"{has(predicate)}"

        try:
            if connector == "AND":
                f = [str(operator(predicate, strip_query(val))) for val in vals]
                _f = " AND ".join(f)
                return f"({_f})"
            else:
                vals = [strip_query(v) for v in vals]
                return f"{operator(predicate, vals)}"
        except:
            return f"{has(predicate)}"

    def _prepare_query_field(self):
        # not a very elegant solution...
        # provides a hook for UI (JavaScript)
        if isinstance(self, ReverseRelationship):
            self.render_kw.update(
                {
                    "data-entities": ",".join(
                        Schema.__reverse_predicates_types__[self.predicate]
                    )
                }
            )
        elif self.predicate:
            self.render_kw.update(
                {"data-entities": ",".join(Schema.__predicates_types__[self.predicate])}
            )

    @property
    def query_field(self) -> StringField:
        self._prepare_query_field()
        return StringField(label=self.query_label, render_kw=self.render_kw)

    """ ORM Methods """

    def __hash__(self):
        return id(self)

    def __eq__(self, other) -> DQLQuery:
        var = GraphQLVariable(other=other)
        if self.bound_dgraph_type:
            query = DQLQuery(
                query_name=self.bound_dgraph_type.lower(),
                func=type_(self.bound_dgraph_type),
                query_filter=self.default_operator(self.query, var),
                fetch=["uid", "expand(_all_)"],
            )
            return query

        query = DQLQuery(
            func=has(self.predicate),
            query_filter=self.default_operator(self.query, var),
            fetch=["uid", "expand(_all_)"],
        )
        return query

    def count(self, **kwargs) -> str:
        query_filter = kwargs.get("query_filter", [])

        if self.bound_dgraph_type:
            query_filter.append(has(self.predicate))
            query = DQLQuery(
                query_name=self.predicate.lower(),
                func=type_(self.bound_dgraph_type),
                query_filter=query_filter,
                fetch=["count(uid)"],
            )
            return query

        query = DQLQuery(
            query_name=self.predicate.lower(),
            func=has(self.predicate),
            query_filter=query_filter,
            fetch=["count(uid)"],
        )

        return query

    """ OpenAPI stuff """

    @property
    def openapi_component(self) -> dict:
        """base property that represents this dgraph predicate as an openapi component"""
        return {"type": "string"}

    @property
    def openapi_query_parameter(self) -> dict:
        qp = {
            "name": self.predicate,
            "in": "query",
            "description": self.description,
            "required": False,
            "example": self.example,
            "schema": {
                "type": "array",
                "items": {"type": "string"},
            },
        }
        connector = {
            "name": self.predicate + "*connector",
            "in": "query",
            "description": "Logical connectors for combining an array",
            "required": False,
            "schema": {
                "type": "string",
                "enum": [c for c in get_args(AvailableConnectors)],
                "default": self.default_connector,
            },
        }
        return {
            self.predicate + "QueryParam": qp,
            self.predicate + "QueryConnector": connector,
        }


class Predicate(_PrimitivePredicate):
    """
    Base Class for representing DGraph Predicates
    Is used for validating data, generating DGraph queries & mutations,
    and also provides generators for WTF Form Fields

    """

    def __init__(self, large_textfield=False, *args, **kwargs) -> None:
        """
        Contruct a new predicate

        :param label:
            User facing label for predicate,
            default: automatically generated from 'predicate'
        :param default:
            Default value when validating when nothing is specified
        :param overwrite:
            delete all values first before writing new ones.
        :param new:
            show this predicate when a new entry is made.
        :param edit:
            show this predicate when entry is edited.
        :param read_only:
            if 'True' users cannot edit this field.
        :param hidden:
            if 'True' form field will be hidden from users.
        :param required:
            Sets required flag for generated WTF Field.
        :param description:
            Passes description to WTF Field.
        :param tom_select:
            Instantiate TomSelect classes for WTF Fields.
        :param large_textfield:
            If true renders a TextAreaField
        """

        super().__init__(*args, **kwargs)

        self.large_textfield = large_textfield

    def __str__(self) -> str:
        return f"{self.predicate}"

    def __repr__(self) -> str:
        if self.predicate:
            return f'<DGraph Predicate "{self.predicate}">'
        else:
            return f"<Unbound DGraph Predicate>"

    @property
    def wtf_field(self) -> StringField:
        if self.required:
            validators = [DataRequired()]
        else:
            validators = [Optional()]
        if self.large_textfield:
            return TextAreaField(
                label=self.label,
                validators=validators,
                description=self.form_description,
                render_kw=self.render_kw,
            )
        return StringField(
            label=self.label,
            validators=validators,
            description=self.form_description,
            render_kw=self.render_kw,
        )


class Scalar:
    """
    Utility class for Single Values
    """

    def __init__(self, value: Any, facets: dict = None) -> None:
        if type(value) in [datetime.date, datetime.datetime]:
            self.year = value.year
            self.month = value.month
            self.day = value.day
            value = value.isoformat()
        elif type(value) is bool:
            value = str(value).lower()

        self.value = str(value).strip()
        if self.value != "*":
            self.value = json.dumps(self.value)
        self.facets = facets

    def __str__(self) -> str:
        if self.value != "*":
            return json.loads(self.value)
        else:
            return self.value

    def __repr__(self) -> str:
        if self.facets:
            return f"{self.value} ({self.facets})"
        return f"{self.value}"

    def update_facets(self, facets: dict) -> None:
        if self.facets:
            self.facets.update(facets)
        else:
            self.facets = facets

    @property
    def nquad(self) -> str:
        if self.value == "*":
            return "*"
        else:
            return f"""{self.value}"""


class GeoScalar(Scalar):
    """
    DGraph uses the convention of Lon, Lat
    Currently only supports Point Locations
    """

    def __init__(self, geotype, coordinates, facets=None):
        self.geotype = geotype
        if isinstance(coordinates, (list, tuple)):
            assert len(coordinates) == 2, "Coordinates are not a pair!"
            self.coordinates = [round(c, 12) for c in coordinates]
            self.lon, self.lat = coordinates
        elif isinstance(coordinates, dict):
            assert (
                "lat" in coordinates and "lon" in coordinates
            ), "Coordinates malformed"
            self.coordinates = [
                round(coordinates.get("lat"), 12),
                round(coordinates.get("lon"), 12),
            ]
            self.lat = coordinates.get("lat")
            self.lon = coordinates.get("lon")
        self.value = {"type": geotype, "coordinates": coordinates}
        self.facets = facets

    def __str__(self) -> str:
        return str(self.value)

    @property
    def nquad(self) -> str:
        return '"' + str(self.value) + '"^^<geo:geojson>'


class Variable:
    """Represents DGraph Query Variable"""

    def __init__(self, var, predicate, val=False):
        self.var = var
        self.predicate = predicate
        self.val = val

    def __str__(self) -> str:
        return f"{self.var}"

    def __repr__(self) -> str:
        return f"{self.var} as {self.predicate}"

    @property
    def nquad(self) -> str:
        if self.val:
            return f"val({self.var})"
        else:
            return f"uid({self.var})"

    @property
    def query(self) -> str:
        return f"{self.var} as {self.predicate}"


class ReverseRelationship(_PrimitivePredicate):
    """
    default_predicates: dict with additional predicates that should be assigned to new entries
    """

    dgraph_predicate_type = "uid"
    default_operator = uid_in

    def __init__(
        self,
        predicate_name,
        allow_new=False,
        autoload_choices=True,
        relationship_constraint=None,
        overwrite=False,
        default_predicates=None,
        example="0x123",
        *args,
        **kwargs,
    ) -> None:
        super().__init__(overwrite=overwrite, example=example, *args, **kwargs)

        if isinstance(relationship_constraint, str):
            relationship_constraint = [relationship_constraint]
        self.relationship_constraint = relationship_constraint
        self._predicate = f"~{predicate_name}"
        self._target_predicate = predicate_name
        self.predicate = predicate_name
        self.allow_new = allow_new
        self.render_kw.update({"data-ts-create": allow_new})

        self.default_predicates = default_predicates

        # Facets
        if self.facets:
            for facet in self.facets.values():
                facet.predicate = predicate_name

        # WTForms
        # if we want the form field to show all choices automatically.
        self.autoload_choices = autoload_choices
        self.choices = {}
        self.choices_dicts = []
        self.choices_tuples = []
        self.entry_uid = None

    def __str__(self) -> str:
        return f"{self._predicate}"

    def __repr__(self) -> str:
        if self._predicate:
            return f'<DGraph Reverse Relationship "{self._predicate}">'
        else:
            return f"<Unbound DGraph Reverse Relationship>"

    def validate(self, data, node, facets=None) -> Union[UID, NewID, dict]:
        uid = validate_uid(data)
        if not uid:
            if not self.allow_new:
                raise InventoryValidationError(
                    f"Error in <{self.predicate}>! Adding new items is not allowed, the provided value is not a UID: {data}"
                )
            d = {"uid": NewID(newid=data, facets=facets), self._target_predicate: node}
            if self.relationship_constraint:
                d.update({"dgraph.type": self.relationship_constraint})
            return d
        d = {"uid": UID(uid, facets=facets), self._target_predicate: node}
        if self.relationship_constraint:
            entry_type = dgraph.get_dgraphtype(uid)
            if entry_type not in self.relationship_constraint:
                raise InventoryValidationError(
                    f"Error in <{self.predicate}>! UID specified does not match constraint, UID is not a {self.relationship_constraint}!: uid <{uid}> <dgraph.type> <{entry_type}>"
                )
        return d

    def get_choices(self):
        assert self.relationship_constraint

        query_string = "{ "

        for dgraph_type in self.relationship_constraint:
            query_string += f"""{dgraph_type.lower()}(func: type("{dgraph_type}"), orderasc: name) {{ uid name _unique_name }} """

        query_string += "}"

        choices = dgraph.query(query_string=query_string)

        if len(self.relationship_constraint) == 1:
            self.choices = {
                c["uid"]: c["name"]
                for c in choices[self.relationship_constraint[0].lower()]
            }
            self.choices_tuples = [
                (c["uid"], c["name"])
                for c in choices[self.relationship_constraint[0].lower()]
            ]

        else:
            self.choices = {}
            self.choices_tuples = {}
            for dgraph_type in self.relationship_constraint:
                self.choices_tuples[dgraph_type] = [
                    (c["uid"], c["name"]) for c in choices[dgraph_type.lower()]
                ]
                self.choices.update(
                    {c["uid"]: c["name"] for c in choices[dgraph_type.lower()]}
                )

    @property
    def wtf_field(self) -> TomSelectField:
        if self.autoload_choices and self.relationship_constraint:
            self.get_choices()
        return TomSelectField(
            label=self.label,
            description=self.form_description,
            choices=self.choices_tuples,
            render_kw=self.render_kw,
        )

    def query_filter(self, vals: Union[str, list], **kwargs) -> str:
        return super().query_filter(vals, predicate=self._predicate, **kwargs)

    @property
    def query_field(self) -> TomSelectMultipleField:
        if self.autoload_choices and self.relationship_constraint:
            self.get_choices()
        self._prepare_query_field()
        return TomSelectMultipleField(
            label=self.query_label,
            choices=self.choices_tuples,
            render_kw=self.render_kw,
        )

    """ ORM Methods """

    def count(self, uid, **kwargs):
        filt = [f"uid_in({self.predicate}, {uid})"]
        if kwargs:
            filt += [f'eq({k}, "{v}")' for k, v in kwargs.items()]

        filt = " AND ".join(filt)
        filt = f"@filter({filt})"

        return f"{{ {self._predicate}(func: has({self.predicate})) {filt} {{ count(uid) }} }}"

    @property
    def openapi_component(self) -> dict:
        o = {"x-allow-new": self.allow_new}
        if self.description:
            o["description"] = self.description
        if self.relationship_constraint:
            if len(self.relationship_constraint) > 1:
                o["oneOf"] = [
                    {"$ref": "#/components/schemas/" + constraint}
                    for constraint in self.relationship_constraint
                ]
            else:
                o["$ref"] = "#/components/schemas/" + self.relationship_constraint[0]

        return o

    @property
    def openapi_query_parameter(self) -> dict:
        qp = {
            "name": self.predicate,
            "in": "query",
            "description": self.description,
            "required": False,
            "example": self.example,
            "schema": {
                "type": "array",
                "items": {"type": "string", "format": "uid"},
            },
        }
        connector = {
            "name": self.predicate + "*connector",
            "in": "query",
            "description": "Logical connectors for combining an array",
            "required": False,
            "schema": {
                "type": "string",
                "enum": [c for c in get_args(AvailableConnectors)],
                "default": self.default_connector,
            },
        }
        return {
            self.predicate + "QueryParam": qp,
            self.predicate + "QueryConnector": connector,
        }


class ReverseListRelationship(ReverseRelationship):
    is_list_predicate = True
    default_connector = "AND"

    def validate(self, data, node, facets=None) -> Union[UID, NewID, dict]:
        if isinstance(data, str):
            data = data.split(",")

        data = set([item.strip() for item in data])
        uids = []

        for item in data:
            uid = super().validate(item, node, facets=facets)
            uids.append(uid)

        return uids

    def get_choices(self):
        assert self.relationship_constraint

        query_string = "{ "

        for dgraph_type in self.relationship_constraint:
            query_string += f"""{dgraph_type.lower()}(func: type("{dgraph_type}"), orderasc: name) {{ uid name _unique_name }} """

        query_string += "}"

        choices = dgraph.query(query_string=query_string)

        if len(self.relationship_constraint) == 1:
            self.choices = {
                c["uid"]: c["name"]
                for c in choices[self.relationship_constraint[0].lower()]
            }
            self.choices_tuples = [
                (c["uid"], c["name"])
                for c in choices[self.relationship_constraint[0].lower()]
            ]

        else:
            self.choices = {}
            self.choices_tuples = {}
            for dgraph_type in self.relationship_constraint:
                self.choices_tuples[dgraph_type] = [
                    (c["uid"], c["name"]) for c in choices[dgraph_type.lower()]
                ]
                self.choices.update(
                    {c["uid"]: c["name"] for c in choices[dgraph_type.lower()]}
                )

    @property
    def wtf_field(self) -> TomSelectMultipleField:
        if self.autoload_choices and self.relationship_constraint:
            self.get_choices()
        return TomSelectMultipleField(
            label=self.label,
            description=self.form_description,
            choices=self.choices_tuples,
            render_kw=self.render_kw,
        )

    @property
    def openapi_component(self) -> dict:
        o = {"type": "array", "x-allow-new": self.allow_new}

        if self.description:
            o["description"] = self.description
        if self.relationship_constraint:
            if len(self.relationship_constraint) > 1:
                o["items"] = {
                    "anyOf": [
                        {"$ref": "#/components/schemas/" + constraint}
                        for constraint in self.relationship_constraint
                    ]
                }
            else:
                o["items"] = {
                    "$ref": "#/components/schemas/" + self.relationship_constraint[0]
                }

        return o


class MutualRelationship(_PrimitivePredicate):
    dgraph_predicate_type = "uid"
    dgraph_directives = ["@reverse"]
    is_list_predicate = False
    default_operator = uid_in

    def __init__(
        self,
        allow_new=False,
        autoload_choices=True,
        relationship_constraint=None,
        overwrite=True,
        example="0x123",
        *args,
        **kwargs,
    ) -> None:
        super().__init__(overwrite=overwrite, example=example, *args, **kwargs)

        if isinstance(relationship_constraint, str):
            relationship_constraint = [relationship_constraint]
        self.relationship_constraint = relationship_constraint

        self.allow_new = allow_new
        self.render_kw.update({"data-ts-create": allow_new})

        # if we want the form field to show all choices automatically.
        self.autoload_choices = autoload_choices
        self.choices = {}
        self.choices_dicts = []
        self.choices_tuples = []
        self.entry_uid = None

    def __str__(self) -> str:
        return f"{self.predicate}"

    def __repr__(self) -> str:
        if self.predicate:
            return f'<Mutual Relationship Predicate "{self.predicate}">'
        else:
            return f"<Unbound Mutual Relationship Predicate>"

    def validate(self, data, node, facets=None) -> Union[UID, NewID, dict]:
        """
        Returns two values:
        1) UID/NewID of target
        2) dict for target relationship
        """
        uid = validate_uid(data)
        if not uid:
            if not self.allow_new:
                raise InventoryValidationError(
                    f"Error in <{self.predicate}>! provided value is not a UID: {data}"
                )
            node_data = NewID(newid=data, facets=facets)
            data_node = {"uid": node_data, self.predicate: node, "name": data}
            if self.relationship_constraint:
                data_node.update({"dgraph.type": self.relationship_constraint})
            return node_data, data_node
        node_data = UID(uid, facets=facets)
        data_node = {"uid": node_data, self.predicate: node}
        if self.relationship_constraint:
            entry_type = dgraph.get_dgraphtype(uid)
            if entry_type not in self.relationship_constraint:
                raise InventoryValidationError(
                    f"Error in <{self.predicate}>! UID specified does not match constraint, UID is not a {self.relationship_constraint}!: uid <{uid}> <dgraph.type> <{entry_type}>"
                )
        return node_data, data_node

    def get_choices(self):
        assert self.relationship_constraint

        query_string = "{ "

        for dgraph_type in self.relationship_constraint:
            query_string += f"""{dgraph_type.lower()}(func: type("{dgraph_type}"), orderasc: name) {{ uid name _unique_name }} """

        query_string += "}"

        choices = dgraph.query(query_string=query_string)

        if len(self.relationship_constraint) == 1:
            self.choices = {
                c["uid"]: c["name"]
                for c in choices[self.relationship_constraint[0].lower()]
            }
            self.choices_tuples = [
                (c["uid"], c["name"])
                for c in choices[self.relationship_constraint[0].lower()]
            ]

        else:
            self.choices = {}
            self.choices_tuples = {}
            for dgraph_type in self.relationship_constraint:
                self.choices_tuples[dgraph_type] = [
                    (c["uid"], c["name"]) for c in choices[dgraph_type.lower()]
                ]
                self.choices.update(
                    {c["uid"]: c["name"] for c in choices[dgraph_type.lower()]}
                )

    @property
    def wtf_field(self) -> TomSelectField:
        if self.autoload_choices and self.relationship_constraint:
            self.get_choices()
        return TomSelectField(
            label=self.label,
            description=self.form_description,
            choices=self.choices_tuples,
            render_kw=self.render_kw,
        )

    @property
    def openapi_component(self) -> dict:
        o = {"x-allow-new": self.allow_new}
        if self.description:
            o["description"] = self.description
        if self.relationship_constraint:
            if len(self.relationship_constraint) > 1:
                o["oneOf"] = [
                    {"$ref": "#/components/schemas/" + constraint}
                    for constraint in self.relationship_constraint
                ]
            else:
                o["$ref"] = "#/components/schemas/" + self.relationship_constraint[0]

        return o

    @property
    def openapi_query_parameter(self) -> dict:
        qp = {
            "name": self.predicate,
            "in": "query",
            "description": self.description,
            "required": False,
            "example": self.example,
            "schema": {
                "type": "array",
                "items": {"type": "string", "format": "uid"},
            },
        }
        connector = {
            "name": self.predicate + "*connector",
            "in": "query",
            "description": "Logical connectors for combining an array",
            "required": False,
            "schema": {
                "type": "string",
                "enum": [c for c in get_args(AvailableConnectors)],
                "default": self.default_connector,
            },
        }
        return {
            self.predicate + "QueryParam": qp,
            self.predicate + "QueryConnector": connector,
        }


class MutualListRelationship(MutualRelationship):
    dgraph_predicate_type = "[uid]"
    _type = list
    is_list_predicate = True
    default_connector = "AND"

    def validate(self, data, node, facets=None) -> Union[UID, NewID, dict]:
        if isinstance(data, (str)):
            data = data.split(",")

        node_data = []
        data_node = []
        for item in data:
            n2d, d2n = super().validate(item, node, facets)
            node_data.append(n2d)
            data_node.append(d2n)

        # permutate all relationships
        all_uids = [item for item in node_data]
        all_uids.append(node)
        for item in data_node:
            item[self.predicate] = [uid for uid in all_uids if uid != item["uid"]]

        return node_data, data_node

    @property
    def wtf_field(self) -> TomSelectField:
        if self.autoload_choices and self.relationship_constraint:
            self.get_choices()
        return TomSelectMultipleField(
            label=self.label,
            description=self.form_description,
            choices=self.choices_tuples,
            render_kw=self.render_kw,
        )

    @property
    def openapi_component(self) -> dict:
        o = {"type": "array", "x-allow-new": self.allow_new}
        if self.description:
            o["description"] = self.description
        if self.relationship_constraint:
            if len(self.relationship_constraint) > 1:
                o["items"] = {
                    "anyOf": [
                        {"$ref": "#/components/schemas/" + constraint}
                        for constraint in self.relationship_constraint
                    ]
                }
            else:
                o["items"] = {
                    "$ref": "#/components/schemas/" + self.relationship_constraint[0]
                }

        return o


"""
    Predicate Classes
"""


class String(Predicate):
    dgraph_predicate_type = "string"
    is_list_predicate = False

    def __init__(self, *args, overwrite=True, **kwargs) -> None:
        super().__init__(*args, overwrite=overwrite, **kwargs)

    @property
    def openapi_component(self) -> dict:
        o = {"type": "string"}
        if self.description:
            o["description"] = self.description
        return o


class UIDPredicate(Predicate):
    """
    This class represents the uid value that each node in Dgraph has by default.
    Not to be confused with relationships!
    """

    dgraph_predicate_type = "_uid"
    is_list_predicate = False
    default_operator = uid_in  # maybe needs to be changed

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(
            read_only=True,
            hidden=True,
            new=False,
            edit=False,
            default=NewID,
            *args,
            **kwargs,
        )

    def validate(self, uid, **kwargs):
        if not validate_uid(uid):
            raise InventoryValidationError(f"This is not a uid: {uid}")
        else:
            return UID(uid)

    def __eq__(self, other) -> DQLQuery:
        var = GraphQLVariable(other=other)

        if self.bound_dgraph_type:
            query = DQLQuery(
                query_name=self.bound_dgraph_type.lower(),
                func=uid(var),
                query_filter=type_(self.bound_dgraph_type),
                fetch=["uid", "expand(_all_)"],
            )
            return query

        return DQLQuery(func=uid(var), fetch=["uid", "expand(_all_)"])

    @property
    def openapi_component(self) -> dict:
        o = {"type": "string"}
        o["description"] = "unique UID of object (hex value)"
        return o


class Integer(Predicate):
    dgraph_predicate_type = "int"
    _type = int
    is_list_predicate = False

    def __init__(self, example=7, *args, **kwargs) -> None:
        super().__init__(*args, example=example, **kwargs)

    def validation_hook(self, data):
        return int(data)

    @property
    def wtf_field(self) -> IntegerField:
        if self.required:
            validators = [DataRequired()]
        else:
            validators = [Optional()]
        return IntegerField(
            label=self.label, validators=validators, description=self.form_description
        )

    @property
    def query_field(self) -> IntegerField:
        self._prepare_query_field()
        return IntegerField(label=self.query_label, render_kw=self.render_kw)

    @property
    def openapi_component(self) -> dict:
        o = {"type": "integer"}
        if self.description:
            o["description"] = self.description
        return o


class ListString(String):
    dgraph_predicate_type = "[string]"
    _type = list
    is_list_predicate = True
    default_connector = "AND"

    def __init__(self, delimiter=",", overwrite=True, *args, **kwargs) -> None:
        self.delimiter = delimiter
        super().__init__(overwrite=overwrite, *args, **kwargs)

    def validation_hook(self, data):
        if data is None:
            return None
        if not isinstance(data, (list, tuple, set, str)):
            raise InventoryValidationError(
                f"Error in <{self.predicate}> Provided data is not a list, tuple, str or set: {data}"
            )
        if type(data) == str:
            data = data.split(self.delimiter)
        return [item.strip() for item in data if item.strip() != ""]

    @property
    def openapi_component(self) -> dict:
        o = {"type": "array", "items": {"type": "string"}}
        if self.description:
            o["description"] = self.description
        return o


class Password(Predicate):
    dgraph_predicate_type = "password"
    is_list_predicate = False

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    @property
    def wtf_field(self) -> PasswordField:
        if self.required:
            validators = [DataRequired()]
        else:
            validators = [Optional()]
        return PasswordField(
            label=self.label, validators=validators, description=self.form_description
        )

    @property
    def openapi_component(self) -> dict:
        o = {"type": "string", "format": "password"}
        if self.description:
            o["description"] = self.description
        return o


class UniqueName(String):
    """
    Included here for Data Modelling
    Actual assignment for new _unique_name happens in the data sanitation
    DGraph does not support a true "unique" constraint yet.
    """

    dgraph_directives = ["@index(hash, trigram)", "@upsert"]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(
            required=True,
            new=False,
            overwrite=False,
            permission=USER_ROLES.Reviewer,
            *args,
            **kwargs,
        )

    @property
    def default(self):
        return None

    # def validate(self, data, uid):
    #     data = str(data)
    #     check = dgraph.get_uid(self.predicate, data)
    #     if check:
    #         if check != str(uid):
    #             raise InventoryValidationError(
    #                 'Unique Name already taken!')
    #     return slugify(data, separator="_")


class SingleChoice(String):
    dgraph_directives = ["@index(hash)"]

    def __init__(
        self, *args, choices: dict = None, default="NA", radio_field=False, **kwargs
    ) -> None:
        super().__init__(*args, default=default, overwrite=True, **kwargs)

        self.choices = choices or {"NA": "NA"}
        self.choices_tuples = [(k, v) for k, v in self.choices.items()]
        self.values = list(self.choices.keys())
        self.radio_field = radio_field

    def validation_hook(self, data):
        if str(data) in self.values:
            return str(data)
        else:
            raise InventoryValidationError(
                f"Wrong value provided for {self.predicate}: {data}. Value has to be one of {', '.join(self.values)}"
            )

    def set_choices(self, choices: dict) -> None:
        self.choices = choices
        self.choices_tuples = [(k, v) for k, v in self.choices.items()]
        self.values = list(self.choices.keys())

    @property
    def wtf_field(self) -> Union[SelectField, TomSelectField, RadioField]:
        if self.required:
            validators = [DataRequired()]
        else:
            validators = [Optional()]
        if self.tom_select:
            return TomSelectField(
                label=self.label,
                validators=validators,
                description=self.form_description,
                choices=self.choices_tuples,
                render_kw=self.render_kw,
            )
        elif self.radio_field:
            return RadioField(
                label=self.label,
                validators=validators,
                description=self.form_description,
                choices=self.choices_tuples,
                render_kw=self.render_kw,
            )
        else:
            return SelectField(
                label=self.label,
                validators=validators,
                description=self.form_description,
                choices=self.choices_tuples,
                render_kw=self.render_kw,
            )

    @property
    def query_field(self) -> TomSelectMultipleField:
        self._prepare_query_field()
        return TomSelectMultipleField(
            label=self.query_label,
            choices=self.choices_tuples,
            render_kw=self.render_kw,
        )

    @property
    def openapi_component(self) -> dict:
        o = {"type": "string", "enum": list(self.choices.keys())}
        o["description"] = ""
        if self.description:
            o["description"] += self.description + "\n  "
        o["description"] += "Allowed choices:\n"
        for k, v in self.choices.items():
            o["description"] += f" * `{k}` - {v}\n"

        return o

    @property
    def openapi_query_parameter(self) -> dict:
        qp = {
            "name": self.predicate,
            "in": "query",
            "description": self.description,
            "required": False,
            "schema": {
                "type": "array",
                "items": {"type": "string", "enum": list(self.choices.keys())},
            },
        }

        return {self.predicate + "QueryParam": qp}


class MultipleChoice(SingleChoice):
    dgraph_predicate_type = "[string]"
    _type = list
    is_list_predicate = True
    default_connector = "AND"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    def validation_hook(self, data):
        if isinstance(data, str):
            data = data.split(",")
        if not isinstance(data, list):
            raise InventoryValidationError(
                f'Error in <{self.predicate}>! Provided data cannot be coerced to "list": {data}'
            )
        for val in data:
            if val.strip() not in self.values:
                raise InventoryValidationError(
                    f"Wrong value provided for {self.predicate}: {val}. Value has to be one of {', '.join(self.values)}"
                )

        return data

    @property
    def wtf_field(self) -> Union[SelectMultipleField, TomSelectMultipleField]:
        if self.required:
            validators = [DataRequired()]
        else:
            validators = [Optional()]
        if self.tom_select:
            return TomSelectMultipleField(
                label=self.label,
                validators=validators,
                description=self.form_description,
                choices=self.choices_tuples,
                render_kw=self.render_kw,
            )
        return SelectMultipleField(
            label=self.label,
            validators=validators,
            description=self.form_description,
            choices=self.choices_tuples,
            render_kw=self.render_kw,
        )

    @property
    def query_field(self) -> TomSelectMultipleField:
        self._prepare_query_field()
        return TomSelectMultipleField(
            label=self.query_label,
            choices=self.choices_tuples,
            render_kw=self.render_kw,
        )

    @property
    def openapi_component(self) -> dict:
        o = {
            "type": "array",
            "items": {"type": "string", "enum": list(self.choices.keys())},
        }
        o["description"] = ""
        if self.description:
            o["description"] += self.description + "\n  "
        o["description"] += "Allowed choices:\n"
        for k, v in self.choices.items():
            o["description"] += f" * `{k}` - {v}\n"

        return o

    @property
    def openapi_query_parameter(self) -> dict:
        qp = {
            "name": self.predicate,
            "in": "query",
            "description": self.description,
            "required": False,
            "schema": {
                "type": "array",
                "items": {"type": "string", "enum": list(self.choices.keys())},
            },
        }
        connector = {
            "name": self.predicate + "*connector",
            "in": "query",
            "description": "Logical connectors for combining an array",
            "required": False,
            "schema": {
                "type": "string",
                "enum": [c for c in get_args(AvailableConnectors)],
                "default": self.default_connector,
            },
        }
        return {
            self.predicate + "QueryParam": qp,
            self.predicate + "QueryConnector": connector,
        }


class DateTime(Predicate):
    dgraph_predicate_type = "datetime"
    is_list_predicate = False
    default_operator = between

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    def validation_hook(self, data):
        if isinstance(data, (datetime.date, datetime.datetime)):
            return data
        elif isinstance(data, int):
            try:
                return datetime.date(year=data, month=1, day=1)
            except:
                pass
        try:
            return dateparser.parse(data)
        except:
            raise InventoryValidationError(
                f"Error in <{self.predicate}> Cannot parse provided value to date: {data}"
            )

    @property
    def wtf_field(self) -> Union[DateField, NullableDateField]:
        render_kw = {"type": "date"}
        if self.render_kw:
            render_kw = {**self.render_kw, **render_kw}
        if self.required:
            return DateField(
                label=self.label, description=self.form_description, render_kw=render_kw
            )
        else:
            return NullableDateField(
                label=self.label, description=self.form_description, render_kw=render_kw
            )

    @property
    def query_field(self) -> IntegerField:
        self._prepare_query_field()
        render_kw = {"step": 1, "min": 1500, "max": 2100}
        if self.render_kw:
            render_kw = {**self.render_kw, **render_kw}
        return IntegerField(label=self.query_label, render_kw=self.render_kw)

    def query_filter(
        self,
        vals: Union[str, list, int],
        operator: Union[le, ge, gt, lt, str] = None,
        **kwargs,
    ) -> str:
        if vals is None:
            return f"{has(self.predicate)}"

        if isinstance(operator, str):
            operator = operator_conversion[operator]

        try:
            if isinstance(vals, list) and len(vals) > 1:
                vals = [self.validation_hook(val) for val in vals[:2]]
                v1 = f'"{vals[0].year}-01-01"'
                v2 = f'"{vals[1].year}-12-31"'
                return f"{self.default_operator(self.predicate, v1, v2)}"

            else:
                if isinstance(vals, list):
                    vals = vals[0]
                date = self.validation_hook(vals)
                if operator:
                    return f"{operator(self.predicate, date.year)}"
                else:
                    v1 = f'"{date.year}-01-01"'
                    v2 = f'"{date.year}-12-31"'
                    return f"{self.default_operator(self.predicate, v1, v2)}"
        except:
            return f"{has(self.predicate)}"

    @property
    def openapi_component(self) -> dict:
        o = {"type": "string", "format": "date-time"}
        if self.description:
            o["description"] = self.description
        return o


class ListDatetime(DateTime):
    dgraph_predicate_type = "[datetime]"
    _type = list

    def __init__(self, overwrite=True, *args, **kwargs) -> None:
        super().__init__(overwrite=overwrite, *args, **kwargs)

    def validation_hook(self, data):
        if data is None:
            return None
        if isinstance(data, (list, tuple, set)):
            _data = []
            for val in data:
                try:
                    _data.append(dateparser.parse(val))
                except:
                    raise InventoryValidationError(
                        f"Error in <{self.predicate}> Cannot parse provided value to date: {data}"
                    )
            return _data
        if isinstance(data, (datetime.date, datetime.datetime)):
            return data
        elif isinstance(data, int):
            try:
                return datetime.date(year=data, month=1, day=1)
            except:
                pass
        try:
            return dateparser.parse(data)
        except:
            raise InventoryValidationError(
                f"Error in <{self.predicate}> Cannot parse provided value to date: {data}"
            )

    @property
    def openapi_component(self) -> dict:
        o = {"type": "array", "items": {"type": "string", "format": "date-time"}}
        if self.description:
            o["description"] = self.description
        return o


class Year(DateTime):
    dgraph_predicate_type = "datetime"
    _type = int

    def validation_hook(self, data):
        if type(data) in [datetime.date, datetime.datetime]:
            return data
        else:
            try:
                return datetime.datetime(year=int(data), month=1, day=1)
            except:
                raise InventoryValidationError(
                    f"Error in <{self.predicate}>: Cannot parse provided value to year: {data}"
                )

    @property
    def wtf_field(self) -> IntegerField:
        render_kw = {"step": 1, "min": 1500, "max": 2100}
        if self.render_kw:
            render_kw = {**self.render_kw, **render_kw}
        if self.required:
            validators = [DataRequired()]
        else:
            validators = [Optional(strip_whitespace=True)]
        return IntegerField(
            label=self.label,
            description=self.form_description,
            render_kw=render_kw,
            validators=validators,
        )

    @property
    def openapi_component(self) -> dict:
        o = {"type": "integer", "minimum": 1500, "maximum": 2100}
        if self.description:
            o["description"] = self.description
        return o


class ListYear(Year):
    dgraph_predicate_type = "[datetime]"
    _type = list

    @property
    def openapi_component(self) -> dict:
        o = {
            "type": "array",
            "items": {"type": "integer", "minimum": 1500, "maximum": 2100},
        }
        if self.description:
            o["description"] = self.description
        return o


class Boolean(Predicate):
    """
    Boolean Predicate (True / False).
    Default always `False`. To change this behaviour set the `default` parameter to `True`

    :param label:
        User facing label for predicate,
        default: automatically generated from 'predicate'
    :param default (False):
        Default value when validating when nothing is specified
    :param description:
        Passes description to WTF Field, will be rendered next to check box.
        E.g., "Yes, I agree"
    """

    dgraph_predicate_type = "bool"
    _type = bool
    is_list_predicate = False

    def __init__(
        self, label: str = None, default=False, overwrite=True, **kwargs
    ) -> None:
        super().__init__(label, default=default, overwrite=overwrite, **kwargs)

    def validation_hook(self, data):
        if isinstance(data, bool):
            return data
        elif isinstance(data, str):
            return data.lower() in ("yes", "true", "t", "1", "y")
        elif isinstance(data, int):
            return data > 0
        else:
            raise InventoryValidationError(
                f"Error in <{self.predicate}>: Cannot evaluate provided value as bool: {data}!"
            )

    def query_filter(self, vals, **kwargs) -> str:
        if isinstance(vals, list):
            vals = vals[0]

        # use DGraph native syntax first
        if vals in ["true", "false"]:
            return f"{eq(self.predicate, vals)}"

        else:
            # try to coerce to bool
            vals = self.validation_hook(vals)
            try:
                return f"{eq(self.predicate, str(vals).lower())}"
            except:
                return f"{has(self.predicate)}"

    @property
    def wtf_field(self) -> BooleanField:
        return BooleanField(label=self.label, description=self.form_description)

    @property
    def query_field(self) -> BooleanField:
        self._prepare_query_field()
        render_kw = deepcopy(self.render_kw)
        render_kw.update({"value": "true"})
        return BooleanField(label=self.query_label, render_kw=render_kw)

    def count(self, **kwargs) -> str:
        query_filter = kwargs.get("query_filter", [])

        if self.bound_dgraph_type:
            query_filter.append(eq(self.predicate, True))
            query = DQLQuery(
                query_name=self.predicate.lower(),
                func=type_(self.bound_dgraph_type),
                query_filter=query_filter,
                fetch=["count(uid)"],
            )
            return query

        query = DQLQuery(
            query_name=self.predicate.lower(),
            func=eq(self.predicate, True),
            query_filter=query_filter,
            fetch=["count(uid)"],
        )

        return query

    @property
    def openapi_component(self) -> dict:
        o = {"type": "boolean"}
        if self.description:
            o["description"] = self.description
        return o

    @property
    def openapi_query_parameter(self) -> dict:
        qp = {
            "name": self.predicate,
            "in": "query",
            "description": self.description,
            "required": False,
            "schema": {"type": "boolean"},
        }

        return {self.predicate + "QueryParam": qp}


class Geo(Predicate):
    dgraph_predicate_type = "geo"
    is_list_predicate = False
    geo_type = "Point"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    def str2geo(self, data: str) -> Union[GeoScalar, None]:
        try:
            geo = geocode(data.strip())
            return GeoScalar(
                self.geo_type,
                coordinates=[float(geo.get("lon")), float(geo.get("lat"))],
            )
        except:
            return None

    def geo2str(self, data: dict) -> Union[str, None]:
        try:
            address_lookup = reverse_geocode(data.get("lat"), data.get("lon"))
            return address_lookup["display_name"]
        except:
            return None


class SingleRelationship(Predicate):
    dgraph_predicate_type = "uid"
    _type = str
    dgraph_directives = ["@reverse"]
    is_list_predicate = False
    default_operator = uid_in

    def __init__(
        self,
        relationship_constraint=None,
        allow_new=False,
        autoload_choices=False,
        example="0x123",
        *args,
        **kwargs,
    ) -> None:
        if isinstance(relationship_constraint, str):
            relationship_constraint = [relationship_constraint]
        self.relationship_constraint = relationship_constraint
        self.allow_new = allow_new

        # if we want the form field to show all choices automatically.
        self.autoload_choices = autoload_choices
        self.choices = {}
        self.choices_dicts = []
        self.choices_tuples = []

        super().__init__(*args, example=example, **kwargs)

        # hook for Tom-Select to decide whether new entries should be allowed
        self.render_kw.update({"data-ts-create": allow_new})

    def validate(self, data, facets=None) -> Union[dict, None]:
        # TODO: Check if this makes sense. Maybe not a good idea to return None
        # Might be better to raise a ValidationError
        if data == "":
            return None
        uid = validate_uid(data)
        if not uid:
            if not self.allow_new:
                raise InventoryValidationError(
                    f"Error in <{self.predicate}>! provided value is not a UID: `{data}`"
                )
            d = {"uid": NewID(newid=data, facets=facets)}
            if self.relationship_constraint:
                d.update({"dgraph.type": self.relationship_constraint})
            return d
        if self.relationship_constraint:
            entry_type = dgraph.get_dgraphtype(uid)
            if entry_type not in self.relationship_constraint:
                raise InventoryValidationError(
                    f"Error in <{self.predicate}>! UID specified does not match constrain, UID is not a {self.relationship_constraint}!: uid <{uid}> <dgraph.type> <{entry_type}>"
                )
        return {"uid": UID(uid, facets=facets)}

    def get_choices(self):
        assert self.relationship_constraint

        query_string = "{ "

        for dgraph_type in self.relationship_constraint:
            query_string += f"""{dgraph_type.lower()}(func: type("{dgraph_type}"), orderasc: name) {{ uid name _unique_name opted_scope dgraph.type entry_review_status }} """

        query_string += "}"

        choices = dgraph.query(query_string=query_string)

        if len(self.relationship_constraint) == 1:
            self.choices = {
                c["uid"]: c.get("name") or c.get("_unique_name")
                for c in choices[self.relationship_constraint[0].lower()]
            }
            self.choices_tuples = [
                (c["uid"], c.get("name") or c.get("_unique_name"))
                for c in choices[self.relationship_constraint[0].lower()]
            ]
            self.choices_tuples.insert(0, ("", ""))
            self.choices_dicts = choices[self.relationship_constraint[0].lower()]

        else:
            self.choices = {}
            self.choices_tuples = {}
            for dgraph_type in self.relationship_constraint:
                self.choices_tuples[dgraph_type] = [
                    (c["uid"], c.get("name") or c.get("_unique_name"))
                    for c in choices[dgraph_type.lower()]
                ]
                self.choices.update(
                    {
                        c["uid"]: c.get("name") or c.get("_unique_name")
                        for c in choices[dgraph_type.lower()]
                    }
                )
                self.choices_dicts += choices[dgraph_type.lower()]

    @property
    def wtf_field(self) -> TomSelectField:
        if self.autoload_choices and self.relationship_constraint:
            self.get_choices()
        if self.required:
            validators = [DataRequired()]
        else:
            validators = [Optional()]
        return TomSelectField(
            label=self.label,
            validators=validators,
            description=self.form_description,
            choices=self.choices_tuples,
            render_kw=self.render_kw,
        )

    @property
    def query_field(self) -> TomSelectMultipleField:
        if self.autoload_choices and self.relationship_constraint:
            self.get_choices()
        self._prepare_query_field()
        return TomSelectMultipleField(
            label=self.query_label,
            choices=self.choices_tuples,
            render_kw=self.render_kw,
        )

    """ ORM Methods """

    def count(self, uid, _reverse=False, **kwargs):
        filt = []
        if self.bound_dgraph_type and _reverse:
            filt.append(f"type({self.bound_dgraph_type})")
        if _reverse:
            filt.append(f'uid_in({self.predicate}, "{uid}")')
        if kwargs:
            filt += [f'eq({k}, "{v}")' for k, v in kwargs.items()]

        if len(filt) > 0:
            filt = " AND ".join(filt)
            filt = f"@filter({filt})"
        else:
            filt = ""

        if _reverse:
            return f"{{ {self.predicate}(func: has({self.predicate})) {filt} {{ count(uid) }} }}"

        return f"{{ {self.predicate}(func: uid({uid})) {{ count({self.predicate} {filt}) }} }}"

    @property
    def openapi_component(self) -> dict:
        o = {"x-allow-new": self.allow_new}
        if self.description:
            o["description"] = self.description
        if self.relationship_constraint:
            if len(self.relationship_constraint) > 1:
                o["oneOf"] = [
                    {"$ref": "#/components/schemas/" + constraint}
                    for constraint in self.relationship_constraint
                ]
            else:
                o["$ref"] = "#/components/schemas/" + self.relationship_constraint[0]

        return o

    @property
    def openapi_query_parameter(self) -> dict:
        qp = {
            "name": self.predicate,
            "in": "query",
            "description": self.description,
            "required": False,
            "example": self.example,
            "schema": {
                "type": "array",
                "items": {"type": "string", "format": "uid"},
            },
        }
        connector = {
            "name": self.predicate + "*connector",
            "in": "query",
            "description": "Logical connectors for combining an array",
            "required": False,
            "schema": {
                "type": "string",
                "enum": [c for c in get_args(AvailableConnectors)],
                "default": self.default_connector,
            },
        }
        return {
            self.predicate + "QueryParam": qp,
            self.predicate + "QueryConnector": connector,
        }


class ListRelationship(SingleRelationship):
    dgraph_predicate_type = "[uid]"
    _type = list
    dgraph_directives = ["@reverse"]
    is_list_predicate = True
    default_connector = "AND"

    def __init__(
        self,
        overwrite=True,
        relationship_constraint=None,
        allow_new=False,
        autoload_choices=False,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(
            relationship_constraint=relationship_constraint,
            allow_new=allow_new,
            autoload_choices=autoload_choices,
            overwrite=overwrite,
            *args,
            **kwargs,
        )

    def validate(self, data, facets=None) -> list:
        if isinstance(data, str):
            data = data.split(",")
        data = set([item.strip() for item in data if item.strip() != ""])
        uids = []
        for item in data:
            uid = super().validate(item, facets=facets)
            if uid:
                uids.append(uid)

        return uids

    @property
    def wtf_field(self) -> TomSelectMultipleField:
        if self.autoload_choices and self.relationship_constraint:
            self.get_choices()
        if self.required:
            validators = [DataRequired()]
        else:
            validators = [Optional()]
        return TomSelectMultipleField(
            label=self.label,
            validators=validators,
            description=self.form_description,
            choices=self.choices_tuples,
            render_kw=self.render_kw,
        )

    @property
    def openapi_component(self) -> dict:
        o = {"type": "array", "x-allow-new": self.allow_new}
        if self.description:
            o["description"] = self.description
        if self.relationship_constraint:
            if len(self.relationship_constraint) > 1:
                o["items"] = {
                    "oneOf": [
                        {"$ref": "#/components/schemas/" + constraint}
                        for constraint in self.relationship_constraint
                    ]
                }
            else:
                o["items"] = {
                    "$ref": "#/components/schemas/" + self.relationship_constraint[0]
                }

        return o


""" Functions for making nquad statements """


def _enquote(string) -> str:
    return f'"{string}"'


def make_nquad(s, p, o) -> str:
    """Strings, Ints, Floats, Bools, Date(times) are converted automatically to Scalar"""

    if not isinstance(s, (UID, NewID, Variable)):
        s = NewID(newid=s)

    if not isinstance(p, Predicate):
        p = Predicate.from_key(p)

    if not isinstance(o, (list, set, Scalar, Variable, UID, NewID)):
        o = Scalar(o)

    nquad_string = f"{s.nquad} {p.nquad} {o.nquad}"

    if hasattr(o, "facets"):
        if o.facets is not None:
            facets = []
            for key, val in o.facets.items():
                if isinstance(val, list):
                    val = val[0]
                if isinstance(val, (datetime.date, datetime.datetime)):
                    facets.append(f"{key}={val.isoformat()}")
                elif isinstance(val, (int, float)):
                    facets.append(f"{key}={val}")
                else:
                    facets.append(f"{key}={_enquote(val)}")
            nquad_string += f' ({", ".join(facets)})'

    nquad_string += " ."
    return nquad_string


def dict_to_nquad(d: dict) -> list:
    if d.get("uid"):
        uid = d["uid"]
    else:
        uid = NewID()
    nquads = []
    for key, val in d.items():
        if val is None:
            continue
        if key == "uid":
            continue
        if not isinstance(key, Predicate):
            key = Predicate.from_key(key)
        if isinstance(val, (list, set)):
            if len(val) > 0:
                for item in val:
                    nquads.append(make_nquad(uid, key, item))
        else:
            nquads.append(make_nquad(uid, key, val))

    return nquads
