import os


def test_langsmith_tracing_is_disabled_for_every_test():
    assert os.environ["LANGSMITH_TRACING"].lower() == "false"
    assert os.environ["LANGCHAIN_TRACING_V2"].lower() == "false"
    assert os.environ["LANGSMITH_API_KEY"] == ""
