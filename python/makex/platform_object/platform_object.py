import logging
import operator
from enum import Enum
from typing import (
    Any,
    Hashable,
    Union,
)

from logging import debug


class PlatformTestObject:
    def __init__(self):
        pass


PlatformRight = Any


class Operator(Enum):
    IN = "in"
    LT = "<"
    GT = ">"
    EQ = "=="
    NE = "!="
    GTE = ">="
    LTE = "<="
    NOT_IN = "not in"
    AND = "and"
    OR = "or"


def not_in(a, b):
    return not operator.contains(a, b)


def one_of(a, b):
    return operator.contains(b, a)


op_map = {
    Operator.IN: one_of,
    Operator.LTE: operator.le,
    Operator.GT: operator.gt,
    Operator.NOT_IN: not_in,
    Operator.EQ: operator.eq,
    Operator.NE: operator.ne,
    Operator.LT: operator.lt,
    Operator.GTE: operator.ge,
    Operator.AND: operator.and_,
    Operator.OR: operator.or_,
}


class PlatformCondition:
    left: "PlatformLeft"
    operator: Operator
    right: PlatformRight

    def __init__(
        self,
        left: Union["PlatformLeft", "PlatformCondition"],
        operator: Operator,
        right: PlatformRight
    ):
        self.left = left
        self.operator = operator
        self.right = right

    def __repr__(self):
        #def __str__(self):
        inside = " ".join((repr(self.left), str(self.operator), str(self.right)))
        return f"({inside})"

    def __hash__(self):
        return hash(self.left)

    def __eq__(self, other: "PlatformLeft"):
        d = {other.name: other.value}
        r = self.evaluate(d)
        debug("Evaluated %s: %s = %s", self, d, r)

        return r

    def returns(self, value):

        pass

    def evaluate(self, platform: dict[Hashable, Any]):
        if self.operator == Operator.AND:
            left_value = self.left.evaluate(platform)
            right_value = self.right.evaluate(platform)
            return bool(left_value and right_value)
        elif self.operator == Operator.OR:
            left_value = self.left.evaluate(platform)
            right_value = self.right.evaluate(platform)
            return bool(left_value or right_value)

        left_value = platform.get(self.left)
        op = op_map.get(self.operator)
        return op(left_value, self.right)

    def __and__(self, other) -> "PlatformCondition":
        """
        c & b & d

        ((c, and, b), and, d)
        c & b | d

        ((c, and, b), or, d)

        :param other:
        :return:
        """
        return PlatformCondition(self, Operator.AND, other)

    def __or__(self, other) -> "PlatformCondition":
        return PlatformCondition(self, Operator.OR, list)


class PlatformLeft:
    def __init__(self, name, value):
        self.name = name
        self.value = value

    def __repr__(self):
        return self.name

    def __str__(self):
        return self.value

    def __hash__(self):
        return hash(self.name)

    def __and__(self, other: PlatformCondition) -> PlatformCondition:
        """
        c & b & d

        ((c, and, b), and, d)
        c & b | d

        ((c, and, b), or, d)

        :param other:
        :return:
        """
        return PlatformCondition(self, Operator.AND, other)

    def __or__(self, other) -> PlatformCondition:
        return PlatformCondition(self, Operator.OR, other)

    def __gt__(self, other) -> PlatformCondition:
        return PlatformCondition(self, Operator.GT, other)

    def __ge__(self, other) -> PlatformCondition:
        return PlatformCondition(self, Operator.GTE, other)

    def __eq__(self, other) -> PlatformCondition:
        return PlatformCondition(self, Operator.EQ, other)

    def __lt__(self, other) -> PlatformCondition:
        return PlatformCondition(self, Operator.LT, other)

    def __le__(self, other) -> PlatformCondition:
        return PlatformCondition(self, Operator.LTE, other)

    def not_in(self, list) -> PlatformCondition:
        return PlatformCondition(self, Operator.NOT_IN, list)

    def one_of(self, *args) -> PlatformCondition: # or in

        if len(args) == 1 and isinstance(args[0], list):
            values = args[0]
        else:
            values = args

        return PlatformCondition(self, Operator.IN, values)


class PlatformObject:
    """
        Platform.os_type ==

    """
    os_type: PlatformLeft
    architecture: PlatformLeft

    #location:FileLocation

    def __init__(self, values):
        self.values = values
        self.os_type = PlatformLeft("os_type", values.get("os_type", None))
        self.architecture = PlatformLeft("architecture", values.get("architecture", None))

    #    self.location = None

    #def with_location(self, location:FileLocation) -> PlatformObject:
    #    self.location = location
