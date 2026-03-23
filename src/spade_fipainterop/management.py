from lark import Lark, Token, Transformer
from datetime import datetime
from typing import Any
from abc import ABC
from functools import wraps
from typing import TypeVar, Callable, Type


from .fipa import AID

sl0_grammar = r"""
// ---------------- ROOT CONTENT ----------------

content: "(" result_expr ")"
       | "(" done_expr ")"
       | "(" action_expr ")"
       | "(" functor_expr ")"

action_expr: "(" "action" agent_id action_term ")"

result_expr: "(" "result" action_expr element ")"

done_expr: "(" "done" action_expr ")"

action_term: "(" verb term* ")" 

functor_expr: "(" predicate term* ")"

?verb: NAME

?predicate: NAME


// ---------------- COLLECTIONS ----------------

?collection: set
           | sequence

set: "(" "set" element* ")"
sequence: "(" "sequence" element* ")"


// ----------------- AID -----------------

agent_id: "(" "agent-identifier" keyword_term* ")"


// ---------------- TERMS ----------------

?term: keyword_term
     | element

keyword_term: KEYWORD element

?element: value
        | collection
        | agent_id
        | functor_expr
        | "(" "=" element element ")"

?value: STRING
      | NUMBER
      | DATETIME
      | "true" | "false"


// ---------------- LEXER ----------------

KEYWORD: ":" NAME
NAME: /[a-zA-Z_][a-zA-Z0-9_-]*/
DATETIME: /\d{8}T\d{6,9}Z/
VARIABLE: "?" NAME

STRING: ESCAPED_STRING | ANY_STRING
// any value without parentheses or whitespace, that does not start with ':' or '?'
ANY_STRING: /(?![:?])[^()\s]+/
NUMBER: SIGNED_NUMBER


%import common.ESCAPED_STRING
%import common.SIGNED_NUMBER
%import common.WS
%ignore WS

"""

sl0_parser = Lark(sl0_grammar, start="content")


class AbstractContentElement:

    def __init__(self, verb, terms):
        self.verb = verb
        self.terms = terms


class Functor(ABC):
    """Abstract base class for Predicate and AgentAction and Concept"""

    _functor_name: str

    def __init__(self, functor: str | None = None, *terms, **kwterms):
        self.functor = functor
        # self.functor = self.__class__._functor_name
        self.terms: list[Any] = list(terms)
        self.kw_terms: dict[str, Any] = kwterms

    def __getitem__(self, key):
        if key in self.kw_terms:
            return self.kw_terms[key]
        return self.terms[key]

    def __repr__(self):
        def _str(t):
            if isinstance(t, list):
                s = " ".join([_str(e) for e in t])
                return f"(sequence {s})"
            elif isinstance(t, set):
                s = " ".join([_str(e) for e in t])
                return f"(set {s})"
            else:
                return str(t)

        args = " ".join(map(_str, self.terms))
        args += " ".join([f":{k} {_str(v)}" for k, v in self.kw_terms.items()])
        return f"({self.functor} {args})"


class Predicate(Functor):
    """A predicate (i.e. a proposition that can be true or false)"""

    pass


class Concept(Functor):
    """A structured term (with attributes)"""

    pass


class AgentAction(Functor):
    """An agent action (i.e. something an agent can do)"""

    pass


class Action:
    """An Action: i.e. a tuple made of an actor (the agent that should do the action)
    and an AgentAction (what should be done)"""

    def __init__(self, actor: AID, action: AgentAction):
        self.actor = actor
        self.action = action

    def __repr__(self):
        return f"((action {self.actor} {self.action}))"


class Done:
    """Represent the fact that an action has been done."""

    def __init__(self, action: Action):
        self.action = action

    def __repr__(self):
        return f"((done {self.action}))"


class Result:
    """Representa the fact that an action has been done and got a result"""

    def __init__(self, action: Action, result: Functor | list[Functor] | set[Functor]):
        self.action = action
        self.result = result

    def __repr__(self):
        return f"((result {self.action} {self.result}))"


class FIPA_SL_Transformer(Transformer):

    def content(self, items):
        return items[0]

    def action_expr(self, items):
        return Action(actor=items[0], action=items[1])

    def action_term(self, items):
        args = []
        kwargs = {}
        for e in items[1:]:
            if isinstance(e, list) and len(e) == 2:
                kwargs[e[0]] = e[1]
            else:
                args.append(e)
        return AgentAction(items[0], *args, **kwargs)

    def result_expr(self, items):
        return Result(items[0], items[1])

    def done_expr(self, items):
        return Done(items[0])

    def functor_expr(self, items):
        args = []
        kwargs = {}
        for e in items[1:]:
            if len(e) == 1:
                args.append(e)
            elif len(e) == 2:
                kwargs[e[0]] = e[1]
        return Concept(items[0], *args, **kwargs)

    def keyword_term(self, items):
        key = str(items[0])[1:]  # remove starting ":"
        value = items[1]
        return key, value

    def agent_id(self, items):
        name = None
        addresses = []
        for k, v in items:
            if k == "name":
                name = v
            elif k == "addresses":
                addresses = v
        assert name, "name cannot be empty"
        return AID(name, addresses)

    # Constantes
    def NAME(self, tok: Token):
        return str(tok)

    def STRING(self, tok: Token):
        return tok.value

    def ESCAPED_STRING(self, tok: Token):
        return str(tok)[1:-1]  # enlever les guillemets

    def NUMBER(self, tok: Token):
        """Convert a token to a number."""
        if "." in str(tok) or "e" in str(tok).lower():
            return float(tok)
        return int(tok)

    def DATETIME(self, tok: Token):
        """Format is YYYYMMDDTHHMMSSZ, we can convert it to a datetime object if needed."""
        return datetime.strptime(str(tok), "%Y%m%dT%H%M%SZ")

    def set(self, items):
        if len(items) == 0:
            return set()
        return set(items)

    def sequence(self, items):
        if len(items) == 0:
            return []
        return list(items)


T = TypeVar("T", bound=Functor)


def concept(name: str | None = None) -> Callable[[Type[T]], Type[T]]:

    def decorator(cls: Type[T], _name=name) -> Type[T]:
        if not issubclass(cls, Functor):
            raise TypeError(
                "@concept can only be applied on classes that inherit from Concept"
            )
        # if no name specified, use class name
        if not _name:
            _name = cls.__name__
        # set a class attribute
        cls._functor_name = _name
        # wrap init
        original_init = cls.__init__

        @wraps(original_init)
        def new_init(self, *args, **kwargs):
            super(cls, self).__init__(functor=_name)  # type: ignore
            original_init(self, *args, **kwargs)

        cls.__init__ = new_init
        return cls

    return decorator


@concept(name="service-description")
class DFService(Concept):

    def __init__(self, name: str | None = None, type: str | None = None):
        if name:
            self.name = name
        if type:
            self.service_type = type

    @property
    def name(self) -> str:
        return self.kw_terms["name"]

    @name.setter
    def name(self, value: str):
        self.kw_terms["name"] = value

    @property
    def service_type(self) -> str:
        return self.kw_terms["type"]

    @service_type.setter
    def service_type(self, value: str):
        self.kw_terms["type"] = value


@concept(name="df-agent-description")
class DFAgentDescription(Concept):

    def __init__(self):
        self.services = set()

    @property
    def services(self) -> set[DFService]:
        return self["services"]

    @services.setter
    def services(self, services: set[DFService]):
        self.kw_terms["services"] = services

    def add_service(self, type: str | None = None, name: str | None = None):
        """Add a Service to set of services of this agent description"""
        if not self.services:
            self.services = set()
        self.services.add(DFService(name=name, type=type))

    @property
    def name(self) -> AID:
        return self.kw_terms["name"]

    @name.setter
    def name(self, value: AID):
        self.kw_terms["name"] = value


@concept(name="search-constraints")
class DFSearchConstraint(Concept):

    def __init__(self, max_result: int = -1):
        self.max_result = max_result

    @property
    def max_result(self) -> int:
        return self.kw_terms["max-results"]

    @max_result.setter
    def max_result(self, value: int):
        self.kw_terms["max-results"] = value


@concept(name="search")
class DFSearch(AgentAction):

    def __init__(
        self,
        description: DFAgentDescription,
        constraint: DFSearchConstraint | None = None,
    ):
        self.description = description
        if not constraint:
            self.constraint = DFSearchConstraint()
        else:
            self.constraint = constraint

    @property
    def description(self) -> DFAgentDescription:
        return self.terms[0]

    @description.setter
    def description(self, value: DFAgentDescription):
        self.terms.insert(0, value)

    @property
    def constraint(self) -> DFSearchConstraint:
        return self.terms[1]

    @constraint.setter
    def constraint(self, value: DFSearchConstraint):
        if len(self.terms) < 1:
            n = len(self.terms) - 1
            self.terms.extend([None] * n)
        self.terms.insert(1, value)


