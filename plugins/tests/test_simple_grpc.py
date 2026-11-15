# SPDX-License-Identifier: MIT
"""Protocol defaults and native health probes for simple deployments."""

import tomllib
from pathlib import Path

import pytest
import yaml

from simple import SimpleBlock, generate_simple


@pytest.mark.parametrize("setting", ["", "grpc = false", "grpc = true"])
def test_simple_protocol_ports_and_health_probes(tmp_path: Path, setting: str) -> None:
    data = tomllib.loads(
        '[[simple]]\nnamespace = "example"\nimage = "example/server:latest"\n' + setting
    )
    block = SimpleBlock()
    block.load_config(data["simple"], tmp_path / "config.toml", data)
    (config,) = block.iter_configs()
    output = tmp_path / "output"
    generate_simple(config, output)
    service = yaml.safe_load((output / "example/service-example.yaml").read_text())
    deployment = yaml.safe_load(
        (output / "example/deployment-example.yaml").read_text()
    )
    container = deployment["spec"]["template"]["spec"]["containers"][0]

    if setting == "grpc = true":
        assert config.grpc is True
        assert container["ports"] == [{"name": "grpc", "containerPort": 50051}]
        assert service["spec"]["ports"] == [
            {
                "name": "grpc",
                "port": 50051,
                "targetPort": "grpc",
                "appProtocol": "kubernetes.io/h2c",
            }
        ]
        assert container["livenessProbe"] == {
            "grpc": {"port": 50051, "service": "liveness"}
        }
        assert container["readinessProbe"] == {
            "grpc": {"port": 50051, "service": "readiness"}
        }
    else:
        assert config.grpc is False
        assert container["ports"] == [{"name": "http", "containerPort": 8080}]
        assert service["spec"]["ports"] == [
            {"name": "http", "port": 80, "targetPort": "http"}
        ]
        assert "livenessProbe" not in container
        assert "readinessProbe" not in container


@pytest.mark.parametrize("value", ["true", "false", 1, 0, [], {}])
def test_simple_grpc_requires_boolean(tmp_path: Path, value: object) -> None:
    block = SimpleBlock()
    with pytest.raises(ValueError, match="'grpc' must be a boolean"):
        block.load_config(
            [{"namespace": "example", "image": "example/server", "grpc": value}],
            tmp_path / "config.toml",
            {},
        )
