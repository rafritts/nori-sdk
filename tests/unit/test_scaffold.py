from nori import Agent


def test_agent_importable():
    assert Agent is not None


def test_agent_instantiable():
    agent = Agent(name="Test", model="grok-4.3")
    assert isinstance(agent, Agent)
