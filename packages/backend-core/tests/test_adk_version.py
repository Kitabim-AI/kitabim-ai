"""Verify google-adk is importable at the expected version range."""

import importlib.metadata


def test_adk_version_is_2x():
    version = importlib.metadata.version("google-adk")
    major = int(version.split(".")[0])
    assert major == 2, f"Expected google-adk major version 2, got {version}"


def test_adk_agents_importable():
    from google.adk.agents import Agent, BaseAgent  # noqa: F401
    from google.adk.runners import InMemoryRunner  # noqa: F401
