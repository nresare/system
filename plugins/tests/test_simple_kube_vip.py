# SPDX-License-Identifier: MIT
"""kube-vip Service configuration and compatibility with simple protocols."""

import json
import tomllib
from pathlib import Path

import pytest
import yaml

from simple import SimpleBlock, generate_simple


@pytest.mark.parametrize("grpc", [False, True])
@pytest.mark.parametrize(
    ("address", "canonical"),
    [
        (None, None),
        ("192.0.2.10", "192.0.2.10"),
        ("2001:0db8:0:0:0:0:0:10", "2001:db8::10"),
    ],
)
def test_simple_kube_vip_service(
    tmp_path: Path, grpc: bool, address: str | None, canonical: str | None
) -> None:
    config = '[[simple]]\nnamespace = "example"\nimage = "example/server"\n'
    config += f"grpc = {str(grpc).lower()}\n"
    if address is not None:
        config += f"kube-vip-ip = {json.dumps(address)}\n"
    data = tomllib.loads(config)
    block = SimpleBlock()
    block.load_config(data["simple"], tmp_path / "config.toml", data)
    (parsed,) = block.iter_configs()
    assert parsed.kube_vip_ip == canonical
    output = tmp_path / "output"
    generate_simple(parsed, output)
    service = yaml.safe_load((output / "example/service-example.yaml").read_text())
    deployment = yaml.safe_load(
        (output / "example/deployment-example.yaml").read_text()
    )
    annotations = service["metadata"].get("annotations", {})
    if canonical is not None:
        assert service["spec"]["type"] == "LoadBalancer"
        assert service["spec"]["loadBalancerClass"] == "kube-vip.io/kube-vip-class"
        assert annotations["kube-vip.io/loadbalancerIPs"] == canonical
    else:
        assert service["spec"]["type"] == "ClusterIP"
        assert "loadBalancerClass" not in service["spec"]
        assert "kube-vip.io/loadbalancerIPs" not in annotations
    assert service["spec"]["selector"] == {"app": "example"}
    port = service["spec"]["ports"][0]
    assert port["port"] == (50051 if grpc else 80)
    assert port["targetPort"] == ("grpc" if grpc else "http")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["ports"][0]["containerPort"] == (50051 if grpc else 8080)
    if grpc:
        assert port["appProtocol"] == "kubernetes.io/h2c"
        assert container["readinessProbe"]["grpc"]["service"] == "readiness"
        assert container["livenessProbe"]["grpc"]["service"] == "liveness"
    else:
        assert "readinessProbe" not in container
        assert "livenessProbe" not in container


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        123,
        [],
        {},
        "",
        "example.com",
        "192.0.2.10/24",
        "192.0.2.10,192.0.2.11",
        "fe80::1%eth0",
        "999.1.1.1",
    ],
)
def test_simple_kube_vip_ip_rejects_invalid_values(
    tmp_path: Path, value: object
) -> None:
    block = SimpleBlock()
    with pytest.raises(
        ValueError, match="'kube-vip-ip' must be an IPv4 or IPv6 address string"
    ):
        block.load_config(
            [{"namespace": "example", "image": "example/server", "kube-vip-ip": value}],
            tmp_path / "config.toml",
            {},
        )
