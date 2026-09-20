# SPDX-License-Identifier: MIT
"""Tests for the [[helm]] config block."""

import re
import textwrap
from collections.abc import Sequence
from pathlib import Path
from threading import Barrier, Lock
from time import sleep
from typing import Any
from unittest import mock

import pytest
import yaml
from manifest_builder.blocks import ConfigBlock
from manifest_builder.config import ManifestConfig, load_configs, resolve_configs
from manifest_builder.generator import generate_manifests
from manifest_builder.helmfile import Helmfile, HelmfileRelease, HelmfileRepository
from pystache.context import KeyNotFoundError

from helm import ChartConfig, HelmBlock, _generate_helm_manifests

NAMESPACED_YAML = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
  namespace: production
spec: {}
"""


def write_toml(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    path.write_text(textwrap.dedent(content))
    return path


def all_configs(blocks: Sequence[ConfigBlock]) -> tuple[ManifestConfig, ...]:
    return tuple(config for block in blocks for config in block.iter_configs())


def only_config(blocks: Sequence[ConfigBlock]) -> ManifestConfig:
    (config,) = all_configs(blocks)
    return config


def config_blocks() -> list[ConfigBlock[Any]]:
    """This directory's helm block, loaded the way a real run loads it."""
    return [HelmBlock()]


def load_test_configs(config_dir: Path) -> Sequence[ConfigBlock]:
    return load_configs(config_dir, config_blocks())


def manifest_configs(
    *,
    helm: list[ChartConfig] | None = None,
) -> list[ConfigBlock[Any]]:
    return [HelmBlock(helm)]


def _make_helmfile() -> Helmfile:
    return Helmfile(
        repositories=[
            HelmfileRepository(name="myrepo", url="https://charts.example.com")
        ],
        releases=[
            HelmfileRelease(
                name="myapp",
                chart="myrepo/myapp",
                version="1.2.3",
                namespace="default",
            )
        ],
    )


# ---------------------------------------------------------------------------


def test_values_resolved_relative_to_config_dir(tmp_path: Path) -> None:
    """Values paths must be resolved relative to the TOML file's directory."""
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    write_toml(
        conf_dir,
        "config.toml",
        """\
        [[helm]]
        namespace = "default"
        chart = "./charts/myapp"
        name = "myapp"
        values = ["myapp/values.yaml"]
        """,
    )

    configs = load_test_configs(conf_dir)
    assert len(all_configs(configs)) == 1
    config = only_config(configs)
    assert isinstance(config, ChartConfig)
    assert config.values == [conf_dir / "myapp/values.yaml"]


def test_values_resolved_relative_to_custom_config_dir(tmp_path: Path) -> None:
    """Specifying a different -c directory changes where values are resolved."""
    conf_a = tmp_path / "conf-a"
    conf_a.mkdir()
    conf_b = tmp_path / "conf-b"
    conf_b.mkdir()

    for conf_dir in (conf_a, conf_b):
        write_toml(
            conf_dir,
            "config.toml",
            """\
            [[helm]]
            namespace = "default"
            chart = "./charts/myapp"
            name = "myapp"
            values = ["values.yaml"]
            """,
        )

    configs_a = load_test_configs(conf_a)
    configs_b = load_test_configs(conf_b)

    config_a = only_config(configs_a)
    config_b = only_config(configs_b)
    assert isinstance(config_a, ChartConfig)
    assert isinstance(config_b, ChartConfig)
    assert config_a.values == [conf_a / "values.yaml"]
    assert config_b.values == [conf_b / "values.yaml"]
    assert config_a.values != config_b.values


def test_values_single_string_treated_as_list(tmp_path: Path) -> None:
    """A bare string for 'values' is treated as a single-element list."""
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    write_toml(
        conf_dir,
        "config.toml",
        """\
        [[helm]]
        namespace = "default"
        chart = "./charts/myapp"
        name = "myapp"
        values = "myapp/values.yaml"
        """,
    )

    configs = load_test_configs(conf_dir)
    config = only_config(configs)
    assert isinstance(config, ChartConfig)
    assert config.values == [conf_dir / "myapp/values.yaml"]


def test_values_empty_when_not_specified(tmp_path: Path) -> None:
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    write_toml(
        conf_dir,
        "config.toml",
        """\
        [[helm]]
        namespace = "default"
        chart = "./charts/myapp"
        name = "myapp"
        """,
    )

    configs = load_test_configs(conf_dir)
    config = only_config(configs)
    assert isinstance(config, ChartConfig)
    assert config.values == []


def test_load_chart_config_with_name_override(tmp_path: Path) -> None:
    """Helm configs can override the release name passed to Helm."""
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    write_toml(
        conf_dir,
        "config.toml",
        """\
        [[helm]]
        namespace = "default"
        release = "myapp"
        name-override = "myapp-rendered"
        """,
    )

    configs = load_test_configs(conf_dir)
    config = only_config(configs)

    assert isinstance(config, ChartConfig)
    assert config.name == "myapp"
    assert config.release == "myapp"
    assert config.name_override == "myapp-rendered"


def test_load_chart_config_with_config(tmp_path: Path) -> None:
    """Helm config can specify ConfigMap keys with local file paths."""
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    config_file = conf_dir / "app.conf"
    config_file.write_text("debug=true\n")
    write_toml(
        conf_dir,
        "config.toml",
        """\
        [[helm]]
        namespace = "default"
        chart = "./charts/myapp"
        name = "myapp"
        config = { "app.conf" = "app.conf" }
        """,
    )

    configs = load_test_configs(conf_dir)
    config = only_config(configs)

    assert isinstance(config, ChartConfig)
    assert config.config == {"app.conf": config_file}


def test_load_chart_config_with_custom_token_audiences(tmp_path: Path) -> None:
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    write_toml(
        conf_dir,
        "config.toml",
        """\
        [[helm]]
        namespace = "default"
        chart = "./charts/myapp"
        name = "myapp"
        custom-token-audiences = ["vault", "api"]
        """,
    )

    config = only_config(load_test_configs(conf_dir))

    assert isinstance(config, ChartConfig)
    assert config.custom_token_audiences == ["vault", "api"]


def test_load_chart_config_with_custom_token_audience(tmp_path: Path) -> None:
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    write_toml(
        conf_dir,
        "config.toml",
        """\
        [[helm]]
        namespace = "default"
        chart = "./charts/myapp"
        name = "myapp"
        custom-token-audience = "vault"
        """,
    )

    config = only_config(load_test_configs(conf_dir))

    assert isinstance(config, ChartConfig)
    assert config.custom_token_audiences == ["vault"]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "custom-token-audience",
            '["vault"]',
            "'custom-token-audience' must be a string",
        ),
        (
            "custom-token-audiences",
            '"vault"',
            "'custom-token-audiences' must be a list of strings",
        ),
    ],
)
def test_load_chart_config_custom_token_audience_type_validation(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    write_toml(
        conf_dir,
        "config.toml",
        f"""\
        [[helm]]
        namespace = "default"
        chart = "./charts/myapp"
        name = "myapp"
        {field} = {value}
        """,
    )

    with pytest.raises(ValueError, match=re.escape(message)):
        load_test_configs(conf_dir)


def test_load_chart_config_custom_token_audience_fields_are_mutually_exclusive(
    tmp_path: Path,
) -> None:
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    write_toml(
        conf_dir,
        "config.toml",
        """\
        [[helm]]
        namespace = "default"
        chart = "./charts/myapp"
        name = "myapp"
        custom-token-audience = "vault"
        custom-token-audiences = ["api"]
        """,
    )

    with pytest.raises(
        ValueError,
        match="Cannot specify both 'custom-token-audience' and "
        "'custom-token-audiences'",
    ):
        load_test_configs(conf_dir)


def test_load_chart_config_unknown_field_raises(tmp_path: Path) -> None:
    """Unknown Helm fields should fail before generation."""
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    write_toml(
        conf_dir,
        "config.toml",
        """\
        [[helm]]
        namespace = "default"
        chart = "./charts/myapp"
        name = "myapp"
        value = ["values.yaml"]
        """,
    )

    with pytest.raises(
        ValueError,
        match=r"Unknown field in \[\[helm\]\]: 'value' on line 5",
    ):
        load_test_configs(conf_dir)


def test_variables_are_loaded_for_helm_configs(tmp_path: Path) -> None:
    """Top-level variables should be attached to helm configs from the same TOML file."""
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    write_toml(
        conf_dir,
        "config.toml",
        """\
        [variables]
        domain = "example.com"
        replica_count = 3
        use_tls = true

        [[helm]]
        namespace = "default"
        chart = "./charts/myapp"
        name = "myapp"
        values = ["values.yaml"]
        """,
    )

    configs = load_test_configs(conf_dir)
    assert len(all_configs(configs)) == 1
    config = only_config(configs)
    assert isinstance(config, ChartConfig)
    assert config.variables == {
        "domain": "example.com",
        "replica_count": 3,
        "use_tls": True,
    }


# ---------------------------------------------------------------------------


def test_validate_config_missing_values_file(tmp_path: Path) -> None:
    config = ChartConfig(
        name="myapp",
        namespace="default",
        chart="./charts/myapp",
        repo=None,
        version=None,
        values=[tmp_path / "nonexistent.yaml"],
        release=None,
    )
    with pytest.raises(ValueError, match="Values file not found"):
        HelmBlock().validate(config, tmp_path)


def test_validate_config_existing_values_file(tmp_path: Path) -> None:
    values_file = tmp_path / "values.yaml"
    values_file.write_text("key: value\n")

    config = ChartConfig(
        name="myapp",
        namespace="default",
        chart=None,
        repo=None,
        version=None,
        values=[values_file],
        release="myapp",
    )
    HelmBlock().validate(config, tmp_path)  # should not raise


def test_validate_config_missing_local_chart(tmp_path: Path) -> None:
    config = ChartConfig(
        name="myapp",
        namespace="default",
        chart="./charts/myapp",
        repo=None,
        version=None,
        values=[],
        release=None,
    )
    with pytest.raises(ValueError, match="Local chart path not found"):
        HelmBlock().validate(config, tmp_path)


def test_load_configs_both_release_and_chart_raises(tmp_path: Path) -> None:
    conf = tmp_path / "conf"
    conf.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [[helm]]
        namespace = "default"
        name = "myapp"
        chart = "./charts/myapp"
        release = "myapp"
        """,
    )
    with pytest.raises(ValueError, match="Cannot specify both"):
        load_test_configs(conf)


def test_load_configs_neither_release_nor_chart_raises(tmp_path: Path) -> None:
    conf = tmp_path / "conf"
    conf.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [[helm]]
        namespace = "default"
        name = "myapp"
        """,
    )
    with pytest.raises(ValueError, match="Must specify either"):
        load_test_configs(conf)


def test_resolve_configs_fills_in_chart_and_repo(tmp_path: Path) -> None:
    config = ChartConfig(
        name="myapp",
        namespace="default",
        chart=None,
        repo=None,
        version=None,
        values=[],
        release="myapp",
        name_override="myapp-rendered",
        custom_token_audiences=["vault"],
    )
    resolved = resolve_configs(manifest_configs(helm=[config]), _make_helmfile())
    assert len(all_configs(resolved)) == 1
    resolved_config = only_config(resolved)
    assert isinstance(resolved_config, ChartConfig)
    assert resolved_config.chart == "myapp"
    assert resolved_config.repo == "https://charts.example.com"
    assert resolved_config.version == "1.2.3"
    assert resolved_config.name_override == "myapp-rendered"
    assert resolved_config.custom_token_audiences == ["vault"]


def test_resolve_configs_no_helmfile_raises_when_release_present(
    tmp_path: Path,
) -> None:
    config = ChartConfig(
        name="myapp",
        namespace="default",
        chart=None,
        repo=None,
        version=None,
        values=[],
        release="myapp",
    )
    with pytest.raises(ValueError, match="no releases.yaml was found"):
        resolve_configs(manifest_configs(helm=[config]), None)


def test_resolve_configs_unknown_release_raises() -> None:
    config = ChartConfig(
        name="unknown",
        namespace="default",
        chart=None,
        repo=None,
        version=None,
        values=[],
        release="unknown",
    )
    with pytest.raises(ValueError, match="not found in releases.yaml"):
        resolve_configs(manifest_configs(helm=[config]), _make_helmfile())


def test_resolve_configs_oci_repository() -> None:
    """OCI repositories should be resolved to a full OCI URL chart and no repo."""
    helmfile = Helmfile(
        repositories=[
            HelmfileRepository(
                name="envoyproxy",
                url="docker.io/envoyproxy",
                oci=True,
            )
        ],
        releases=[
            HelmfileRelease(
                name="envoy-gateway",
                chart="envoyproxy/gateway-helm",
                version="v1.7.0",
                namespace="default",
            )
        ],
    )
    config = ChartConfig(
        name="envoy-gateway",
        namespace="default",
        chart=None,
        repo=None,
        version=None,
        values=[],
        release="envoy-gateway",
    )
    resolved = resolve_configs(manifest_configs(helm=[config]), helmfile)
    assert len(all_configs(resolved)) == 1
    resolved_config = only_config(resolved)
    assert isinstance(resolved_config, ChartConfig)
    assert resolved_config.chart == "oci://docker.io/envoyproxy/gateway-helm"
    assert resolved_config.repo is None
    assert resolved_config.version == "v1.7.0"


def test_resolve_configs_passthrough_for_direct_chart() -> None:
    config = ChartConfig(
        name="myapp",
        namespace="default",
        chart="./charts/myapp",
        repo=None,
        version=None,
        values=[],
        release=None,
        extra_resources=None,
    )
    resolved = resolve_configs(manifest_configs(helm=[config]), None)
    assert all_configs(resolved) == (config,)


def test_load_chart_config_with_extra_resources(tmp_path: Path) -> None:
    """Chart config can specify a directory with extra YAML resources."""
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    resources_dir = conf_dir / "resources"
    resources_dir.mkdir()

    write_toml(
        conf_dir,
        "config.toml",
        """\
[[helm]]
name = "my-chart"
namespace = "default"
chart = "./charts/myapp"
extra-resources = "resources"
""",
    )

    configs = load_test_configs(conf_dir)
    config = only_config(configs)
    assert isinstance(config, ChartConfig)
    assert config.extra_resources == resources_dir


def test_validate_config_chart_extra_resources_missing_directory(
    tmp_path: Path,
) -> None:
    """Validation should fail if extra_resources directory doesn't exist."""
    config = ChartConfig(
        name="my-chart",
        namespace="default",
        chart="./charts/myapp",
        repo=None,
        version=None,
        values=[],
        release=None,
        extra_resources=tmp_path / "nonexistent",
    )
    with pytest.raises(ValueError, match="Extra resources directory not found"):
        HelmBlock().validate(config, tmp_path)


def test_validate_config_chart_config_missing_file(tmp_path: Path) -> None:
    """Validation should fail if a Helm config file doesn't exist."""
    config = ChartConfig(
        name="my-chart",
        namespace="default",
        chart="./charts/myapp",
        repo=None,
        version=None,
        values=[],
        release=None,
        config={"app.conf": tmp_path / "missing.conf"},
    )
    with pytest.raises(ValueError, match="Config file not found for chart"):
        HelmBlock().validate(config, tmp_path)


def test_validate_config_chart_extra_resources_not_a_directory(tmp_path: Path) -> None:
    """Validation should fail if extra_resources path is not a directory."""
    not_a_dir = tmp_path / "file.txt"
    not_a_dir.write_text("content")

    config = ChartConfig(
        name="my-chart",
        namespace="default",
        chart="./charts/myapp",
        repo=None,
        version=None,
        values=[],
        release=None,
        extra_resources=not_a_dir,
    )
    with pytest.raises(ValueError, match="Extra resources path is not a directory"):
        HelmBlock().validate(config, tmp_path)


def test_load_chart_config_with_init(tmp_path: Path) -> None:
    """Chart config can specify an init script to inject as initContainer."""
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    script_file = conf_dir / "setup.sh"
    script_file.write_text("#!/bin/sh\necho 'initializing'")

    write_toml(
        conf_dir,
        "config.toml",
        """\
[[helm]]
name = "my-chart"
namespace = "default"
chart = "./charts/myapp"
init = "setup.sh"
""",
    )

    configs = load_test_configs(conf_dir)
    config = only_config(configs)
    assert isinstance(config, ChartConfig)
    assert config.init == script_file


def test_validate_config_chart_init_missing_file(tmp_path: Path) -> None:
    """Validation should fail if init script file doesn't exist."""
    # Create the chart directory so that check passes
    chart_dir = tmp_path / "charts" / "myapp"
    chart_dir.mkdir(parents=True)

    config = ChartConfig(
        name="my-chart",
        namespace="default",
        chart="./charts/myapp",
        repo=None,
        version=None,
        values=[],
        release=None,
        init=tmp_path / "nonexistent.sh",
    )
    with pytest.raises(ValueError, match="init script not found"):
        HelmBlock().validate(config, tmp_path)


def test_generate_manifests_renders_helm_configs_concurrently(tmp_path: Path) -> None:
    """Helm renders should overlap without racing chart cache access."""
    chart_dir = tmp_path / "chart"
    chart_dir.mkdir()
    configs = [
        ChartConfig(
            name=name,
            namespace="default",
            chart="chart",
            repo="https://charts.example.com",
            version=None,
            values=[],
            release=None,
        )
        for name in ("first", "second")
    ]
    render_barrier = Barrier(len(configs))
    counter_lock = Lock()
    active_pulls = 0
    max_active_pulls = 0

    def pull(**kwargs: object) -> Path:
        nonlocal active_pulls, max_active_pulls
        with counter_lock:
            active_pulls += 1
            max_active_pulls = max(max_active_pulls, active_pulls)
        sleep(0.02)
        with counter_lock:
            active_pulls -= 1
        return chart_dir

    def render(**kwargs: object) -> str:
        render_barrier.wait(timeout=5)
        release_name = kwargs["release_name"]
        return f"""\
apiVersion: v1
kind: ConfigMap
metadata:
  name: {release_name}
data: {{}}
"""

    with (
        mock.patch("helm.pull_chart", side_effect=pull),
        mock.patch("helm.run_helm_template", side_effect=render),
    ):
        written = generate_manifests(
            [HelmBlock(configs)],
            tmp_path / "out",
            repo_root=tmp_path,
        )

    assert {path.name for path in written} >= {
        "configmap-first.yaml",
        "configmap-second.yaml",
    }
    assert max_active_pulls == 1


# ---------------------------------------------------------------------------
# _generate_helm_manifests CRD handling
# ---------------------------------------------------------------------------


def test_generate_helm_manifests_uses_name_override(tmp_path: Path) -> None:
    """The Helm invocation should use the configured release name override."""
    chart_dir = tmp_path / "chart"
    chart_dir.mkdir()
    config = ChartConfig(
        name="release-from-helmfile",
        namespace="default",
        chart=str(chart_dir),
        repo=None,
        version=None,
        values=[],
        release="release-from-helmfile",
        name_override="rendered-release",
    )

    with mock.patch("helm.run_helm_template", return_value="") as run_helm_template:
        paths = _generate_helm_manifests(
            config, tmp_path / "output", tmp_path / "charts"
        )

    assert paths == set()
    run_helm_template.assert_called_once_with(
        release_name="rendered-release",
        chart=str(chart_dir),
        namespace="default",
        values_files=[],
    )


def test_generate_helm_manifests_writes_crds_returned_by_helm(
    tmp_path: Path,
) -> None:
    """CRDs emitted by helm template are written as cluster-scoped manifests."""
    output_dir = tmp_path / "output"
    charts_dir = tmp_path / "charts"
    charts_dir.mkdir()

    chart_dir = charts_dir / "my-chart"
    chart_dir.mkdir()

    config = ChartConfig(
        name="my-chart",
        namespace="default",
        chart="my-chart",
        repo="https://example.com",
        version="1.0.0",
        values=[],
        release=None,
    )

    templated_manifest = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec: {}
---
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: myresources.example.com
spec:
  group: example.com
  names:
    kind: MyResource
  scope: Namespaced
"""

    with (
        mock.patch(
            "helm.pull_chart",
            return_value=chart_dir,
        ),
        mock.patch(
            "helm.run_helm_template",
            return_value=templated_manifest,
        ),
    ):
        paths = _generate_helm_manifests(config, output_dir, charts_dir)

    crd_output = (
        output_dir / "cluster" / "customresourcedefinition-myresources.example.com.yaml"
    )
    deployment_output = output_dir / "default" / "deployment-my-app.yaml"

    assert crd_output.exists()
    assert deployment_output.exists()
    assert len(paths) == 2


def test_generate_helm_manifests_does_not_copy_crds_from_chart_directory(
    tmp_path: Path,
) -> None:
    """CRDs are not copied separately from the chart filesystem."""
    output_dir = tmp_path / "output"
    charts_dir = tmp_path / "charts"
    charts_dir.mkdir()

    chart_dir = charts_dir / "my-chart"
    chart_dir.mkdir()
    crds_dir = chart_dir / "crds"
    crds_dir.mkdir()
    crd_yaml = crds_dir / "crd.yaml"
    crd_yaml.write_text("""\
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: myresources.example.com
spec:
  group: example.com
  names:
    kind: MyResource
  scope: Namespaced
""")

    config = ChartConfig(
        name="my-chart",
        namespace="default",
        chart="my-chart",
        repo="https://example.com",
        version="1.0.0",
        values=[],
        release=None,
    )

    with (
        mock.patch(
            "helm.pull_chart",
            return_value=chart_dir,
        ),
        mock.patch(
            "helm.run_helm_template",
            return_value="",
        ),
    ):
        paths = _generate_helm_manifests(config, output_dir, charts_dir)

    crd_output = (
        output_dir / "cluster" / "customresourcedefinition-myresources.example.com.yaml"
    )
    assert not crd_output.exists()
    assert paths == set()


def test_generate_helm_manifests_init_single_deployment(tmp_path: Path) -> None:
    """init script should be injected as initContainer when exactly one Deployment exists."""
    chart_dir = tmp_path / "chart"
    chart_dir.mkdir()

    script_file = tmp_path / "setup.sh"
    script_file.write_text("mkdir -p /data && chown 65532:65532 /data")

    config = ChartConfig(
        name="my-chart",
        namespace="default",
        chart=str(chart_dir),
        repo=None,
        version=None,
        values=[],
        release=None,
        init=script_file,
    )

    output_dir = tmp_path / "output"
    charts_dir = tmp_path / "charts"

    deployment_yaml = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  template:
    spec:
      containers:
      - name: app
        image: myapp:1.0
        volumeMounts:
        - name: data
          mountPath: /data
      volumes:
      - name: data
        emptyDir: {}
"""

    images = {"alpine_image": "alpine:3.21"}

    with (
        mock.patch(
            "helm.pull_chart",
            return_value=chart_dir,
        ),
        mock.patch(
            "helm.run_helm_template",
            return_value=deployment_yaml,
        ),
    ):
        paths = _generate_helm_manifests(config, output_dir, charts_dir, images=images)

    assert len(paths) == 1
    deployment_file = output_dir / "default" / "deployment-my-app.yaml"
    assert deployment_file.exists()

    doc = yaml.safe_load(deployment_file.read_text())
    assert "initContainers" in doc["spec"]["template"]["spec"]
    init_containers = doc["spec"]["template"]["spec"]["initContainers"]
    assert len(init_containers) == 1
    assert init_containers[0]["name"] == "setup"
    assert init_containers[0]["image"] == "alpine:3.21"
    assert init_containers[0]["command"] == [
        "/bin/sh",
        "-c",
        "mkdir -p /data && chown 65532:65532 /data",
    ]
    assert len(init_containers[0]["volumeMounts"]) == 1
    assert init_containers[0]["volumeMounts"][0]["name"] == "data"


def test_generate_helm_manifests_init_multiple_deployments(tmp_path: Path) -> None:
    """init should fail with ValueError if more than one Deployment exists."""
    chart_dir = tmp_path / "chart"
    chart_dir.mkdir()

    script_file = tmp_path / "setup.sh"
    script_file.write_text("echo 'init'")

    config = ChartConfig(
        name="my-chart",
        namespace="default",
        chart=str(chart_dir),
        repo=None,
        version=None,
        values=[],
        release=None,
        init=script_file,
    )

    output_dir = tmp_path / "output"
    charts_dir = tmp_path / "charts"

    two_deployments = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app1
spec:
  template:
    spec:
      containers:
      - name: app
        image: myapp:1.0
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app2
spec:
  template:
    spec:
      containers:
      - name: app
        image: myapp:1.0
"""

    images = {"alpine_image": "alpine:3.21"}

    with (
        mock.patch(
            "helm.pull_chart",
            return_value=chart_dir,
        ),
        mock.patch(
            "helm.run_helm_template",
            return_value=two_deployments,
        ),
        pytest.raises(
            ValueError, match="init requires exactly one Deployment.*found 2"
        ),
    ):
        _generate_helm_manifests(config, output_dir, charts_dir, images=images)


def test_generate_helm_manifests_init_no_deployments(tmp_path: Path) -> None:
    """init should fail with ValueError if no Deployments exist."""
    chart_dir = tmp_path / "chart"
    chart_dir.mkdir()

    script_file = tmp_path / "setup.sh"
    script_file.write_text("echo 'init'")

    config = ChartConfig(
        name="my-chart",
        namespace="default",
        chart=str(chart_dir),
        repo=None,
        version=None,
        values=[],
        release=None,
        init=script_file,
    )

    output_dir = tmp_path / "output"
    charts_dir = tmp_path / "charts"

    service_yaml = """\
apiVersion: v1
kind: Service
metadata:
  name: my-service
spec:
  selector:
    app: myapp
"""

    images = {"alpine_image": "alpine:3.21"}

    with (
        mock.patch(
            "helm.pull_chart",
            return_value=chart_dir,
        ),
        mock.patch(
            "helm.run_helm_template",
            return_value=service_yaml,
        ),
        pytest.raises(
            ValueError, match="init requires exactly one Deployment.*found 0"
        ),
    ):
        _generate_helm_manifests(config, output_dir, charts_dir, images=images)


def test_generate_helm_manifests_init_missing_alpine_image(tmp_path: Path) -> None:
    """init should fail if alpine_image is not in images dict."""
    chart_dir = tmp_path / "chart"
    chart_dir.mkdir()

    script_file = tmp_path / "setup.sh"
    script_file.write_text("echo 'init'")

    config = ChartConfig(
        name="my-chart",
        namespace="default",
        chart=str(chart_dir),
        repo=None,
        version=None,
        values=[],
        release=None,
        init=script_file,
    )

    output_dir = tmp_path / "output"
    charts_dir = tmp_path / "charts"

    deployment_yaml = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  template:
    spec:
      containers:
      - name: app
        image: myapp:1.0
"""

    images = {}  # missing alpine_image

    with (
        mock.patch(
            "helm.pull_chart",
            return_value=chart_dir,
        ),
        mock.patch(
            "helm.run_helm_template",
            return_value=deployment_yaml,
        ),
        pytest.raises(
            ValueError,
            match="init requires 'alpine_image' to be defined in images.toml",
        ),
    ):
        _generate_helm_manifests(config, output_dir, charts_dir, images=images)


def test_generate_helm_manifests_init_no_volumemounts(tmp_path: Path) -> None:
    """init container should have no volumeMounts if containers have none."""
    chart_dir = tmp_path / "chart"
    chart_dir.mkdir()

    script_file = tmp_path / "setup.sh"
    script_file.write_text("echo 'init'")

    config = ChartConfig(
        name="my-chart",
        namespace="default",
        chart=str(chart_dir),
        repo=None,
        version=None,
        values=[],
        release=None,
        init=script_file,
    )

    output_dir = tmp_path / "output"
    charts_dir = tmp_path / "charts"

    deployment_yaml = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  template:
    spec:
      containers:
      - name: app
        image: myapp:1.0
"""

    images = {"alpine_image": "alpine:3.21"}

    with (
        mock.patch(
            "helm.pull_chart",
            return_value=chart_dir,
        ),
        mock.patch(
            "helm.run_helm_template",
            return_value=deployment_yaml,
        ),
    ):
        _generate_helm_manifests(config, output_dir, charts_dir, images=images)

    deployment_file = output_dir / "default" / "deployment-my-app.yaml"
    doc = yaml.safe_load(deployment_file.read_text())
    init_containers = doc["spec"]["template"]["spec"]["initContainers"]
    assert "volumeMounts" not in init_containers[0]


def test_generate_helm_manifests_no_init(tmp_path: Path) -> None:
    """Without init configured, Deployment should not have initContainers."""
    chart_dir = tmp_path / "chart"
    chart_dir.mkdir()

    config = ChartConfig(
        name="my-chart",
        namespace="default",
        chart=str(chart_dir),
        repo=None,
        version=None,
        values=[],
        release=None,
        init=None,  # no init script
    )

    output_dir = tmp_path / "output"
    charts_dir = tmp_path / "charts"

    deployment_yaml = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  template:
    spec:
      containers:
      - name: app
        image: myapp:1.0
"""

    with (
        mock.patch(
            "helm.pull_chart",
            return_value=chart_dir,
        ),
        mock.patch(
            "helm.run_helm_template",
            return_value=deployment_yaml,
        ),
    ):
        _generate_helm_manifests(config, output_dir, charts_dir)

    deployment_file = output_dir / "default" / "deployment-my-app.yaml"
    doc = yaml.safe_load(deployment_file.read_text())
    assert "initContainers" not in doc["spec"]["template"]["spec"]


def test_generate_helm_manifests_emits_configmap_without_mounts(
    tmp_path: Path,
) -> None:
    """Helm config files should create a ConfigMap and annotate workloads."""
    chart_dir = tmp_path / "chart"
    chart_dir.mkdir()
    config_file = tmp_path / "app.conf"
    config_file.write_text("[app]\ndebug = true\n")

    config = ChartConfig(
        name="my-chart",
        namespace="default",
        chart=str(chart_dir),
        repo=None,
        version=None,
        values=[],
        release=None,
        config={"app.conf": config_file},
    )

    output_dir = tmp_path / "output"
    charts_dir = tmp_path / "charts"
    deployment_yaml = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  template:
    metadata:
      annotations:
        existing: annotation
    spec:
      containers:
      - name: app
        image: myapp:1.0
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: my-stateful-app
spec:
  template:
    spec:
      containers:
      - name: app
        image: myapp:1.0
"""

    with mock.patch(
        "helm.run_helm_template",
        return_value=deployment_yaml,
    ):
        paths = _generate_helm_manifests(config, output_dir, charts_dir)

    deployment_file = output_dir / "default" / "deployment-my-app.yaml"
    statefulset_file = output_dir / "default" / "statefulset-my-stateful-app.yaml"
    configmap_file = output_dir / "default" / "configmap-my-chart-config.yaml"

    assert paths == {deployment_file, statefulset_file, configmap_file}

    configmap = yaml.safe_load(configmap_file.read_text())
    assert configmap["kind"] == "ConfigMap"
    assert configmap["metadata"]["name"] == "my-chart-config"
    assert configmap["metadata"]["namespace"] == "default"
    assert configmap["data"] == {"app.conf": "[app]\ndebug = true\n"}

    deployment = yaml.safe_load(deployment_file.read_text())
    deployment_annotations = deployment["spec"]["template"]["metadata"]["annotations"]
    assert deployment_annotations["existing"] == "annotation"
    assert len(deployment_annotations["checksum/config"]) == 64
    pod_spec = deployment["spec"]["template"]["spec"]
    assert "volumes" not in pod_spec
    assert "volumeMounts" not in pod_spec["containers"][0]

    statefulset = yaml.safe_load(statefulset_file.read_text())
    statefulset_annotations = statefulset["spec"]["template"]["metadata"]["annotations"]
    assert (
        statefulset_annotations["checksum/config"]
        == deployment_annotations["checksum/config"]
    )


def test_generate_helm_manifests_injects_custom_token_audiences(
    tmp_path: Path,
) -> None:
    chart_dir = tmp_path / "chart"
    chart_dir.mkdir()
    config = ChartConfig(
        name="my-chart",
        namespace="default",
        chart=str(chart_dir),
        repo=None,
        version=None,
        values=[],
        release=None,
        custom_token_audiences=["vault", "api"],
    )
    deployment_yaml = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  template:
    spec:
      containers:
      - name: app
        image: myapp:1.0
      - name: sidecar
        image: sidecar:1.0
"""

    with mock.patch(
        "helm.run_helm_template",
        return_value=deployment_yaml,
    ):
        _generate_helm_manifests(config, tmp_path / "output", tmp_path / "charts")

    deployment = yaml.safe_load(
        (tmp_path / "output/default/deployment-my-app.yaml").read_text()
    )
    pod_spec = deployment["spec"]["template"]["spec"]
    assert pod_spec["volumes"] == [
        {
            "name": "tokens",
            "projected": {
                "sources": [
                    {
                        "serviceAccountToken": {
                            "path": "vault",
                            "expirationSeconds": 3600,
                            "audience": "vault",
                        }
                    },
                    {
                        "serviceAccountToken": {
                            "path": "api",
                            "expirationSeconds": 3600,
                            "audience": "api",
                        }
                    },
                ]
            },
        }
    ]
    expected_mount = {
        "name": "tokens",
        "mountPath": "/var/run/secrets/tokens",
        "readOnly": True,
    }
    assert all(
        container["volumeMounts"] == [expected_mount]
        for container in pod_spec["containers"]
    )


@pytest.mark.parametrize(
    ("rendered_yaml", "deployment_count"),
    [
        (
            """\
apiVersion: v1
kind: Service
metadata:
  name: my-service
""",
            0,
        ),
        (
            """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: first
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: second
""",
            2,
        ),
    ],
)
def test_generate_helm_custom_token_audiences_requires_one_deployment(
    tmp_path: Path, rendered_yaml: str, deployment_count: int
) -> None:
    chart_dir = tmp_path / "chart"
    chart_dir.mkdir()
    config = ChartConfig(
        name="my-chart",
        namespace="default",
        chart=str(chart_dir),
        repo=None,
        version=None,
        values=[],
        release=None,
        custom_token_audiences=["vault"],
    )

    with (
        mock.patch(
            "helm.run_helm_template",
            return_value=rendered_yaml,
        ),
        pytest.raises(
            ValueError,
            match=(
                "Custom token audience injection for Helm chart 'my-chart' "
                f"requires exactly one Deployment, found {deployment_count}"
            ),
        ),
    ):
        _generate_helm_manifests(config, tmp_path / "output", tmp_path / "charts")


def test_name_overrides_avoid_helm_configmap_collisions(tmp_path: Path) -> None:
    """Name overrides should distinguish ConfigMaps for a shared Helmfile release."""
    chart_dir = tmp_path / "chart"
    chart_dir.mkdir()
    first_config_file = tmp_path / "first.conf"
    first_config_file.write_text("instance = first\n")
    second_config_file = tmp_path / "second.conf"
    second_config_file.write_text("instance = second\n")
    configs = [
        ChartConfig(
            name="shared-release",
            namespace="default",
            chart=str(chart_dir),
            repo=None,
            version=None,
            values=[],
            release="shared-release",
            config={"app.conf": first_config_file},
            name_override="first-release",
        ),
        ChartConfig(
            name="shared-release",
            namespace="default",
            chart=str(chart_dir),
            repo=None,
            version=None,
            values=[],
            release="shared-release",
            config={"app.conf": second_config_file},
            name_override="second-release",
        ),
    ]
    output_dir = tmp_path / "output"

    with mock.patch("helm.run_helm_template", return_value=""):
        paths = generate_manifests(
            [HelmBlock(configs)],
            output_dir,
            repo_root=tmp_path,
            charts_dir=tmp_path / "charts",
        )

    first_path = output_dir / "default" / "configmap-first-release-config.yaml"
    second_path = output_dir / "default" / "configmap-second-release-config.yaml"
    assert first_path in paths
    assert second_path in paths
    assert yaml.safe_load(first_path.read_text())["data"] == {
        "app.conf": "instance = first\n"
    }
    assert yaml.safe_load(second_path.read_text())["data"] == {
        "app.conf": "instance = second\n"
    }


def test_generate_helm_manifests_config_checksum_changes_with_content(
    tmp_path: Path,
) -> None:
    """Changing Helm config content should produce a different checksum."""
    chart_dir = tmp_path / "chart"
    chart_dir.mkdir()
    config_file = tmp_path / "app.conf"
    config_file.write_text("debug = true\n")
    config = ChartConfig(
        name="my-chart",
        namespace="default",
        chart=str(chart_dir),
        repo=None,
        version=None,
        values=[],
        release=None,
        config={"app.conf": config_file},
    )
    deployment_yaml = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  template:
    spec:
      containers: []
"""

    with mock.patch(
        "helm.run_helm_template",
        return_value=deployment_yaml,
    ):
        _generate_helm_manifests(config, tmp_path / "first", tmp_path / "charts")
        config_file.write_text("debug = false\n")
        _generate_helm_manifests(config, tmp_path / "second", tmp_path / "charts")

    first = yaml.safe_load(
        (tmp_path / "first/default/deployment-my-app.yaml").read_text()
    )
    second = yaml.safe_load(
        (tmp_path / "second/default/deployment-my-app.yaml").read_text()
    )
    first_checksum = first["spec"]["template"]["metadata"]["annotations"][
        "checksum/config"
    ]
    second_checksum = second["spec"]["template"]["metadata"]["annotations"][
        "checksum/config"
    ]
    assert first_checksum != second_checksum


def test_generate_helm_manifests_renders_values_files_with_variables(
    tmp_path: Path,
) -> None:
    """Helm values files should be rendered with config variables before templating."""
    chart_dir = tmp_path / "chart"
    chart_dir.mkdir()
    values_file = tmp_path / "values.yaml"
    values_file.write_text("hostname: {{domain}}\nreplicas: {{replicas}}\n")

    config = ChartConfig(
        name="my-chart",
        namespace="default",
        chart=str(chart_dir),
        repo=None,
        version=None,
        values=[values_file],
        variables={"domain": "example.com", "replicas": 2},
        release=None,
    )

    output_dir = tmp_path / "output"
    charts_dir = tmp_path / "charts"
    captured_values: dict[str, str] = {}

    def fake_run_helm_template(
        release_name: str,
        chart: str,
        namespace: str,
        values_files: list[Path],
        version: str | None = None,
    ) -> str:
        del release_name, chart, namespace, version
        captured_values["content"] = values_files[0].read_text()
        return ""

    with mock.patch(
        "helm.run_helm_template",
        side_effect=fake_run_helm_template,
    ):
        paths = _generate_helm_manifests(config, output_dir, charts_dir)

    assert paths == set()
    assert captured_values["content"] == "hostname: example.com\nreplicas: 2\n"


def test_generate_helm_manifests_raises_on_missing_variable_in_values_file(
    tmp_path: Path,
) -> None:
    """Rendering values files should fail when a referenced variable is missing."""
    chart_dir = tmp_path / "chart"
    chart_dir.mkdir()
    values_file = tmp_path / "values.yaml"
    values_file.write_text("hostname: {{domain}}\n")

    config = ChartConfig(
        name="my-chart",
        namespace="default",
        chart=str(chart_dir),
        repo=None,
        version=None,
        values=[values_file],
        release=None,
    )

    output_dir = tmp_path / "output"
    charts_dir = tmp_path / "charts"

    with pytest.raises(KeyNotFoundError):
        _generate_helm_manifests(config, output_dir, charts_dir)


def test_generate_helm_manifests_renders_extra_resources_with_variables(
    tmp_path: Path,
) -> None:
    """Extra resource manifests should be rendered with config variables before parsing."""
    chart_dir = tmp_path / "chart"
    chart_dir.mkdir()
    extra_dir = tmp_path / "extra"
    extra_dir.mkdir()
    (extra_dir / "configmap.yaml").write_text(
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: my-config\n"
        "data:\n  domain: {{domain}}\n"
    )

    config = ChartConfig(
        name="my-chart",
        namespace="default",
        chart=str(chart_dir),
        repo=None,
        version=None,
        values=[],
        variables={"domain": "example.com"},
        release=None,
        extra_resources=extra_dir,
    )

    output_dir = tmp_path / "output"
    charts_dir = tmp_path / "charts"

    with mock.patch(
        "helm.run_helm_template",
        return_value="",
    ):
        _generate_helm_manifests(config, output_dir, charts_dir)

    written = list(output_dir.rglob("*.yaml"))
    assert len(written) == 1
    content = written[0].read_text()
    assert "example.com" in content
    assert "{{domain}}" not in content
