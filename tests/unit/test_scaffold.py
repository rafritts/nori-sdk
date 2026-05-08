from nori import Agent


def test_agent_importable():
    assert Agent is not None


def test_agent_instantiable():
    agent = Agent()
    assert isinstance(agent, Agent)
