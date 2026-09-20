# SPDX-License-Identifier: MIT
"""Tests for the [[simple]] config block."""

import textwrap
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml
from manifest_builder.blocks import ConfigBlock
from manifest_builder.config import ManifestConfig, load_configs
from manifest_builder.generator import generate_manifests
from pystache.context import KeyNotFoundError

from simple import SimpleBlock, SimpleConfig, generate_simple


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
    """This directory's simple block, loaded the way a real run loads it."""
    return [SimpleBlock()]


def load_test_configs(config_dir: Path) -> Sequence[ConfigBlock]:
    return load_configs(config_dir, config_blocks())


def manifest_configs(
    *,
    simples: list[SimpleConfig] | None = None,
) -> list[ConfigBlock[Any]]:
    return [SimpleBlock(simples)]


def _read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def test_load_simple_config(tmp_path: Path) -> None:
    """Simple config can omit name and use namespace as the generated name."""
    conf = tmp_path / "conf"
    conf.mkdir()
    (conf / "idcat").mkdir()
    (conf / "idcat" / "myconfig.toml").write_text("[idcat]\nenabled = true\n")
    write_toml(
        conf,
        "config.toml",
        """\
        [[simple]]
        namespace = "idcat"
        image = "example.com/idcat:1.0"

        [[simple.config]]
        "/config/myconfig.toml" = "idcat/myconfig.toml"
        """,
    )

    configs = load_test_configs(conf)
    config = only_config(configs)
    assert isinstance(config, SimpleConfig)
    assert config.name == "idcat"
    assert config.namespace == "idcat"
    assert config.image == "example.com/idcat:1.0"
    assert config.config == {"/config/myconfig.toml": conf / "idcat" / "myconfig.toml"}


def test_load_simple_config_uses_default_namespace(tmp_path: Path) -> None:
    """Simple config can get its namespace from namespace-owner mode."""
    conf = tmp_path / "conf"
    conf.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [[simple]]
        image = "example.com/idcat:1.0"
        """,
    )

    configs = load_configs(conf, config_blocks(), default_namespace="idcat")
    config = only_config(configs)
    assert isinstance(config, SimpleConfig)
    assert config.name == "idcat"
    assert config.namespace == "idcat"


def test_load_simple_config_uses_default_image(tmp_path: Path) -> None:
    """Simple config can get its image from namespace-mode API input."""
    conf = tmp_path / "conf"
    conf.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [[simple]]
        """,
    )

    configs = load_configs(
        conf,
        config_blocks(),
        default_namespace="idcat",
        default_image="example.com/idcat:1.0",
    )
    config = only_config(configs)
    assert isinstance(config, SimpleConfig)
    assert config.namespace == "idcat"
    assert config.image == "example.com/idcat:1.0"


def test_load_simple_config_rejects_image_with_default_image(tmp_path: Path) -> None:
    """Config image and API image override are mutually exclusive."""
    conf = tmp_path / "conf"
    conf.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [[simple]]
        image = "example.com/idcat:1.0"
        """,
    )

    with pytest.raises(ValueError, match="Cannot specify 'image'.*generate"):
        load_configs(
            conf,
            config_blocks(),
            default_namespace="idcat",
            default_image="example.com/override:1.0",
        )


def test_load_simple_config_with_extra_resources(tmp_path: Path) -> None:
    """Simple config can specify a directory with extra YAML resources."""
    conf = tmp_path / "conf"
    conf.mkdir()
    resources_dir = conf / "resources"
    resources_dir.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [[simple]]
        namespace = "idcat"
        image = "example.com/idcat:1.0"
        extra-resources = "resources"
        """,
    )

    configs = load_test_configs(conf)
    config = only_config(configs)
    assert isinstance(config, SimpleConfig)
    assert config.extra_resources == resources_dir


def test_load_simple_config_with_iam_role_and_variables(tmp_path: Path) -> None:
    """Simple iam-role is parsed with the variables used during rendering."""
    conf = tmp_path / "conf"
    conf.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [variables]
        account_id = "123456789012"
        cluster_name = "berries"

        [[simple]]
        namespace = "idcat"
        image = "example.com/idcat:1.0"
        iam-role = "arn:aws:iam::{{account_id}}:role/{{cluster_name}}-idcat"
        """,
    )

    configs = load_test_configs(conf)
    config = only_config(configs)
    assert isinstance(config, SimpleConfig)
    assert config.iam_role == "arn:aws:iam::{{account_id}}:role/{{cluster_name}}-idcat"
    assert config.variables == {
        "account_id": "123456789012",
        "cluster_name": "berries",
    }


def test_load_simple_config_with_k8s_role(tmp_path: Path) -> None:
    """Simple config can specify a Kubernetes Role to bind to its ServiceAccount."""
    conf = tmp_path / "conf"
    conf.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [[simple]]
        namespace = "idcat"
        image = "example.com/idcat:1.0"
        k8s-role = "idcat-reader"
        """,
    )

    configs = load_test_configs(conf)
    config = only_config(configs)
    assert isinstance(config, SimpleConfig)
    assert config.k8s_role == "idcat-reader"


def test_load_simple_config_with_service_account_annotations(tmp_path: Path) -> None:
    """Simple config can specify a table of ServiceAccount annotations."""
    conf = tmp_path / "conf"
    conf.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [[simple]]
        namespace = "idcat"
        image = "example.com/idcat:1.0"

        [simple.service-account-annotations]
        "example.com/owner" = "platform"
        "example.com/team" = "berries"
        """,
    )

    configs = load_test_configs(conf)
    config = only_config(configs)
    assert isinstance(config, SimpleConfig)
    assert config.service_account_annotations == {
        "example.com/owner": "platform",
        "example.com/team": "berries",
    }


def test_load_simple_config_service_account_annotations_must_be_strings(
    tmp_path: Path,
) -> None:
    """Non-string annotation values are rejected."""
    conf = tmp_path / "conf"
    conf.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [[simple]]
        namespace = "idcat"
        image = "example.com/idcat:1.0"

        [simple.service-account-annotations]
        "example.com/replicas" = 3
        """,
    )

    with pytest.raises(
        ValueError, match=r"'service-account-annotations' must be a table"
    ):
        load_test_configs(conf)


def test_load_simple_config_rejects_role_arn_annotation_with_iam_role(
    tmp_path: Path,
) -> None:
    """Setting the role-arn annotation and iam-role together fails clearly."""
    conf = tmp_path / "conf"
    conf.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [[simple]]
        namespace = "idcat"
        image = "example.com/idcat:1.0"
        iam-role = "arn:aws:iam::123456789012:role/berries-idcat"

        [simple.service-account-annotations]
        "eks.amazonaws.com/role-arn" = "arn:aws:iam::123456789012:role/other"
        """,
    )

    with pytest.raises(
        ValueError,
        match=r"cannot set 'eks\.amazonaws\.com/role-arn' when 'iam-role'",
    ):
        load_test_configs(conf)


def test_load_simple_config_with_arch(tmp_path: Path) -> None:
    """Simple config can declare a node architecture for the Pod nodeSelector."""
    conf = tmp_path / "conf"
    conf.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [[simple]]
        namespace = "idcat"
        image = "example.com/idcat:1.0"
        arch = "arm64"
        """,
    )

    configs = load_test_configs(conf)
    config = only_config(configs)
    assert isinstance(config, SimpleConfig)
    assert config.arch == "arm64"


def test_load_simple_config_with_args(tmp_path: Path) -> None:
    """Simple config accepts an ordered list of container arguments."""
    conf = tmp_path / "conf"
    conf.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [[simple]]
        namespace = "idcat"
        image = "example.com/idcat:1.0"
        args = ["serve", "--port=8080"]
        """,
    )

    configs = load_test_configs(conf)
    config = only_config(configs)
    assert isinstance(config, SimpleConfig)
    assert config.args == ["serve", "--port=8080"]


def test_load_simple_config_args_must_be_list_of_strings(tmp_path: Path) -> None:
    """Simple args reject scalar values instead of changing their meaning."""
    conf = tmp_path / "conf"
    conf.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [[simple]]
        namespace = "idcat"
        image = "example.com/idcat:1.0"
        args = "serve"
        """,
    )

    with pytest.raises(ValueError, match="'args' must be a list of strings"):
        load_test_configs(conf)


def test_load_simple_config_with_custom_token_audiences(tmp_path: Path) -> None:
    """Simple config can specify custom audiences for projected tokens."""
    conf = tmp_path / "conf"
    conf.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [[simple]]
        namespace = "idcat"
        image = "example.com/idcat:1.0"
        custom-token-audiences = ["vault", "api"]
        """,
    )

    configs = load_test_configs(conf)
    config = only_config(configs)
    assert isinstance(config, SimpleConfig)
    assert config.custom_token_audiences == ["vault", "api"]


def test_load_simple_config_custom_token_audiences_must_be_list(
    tmp_path: Path,
) -> None:
    """Simple custom token audiences must be configured as a string list."""
    conf = tmp_path / "conf"
    conf.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [[simple]]
        namespace = "idcat"
        image = "example.com/idcat:1.0"
        custom-token-audiences = "vault"
        """,
    )

    with pytest.raises(
        ValueError,
        match="'custom-token-audiences' must be a list of strings",
    ):
        load_test_configs(conf)


def test_load_simple_config_arch_must_be_string(tmp_path: Path) -> None:
    conf = tmp_path / "conf"
    conf.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [[simple]]
        namespace = "idcat"
        image = "example.com/idcat:1.0"
        arch = 64
        """,
    )

    with pytest.raises(ValueError, match="'arch' must be a string"):
        load_test_configs(conf)


def test_load_simple_config_with_external_secrets(tmp_path: Path) -> None:
    """An external-secrets list is preserved in order."""
    conf = tmp_path / "conf"
    conf.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [[simple]]
        namespace = "idcat"
        image = "example.com/idcat:1.0"
        external-secrets = ["/email-password", "/db/credentials"]
        """,
    )

    configs = load_test_configs(conf)
    config = only_config(configs)
    assert isinstance(config, SimpleConfig)
    assert config.external_secrets == ["/email-password", "/db/credentials"]


def test_load_simple_config_with_external_secrets_string(tmp_path: Path) -> None:
    """A single external secret is normalized into a one-element list."""
    conf = tmp_path / "conf"
    conf.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [[simple]]
        namespace = "idcat"
        image = "example.com/idcat:1.0"
        external-secrets = "/api-key"
        """,
    )

    configs = load_test_configs(conf)
    config = only_config(configs)
    assert isinstance(config, SimpleConfig)
    assert config.external_secrets == ["/api-key"]


def test_load_simple_config_with_external_secret(tmp_path: Path) -> None:
    """A singular external-secret is normalized to a one-element list."""
    conf = tmp_path / "conf"
    conf.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [[simple]]
        namespace = "idcat"
        image = "example.com/idcat:1.0"
        external-secret = "/api-key"
        """,
    )

    configs = load_test_configs(conf)
    config = only_config(configs)
    assert isinstance(config, SimpleConfig)
    assert config.external_secrets == ["/api-key"]


def test_load_simple_config_rejects_both_external_secret_forms(
    tmp_path: Path,
) -> None:
    """The singular and plural external secret fields are mutually exclusive."""
    conf = tmp_path / "conf"
    conf.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [[simple]]
        namespace = "idcat"
        image = "example.com/idcat:1.0"
        external-secret = "/api-key"
        external-secrets = ["/email-password"]
        """,
    )

    with pytest.raises(
        ValueError,
        match="Cannot specify both 'external-secret' and 'external-secrets'",
    ):
        load_test_configs(conf)


def test_load_simple_config_external_secret_must_be_string(tmp_path: Path) -> None:
    """The singular external-secret field only accepts a string."""
    conf = tmp_path / "conf"
    conf.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [[simple]]
        namespace = "idcat"
        image = "example.com/idcat:1.0"
        external-secret = ["/api-key"]
        """,
    )

    with pytest.raises(ValueError, match="'external-secret' must be a string"):
        load_test_configs(conf)


def test_load_simple_config_external_secrets_must_be_strings(tmp_path: Path) -> None:
    """external-secrets must be a string or list of strings."""
    conf = tmp_path / "conf"
    conf.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [[simple]]
        namespace = "idcat"
        image = "example.com/idcat:1.0"
        external-secrets = [1]
        """,
    )

    with pytest.raises(
        ValueError,
        match="'external-secrets' must be a string or list of strings",
    ):
        load_test_configs(conf)


def test_load_simple_config_with_random_secret(tmp_path: Path) -> None:
    """A single random-secret is normalized into a one-element list."""
    conf = tmp_path / "conf"
    conf.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [[simple]]
        namespace = "idcat"
        image = "example.com/idcat:1.0"
        random-secret = "SESSION_KEY"
        """,
    )

    configs = load_test_configs(conf)
    config = only_config(configs)
    assert isinstance(config, SimpleConfig)
    assert config.random_secrets == ["SESSION_KEY"]


def test_load_simple_config_with_random_secrets_list(tmp_path: Path) -> None:
    """A random-secrets list is preserved in order."""
    conf = tmp_path / "conf"
    conf.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [[simple]]
        namespace = "idcat"
        image = "example.com/idcat:1.0"
        random-secrets = ["API_KEY", "SIGNING_KEY"]
        """,
    )

    configs = load_test_configs(conf)
    config = only_config(configs)
    assert isinstance(config, SimpleConfig)
    assert config.random_secrets == ["API_KEY", "SIGNING_KEY"]


def test_load_simple_config_rejects_both_random_secret_forms(tmp_path: Path) -> None:
    """Specifying both random-secret and random-secrets is an error."""
    conf = tmp_path / "conf"
    conf.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [[simple]]
        namespace = "idcat"
        image = "example.com/idcat:1.0"
        random-secret = "SESSION_KEY"
        random-secrets = ["API_KEY"]
        """,
    )

    with pytest.raises(
        ValueError,
        match="Cannot specify both 'random-secret' and 'random-secrets'",
    ):
        load_test_configs(conf)


def test_load_simple_config_random_secrets_must_be_list_of_strings(
    tmp_path: Path,
) -> None:
    """random-secrets must be a list of strings."""
    conf = tmp_path / "conf"
    conf.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [[simple]]
        namespace = "idcat"
        image = "example.com/idcat:1.0"
        random-secrets = "API_KEY"
        """,
    )

    with pytest.raises(
        ValueError,
        match="'random-secrets' must be a list of strings",
    ):
        load_test_configs(conf)


def test_load_simple_config_unknown_field_raises(tmp_path: Path) -> None:
    """Unknown simple fields should fail before generation."""
    conf = tmp_path / "conf"
    conf.mkdir()
    write_toml(
        conf,
        "config.toml",
        """\
        [[simple]]
        namespace = "idcat"
        image = "example.com/idcat:1.0"
        iam_role = "typo"
        """,
    )

    with pytest.raises(
        ValueError,
        match=r"Unknown field in \[\[simple\]\]: 'iam_role' on line 4",
    ):
        load_test_configs(conf)


def test_validate_config_simple_extra_resources_missing_directory(
    tmp_path: Path,
) -> None:
    """Validation should fail if simple extra_resources directory doesn't exist."""
    config = SimpleConfig(
        name="idcat",
        namespace="idcat",
        image="example.com/idcat:1.0",
        extra_resources=tmp_path / "nonexistent",
    )
    with pytest.raises(ValueError, match="Extra resources directory not found"):
        SimpleBlock().validate(config, tmp_path)


def test_validate_config_simple_extra_resources_not_a_directory(tmp_path: Path) -> None:
    """Validation should fail if simple extra_resources path is not a directory."""
    not_a_dir = tmp_path / "file.txt"
    not_a_dir.write_text("content")

    config = SimpleConfig(
        name="idcat",
        namespace="idcat",
        image="example.com/idcat:1.0",
        extra_resources=not_a_dir,
    )
    with pytest.raises(ValueError, match="Extra resources path is not a directory"):
        SimpleBlock().validate(config, tmp_path)


def _read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def test_generate_simple_writes_deployment_from_bundled_template(
    tmp_path: Path,
) -> None:
    """Simple generation creates a Deployment and ClusterIP Service."""
    config = SimpleConfig(
        name="idcat",
        namespace="idcat",
        image="registry.example.com/idcat:1.0",
    )

    paths = generate_simple(config, tmp_path / "output")

    assert {path.name for path in paths} == {
        "deployment-idcat.yaml",
        "service-idcat.yaml",
    }
    deployment = _read_yaml(tmp_path / "output" / "idcat" / "deployment-idcat.yaml")
    assert deployment["kind"] == "Deployment"
    assert deployment["metadata"]["name"] == "idcat"
    assert deployment["metadata"]["namespace"] == "idcat"
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == "registry.example.com/idcat:1.0"
    assert container["ports"] == [{"name": "http", "containerPort": 8080}]
    assert "args" not in container

    service = _read_yaml(tmp_path / "output" / "idcat" / "service-idcat.yaml")
    assert service["kind"] == "Service"
    assert service["metadata"]["name"] == "idcat"
    assert service["metadata"]["namespace"] == "idcat"
    assert service["spec"]["type"] == "ClusterIP"
    assert service["spec"]["selector"] == {"app": "idcat"}
    assert service["spec"]["ports"] == [
        {"name": "http", "port": 80, "targetPort": "http"}
    ]


def test_generate_simple_propagates_args_to_deployment(tmp_path: Path) -> None:
    """Configured args are preserved as strings in the container spec."""
    config = SimpleConfig(
        name="idcat",
        namespace="idcat",
        image="registry.example.com/idcat:1.0",
        args=["serve", "--port=8080", "true", "key: value"],
    )

    generate_simple(config, tmp_path / "output")

    deployment = _read_yaml(tmp_path / "output" / "idcat" / "deployment-idcat.yaml")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["args"] == ["serve", "--port=8080", "true", "key: value"]


def test_generate_simple_writes_configmap_when_config_is_specified(
    tmp_path: Path,
) -> None:
    """Config entries create ConfigMaps and mount them in the Deployment."""
    config_file = tmp_path / "myconfig.toml"
    config_file.write_text("[idcat]\nenabled = true\n")
    config = SimpleConfig(
        name="idcat",
        namespace="idcat",
        image="registry.example.com/idcat:1.0",
        config={"/config/myconfig.toml": config_file},
    )

    paths = generate_simple(config, tmp_path / "output")

    assert {path.name for path in paths} == {
        "deployment-idcat.yaml",
        "service-idcat.yaml",
        "configmap-idcat-config.yaml",
    }
    assert not any(
        path.name.startswith(("certificate-", "gateway-", "httproute-"))
        for path in paths
    )

    configmap = _read_yaml(
        tmp_path / "output" / "idcat" / "configmap-idcat-config.yaml"
    )
    assert configmap["kind"] == "ConfigMap"
    assert configmap["metadata"]["name"] == "idcat-config"
    assert configmap["metadata"]["namespace"] == "idcat"
    assert configmap["data"]["myconfig.toml"] == "[idcat]\nenabled = true\n"

    deployment = _read_yaml(tmp_path / "output" / "idcat" / "deployment-idcat.yaml")
    pod_template = deployment["spec"]["template"]
    assert "checksum/config" in pod_template["metadata"]["annotations"]
    pod_spec = pod_template["spec"]
    assert pod_spec["volumes"] == [
        {"name": "idcat-config", "configMap": {"name": "idcat-config"}}
    ]
    assert pod_spec["containers"][0]["volumeMounts"] == [
        {"name": "idcat-config", "mountPath": "/config"}
    ]


def test_generate_simple_renders_config_file_with_variables(
    tmp_path: Path,
) -> None:
    """Config files are rendered with the simple template context."""
    config_file = tmp_path / "myconfig.toml"
    config_file.write_text('[idcat]\ndomain = "{{domain}}"\nreplicas = {{replicas}}\n')
    config = SimpleConfig(
        name="idcat",
        namespace="idcat",
        image="registry.example.com/idcat:1.0",
        config={"/config/myconfig.toml": config_file},
        variables={"domain": "example.com"},
        replicas=3,
    )

    generate_simple(config, tmp_path / "output")

    configmap = _read_yaml(
        tmp_path / "output" / "idcat" / "configmap-idcat-config.yaml"
    )
    assert configmap["data"]["myconfig.toml"] == (
        '[idcat]\ndomain = "example.com"\nreplicas = 3\n'
    )


def test_generate_simple_config_file_missing_variable_raises(
    tmp_path: Path,
) -> None:
    """Missing variables in rendered config files fail instead of being blank."""
    config_file = tmp_path / "myconfig.toml"
    config_file.write_text('[idcat]\ndomain = "{{domain}}"\n')
    config = SimpleConfig(
        name="idcat",
        namespace="idcat",
        image="registry.example.com/idcat:1.0",
        config={"/config/myconfig.toml": config_file},
    )

    with pytest.raises(KeyNotFoundError):
        generate_simple(config, tmp_path / "output")


def test_generate_simple_writes_serviceaccount_when_iam_role_is_specified(
    tmp_path: Path,
) -> None:
    """iam_role creates a ServiceAccount and references it from the Deployment."""
    config = SimpleConfig(
        name="idcat",
        namespace="idcat",
        image="registry.example.com/idcat:1.0",
        iam_role=("arn:aws:iam::{{account_id}}:role/{{cluster_name}}-idcat"),
        variables={"account_id": "123456789012", "cluster_name": "berries"},
    )

    paths = generate_simple(config, tmp_path / "output")

    assert {path.name for path in paths} == {
        "deployment-idcat.yaml",
        "service-idcat.yaml",
        "serviceaccount-idcat.yaml",
    }

    serviceaccount = _read_yaml(
        tmp_path / "output" / "idcat" / "serviceaccount-idcat.yaml"
    )
    assert serviceaccount["kind"] == "ServiceAccount"
    assert serviceaccount["metadata"]["name"] == "idcat"
    assert serviceaccount["metadata"]["namespace"] == "idcat"
    assert serviceaccount["metadata"]["annotations"] == {
        "eks.amazonaws.com/role-arn": ("arn:aws:iam::123456789012:role/berries-idcat")
    }

    deployment = _read_yaml(tmp_path / "output" / "idcat" / "deployment-idcat.yaml")
    assert deployment["spec"]["template"]["spec"]["serviceAccountName"] == "idcat"


def test_generate_simple_writes_serviceaccount_annotations(
    tmp_path: Path,
) -> None:
    """service_account_annotations create a ServiceAccount with those annotations."""
    config = SimpleConfig(
        name="idcat",
        namespace="idcat",
        image="registry.example.com/idcat:1.0",
        service_account_annotations={
            "example.com/owner": "platform",
            "example.com/team": "{{team}}",
        },
        variables={"team": "berries"},
    )

    paths = generate_simple(config, tmp_path / "output")

    assert {path.name for path in paths} == {
        "deployment-idcat.yaml",
        "service-idcat.yaml",
        "serviceaccount-idcat.yaml",
    }

    serviceaccount = _read_yaml(
        tmp_path / "output" / "idcat" / "serviceaccount-idcat.yaml"
    )
    assert serviceaccount["kind"] == "ServiceAccount"
    assert serviceaccount["metadata"]["name"] == "idcat"
    assert serviceaccount["metadata"]["namespace"] == "idcat"
    assert serviceaccount["metadata"]["annotations"] == {
        "example.com/owner": "platform",
        "example.com/team": "berries",
    }

    deployment = _read_yaml(tmp_path / "output" / "idcat" / "deployment-idcat.yaml")
    assert deployment["spec"]["template"]["spec"]["serviceAccountName"] == "idcat"


def test_generate_simple_combines_iam_role_and_serviceaccount_annotations(
    tmp_path: Path,
) -> None:
    """iam_role and service_account_annotations merge into one annotations block."""
    config = SimpleConfig(
        name="idcat",
        namespace="idcat",
        image="registry.example.com/idcat:1.0",
        iam_role="arn:aws:iam::123456789012:role/berries-idcat",
        service_account_annotations={"example.com/owner": "platform"},
    )

    generate_simple(config, tmp_path / "output")

    serviceaccount = _read_yaml(
        tmp_path / "output" / "idcat" / "serviceaccount-idcat.yaml"
    )
    assert serviceaccount["metadata"]["annotations"] == {
        "eks.amazonaws.com/role-arn": "arn:aws:iam::123456789012:role/berries-idcat",
        "example.com/owner": "platform",
    }


def test_generate_simple_serviceaccount_annotation_values_are_quoted(
    tmp_path: Path,
) -> None:
    """Annotation values that look like non-strings stay strings in the output."""
    config = SimpleConfig(
        name="idcat",
        namespace="idcat",
        image="registry.example.com/idcat:1.0",
        service_account_annotations={"example.com/enabled": "true"},
    )

    generate_simple(config, tmp_path / "output")

    serviceaccount = _read_yaml(
        tmp_path / "output" / "idcat" / "serviceaccount-idcat.yaml"
    )
    assert serviceaccount["metadata"]["annotations"] == {"example.com/enabled": "true"}
    assert isinstance(
        serviceaccount["metadata"]["annotations"]["example.com/enabled"], str
    )


def test_generate_simple_writes_rolebinding_when_k8s_role_is_specified(
    tmp_path: Path,
) -> None:
    """k8s_role creates a ServiceAccount and binds it to the named Role."""
    config = SimpleConfig(
        name="idcat",
        namespace="idcat",
        image="registry.example.com/idcat:1.0",
        k8s_role="{{role_name}}",
        variables={"role_name": "idcat-reader"},
    )

    paths = generate_simple(config, tmp_path / "output")

    assert {path.name for path in paths} == {
        "deployment-idcat.yaml",
        "service-idcat.yaml",
        "serviceaccount-idcat.yaml",
        "rolebinding-idcat-idcat-reader.yaml",
    }

    serviceaccount = _read_yaml(
        tmp_path / "output" / "idcat" / "serviceaccount-idcat.yaml"
    )
    assert serviceaccount["kind"] == "ServiceAccount"
    assert serviceaccount["metadata"]["name"] == "idcat"
    assert serviceaccount["metadata"]["namespace"] == "idcat"
    assert "annotations" not in serviceaccount["metadata"]

    rolebinding = _read_yaml(
        tmp_path / "output" / "idcat" / "rolebinding-idcat-idcat-reader.yaml"
    )
    assert rolebinding["kind"] == "RoleBinding"
    assert rolebinding["metadata"]["name"] == "idcat-idcat-reader"
    assert rolebinding["metadata"]["namespace"] == "idcat"
    assert rolebinding["subjects"] == [
        {"kind": "ServiceAccount", "name": "idcat", "namespace": "idcat"}
    ]
    assert rolebinding["roleRef"] == {
        "apiGroup": "rbac.authorization.k8s.io",
        "kind": "Role",
        "name": "idcat-reader",
    }

    deployment = _read_yaml(tmp_path / "output" / "idcat" / "deployment-idcat.yaml")
    assert deployment["spec"]["template"]["spec"]["serviceAccountName"] == "idcat"


def test_generate_simple_renders_extra_resources_with_variables(
    tmp_path: Path,
) -> None:
    """Extra resource manifests are rendered and namespace defaults are applied."""
    extra_dir = tmp_path / "extra"
    extra_dir.mkdir()
    (extra_dir / "configmap.yaml").write_text(
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: {{k8s_name}}-settings\n"
        "data:\n  domain: {{domain}}\n"
    )
    (extra_dir / "storageclass.yaml").write_text(
        "apiVersion: storage.k8s.io/v1\nkind: StorageClass\nmetadata:\n"
        "  name: {{k8s_name}}-storage\nprovisioner: example.com/storage\n"
    )
    config = SimpleConfig(
        name="idcat",
        namespace="idcat",
        image="registry.example.com/idcat:1.0",
        variables={"domain": "example.com"},
        extra_resources=extra_dir,
    )

    paths = generate_simple(config, tmp_path / "output")

    assert "configmap-idcat-settings.yaml" in {path.name for path in paths}
    configmap = _read_yaml(
        tmp_path / "output" / "idcat" / "configmap-idcat-settings.yaml"
    )
    assert configmap["metadata"]["namespace"] == "idcat"
    assert configmap["data"]["domain"] == "example.com"

    storageclass = _read_yaml(
        tmp_path / "output" / "cluster" / "storageclass-idcat-storage.yaml"
    )
    assert storageclass["kind"] == "StorageClass"
    assert "namespace" not in storageclass["metadata"]


def test_generate_simple_sets_arch_node_selector(tmp_path: Path) -> None:
    """arch field renders kubernetes.io/arch nodeSelector in the Pod spec."""
    config = SimpleConfig(
        name="idcat",
        namespace="idcat",
        image="registry.example.com/idcat:1.0",
        arch="arm64",
    )

    generate_simple(config, tmp_path / "output")

    deployment = _read_yaml(tmp_path / "output" / "idcat" / "deployment-idcat.yaml")
    pod_spec = deployment["spec"]["template"]["spec"]
    assert pod_spec["nodeSelector"] == {"kubernetes.io/arch": "arm64"}


def test_generate_simple_omits_arch_node_selector_when_unset(tmp_path: Path) -> None:
    """Without arch, no nodeSelector is added to the Pod spec."""
    config = SimpleConfig(
        name="idcat",
        namespace="idcat",
        image="registry.example.com/idcat:1.0",
    )

    generate_simple(config, tmp_path / "output")

    deployment = _read_yaml(tmp_path / "output" / "idcat" / "deployment-idcat.yaml")
    assert "nodeSelector" not in deployment["spec"]["template"]["spec"]


def test_generate_simple_custom_token_audiences_inject_projected_tokens(
    tmp_path: Path,
) -> None:
    """Custom token audiences inject projected service account tokens."""
    config = SimpleConfig(
        name="idcat",
        namespace="idcat",
        image="registry.example.com/idcat:1.0",
        custom_token_audiences=["vault", "api"],
    )

    generate_simple(config, tmp_path / "output")

    deployment = _read_yaml(tmp_path / "output" / "idcat" / "deployment-idcat.yaml")
    pod_spec = deployment["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]
    assert container["volumeMounts"] == [
        {
            "name": "tokens",
            "mountPath": "/var/run/secrets/tokens",
            "readOnly": True,
        }
    ]
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


def test_generate_simple_external_secrets_injects_volumes_and_mounts(
    tmp_path: Path,
) -> None:
    """External secrets are mounted as Secret volumes named after the mount path."""
    config = SimpleConfig(
        name="idcat",
        namespace="idcat",
        image="registry.example.com/idcat:1.0",
        external_secrets=["/email-password", "/db/credentials"],
    )

    generate_simple(config, tmp_path / "output")

    deployment = _read_yaml(tmp_path / "output" / "idcat" / "deployment-idcat.yaml")
    pod_spec = deployment["spec"]["template"]["spec"]
    assert pod_spec["containers"][0]["volumeMounts"] == [
        {"name": "email-password", "mountPath": "/email-password"},
        {"name": "db-credentials", "mountPath": "/db/credentials"},
    ]
    assert pod_spec["volumes"] == [
        {"name": "email-password", "secret": {"secretName": "email-password"}},
        {"name": "db-credentials", "secret": {"secretName": "db-credentials"}},
    ]


def test_generate_simple_omits_external_secrets_when_unset(tmp_path: Path) -> None:
    """Without external secrets, no Secret volumes are produced."""
    config = SimpleConfig(
        name="idcat",
        namespace="idcat",
        image="registry.example.com/idcat:1.0",
    )

    generate_simple(config, tmp_path / "output")

    deployment = _read_yaml(tmp_path / "output" / "idcat" / "deployment-idcat.yaml")
    assert "volumes" not in deployment["spec"]["template"]["spec"]


def test_generate_simple_random_secret_emits_manifest_and_mount(
    tmp_path: Path,
) -> None:
    """A single random-secret emits a RandomSecret and mounts it at /random-secrets."""
    config = SimpleConfig(
        name="idcat",
        namespace="idcat",
        image="registry.example.com/idcat:1.0",
        random_secrets=["SESSION_KEY"],
    )

    paths = generate_simple(config, tmp_path / "output")

    assert "randomsecret-idcat.yaml" in {path.name for path in paths}
    random_secret = _read_yaml(
        tmp_path / "output" / "idcat" / "randomsecret-idcat.yaml"
    )
    assert random_secret["apiVersion"] == "noa.re/v1alpha1"
    assert random_secret["kind"] == "RandomSecret"
    assert random_secret["metadata"]["name"] == "idcat"
    assert random_secret["metadata"]["namespace"] == "idcat"
    assert random_secret["spec"]["secrets"] == [{"name": "SESSION_KEY"}]

    deployment = _read_yaml(tmp_path / "output" / "idcat" / "deployment-idcat.yaml")
    pod_spec = deployment["spec"]["template"]["spec"]
    assert pod_spec["containers"][0]["volumeMounts"] == [
        {"name": "random-secrets", "mountPath": "/random-secrets"}
    ]
    assert pod_spec["volumes"] == [
        {"name": "random-secrets", "secret": {"secretName": "idcat"}}
    ]


def test_generate_simple_random_secrets_list_enumerates_names(tmp_path: Path) -> None:
    """A random-secrets list enumerates each name into the RandomSecret spec."""
    config = SimpleConfig(
        name="idcat",
        namespace="idcat",
        image="registry.example.com/idcat:1.0",
        random_secrets=["API_KEY", "SIGNING_KEY"],
    )

    generate_simple(config, tmp_path / "output")

    random_secret = _read_yaml(
        tmp_path / "output" / "idcat" / "randomsecret-idcat.yaml"
    )
    assert random_secret["spec"]["secrets"] == [
        {"name": "API_KEY"},
        {"name": "SIGNING_KEY"},
    ]


def test_generate_simple_omits_random_secret_when_unset(tmp_path: Path) -> None:
    """Without random secrets, no RandomSecret or mount is produced."""
    config = SimpleConfig(
        name="idcat",
        namespace="idcat",
        image="registry.example.com/idcat:1.0",
    )

    paths = generate_simple(config, tmp_path / "output")

    assert not any(path.name.startswith("randomsecret-") for path in paths)
    deployment = _read_yaml(tmp_path / "output" / "idcat" / "deployment-idcat.yaml")
    assert "volumes" not in deployment["spec"]["template"]["spec"]


def test_generate_manifests_with_simple_config(tmp_path: Path) -> None:
    """generate_manifests dispatches to simple generation."""
    config = SimpleConfig(
        name="idcat",
        namespace="idcat",
        image="registry.example.com/idcat:1.0",
    )

    paths = generate_manifests(
        [SimpleBlock([config])],
        tmp_path / "output",
        repo_root=tmp_path,
    )

    assert {path.name for path in paths} == {
        "deployment-idcat.yaml",
        "service-idcat.yaml",
        "namespace-idcat.yaml",
    }
