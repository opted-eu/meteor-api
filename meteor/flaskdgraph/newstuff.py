class DeclarativeBase:
    __tablename__ = None
    __dgraphtype__ = None # maybe makes sense

    # some more dunder attributes 
    # ...

    def __init_subclass__(cls) -> None:
        if DeclarativeBase in cls.__bases__:
            _check_not_declarative(cls, DeclarativeBase)
            _setup_declarative_base(cls)
        else:
            _as_declarative(cls._sa_registry, cls, cls.__dict__)
        super().__init_subclass__()



def _check_not_declarative(*args):
    # make sure the new class is not DeclarativeBase
    # maybe we wont need this validation
    pass

def _setup_declarative_base(cls):
    # assign DB metadata

    # deal with type annotations

    # create/validate registry
    # check if the cls has a registry attribute in cls.__dict__
    # if not assign a new resistry

    reg = None # the registry class

    cls.registry = reg
    cls._sa_resgistry # not sure why it has the registry twice

    # assign the __init__ method to the cls
    if getattr(cls, "__init__", object.__init__) is object.__init__:
        # the generic constructor just assigns **kwargs as attributes
        cls.__init__ = cls.registry.constructor



def _as_declarative(registry,
                    cls,
                    dict_):
    return _MapperConfig.setup_mapping(registry, cls, dict_, None, {})


class _MapperConfig:

    @staticmethod
    def setup_mapping(*args):
        pass