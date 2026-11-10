import io
import json
import os
import unittest
import urllib.error
from unittest.mock import patch

from src.models import HTTPModel, ModelServiceError


class ModelTests(unittest.TestCase):
    def test_http_contract_and_key_is_not_in_prompt(self):
        env = {"LLM_BASE_URL": "https://provider.example/v1", "LLM_MODEL": "example", "LLM_API_KEY": "local-secret"}
        decision = {"action": "search_documents", "arguments": {"query": "报销期限"}, "basis": "Need sources"}
        body = json.dumps({"choices": [{"message": {"content": json.dumps(decision)}}]}).encode()
        with patch.dict(os.environ, env), patch("urllib.request.urlopen", return_value=io.BytesIO(body)) as mocked:
            self.assertEqual(HTTPModel().decide({"question": "报销期限？"}), decision)
            self.assertNotIn(b"local-secret", mocked.call_args.args[0].data)

    def test_provider_error_does_not_leak_body_or_key(self):
        env = {"LLM_BASE_URL": "https://provider.example/v1", "LLM_MODEL": "example", "LLM_API_KEY": "local-secret"}
        error = urllib.error.HTTPError("https://private-host/", 401, "local-secret", {}, None)
        with patch.dict(os.environ, env), patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(ModelServiceError) as caught:
                HTTPModel().decide({})
            self.assertEqual(str(caught.exception), "provider_http_401")
