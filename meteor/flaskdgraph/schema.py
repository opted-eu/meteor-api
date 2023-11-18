import typing as t
from copy import deepcopy
import json
from datetime import datetime
from flask_wtf import FlaskForm
from wtforms import SubmitField
from wtforms import IntegerField

from meteor.users.constants import USER_ROLES
from inspect import cleandoc

class Schema:

    # TODO: run consititency check. Currently one predicate declaration 
    # can overwrite other predicate declarations with the same name
    # it should be consistent with dgraph that the type of predicate is the same

    # registry of all types and which predicates they have
    # Key = Dgraph Type (string), val = dict of predicates
    __types__ = {}
    __types_meta__ = {}


    # registry of all predicates and which types use them
    # Key = predicate (string), Val = list(Dgraph Type (string))
    __predicates_types__ = {}
    __reverse_predicates_types__ = {}

    __inheritance__ = {}

    # Registry of permissions for each type
    __perm_registry_new__ = {}
    __perm_registry_edit__ = {}

    # Registry of all predicates
    # key = Name of predicate (string), value = predicate (object)
    __predicates__ = {}

    # registry of all relationship predicates
    __relationship_predicates__ = {}

    # registry of all reverse relationships
    # key: dgraph.type where reverse relationship points to
    # value: predicate that points to dgraph.type
    # e.g., {'User': <DGraph Predicate "_added_by">}
    __reverse_relationships__ = {}

    # registry of explicit reverse relationship that should generate a form field
    # key = predicate (string), val = dict of predicates
    __explicit_reverse_relationship_predicates__ = {}

    # registry of all predicates that can be queried by users
    # have their attribute `queryable` set to `True`
    __queryable_predicates__ = {}

    __queryable_predicates_by_type__ = {}

    __private_types__ = []

    # Flag to protect certain dgraph types to be exposed to API endpoints
    __private__ = False

    def __init_subclass__(cls) -> None:

        from .dgraph_types import _PrimitivePredicate, Facet, Predicate, SingleRelationship, ReverseRelationship, MutualRelationship
        # all predicates associated with type
        predicates = {}
        # only relationship predicates
        relationship_predicates = {}
        # reverse relationship predicates
        # reverse_relationships = {}
        # explicit reverse predicates
        reverse_predicates = {}

        # register in __types_meta__
        Schema.__types_meta__[cls.__name__] = {'private': cls.__private__}
        try:
            Schema.__types_meta__[cls.__name__]['description'] = cleandoc(cls.__doc__).replace('\n', '').strip()
        except AttributeError:
            pass

        for key in cls.__dict__:
            val = getattr(cls, key)
            if isinstance(val, (Predicate, MutualRelationship)):
                predicates[key] = val
            if isinstance(val, (SingleRelationship, MutualRelationship)):
                relationship_predicates[key] = val
            if isinstance(val, ReverseRelationship):
                reverse_predicates[key] = val


        # base list of queryable predicates
        queryable_predicates = {key: val for key,
                                val in predicates.items() if val.queryable}
        # add reverse predicates that can be queried
        queryable_predicates.update(
            {val._predicate: val for key, val in reverse_predicates.items() if val.queryable})
        
        if cls.__private__:
            Schema.__private_types__.append(cls.__name__)

        # inherit predicates from parent classes
        for parent in cls.__bases__:
            if parent.__name__ != Schema.__name__ and issubclass(parent, Schema):
                predicates.update({k: v for k, v in Schema.get_predicates(
                    parent.__name__).items() if k not in predicates})
                relationship_predicates.update({k: v for k, v in Schema.get_relationships(
                    parent.__name__).items() if k not in predicates})
                reverse_predicates.update({k: v for k, v in Schema.get_reverse_predicates(
                    parent.__name__).items() if k not in reverse_predicates})
                
                # register inheritance
                if cls.__name__ not in Schema.__inheritance__:
                    Schema.__inheritance__[cls.__name__] = [parent.__name__]
                else:
                    Schema.__inheritance__[
                        cls.__name__].append(parent.__name__)
                if parent.__name__ in Schema.__inheritance__:
                    Schema.__inheritance__[
                        cls.__name__] += Schema.__inheritance__[parent.__name__]
                    Schema.__inheritance__[cls.__name__] = list(
                        set(Schema.__inheritance__[cls.__name__]))

        Schema.__types__[cls.__name__] = predicates
        Schema.__explicit_reverse_relationship_predicates__[
            cls.__name__] = reverse_predicates
        Schema.__perm_registry_new__[cls.__name__] = cls.__permission_new__
        Schema.__perm_registry_edit__[cls.__name__] = cls.__permission_edit__

        # Bind and "activate" predicates for initialized class
        for key in predicates:
            attribute = getattr(cls, key)
            setattr(attribute, 'predicate', key)

            cls_attribute = deepcopy(attribute)
            setattr(cls_attribute, 'bound_dgraph_type', cls.__name__)
            setattr(cls, key, cls_attribute)
            if attribute.facets:
                for facet in attribute.facets.values():
                    facet.predicate = key
                    if facet.queryable:
                        queryable_predicates.update({str(facet): facet})
            if key not in cls.__predicates_types__:
                cls.__predicates_types__.update({key: [cls.__name__]})
            else:
                cls.__predicates_types__[key].append(cls.__name__)
            if isinstance(attribute, (SingleRelationship, MutualRelationship)):
                if key not in cls.__relationship_predicates__:
                    cls.__relationship_predicates__.update(
                        {key: [cls.__name__]})
                else:
                    cls.__relationship_predicates__[
                        key].append(cls.__name__)
                if not isinstance(attribute, MutualRelationship) and cls_attribute.dgraph_directives is not None and '@reverse' in cls_attribute.dgraph_directives:
                    for constraint in cls_attribute.relationship_constraint:
                        try:
                            Schema.__reverse_relationships__[constraint].append(cls_attribute)
                        except:
                            Schema.__reverse_relationships__[constraint] = [cls_attribute]
            if key not in cls.__predicates__:
                cls.__predicates__.update({key: attribute})
            
        for key in reverse_predicates:
            attribute = getattr(cls, key)
            if attribute.predicate not in cls.__reverse_predicates_types__:
                cls.__reverse_predicates_types__.update(
                    {attribute.predicate: [cls.__name__]})
            else:
                if cls.__name__ not in cls.__reverse_predicates_types__[attribute.predicate]:
                    cls.__reverse_predicates_types__[
                        attribute.predicate].append(cls.__name__)

        Schema.__queryable_predicates__.update(queryable_predicates)

        Schema.__queryable_predicates_by_type__[cls.__name__] = {
            key: val for key, val in predicates.items() if val.queryable}
        Schema.__queryable_predicates_by_type__[cls.__name__].update(
            {key: val for key, val in queryable_predicates.items() if isinstance(val, Facet)})
        Schema.__queryable_predicates_by_type__[cls.__name__].update(
            {val._predicate: val for key, val in reverse_predicates.items() if val.queryable})

        if getattr(cls, "__init__", object.__init__) is object.__init__:
            # the generic constructor just assigns **kwargs as attributes
            cls.__init__ = _declarative_constructor

    """ ORM Methods """
    @staticmethod
    def _normalize_dict_vals(val):
        if isinstance(val, datetime):
            return val.isoformat()
        else:
            return str(val)

    def as_dict(self) -> dict:
        """ 
            Provides the instance as a dict so it can be passed on to dgraph as a set object 

            The dict is a copy of the instance's attributes. So, if the returned dict is changed,
            the instance is not affected.
        """
        from .dgraph_types import (_PrimitivePredicate, Facet, 
                                   SingleRelationship, MutualRelationship, ReverseRelationship, 
                                   ListRelationship, MutualListRelationship, ReverseListRelationship)
        
        d = {}
        for k, v in self.__dict__.items():
            if isinstance(self.predicates()[k], (ListRelationship, MutualListRelationship, ReverseListRelationship)):
                if type(v) == list:
                    d[k] = [{'uid': u} for u in v]
                else:
                    d[k] = [{'uid': v}]
            elif isinstance(self.predicates()[k], (SingleRelationship, MutualRelationship, ReverseRelationship)):
                d[k] = {'uid': v}
            elif isinstance(self.predicates()[k], (_PrimitivePredicate, Facet)):
                d[k] = v

        d['dgraph.type'] = self.resolve_inheritance(type(self).__name__)
        d = json.loads(json.dumps(d, default=self._normalize_dict_vals))      

        return d

    @classmethod
    def get_types(cls, private: bool = True) -> t.List[str]:
        """
            Get all types registered in the Schema.
            
            By default returns private types as well.
            Change behaviour by calling method with `private=False`
        """
        if private:
            return list(cls.__types__.keys())
        return [k for k in cls.__types__.keys() if k not in cls.__private_types__]


    @classmethod
    def get_type(cls, dgraph_type: str) -> t.Union[str, None]:
        """
            Get the correct name of a DGraph Type
            Helpful when input is all lower case
            
            `Schema.get_type('fileformat')` -> 'FileFormat'
        """
        if not dgraph_type:
            return None
        assert isinstance(dgraph_type, str), TypeError
        for t in list(cls.__types__.keys()):
            if t.lower() == dgraph_type.lower():
                return t
        return None
    
    @classmethod
    def get_type_description(cls, dgraph_type: str) -> t.Union[str, None]:
        """
            Get the documentation / description (i.e. docstring) of a dgraph type
        """
        dgraph_type = cls.get_type(dgraph_type)
        if not dgraph_type:
            return None
        return cls.__types_meta__[dgraph_type]['description']

    @classmethod
    def get_predicates(cls, _cls) -> dict:
        """
            Get all predicates of a DGraph Type
            Returns a deepcopy dict of `{'predicate_name': <DGraph Predicate>}`
            `Schema.get_predicates('NewsSource')` -> {'name': <DGraph Predicate "name"> ...}
        """
        if not isinstance(_cls, str):
            _cls = _cls.__name__
        return deepcopy(cls.__types__[_cls])

    @classmethod
    def get_relationships(cls, _cls) -> dict:
        """
            Get all Relationships from the DGraph Type to other DGraph Types.
            Returns a dict of `{'predicate_name': <DGraph Predicate>}`
            `Schema.get_relationships('NewsSource')` -> {'channel': <DGraph Predicate "channel"> ...}
        """
        from .dgraph_types import SingleRelationship, MutualRelationship
        if not isinstance(_cls, str):
            _cls = _cls.__name__

        relationships = cls.__types__[_cls]
        return {k: v for k, v in relationships.items() if isinstance(v, (SingleRelationship, MutualRelationship))}
    
    @classmethod
    def get_reverse_relationships(cls, _cls) -> t.List[tuple]:
        """
            Get all implicit reverse relationships from the DGraph Type to other DGraph Types.

            Returns a list of tuples of `[('predicate_name', 'dgraph.type')]`

            `Schema.get_reverse_relationships('NewsSource')` -> ('publishes', 'PoliticalParty'), ('publishes', 'Organization'), ('sources_included', 'JournalisticBrand') ... `
        """
        if not isinstance(_cls, str):
            _cls = _cls.__name__

        try:
            return [(p.predicate, p.bound_dgraph_type) for p in Schema.__reverse_relationships__[_cls]]
        except KeyError:
            return None
      
    @classmethod
    def get_reverse_predicates(cls, _cls) -> dict:
        """
            Get all explicit reverse relationships from other DGraph Types to this DGraph Type.
            Returns a dict of `{'alias_reverse_predicate': <DGraph Predicate>}`
            `Schema.get_reverse_predicates('NewsSource')` -> {'publishes_org': <DGraph Reverse Relationship "~publishes"> ...}
        """
        if not isinstance(_cls, str):
            _cls = _cls.__name__
        if _cls in cls.__explicit_reverse_relationship_predicates__:
            return deepcopy(cls.__explicit_reverse_relationship_predicates__[_cls])
        else:
            return None

    @classmethod
    def predicates(cls) -> dict:
        """
            Get all predicates.
            If used on `Schema` get a complete dict of all registered predicates.
            If used on a class of a DGraph Type get a dict of all predicates for this type.
            Returns a dict of `{'predicate_name': <DGraph Predicate>}`
            `Schema.predicates()` -> Complete dict
            `FileFormat.predicates()` -> Only predicates for this DGraph Type
        """
        try:
            predicates = deepcopy(cls.__types__[cls.__name__])
        except KeyError:
            predicates = deepcopy(cls.__predicates__)

        return predicates

    @classmethod
    def relationship_predicates(cls) -> dict:
        return deepcopy(cls.__relationship_predicates__)

    @classmethod
    def reverse_predicates(cls) -> dict:
        if cls.__name__ in cls.__explicit_reverse_relationship_predicates__:
            return deepcopy(cls.__explicit_reverse_relationship_predicates__[cls.__name__])
        else:
            return None

    @classmethod
    def predicate_names(cls) -> list:
        try:
            predicates = list(cls.__types__[cls.__name__].keys())
        except KeyError:
            predicates = list(cls.__predicates__.keys())

        return predicates

    @classmethod
    def resolve_inheritance(cls, _cls) -> list:
        if not isinstance(_cls, str):
            _cls = _cls.__name__
        assert _cls in cls.__types__, f'DGraph Type "{_cls}" not found!'
        dgraph_types = [_cls]
        if _cls in cls.__inheritance__:
            dgraph_types += cls.__inheritance__[_cls]
        return dgraph_types
    
    @classmethod
    def generate_dgraph_schema(cls) -> str:
        """ Produces a schema that can be read by DGraph """

        # The Schema first defines all types and their predicates
        type_definitions = []

        # We get every dgraph type in the schema
        for dgraph_type in cls.get_types():    
            # get every predicate for this type
            predicates = cls.get_predicates(dgraph_type)
            # get potential parent types
            inheritance = cls.resolve_inheritance(dgraph_type)
            inheritance.remove(dgraph_type)
            # remove predicates that are inherited
            for parent in inheritance:
                for inherited_predicate in cls.get_predicates(parent):
                    predicates.pop(inherited_predicate)
            # remove the special uid predicate that all dgraph types have by default
            if 'uid' in predicates:
                _ = predicates.pop('uid')
            type_definition = "\n    ".join(predicates.keys())
            type_definition = 'type ' + dgraph_type + ' {\n    ' + type_definition + '\n}' 
            type_definitions.append(type_definition)

        # Next we declare all predicates and their directives

        predicate_definitions = []

        for predicate_name, predicate in cls.predicates().items():
            if predicate_name == 'uid':
                continue
            definition = f'{predicate_name}: {predicate.dgraph_predicate_type} {" ".join(predicate.dgraph_directives or [])} .'
            predicate_definitions.append(definition)

        schema_string = "\n\n".join(type_definitions) + '\n\n'
        schema_string += "\n".join(predicate_definitions)

        return schema_string
    
    @classmethod
    def provide_types(cls) -> t.Iterable[dict]:
        """ Provide all dgraph types in a format usable for Open API 3"""
        
        schemas = {}
        requestBodies = {}
        for t in Schema.__types_meta__:
            # if Schema.__types_meta__[t]['private']:
            #     continue
            if t.startswith('_'):
                continue
            schemas[t] = {'type': 'object',
                          'x-private': Schema.__types_meta__[t]['private'],
                          'properties': {}}
            try:
                schemas[t]['description'] = Schema.__types_meta__[t]['description']
            except KeyError:
                pass
            requestBodies[t] = {"content": {
                                    "application/json": {
                                        "schema": {
                                        "$ref": "#/components/schemas/" + t}
                                        }
                                    }
                                }
            
            required_predicates = []
            for predicate_name, predicate in Schema.get_predicates(t).items():
                if predicate.required:
                    required_predicates.append(predicate_name)
                schemas[t]['properties'][predicate_name] = predicate.openapi_component
            if len(required_predicates) > 0:
                schemas[t]['required'] = required_predicates

        return {'schemas': schemas,
                'requestBodies': requestBodies}

    @classmethod
    def provide_queryable_predicates(cls) -> t.Iterable[dict]:
        qp = {'name': 'dgraph.type',
                'in': 'query',
                'description': 'DGraph Type',
                'required': False,
                'schema': {
                    'type': 'array',
                    'items': {
                        'type': 'string',
                        'enum': [k for k in cls.__types__.keys() if k not in cls.__private_types__]
                        }
                    }
                }
        connector = {'name': 'dgraph.type' + '*connector',
                     'in': 'query',
                     'description': 'Logical connectors for combining an array',
                     'required': False,
                     'schema': {
                         'type': 'string',
                         'enum': ['or'],
                         'default': 'or'
                     }
                     }
        queryable = {'dgraph.type': qp,
                     'dgraph.type*connector': connector}
        for predicate in Schema.get_queryable_predicates().values():
            queryable.update(predicate.openapi_query_parameter)

        return queryable

    @classmethod
    def permissions_new(cls, _cls) -> int:
        if not isinstance(_cls, str):
            _cls = _cls.__name__
        return cls.__perm_registry_new__[_cls]

    @classmethod
    def permissions_edit(cls, _cls) -> int:
        if not isinstance(_cls, str):
            _cls = _cls.__name__
        return cls.__perm_registry_edit__[_cls]

    @classmethod
    def get_queryable_predicates(cls, _cls=None) -> dict:
        if _cls is None:
            try:
                return deepcopy(cls.__queryable_predicates_by_type__[cls.__name__])
            except KeyError:
                return deepcopy(cls.__queryable_predicates__)

        if not isinstance(_cls, str):
            _cls = _cls.__name__
        else:
            _cls = cls.get_type(_cls)

        try:
            return deepcopy(cls.__queryable_predicates_by_type__[_cls])
        except KeyError:
            return {}
        
    @classmethod
    def is_private(cls, dgraph_type: str) -> bool:
        return dgraph_type in cls.__private_types__
    
    @staticmethod
    def populate_form(form: FlaskForm, populate_obj: dict, fields: dict) -> FlaskForm:
        from meteor.flaskdgraph.dgraph_types import SingleChoice

        for k, value in populate_obj.items():
            if hasattr(form, k):
                if type(value) is dict:
                    if 'uid' in value.keys():
                        value = value['uid']
                elif type(value) is list and not isinstance(fields[k], SingleChoice):
                    if type(value[0]) is str:
                        delimiter = getattr(fields[k], 'delimiter', ',')
                        value = delimiter.join(value)
                    elif type(value[0]) is int:
                        value = [str(val) for val in value]
                    elif 'uid' in value[0].keys():
                        value = [subval['uid'] for subval in value]
                        if len(value) == 1:
                            value = value[0]
                if isinstance(getattr(form, k), IntegerField) and isinstance(value, datetime):
                    # cast datetime as year if field does not need to be too specific
                    value = value.year
                setattr(getattr(form, k), 'data', value)
        return form

    @classmethod
    def generate_new_entry_form(cls, dgraph_type=None, populate_obj: dict = None) -> FlaskForm:

        if dgraph_type:
            fields = cls.get_predicates(dgraph_type)
            if cls.get_reverse_predicates(dgraph_type):
                fields.update(cls.get_reverse_predicates(dgraph_type))
        else:
            fields = cls.predicates()
            if cls.reverse_predicates():
                fields.update(cls.reverse_predicates())

        if not isinstance(dgraph_type, str):
            submit_label = dgraph_type.__name__
        else:
            submit_label = dgraph_type

        class F(FlaskForm):

            submit = SubmitField(f'Add New {submit_label}')

            def get_field(self, field):
                return getattr(self, field)

        for k, v in fields.items():
            if v.new:
                setattr(F, k, v.wtf_field)

        form = F()
        # ability to pre-populate the form with data
        if populate_obj:
            form = cls.populate_form(form, populate_obj, fields)

        return form

    @classmethod
    def generate_edit_entry_form(cls, dgraph_type=None,
                                 populate_obj: dict = None,
                                 entry_review_status='pending',
                                 skip_fields: list = None) -> FlaskForm:

        from .dgraph_types import SingleRelationship, ReverseRelationship, MutualRelationship

        if populate_obj is None:
            populate_obj = {}

        if dgraph_type:
            fields = cls.get_predicates(dgraph_type)
        else:
            fields = cls.predicates()

        if not isinstance(dgraph_type, str):
            dtype_label = dgraph_type.__name__
        else:
            dtype_label = dgraph_type

        class F(FlaskForm):

            submit = SubmitField(f'Edit this {dtype_label}')

            def get_field(self, field):
                try:
                    return getattr(self, field)
                except AttributeError:
                    return None

        from flask_login import current_user

        # FlaskForm Factory
        # Add fields depending on DGraph Type
        skip_fields = skip_fields or []
        for k, v in fields.items():
            # Allow to manually filter out some fields / hide them from users
            if k in skip_fields:
                continue
            if k.startswith('_'):
                k = 'private' + k
            if v.edit and current_user._role >= v.permission:
                if isinstance(v, (SingleRelationship, ReverseRelationship, MutualRelationship)) and k in populate_obj.keys():
                    if not v.autoload_choices:
                        if isinstance(populate_obj[k], list):
                            choices = [(subval['uid'], subval.get('name', subval['uid']))
                                    for subval in populate_obj[k]]
                        else:
                            choices = [(populate_obj[k]['uid'], populate_obj[k].get('name', populate_obj[k]['uid']))]
                        
                        v.choices_tuples = choices
                setattr(F, k, v.wtf_field)

        if current_user._role >= USER_ROLES.Reviewer and entry_review_status == 'pending':
            setattr(F, "accept", SubmitField('Edit and Accept'))

        # Instatiate the form from the factory
        form = F()

        # Populate instance with existing values
        form = cls.populate_form(form, populate_obj, fields)

        return form


""" 
    Taken from SQL Alchemy ORM 
    Maybe we will keep this for implementing ORM style queries
"""

def _declarative_constructor(self: Schema, **kwargs: t.Any) -> None:
    """A simple constructor that allows initialization from kwargs.
    Sets attributes on the constructed instance using the names and
    values in ``kwargs``.
    Only keys that are present as
    attributes of the instance's class are allowed. These could be,
    for example, any mapped columns or relationships.
    """
    cls_ = type(self)
    for k, v in self.predicates().items():
        if v.default:
            setattr(self, k, v.default)
        if v.required and k not in kwargs:
            raise TypeError(
                f'Predicate <{k}> is required!'
            )
    for k in kwargs:
        if not hasattr(cls_, k):
            raise TypeError(
                "%r is an invalid keyword argument for %s" % (k, cls_.__name__)
            )
        setattr(self, k, kwargs[k])


_declarative_constructor.__name__ = "__init__"
