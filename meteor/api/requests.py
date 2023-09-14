"""
    Defines Request Parameters / Bodies of API routes
    We use python's built-in type hinting system
    for the self documentation of the API routes.
    To keep things less messy, complex request types are declared here 
"""

import typing
from meteor.main.model import *

editable = [Entry, PoliticalParty,
                    Organization, JournalisticBrand, 
                    NewsSource, Government, 
                    Parliament, Person,
                    Channel, Country,
                    Multinational, Subnational,
                    Archive, Dataset,
                    Tool, ScientificPublication,
                    Author, Language,
                    ProgrammingLanguage,
                    Operation, 
                    FileFormat,
                    MetaVariable,
                    ConceptVariable,
                    TextType,
                    UnitOfAnalysis,
                    Collection,
                    LearningMaterial]

EditablePredicates = typing.TypedDict('EditablePredicates', 
                                      {k: v._type for k, v in Schema.get_predicates(Entry).items() if v.edit})

PublicDgraphTypes = typing.Literal[tuple([t for t in Schema.get_types(private=False)])]
