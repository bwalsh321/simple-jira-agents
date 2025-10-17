def test_config_loads(config):
    assert config.jira_base_url is not None
    assert config.model is not None