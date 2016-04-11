import typing
from abc import ABC, abstractmethod


class BaseNode(ABC):

    def __init__(self, data_type, strict, type_var=False):
        self.data_type = data_type
        self.strict = strict
        self.type_var = type_var

        self.data_out = None
        self.last_type = None
        self.original_children = []
        self.children = []

    def __str__(self):
        children_nest = ', '.join([str(c) for c in self.children])
        str_repr = '{}:{}'.format(str(self.data_type), self.__class__.__name__)
        if children_nest:
            str_repr += ' -> ({})'.format(children_nest)
        return str_repr

    def validate(self, data, validator, force=False):
        valid = self.validate_data(validator, data, force)

        if not valid:
            yield False
            return

        results = []
        propagated_data = self.map_data(validator, data)

        # Not using zip because it will silence a mismatch in sizes
        # between children and propagated_data
        # And, for now, at least, I'd prefer it be explicit
        # Note, if len(self.children) changes during iteration, errors *will* occur
        for i, child in enumerate(self.children):
            result = yield child.validate(propagated_data[i], validator, self.type_var)
            results.append(result)

        valid = all(results) if self.strict else any(results)

        if not valid:
            yield False
            return

        returned_data = [a.data_out for a in self.children]
        self.data_out = self.reduce_data(validator, returned_data, data)

        if results and force:
            self.children = [self.children[results.index(True)]]

        self.last_type = type(data)
        yield True

    @abstractmethod
    def validate_data(self, validator, data, sticky=False) -> bool:
        """
        Responsible for determining if node is of specific type
        """
        pass

    @abstractmethod
    def map_data(self, validator, data):
        """
        Finds the children of the type
        """
        pass

    @abstractmethod
    def reduce_data(self, validator, data, old_data):
        """
        Return the pure form of the data?
        """
        pass

    def add_child(self, child):
        self.children.append(child)
        self.original_children.append(child)

    def reset(self):
        self.data_out = None
        self.last_type = None
        self.children = [a for a in self.original_children]


class SimpleNode(BaseNode):

    def __init__(self, data_type):
        super().__init__(data_type, strict=True, type_var=False)

    def validate_data(self, validator, data, sticky=False):
        # Will keep till all the debugging is over
        #print('Simple Validation: {}:{}, {}\n=> {}'.format(
        #    data, type(data), self.data_type, issubclass(type(data),
        #                                                 self.data_type)))
        # This conditional is for when Callable object arguments are
        # mapped to SimpleNodes
        if isinstance(data, type):
            result = issubclass(data, self.data_type)
        else:
            result = issubclass(type(data), self.data_type)
        return result

    def map_data(self, validator, data):
        propagated_data = []
        if isinstance(data, list):
            # If it's a list we need to make child for every item in list
            propagated_data = data
            self.children *= len(data)
        return propagated_data

    def reduce_data(self, validator, data, old_data):
        return old_data


class UnionNode(BaseNode):

    def __init__(self):
        super().__init__(typing.Any, False)

    def validate_data(self, validator, data, sticky=False):
        # Will keep till all the debugging is over
        #print('Validation:', data, self.data_type)
        if sticky and self.last_type is not None:
            return type(data) == self.last_type
        return True

    def map_data(self, validator, data):
        output = []
        for _ in self.children:
            output.append(data)
        return output

    def reduce_data(self, validator, data, old_data):
        for element in data:
            if element is not None:
                return element
        return None


class TypeVarNode(BaseNode):
    # TODO: This node does not yet take covariant and contravariant properties
    # of the TypeVar into an account

    def __init__(self):
        super().__init__(typing.Any, False, True)

    def validate_data(self, validator, data, sticky=False):
        return True

    def map_data(self, validator, data):
        return [data]

    def reduce_data(self, validator, data, old_data):
        return data[0]


class TupleNode(BaseNode):

    def __init__(self):
        super().__init__(typing.Tuple, True)

    def validate_data(self, validator, data, sticky=False):
        if issubclass(type(data), self.data_type):
            return len(data) == len(self.children)
        else:
            return False

    def map_data(self, validator, data):
        output = []
        for element in data:
            output.append(element)
        return output

    def reduce_data(self, validator, data, old_data):
        return tuple(data)


class CallableNode(BaseNode):
    """
    This node is used when we have a function that expects another function
    as input. As an example:

        import typing
        def foo(func: typing.Callable[[int, int], int]) -> int:
            return func(5, 5)

    The typing.Callable type variable takes two parameters, the first being a
    list of its expected argument types with the second being its expected
    output type.
    """

    def __init__(self):
        super().__init__(typing.Callable, strict=True, type_var=False)

    def validate_data(self, validator, data, sticky=False):
        # Will keep till all the debugging is over
        #print('Callable Validation: {}:{}, {}\n=> {}'.format(data, type(data),
        #                                       self.data_type,
        #                                       isinstance(data, self.data_type)))
        return isinstance(data, self.data_type)

    def map_data(self, validator, data):
        func_hints = typing.get_type_hints(data)
        result = [value for key, value in
                  func_hints.items() if key != 'return']
        result.append(func_hints['return'])
        return result

    def reduce_data(self, validator, data, old_data):
        return old_data
