from typing import Any, Union

"""
    Smallest Units first
"""

class GraphQLVariable:


    """
        Represents a GraphQL Query Variable that are declared at the beginning of the query
        and provided separately as json object

        Construct a new GraphQLVariable with arbitrary keyword parameters:
        `my_vars = GraphQLVariable(name="Indiana Jones")`

        is equivalent to:

        `query MyQuery ($name: string = "Indiana Jones")`

        You can optionally declare the type of the variable: 
        `my_vars = GraphQLVariable(year=1998, dtype="int")`

        Current Caveat: could accidentally use the same variable name twice
        Solutions: 
            - use meta-classes to manage pool of variable names :/ (e.g. greek letters)
            - use completely random variable names (need to be long, lowercase, and only letters)
            - let the user of this module be aware of the caveat and handle it themselves ¯\_(ツ)_/¯
    """

    __slots__ = "name", "dtype", "value"

    def __init__(self, dtype="string", **kwargs) -> None:
        assert len(kwargs) == 1, "Too many or not enough parameters!"
        name, self.value = kwargs.popitem()
        self.name = "$" + name
        self.dtype = dtype

    def __repr__(self) -> str:
        return f'<GraphQLVariable {self.name}: {self.dtype} = "{self.value}"'


"""
    Query Functions
"""


class _FuncPrimitive:

    __slots__ = 'func', 'predicate', 'value', 'value2'


"""
    Comparison Functions: eq, ge, gt, le, lt
"""


class eq(_FuncPrimitive):

    func = "eq"

    def __init__(self, *args, **kwargs) -> None:
        try:
            self.predicate, value = args[0], args[1]
        except:
            assert len(kwargs) == 1, "Too many or not enough parameters!"
            self.predicate, value = kwargs.popitem()
            
        if isinstance(value, list) and len(value) == 1:
            value = value[0]
        self.value = value


    def __str__(self) -> str:
        if isinstance(self.value, GraphQLVariable):
            return f'{self.func}({self.predicate}, {self.value.name})'
        if isinstance(self.value, list):
            values = ", ".join([f'"{v}"' for v in self.value])
            return f'{self.func}({self.predicate}, [{values}])'
        return f'{self.func}({self.predicate}, "{self.value}")'


class ge(eq):

    func = "ge"


class gt(eq):

    func = "gt"


class le(eq):

    func = "le"


class lt(eq):

    func = "lt"


"""
    Range: between
"""


class between(_FuncPrimitive):

    func = "between"

    def __init__(self, *args, **kwargs) -> None:
        try:
            self.predicate, v = args[0], args[1:]
        except:
            assert len(kwargs) == 1, "Too many or not enough parameters!"
            self.predicate, v = kwargs.popitem()
        assert isinstance(v, (list, tuple, set))
        self.value = v[0]
        self.value2 = v[1]

    def __str__(self) -> str:
        query_string = f'{self.func}({self.predicate}, '
        if isinstance(self.value, GraphQLVariable):
            query_string += f"{self.value.name}, "
        else:
            query_string += f"{self.value}, "
        if isinstance(self.value2, GraphQLVariable):
            return query_string + f"{self.value2.name})"
        else:
            return query_string + f"{self.value2})"


"""
    testing string attributes
        term matching: allofterms, anyofterms
        fuzzy match: match
        full-text search: alloftext
        regular Expression: regexp
"""


class allofterms(eq):

    func = "allofterms"


class anyofterms(eq):

    func = "anyofterms"


class match(eq):

    func = "match"


class regexp(eq):

    func = "regexp"

    def __init__(self, *args, case_insensitive=False, **kwargs) -> None:
        try:
            self.predicate, value = args[0], args[1]
        except:
            assert len(kwargs) == 1, "Too many or not enough parameters!"
            self.predicate, value = kwargs.popitem()
        value = f'/{value}/'
        if case_insensitive:
            value += 'i'
        self.value = value


"""
    uid, has, uid_in
"""


class uid(_FuncPrimitive):

    func = "uid"

    def __init__(self, val) -> None:
        self.value = val

    def __str__(self) -> str:
        if isinstance(self.value, GraphQLVariable):
            return f'{self.func}({self.value.name})'
        return f'{self.func}({self.value})'


class has(_FuncPrimitive):

    func = "has"

    def __init__(self, val) -> None:
        self.value = val

    def __str__(self) -> str:
        return f'{self.func}({self.value})'
    

class type_(_FuncPrimitive):

    func = "type"

    def __init__(self, val) -> None:
        self.value = val

    def __str__(self) -> str:
        return f'{self.func}({self.value})'


class uid_in(eq):

    func = "uid_in"

    def __str__(self) -> str:
        if isinstance(self.value, GraphQLVariable):
            return f'{self.func}({self.predicate}, {self.value.name})'
        elif isinstance(self.value, (list, set, tuple)):
            return f'{self.func}({self.predicate}, [{", ".join(self.value)}])'
        return f'{self.func}({self.predicate}, {self.value})'


class QueryBlock:

    __slots__ = ("func", "block_name", "attributes_to_fetch",
                 "sorting", "first", "offset", "query_filter",
                 "filter_connector", "graphql_variables")

    def __init__(self, func: _FuncPrimitive,
                 block_name: str = "q",
                 fetch: list = None,
                 sorting=None,
                 first: int = None,
                 offset: int = None,
                 query_filter: Union[list, _FuncPrimitive] = None,
                 filter_connector="AND") -> None:

        self.graphql_variables = []

        self.func = func
        if isinstance(func.value, GraphQLVariable):
            self.graphql_variables.append(func.value)
        try:
            if isinstance(func.value2, GraphQLVariable):
                self.graphql_variables.append(func.value)
        except:
            pass

        self.block_name = block_name
        self.attributes_to_fetch = fetch or ["uid", func.predicate]

        self.sorting = sorting

        self.first = first
        self.offset = offset
        if isinstance(query_filter, _FuncPrimitive):
            query_filter = [query_filter]
        self.query_filter = query_filter
        self.filter_connector = filter_connector

        try:
            for f in query_filter:
                if isinstance(f.value, GraphQLVariable):
                    self.graphql_variables.append(f.value)
                try:
                    if isinstance(f.value2, GraphQLVariable):
                        self.graphql_variables.append(f.value)
                except:
                    pass
        except:
            pass

    def __str__(self) -> str:
        query_string = f'    {self.block_name}(func: {self.func}'
        
        if self.first:
            query_string += f', first: {self.first}'
        
        if self.offset:
            query_string += f', offset: {self.offset}'
        query_string += ') '

        if self.query_filter:
            _query_filter = [str(f) for f in self.query_filter]
            _filters = f' {self.filter_connector} '.join(_query_filter)

            query_string += f'@filter({_filters}) '
        
        query_string += f'''{{\n         {" ".join(self.attributes_to_fetch)} \n    }}'''

        return '{\n' + query_string + '\n}'

class DQLQuery:

    __slots__ = "query_name", "graphql_variable_declarations", "query_blocks"

    def __init__(self, query_name="q", **kwargs) -> None:

        self.graphql_variable_declarations = []
        self.query_name = query_name
        self.query_blocks = [QueryBlock(**kwargs)]

        for q in self.query_blocks:
            self.graphql_variable_declarations += q.graphql_variables

    def __str__(self) -> str:
        return self.render()

    
    def render(self) -> str:
        query_string = ""
        if len(self.graphql_variable_declarations) > 0:
            query_string += f"query {self.query_name} "
            if len(self.graphql_variable_declarations) > 0:
                var_declarations = [f'{v.name} : {v.dtype}' for v in self.graphql_variable_declarations]
                var_declarations = ", ".join(var_declarations)
                query_string += '(' + var_declarations + ') '
        
        for block in self.query_blocks:
            query_string += str(block)
                
        return query_string
    
    def get_graphql_variables(self) -> dict:
        return {var.name: var.value for var in self.graphql_variable_declarations}