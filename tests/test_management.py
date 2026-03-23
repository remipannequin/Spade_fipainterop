import pytest
from helpers import assert_equal_ignore_whitespace
from spade_fipainterop.content import get_content, get_abstract_content, Action, Result
from spade_fipainterop.management import (
    AID,
    AgentAction,
    DFSearch,
    DFAgentDescription,
    FipaManagementOntology
)


@pytest.fixture
def search_request_content():
    return """
    ((action 
        (agent-identifier 
        :name df@Platform1  
        :addresses (sequence http://localhost:7771/JADE)) 
        (search 
        (df-agent-description 
            :services 
            (set 
                (service-description 
                :name Ping
                :type Test-Service))) 
        (search-constraints 
            :max-results -1))))
    """


@pytest.fixture
def search_response_content():
    return """
 ((result 
     (action 
       (agent-identifier 
         :name df@Platform1 
         :addresses (sequence http://localhost:7771/JADE)) 
       (search 
         (df-agent-description 
           :services 
             (set 
               (service-description 
                 :name Ping 
                 :type Test-Service))) 
         (search-constraints 
           :max-results -1))) 
     (sequence
       (df-agent-description 
         :name 
           (agent-identifier 
             :name ping1@Platform1 
             :addresses (sequence http://localhost:7771/JADE)) 
         :services 
           (set 
             (service-description 
               :name Ping 
               :type Test-Service))))))
    """


def test_df_search_request(search_request_content):
    content = get_abstract_content(search_request_content)
    assert content
    assert isinstance(content, Action)
    assert content.actor
    assert isinstance(content.actor, AID)
    act = content.action
    assert act
    assert isinstance(act, AgentAction)
    assert act.functor == "search"
    assert act[0], act[1]
    print(act)
    assert act[0].functor == "df-agent-description"
    assert act[1].functor == "search-constraints"
    assert isinstance(act[0]["services"], set)


def test_df_search_response(search_response_content):
    content = get_abstract_content(search_response_content)
    assert content
    assert isinstance(content, Result)
    res = content.result
    assert isinstance(res, list)
    assert len(res) == 1
    assert isinstance(res[0]["name"], AID)


def test_write_dfsearch(search_request_content):
    dfad = DFAgentDescription()
    dfad.add_service(type="Test-Service", name="Ping")
    act = DFSearch(description=dfad)
    assert act
    print(act)
    assert dfad._functor_name == "df-agent-description"
    assert act._functor_name == "search"
    assert len(act.terms) == 2
    df = AID("df@Platform1", ["http://localhost:7771/JADE"])
    content = Action(df, act)
    print(content)
    assert_equal_ignore_whitespace(str(content), search_request_content)

def test_management_onto():
    onto = FipaManagementOntology()
    assert onto
    assert onto.name == "FIPA-Agent-Management"
    assert DFSearch in onto.classes.values()
    assert DFSearch._functor_name in onto.classes
    assert DFAgentDescription in onto.classes.values()
    assert DFAgentDescription._functor_name in onto.classes


def test_read_dfsearch(search_response_content):
    """Test substitution of abstract classes with instances of the
    ontology."""
    content = get_content(search_response_content, FipaManagementOntology())
    assert isinstance(content, Result)
    assert isinstance(content.action.action, DFSearch)
    assert isinstance(content.result, list)
    r = content.result[0]
    assert isinstance(r, DFAgentDescription)
