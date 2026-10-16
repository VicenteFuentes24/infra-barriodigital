import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "deploy.py"
SPEC = importlib.util.spec_from_file_location("deploy", MODULE)
deploy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy)
DEFINITIONS = json.loads((deploy.ROOT.parent / "rabbitmq" / "definitions.json").read_text(encoding="utf-8-sig"))


class SafetyTests(unittest.TestCase):
    def test_empty_topology_is_importable(self):
        self.assertEqual("empty", deploy.topology_state(DEFINITIONS, {}))

    def test_exact_existing_topology_is_retained(self):
        self.assertEqual("ready", deploy.topology_state(DEFINITIONS, copy.deepcopy(DEFINITIONS)))

    def test_exported_extra_fields_do_not_change_semantics(self):
        actual = copy.deepcopy(DEFINITIONS)
        actual["queues"][0]["type"] = "classic"
        self.assertEqual("ready", deploy.topology_state(DEFINITIONS, actual))

    def test_partial_topology_is_never_overwritten(self):
        actual = copy.deepcopy(DEFINITIONS)
        actual["queues"].pop()
        with self.assertRaises(deploy.DeploymentError):
            deploy.topology_state(DEFINITIONS, actual)

    def test_queue_type_drift_is_rejected(self):
        actual = copy.deepcopy(DEFINITIONS)
        actual["queues"][0]["arguments"]["x-queue-type"] = "quorum"
        with self.assertRaises(deploy.DeploymentError):
            deploy.topology_state(DEFINITIONS, actual)

    def test_dlx_policy_drift_is_rejected(self):
        actual = copy.deepcopy(DEFINITIONS)
        actual["policies"][0]["definition"]["dead-letter-routing-key"] = "wrong"
        with self.assertRaises(deploy.DeploymentError):
            deploy.topology_state(DEFINITIONS, actual)

    def test_additional_policy_cannot_silently_override_dlx(self):
        actual = copy.deepcopy(DEFINITIONS)
        actual["policies"].append({"name": "override", "vhost": "barriodigital", "priority": 100, "pattern": ".*"})
        with self.assertRaises(deploy.DeploymentError):
            deploy.topology_state(DEFINITIONS, actual)

    def test_operator_policy_requires_manual_review(self):
        with self.assertRaises(deploy.DeploymentError):
            deploy.topology_state(DEFINITIONS, {"operator_policies": [{"name": "override", "vhost": "barriodigital"}]})

    def test_binding_drift_is_rejected(self):
        actual = copy.deepcopy(DEFINITIONS)
        actual["bindings"][0]["routing_key"] = "wrong"
        with self.assertRaises(deploy.DeploymentError):
            deploy.topology_state(DEFINITIONS, actual)

    def test_fresh_node_can_join(self):
        deploy.ensure_empty_join_target({"users": [{"name": "bootstrap"}], "vhosts": [{"name": "barriodigital"}],
                                        "exchanges": [{"name": ""}, {"name": "amq.direct"}]}, "bootstrap")

    def test_even_empty_existing_queues_prevent_join(self):
        with self.assertRaises(deploy.DeploymentError):
            deploy.ensure_empty_join_target({"queues": [{"name": "important", "messages": 0}]}, "bootstrap")

    def test_custom_exchanges_prevent_join(self):
        with self.assertRaises(deploy.DeploymentError):
            deploy.ensure_empty_join_target({"exchanges": [{"name": "custom"}]}, "bootstrap")

    def test_other_users_prevent_join(self):
        with self.assertRaises(deploy.DeploymentError):
            deploy.ensure_empty_join_target({"users": [{"name": "other"}]}, "bootstrap")

    def test_existing_bindings_prevent_join(self):
        with self.assertRaises(deploy.DeploymentError):
            deploy.ensure_empty_join_target({"bindings": [{"source": "amq.direct"}]}, "bootstrap")

    def test_private_addresses_are_configurable(self):
        self.assertEqual("10.0.1.62", deploy.private_ipv4("10.0.1.62"))
        self.assertEqual("172.20.1.2", deploy.private_ipv4("172.20.1.2"))

    def test_public_loopback_and_metadata_addresses_are_rejected(self):
        for address in ("8.8.8.8", "127.0.0.1", "169.254.169.254", "::1"):
            with self.subTest(address=address), self.assertRaises(deploy.DeploymentError):
                deploy.private_ipv4(address)

    def test_cluster_must_contain_both_expected_nodes(self):
        compose = unittest.mock.Mock()
        compose.api.return_value = [{"name": "rabbit@rabbitmq-node1", "running": True}]
        with self.assertRaises(deploy.DeploymentError):
            deploy.verify_cluster(compose)

    def test_partitions_fail_verification(self):
        compose = unittest.mock.Mock()
        compose.api.return_value = [{"name": "rabbit@rabbitmq-node1", "running": True, "partitions": ["rabbit@rabbitmq-node2"]}]
        with self.assertRaises(deploy.DeploymentError):
            deploy.running_nodes(compose)


@unittest.skipUnless(shutil.which("docker"), "Docker Compose CLI required; daemon is NOT required")
class ComposeConfigurationTests(unittest.TestCase):
    def test_existing_local_compose_remains_valid_without_loading_private_env_files(self):
        help_result = subprocess.run(["docker", "compose", "config", "--help"], capture_output=True, text=True)
        if "--no-env-resolution" not in help_result.stdout:
            self.skipTest("Compose 2.30+ required to validate local files without reading private env files")
        for name in ("compose.yml", "compose.rabbitmq.yml"):
            with self.subTest(file=name), patch.dict(os.environ, {"RABBITMQ_DEFAULT_USER": "configuration-test-only",
                                                                  "RABBITMQ_DEFAULT_PASS": "broker-configuration-test-only"}):
                result = subprocess.run(["docker", "compose", "--env-file", str(deploy.ROOT.parent / ".env.rabbitmq.example"),
                                         "-f", str(deploy.ROOT.parent / name), "config", "--quiet", "--no-env-resolution"],
                                        capture_output=True, text=True)
                self.assertEqual(0, result.returncode, "Existing local Compose did not validate")

    def configuration(self, target):
        self.directory = tempfile.TemporaryDirectory(prefix=".validation-", dir=deploy.ROOT)
        self.addCleanup(self.directory.cleanup)
        text = (deploy.ROOT / (".env." + target + ".example")).read_text()
        values = {}
        for line in text.splitlines():
            if line and not line.startswith("#"):
                key, value = line.split("=", 1)
                values[key] = value or "configuration-test-only"
        values.update({
            "RABBITMQ_COOKIE_FILE": "/tmp/existing-test-cookie-not-created",
            "REQUESTS_DB_URL": "jdbc:postgresql://database.invalid/db?sslmode=require",
            "CATALOG_DB_URL": "jdbc:postgresql://database.invalid/db?sslmode=require",
            "FRONTEND_ORIGIN": "https://frontend.invalid",
            "ADMIN_HTTP_PASSWORD": "separate-http-test-only-password",
        })
        file = Path(self.directory.name) / "config.env"
        file.write_text("\n".join(key + "=" + value for key, value in values.items()), encoding="utf-8")
        file.chmod(0o600)
        with patch.dict(os.environ, values):
            return deploy.Compose(target, file)

    def test_node1_private_host_network_and_no_definition_import(self):
        config = self.configuration("node1").config
        rabbit = config["services"]["rabbitmq"]
        self.assertEqual("host", rabbit["network_mode"])
        self.assertEqual("999:999", rabbit["user"])
        self.assertEqual("rabbit@rabbitmq-node1", rabbit["environment"]["RABBITMQ_NODENAME"])
        self.assertEqual("10.0.1.62", rabbit["environment"]["RABBITMQ_BIND_IP"])
        self.assertFalse(rabbit.get("ports"))
        self.assertNotIn("rabbitmq-topology", config["services"])
        self.assertTrue(next(v for v in rabbit["volumes"] if v["target"].endswith(".erlang.cookie"))["read_only"])

    def test_node2_has_separate_identity_and_private_resolution(self):
        rabbit = self.configuration("node2").config["services"]["rabbitmq"]
        self.assertEqual("rabbit@rabbitmq-node2", rabbit["environment"]["RABBITMQ_NODENAME"])
        self.assertEqual("10.0.2.151", rabbit["environment"]["RABBITMQ_BIND_IP"])
        self.assertEqual("10.0.1.62", deploy.resolved_hosts(rabbit["extra_hosts"])["rabbitmq-node1"])

    def test_applications_are_internal_persistent_and_use_private_rabbit(self):
        compose = self.configuration("apps")
        deploy.apps_preflight(compose)
        services = compose.config["services"]
        self.assertEqual(6, len(services))
        for name in ("requests", "catalog", "notify", "rabbitmq-admin"):
            self.assertFalse(services[name].get("ports"))
        for name in ("requests", "notify", "rabbitmq-admin"):
            self.assertEqual("10.0.1.62:5672,10.0.2.151:5672", compose.env(name)["RABBITMQ_ADDRESSES"])
        self.assertEqual("validate", compose.env("requests")["JPA_DDL_AUTO"])
        self.assertEqual("validate", compose.env("catalog")["JPA_DDL_AUTO"])
        self.assertEqual("http://requests:8081", compose.env("bff")["REQUESTS_SERVICE_URL"])
        self.assertEqual("mailpit", compose.env("notify")["SMTP_HOST"])
        self.assertEqual("/app/data", services["notify"]["volumes"][0]["target"])
        self.assertEqual("127.0.0.1", services["mailpit"]["ports"][0]["host_ip"])
        self.assertEqual("127.0.0.1", services["bff"]["ports"][0]["host_ip"])

    def test_admin_cannot_reuse_a_broker_password(self):
        compose = self.configuration("apps")
        compose.env("rabbitmq-admin")["ADMIN_HTTP_PASSWORD"] = compose.env("notify")["RABBITMQ_PASSWORD"]
        with self.assertRaises(deploy.DeploymentError):
            deploy.apps_preflight(compose)

    def test_supabase_without_ssl_is_rejected(self):
        compose = self.configuration("apps")
        compose.env("requests")["DB_URL"] = "jdbc:postgresql://database.invalid/db"
        with self.assertRaises(deploy.DeploymentError):
            deploy.apps_preflight(compose)


if __name__ == "__main__":
    unittest.main()
