from flask import Flask
from openai import OpenAI


def test_required_libraries_are_available():
    assert callable(Flask)
    assert callable(OpenAI)
