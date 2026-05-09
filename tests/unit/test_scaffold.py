from nori import Agent, Model


def test_agent_importable():
    assert Agent is not None


def test_agent_instantiable():
    agent = Agent(name="Test", model=Model(id="grok-4.3", api_key="test-key"))
    assert isinstance(agent, Agent)
