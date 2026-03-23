from .fipa import AID
from .content import Ontology, Concept, AgentAction, concept


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
        description: DFAgentDescription | None = None,
        constraint: DFSearchConstraint | None = None,
    ):
        if description:
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


class FipaManagementOntology(Ontology):

    name = "FIPA-Agent-Management"

    def __init__(self):
        super().__init__()
        self.add(DFSearch, DFAgentDescription, DFSearchConstraint, DFService)