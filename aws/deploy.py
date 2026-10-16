#!/usr/bin/env python3
"""Local EC2 deployment helpers. No AWS API, secret generation, resets or volume deletion."""

import argparse
import base64
import ipaddress
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
EXPECTED_NODES = {"rabbit@rabbitmq-node1", "rabbit@rabbitmq-node2"}


class DeploymentError(Exception):
    pass


def private_ipv4(value):
    address = ipaddress.ip_address(value)
    networks = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
    if address.version != 4 or not any(address in ipaddress.ip_network(n) for n in networks):
        raise DeploymentError("Use only RFC1918 private IPv4 addresses for RabbitMQ.")
    return str(address)


def resolved_hosts(value):
    if isinstance(value, dict):
        return value
    # Compose JSON represents extra_hosts as host=IPv4 entries, not always as a map.
    return dict(item.split("=", 1) if "=" in item else item.split(":", 1) for item in value)


def canonical(resource, fields):
    return json.dumps({field: resource.get(field) for field in fields}, sort_keys=True)


def topology_state(expected, actual):
    """Allow an empty topology or the exact existing project resources; never overwrite drift."""
    if any(p.get("vhost") == "barriodigital" for p in actual.get("operator_policies", [])):
        raise DeploymentError("Existing operator policies require manual review before topology import/verification.")
    resources = {
        "exchanges": ("name", "vhost", "type", "durable", "auto_delete", "internal", "arguments"),
        "queues": ("name", "vhost", "durable", "auto_delete", "arguments"),
        "policies": ("name", "vhost", "pattern", "apply-to", "priority", "definition"),
        "bindings": ("source", "vhost", "destination", "destination_type", "routing_key", "arguments"),
    }
    present = {}
    for kind, fields in resources.items():
        wanted = {item.get("name", item.get("source")) for item in expected[kind]}
        present[kind] = [item for item in actual.get(kind, [])
                         if item.get("vhost") == "barriodigital"
                         and (kind == "policies" or item.get("name", item.get("source")) in wanted
                              or item.get("name", item.get("source", "")).startswith(("cmd.", "q.cmd.")))]
    if not any(present.values()):
        return "empty"
    for kind, fields in resources.items():
        if {canonical(r, fields) for r in expected[kind]} != {canonical(r, fields) for r in present[kind]}:
            raise DeploymentError("Existing project topology differs in " + kind + "; manual review required. Nothing imported.")
    return "ready"


def ensure_empty_join_target(definitions, bootstrap_user):
    if definitions.get("queues") or definitions.get("policies") or definitions.get("parameters") or definitions.get("bindings"):
        raise DeploymentError("Node2 is not empty. Joining could lose metadata/data; operation refused.")
    for exchange in definitions.get("exchanges", []):
        if exchange["name"] and not exchange["name"].startswith("amq."):
            raise DeploymentError("Node2 contains a custom exchange; operation refused.")
    if any(v["name"] not in ("/", "barriodigital") for v in definitions.get("vhosts", [])):
        raise DeploymentError("Node2 contains custom vhosts; operation refused.")
    if any(u["name"] != bootstrap_user for u in definitions.get("users", [])):
        raise DeploymentError("Node2 contains additional users; operation refused.")
    if definitions.get("global_parameters"):
        # RabbitMQ may export its generated cluster name and internal ID even on a fresh node.
        allowed = {"cluster_name", "internal_cluster_id"}
        if any(p["name"] not in allowed for p in definitions["global_parameters"]):
            raise DeploymentError("Node2 contains custom global parameters; operation refused.")


class Compose:
    def __init__(self, target, env_file):
        self.target = target
        self.env_file = Path(env_file).resolve()
        if not self.env_file.is_file():
            raise DeploymentError("Missing env file. Copy the corresponding .example and configure it locally.")
        if platform.system() == "Linux" and stat.S_IMODE(self.env_file.stat().st_mode) & 0o077:
            raise DeploymentError("Protect the env file with chmod 600 before continuing.")
        files = ["compose.apps.yml"] if target == "apps" else ["compose.rabbitmq.common.yml", "compose.rabbitmq." + target + ".yml"]
        self.command = ["docker", "compose", "--project-directory", str(ROOT), "--env-file", str(self.env_file)]
        for file in files:
            self.command.extend(["-f", str(ROOT / file)])
        result = subprocess.run(self.command + ["config", "--format", "json"], capture_output=True, text=True)
        if result.returncode:
            raise DeploymentError("Compose configuration invalid: check required variables with 'docker compose ... config --quiet'.")
        self.config = json.loads(result.stdout)

    def run(self, *args, capture=False, timeout=900):
        environment = dict(os.environ, COMPOSE_PARALLEL_LIMIT="1")
        result = subprocess.run(self.command + list(args), capture_output=capture, text=True,
                                env=environment, timeout=timeout)
        if result.returncode:
            # Captured output could contain credentials. Never print it on failure.
            raise DeploymentError("Docker Compose operation failed; inspect container health locally without sharing secrets.")
        return result.stdout if capture else None

    def env(self, service):
        return self.config["services"][service]["environment"]

    def api(self, path, payload=None):
        environment = self.env("rabbitmq")
        auth = base64.b64encode((environment["RABBITMQ_DEFAULT_USER"] + ":" + environment["RABBITMQ_DEFAULT_PASS"]).encode()).decode()
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request("http://127.0.0.1:15672/api/" + path, data=data,
                                         headers={"Authorization": "Basic " + auth, "Content-Type": "application/json"})
        try:
            # Management is local only: do not route credentials through an HTTP proxy.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=30) as response:
                body = response.read()
                return json.loads(body) if body else None
        except (urllib.error.URLError, TimeoutError) as error:
            code = getattr(error, "code", "unreachable")
            raise DeploymentError("Local RabbitMQ Management API failed (" + str(code) + "). Check existing bootstrap credentials and health.") from None


def running_nodes(compose):
    nodes = compose.api("nodes")
    if any(node.get("partitions") for node in nodes):
        raise DeploymentError("A network partition is reported; manual investigation required.")
    return {node["name"] for node in nodes if node.get("running") is True}


def cluster_status(compose, node=None):
    command = ["exec", "-T", "rabbitmq", "rabbitmqctl", "-q"]
    if node:
        command.extend(["--node", node])
    return json.loads(compose.run(*command, "cluster_status", "--formatter", "json", capture=True))


def verify_cluster(compose):
    if running_nodes(compose) != EXPECTED_NODES:
        raise DeploymentError("Both expected nodes must be running in the same cluster.")
    status = cluster_status(compose)
    if set(status["disk_nodes"]) != EXPECTED_NODES or status.get("alarms") or status.get("partitions"):
        raise DeploymentError("Unexpected cluster membership, alarms or partitions; manual investigation required.")
    compose.run("exec", "-T", "rabbitmq", "rabbitmqctl", "cluster_status")
    print("Both expected nodes are running. This does NOT imply replicated classic queues or complete HA.")


def node_preflight(compose):
    environment = compose.env("rabbitmq")
    addresses = resolved_hosts(compose.config["services"]["rabbitmq"]["extra_hosts"])
    for address in addresses.values():
        private_ipv4(address)
    if len(set(addresses.values())) != 2:
        raise DeploymentError("Node addresses must be distinct.")
    mounts = {volume["target"]: Path(volume["source"]).resolve(strict=True)
              for volume in compose.config["services"]["rabbitmq"]["volumes"]}
    data = mounts["/var/lib/rabbitmq"]
    cookie = mounts["/var/lib/rabbitmq/.erlang.cookie"]
    if not data.is_dir() or not cookie.is_file() or cookie.stat().st_size == 0:
        raise DeploymentError("An existing data directory and nonempty existing cookie file are required.")
    if cookie.is_relative_to(ROOT.parent):
        raise DeploymentError("The existing cookie must remain outside the infrastructure Git checkout.")
    for path in (data, cookie):
        metadata = path.stat()
        if metadata.st_uid != 999 or metadata.st_gid != 999:
            raise DeploymentError("Data/cookie must belong to UID/GID 999. No ownership changes performed.")
    if stat.S_IMODE(cookie.stat().st_mode) not in (0o400, 0o600):
        raise DeploymentError("Existing cookie must have mode 0400 or 0600. No secret generated or changed.")
    mnesia = data / "mnesia"
    if mnesia.exists():
        expected = environment["RABBITMQ_NODENAME"]
        if any(p.is_dir() and p.name.startswith("rabbit@") and p.name != expected
               and not p.name.startswith(expected + "-") for p in mnesia.iterdir()):
            raise DeploymentError("Data belongs to a different Erlang node name. Do not rename or reuse it automatically.")
    # Refuse to start a second deployment over another running container's storage.
    ids = subprocess.run(["docker", "ps", "-q"], capture_output=True, text=True, check=True).stdout.split()
    if ids:
        containers = json.loads(subprocess.run(["docker", "inspect", *ids], capture_output=True, text=True, check=True).stdout)
        for container in containers:
            same_project = (container.get("Config", {}).get("Labels") or {}).get("com.docker.compose.project") == compose.config["name"]
            if not same_project and any(Path(m["Source"]).resolve() == data for m in container.get("Mounts", []) if m.get("Type") == "bind"):
                raise DeploymentError("Another running container already uses this data directory. Manual migration/backup required.")
    # Also detects an already-running native broker or a different host-network container.
    own_ids = compose.run("ps", "-q", "rabbitmq", capture=True).split()
    if not own_ids:
        try:
            with socket.socket() as probe:
                probe.bind((private_ipv4(environment["RABBITMQ_BIND_IP"]), 5672))
        except OSError:
            raise DeploymentError("Private AMQP bind unavailable: wrong host IP or another broker already listening.") from None


def apps_preflight(compose):
    services = compose.config["services"]
    for service in ("requests", "catalog"):
        url = urllib.parse.urlsplit(compose.env(service)["DB_URL"].removeprefix("jdbc:"))
        mode = urllib.parse.parse_qs(url.query).get("sslmode", [""])[0]
        if mode not in ("require", "verify-ca", "verify-full"):
            raise DeploymentError(service + ": Supabase JDBC must explicitly require SSL.")
    addresses = compose.env("requests")["RABBITMQ_ADDRESSES"].split(",")
    if len(addresses) != 2:
        raise DeploymentError("Configure the two private RabbitMQ host:port addresses.")
    for address in addresses:
        host, port = address.strip().rsplit(":", 1)
        private_ipv4(host)
        if port != "5672":
            raise DeploymentError("This AWS configuration expects private AMQP on port 5672.")
    if len(set(addresses)) != 2:
        raise DeploymentError("RabbitMQ addresses must be distinct.")
    admin = compose.env("rabbitmq-admin")
    password = admin["ADMIN_HTTP_PASSWORD"]
    if len(password) < 16 or len(password.encode()) > 72:
        raise DeploymentError("Internal HTTP password must have at least 16 characters and at most 72 UTF-8 bytes.")
    if password in [compose.env(s)["RABBITMQ_PASSWORD"] for s in ("requests", "notify", "rabbitmq-admin")]:
        raise DeploymentError("Do not reuse broker credentials for the Admin HTTP account.")
    origin = urllib.parse.urlsplit(compose.env("bff")["FRONTEND_ORIGIN"])
    if origin.scheme != "https" or not origin.netloc or origin.path or origin.query or origin.fragment:
        raise DeploymentError("FRONTEND_ORIGIN must be the HTTPS Amplify origin, without a trailing slash or path.")
    if any(services[s].get("ports") for s in ("requests", "catalog", "notify", "rabbitmq-admin")):
        raise DeploymentError("Internal microservices must not publish host ports.")
    for service in services.values():
        build = service.get("build")
        if build and not (Path(build["context"]) / "Dockerfile").is_file():
            raise DeploymentError("A sibling repository or its Dockerfile is missing. Clone the documented paths first.")


def check_apps_capacity():
    with open("/proc/meminfo", encoding="ascii") as memory:
        total_kib = int(next(line.split()[1] for line in memory if line.startswith("MemTotal:")))
    if total_kib < 6 * 1024 * 1024:
        raise DeploymentError("Five JVMs plus builds need an 8 GiB-class host (recommend t3.large). Historical t3.micro is insufficient. No AWS change made.")
    if shutil.disk_usage(ROOT).free < 15 * 1024**3:
        raise DeploymentError("Keep at least 15 GiB free for serial Docker builds; recommend 30-40 GiB EBS or more after measuring artifacts.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=("node1", "node2", "apps"))
    parser.add_argument("action", choices=("validate", "start", "ps", "verify", "join", "topology"))
    parser.add_argument("--env-file")
    parser.add_argument("--confirm-empty-node2", action="store_true")
    parser.add_argument("--apply", action="store_true", help="Import original topology only if no project resources exist")
    args = parser.parse_args()
    compose = Compose(args.target, args.env_file or ROOT / (".env." + args.target))
    if args.target == "apps":
        apps_preflight(compose)
    if args.action == "validate":
        print("Compose configuration valid. No container started; no secret values printed.")
        return
    if platform.system() != "Linux":
        raise DeploymentError("Runtime operations are intended for the Linux EC2 host. Use validate on Windows.")
    if args.action == "ps":
        compose.run("ps")
    elif args.action == "start":
        if args.target == "apps":
            check_apps_capacity()
            compose.run("build", timeout=3600)
            compose.run("up", "-d", "--wait", "--wait-timeout", "300")
        else:
            node_preflight(compose)
            compose.run("up", "-d", "--wait", "--wait-timeout", "300", "rabbitmq")
        compose.run("ps")
    elif args.target == "apps":
        raise DeploymentError("Use validate, start or ps for applications.")
    elif args.action == "verify":
        verify_cluster(compose)
    elif args.action == "join":
        if args.target != "node2" or not args.confirm_empty_node2:
            raise DeploymentError("Join only on an EMPTY node2 with --confirm-empty-node2, before running any producer/consumer.")
        nodes = running_nodes(compose)
        if nodes != EXPECTED_NODES:
            if nodes != {"rabbit@rabbitmq-node2"}:
                raise DeploymentError("Unexpected existing cluster membership; operation refused.")
            ensure_empty_join_target(compose.api("definitions"), compose.env("rabbitmq")["RABBITMQ_DEFAULT_USER"])
            compose.run("exec", "-T", "rabbitmq", "rabbitmq-diagnostics", "-q", "-n", "rabbit@rabbitmq-node1", "ping")
            seed = cluster_status(compose, "rabbit@rabbitmq-node1")
            if set(seed["disk_nodes"]) != {"rabbit@rabbitmq-node1"} or seed.get("partitions") or seed.get("alarms"):
                raise DeploymentError("Node1 must be the healthy authoritative single-node seed. Unexpected membership; join refused.")
            # RabbitMQ 4.1+ supports live join; never stop_app/reset or discard existing data.
            compose.run("exec", "-T", "rabbitmq", "rabbitmqctl", "join_cluster", "rabbit@rabbitmq-node1")
        verify_cluster(compose)
    elif args.action == "topology":
        if args.target != "node1":
            raise DeploymentError("Import/verify centralized topology through node1 only.")
        verify_cluster(compose)
        expected = json.loads((ROOT.parent / "rabbitmq" / "definitions.json").read_text(encoding="utf-8-sig"))
        state = topology_state(expected, compose.api("definitions"))
        if state == "empty":
            if not args.apply:
                raise DeploymentError("Project topology is absent. Use --apply once after reviewing the empty cluster.")
            compose.api("definitions", expected)
        for attempt in range(15):
            try:
                if topology_state(expected, compose.api("definitions")) == "ready":
                    print("Original topology verified: 3 exchanges, 6 classic queues, 9 bindings, 3 DLX policies. Existing resources retained.")
                    return
            except DeploymentError:
                if attempt == 14:
                    raise
            time.sleep(2)
        raise DeploymentError("Topology is not ready; no reset or destructive operation attempted.")


if __name__ == "__main__":
    try:
        main()
    except (DeploymentError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        # Exception details from network/process libraries can contain secrets.
        error = sys.exc_info()[1]
        print(str(error) if isinstance(error, DeploymentError) else "Operation failed. Review paths, permissions and local tools; no secret values printed.", file=sys.stderr)
        sys.exit(1)
