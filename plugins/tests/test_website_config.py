# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: The manifest-builder contributors
"""Tests for website plugin configuration parsing and validation."""

import textwrap
from collections.abc import Sequence
from pathlib import Path

import pytest
from manifest_builder.blocks import ConfigBlock
from manifest_builder.config import (
    DEFAULT_REPLICA_COUNT,
    ManifestConfig,
    load_configs,
    resolve_configs,
)

from website import WebsiteBlock, WebsiteConfig


def write_toml(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    path.write_text(textwrap.dedent(content))
    return path


def all_configs(
    blocks: Sequence[ConfigBlock],
) -> tuple[ManifestConfig, ...]:
    return tuple(config for block in blocks for config in block.iter_configs())


def only_config(
    blocks: Sequence[ConfigBlock],
) -> ManifestConfig:
    (config,) = all_configs(blocks)
    return config


def config_blocks() -> list[WebsiteBlock]:
    return [WebsiteBlock()]


def load_test_configs(
    config_dir: Path,
) -> Sequence[ConfigBlock]:
    return load_configs(config_dir, config_blocks())


def manifest_configs(
    *,
    websites: list[WebsiteConfig] | None = None,
) -> list[WebsiteBlock]:
    return [WebsiteBlock(websites)]


# WebsiteConfig parsing
# ---------------------------------------------------------------------------


def test_load_website_config(tmp_path: Path) -> None:
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    write_toml(
        conf_dir,
        "config.toml",
        """\
        [[website]]
        name = "my-website"
        namespace = "production"
        """,
    )

    configs = load_test_configs(conf_dir)
    assert len(all_configs(configs)) == 1
    config = only_config(configs)
    assert isinstance(config, WebsiteConfig)
    assert config.name == "my-website"
    assert config.namespace == "production"


def test_load_website_config_unknown_field_raises(tmp_path: Path) -> None:
    """Unknown website fields should fail before generation."""
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    write_toml(
        conf_dir,
        "config.toml",
        """\
        [[website]]
        name = "my-website"
        namespace = "production"
        external_secret = ["/password"]
        """,
    )

    with pytest.raises(
        ValueError,
        match=r"Unknown field in \[\[website\]\]: 'external_secret' on line 4",
    ):
        load_test_configs(conf_dir)


def test_load_website_config_missing_name_field(tmp_path: Path) -> None:
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    write_toml(
        conf_dir,
        "config.toml",
        """\
        [[website]]
        namespace = "default"
        """,
    )
    with pytest.raises(ValueError, match="Missing required field 'name'"):
        load_test_configs(conf_dir)


def test_load_website_config_with_hugo_repo(tmp_path: Path) -> None:
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    write_toml(
        conf_dir,
        "config.toml",
        """\
        [[website]]
        name = "my-website"
        namespace = "production"
        hugo-repo = "https://github.com/user/repo"
        """,
    )

    configs = load_test_configs(conf_dir)
    assert len(all_configs(configs)) == 1
    config = only_config(configs)
    assert isinstance(config, WebsiteConfig)
    assert config.hugo_repo == "https://github.com/user/repo"


def test_load_website_config_with_image(tmp_path: Path) -> None:
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    write_toml(
        conf_dir,
        "config.toml",
        """\
        [[website]]
        name = "my-website"
        namespace = "production"
        image = "nginx:latest"
        """,
    )

    configs = load_test_configs(conf_dir)
    assert len(all_configs(configs)) == 1
    config = only_config(configs)
    assert isinstance(config, WebsiteConfig)
    assert config.image == "nginx:latest"


def test_load_website_config_uses_default_image(tmp_path: Path) -> None:
    """Website config can get its image from namespace-mode API input."""
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    write_toml(
        conf_dir,
        "config.toml",
        """\
        [[website]]
        name = "my-website"
        """,
    )

    configs = load_configs(
        conf_dir,
        config_blocks(),
        default_namespace="production",
        default_image="nginx:latest",
    )
    config = only_config(configs)
    assert isinstance(config, WebsiteConfig)
    assert config.namespace == "production"
    assert config.image == "nginx:latest"


def test_load_website_config_rejects_image_with_default_image(
    tmp_path: Path,
) -> None:
    """Config image and API image override are mutually exclusive for websites."""
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    write_toml(
        conf_dir,
        "config.toml",
        """\
        [[website]]
        name = "my-website"
        image = "nginx:latest"
        """,
    )

    with pytest.raises(ValueError, match="Cannot specify 'image'.*generate"):
        load_configs(
            conf_dir,
            config_blocks(),
            default_namespace="production",
            default_image="example.com/override:1.0",
        )


def test_load_website_config_with_args_string(tmp_path: Path) -> None:
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    write_toml(
        conf_dir,
        "config.toml",
        """\
        [[website]]
        name = "my-website"
        namespace = "production"
        args = "--flag=value"
        """,
    )

    configs = load_test_configs(conf_dir)
    assert len(all_configs(configs)) == 1
    config = only_config(configs)
    assert isinstance(config, WebsiteConfig)
    assert config.args == "--flag=value"


def test_load_website_config_with_args_list(tmp_path: Path) -> None:
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    write_toml(
        conf_dir,
        "config.toml",
        """\
        [[website]]
        name = "my-website"
        namespace = "production"
        args = ["--flag1=value1", "--flag2=value2"]
        """,
    )

    configs = load_test_configs(conf_dir)
    assert len(all_configs(configs)) == 1
    config = only_config(configs)
    assert isinstance(config, WebsiteConfig)
    assert config.args == ["--flag1=value1", "--flag2=value2"]


def test_load_website_config_with_env(tmp_path: Path) -> None:
    """Website config can specify container environment variables."""
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    write_toml(
        conf_dir,
        "config.toml",
        """\
        [[website]]
        name = "my-website"
        namespace = "production"

        [website.env]
        LOG_LEVEL = "debug"
        PUBLIC_URL = "https://example.com"
        """,
    )

    configs = load_test_configs(conf_dir)
    config = only_config(configs)
    assert isinstance(config, WebsiteConfig)
    assert config.env == {
        "LOG_LEVEL": "debug",
        "PUBLIC_URL": "https://example.com",
    }


def test_load_website_config_env_value_must_be_string(tmp_path: Path) -> None:
    """Website env values must be strings."""
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    write_toml(
        conf_dir,
        "config.toml",
        """\
        [[website]]
        name = "my-website"
        namespace = "production"

        [website.env]
        DEBUG = true
        """,
    )

    with pytest.raises(ValueError, match="'env' values must be strings"):
        load_test_configs(conf_dir)


def test_load_website_config_hugo_repo_and_image_mutually_exclusive(
    tmp_path: Path,
) -> None:
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    write_toml(
        conf_dir,
        "config.toml",
        """\
        [[website]]
        name = "my-website"
        namespace = "production"
        hugo-repo = "https://github.com/user/repo"
        image = "nginx:latest"
        """,
    )

    with pytest.raises(ValueError, match="Cannot specify both 'hugo-repo' and 'image'"):
        load_test_configs(conf_dir)


def test_resolve_configs_passes_website_config_through() -> None:
    config = WebsiteConfig(
        name="my-website",
        namespace="default",
    )
    resolved = resolve_configs(manifest_configs(websites=[config]), None)
    assert all_configs(resolved) == (config,)


def test_load_website_config_with_config(tmp_path: Path) -> None:
    """Website config can specify config with local paths."""
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()

    # Create config files in the conf directory (not with .toml extension to avoid glob)
    config_file = conf_dir / "app.conf"
    config_file.write_text("[app]\nkey = value\n")

    write_toml(
        conf_dir,
        "config.toml",
        """\
[[website]]
name = "my-app"
namespace = "default"
config = { "/config/app.conf" = "app.conf" }
""",
    )

    configs = load_test_configs(conf_dir)
    assert len(all_configs(configs)) == 1
    config = only_config(configs)
    assert isinstance(config, WebsiteConfig)
    assert config.config is not None
    assert config.config["/config/app.conf"] == conf_dir / "app.conf"


def test_load_website_config_multiple_config(tmp_path: Path) -> None:
    """Website config can specify multiple config files in different directories."""
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()

    # Create config files (use .conf and .yaml to avoid .toml glob)
    (conf_dir / "app.conf").write_text("app")
    (conf_dir / "db.yaml").write_text("db")

    write_toml(
        conf_dir,
        "config.toml",
        """\
[[website]]
name = "my-app"
namespace = "default"
config = { "/config/app.conf" = "app.conf", "/etc/db.yaml" = "db.yaml" }
""",
    )

    configs = load_test_configs(conf_dir)
    config = only_config(configs)
    assert isinstance(config, WebsiteConfig)
    assert config.config is not None
    assert len(config.config) == 2
    assert config.config["/config/app.conf"] == conf_dir / "app.conf"
    assert config.config["/etc/db.yaml"] == conf_dir / "db.yaml"


def test_load_website_config_with_persistence(tmp_path: Path) -> None:
    """Website config can specify persistent storage by mount path."""
    write_toml(
        tmp_path,
        "config.toml",
        """\
[[website]]
name = "my-app"
namespace = "default"
image = "nginx:latest"
persistence = { "/data" = "1Gi" }
""",
    )

    configs = load_test_configs(tmp_path)
    config = only_config(configs)
    assert isinstance(config, WebsiteConfig)
    assert config.persistence == {"/data": "1Gi"}


def test_load_website_config_with_emptydir_path(tmp_path: Path) -> None:
    """Website config can specify an ephemeral writable emptyDir mount path."""
    write_toml(
        tmp_path,
        "config.toml",
        """\
[[website]]
name = "my-app"
namespace = "default"
image = "nginx:latest"
emptydir-path = "/cache"
""",
    )

    configs = load_test_configs(tmp_path)
    config = only_config(configs)
    assert isinstance(config, WebsiteConfig)
    assert config.emptydir_path == "/cache"


def test_load_website_config_emptydir_path_must_be_absolute(
    tmp_path: Path,
) -> None:
    """Website emptydir-path must be an absolute container path."""
    write_toml(
        tmp_path,
        "config.toml",
        """\
[[website]]
name = "my-app"
namespace = "default"
image = "nginx:latest"
emptydir-path = "cache"
""",
    )

    with pytest.raises(ValueError, match="'emptydir-path' must be an absolute path"):
        load_test_configs(tmp_path)


def test_validate_config_missing_config_file(tmp_path: Path) -> None:
    """Validation should fail if a referenced config file doesn't exist."""
    config = WebsiteConfig(
        name="my-app",
        namespace="default",
        config={"/config/app.toml": tmp_path / "nonexistent.toml"},
    )
    with pytest.raises(ValueError, match="Config file not found"):
        WebsiteBlock().validate(config, tmp_path)


def test_load_website_config_with_extra_hostnames_string(tmp_path: Path) -> None:
    """Website config can specify extra_hostnames as a string."""
    write_toml(
        tmp_path,
        "config.toml",
        """\
[[website]]
name = "my-app"
namespace = "default"
extra-hostnames = "www.example.com"
""",
    )

    configs = load_test_configs(tmp_path)
    config = only_config(configs)
    assert isinstance(config, WebsiteConfig)
    assert config.extra_hostnames == "www.example.com"


def test_load_website_config_with_extra_hostnames_list(tmp_path: Path) -> None:
    """Website config can specify extra_hostnames as a list."""
    write_toml(
        tmp_path,
        "config.toml",
        """\
[[website]]
name = "my-app"
namespace = "default"
extra-hostnames = ["www.example.com", "example.cdn.com"]
""",
    )

    configs = load_test_configs(tmp_path)
    config = only_config(configs)
    assert isinstance(config, WebsiteConfig)
    assert config.extra_hostnames == ["www.example.com", "example.cdn.com"]


def test_load_website_config_with_external_secrets_list(tmp_path: Path) -> None:
    """Website config can specify external_secrets as a list of mount paths."""
    write_toml(
        tmp_path,
        "config.toml",
        """\
[[website]]
name = "my-app"
namespace = "default"
image = "nginx:latest"
external-secrets = ["/email-password", "/db/credentials"]
""",
    )

    configs = load_test_configs(tmp_path)
    config = only_config(configs)
    assert isinstance(config, WebsiteConfig)
    assert config.external_secrets == ["/email-password", "/db/credentials"]


def test_load_website_config_with_external_secrets_string(tmp_path: Path) -> None:
    """Website config can specify external_secrets as a single string (normalized to list)."""
    write_toml(
        tmp_path,
        "config.toml",
        """\
[[website]]
name = "my-app"
namespace = "default"
image = "nginx:latest"
external-secrets = "/api-key"
""",
    )

    configs = load_test_configs(tmp_path)
    config = only_config(configs)
    assert isinstance(config, WebsiteConfig)
    assert config.external_secrets == ["/api-key"]


def test_load_website_config_with_external_secret(tmp_path: Path) -> None:
    """A singular external-secret is normalized to a one-element list."""
    write_toml(
        tmp_path,
        "config.toml",
        """\
[[website]]
name = "my-app"
namespace = "default"
image = "nginx:latest"
external-secret = "/api-key"
""",
    )

    configs = load_test_configs(tmp_path)
    config = only_config(configs)
    assert isinstance(config, WebsiteConfig)
    assert config.external_secrets == ["/api-key"]


def test_load_website_config_rejects_both_external_secret_forms(
    tmp_path: Path,
) -> None:
    """The singular and plural external secret fields are mutually exclusive."""
    write_toml(
        tmp_path,
        "config.toml",
        """\
[[website]]
name = "my-app"
namespace = "default"
image = "nginx:latest"
external-secret = "/api-key"
external-secrets = ["/email-password"]
""",
    )

    with pytest.raises(
        ValueError,
        match="Cannot specify both 'external-secret' and 'external-secrets'",
    ):
        load_test_configs(tmp_path)


def test_load_website_config_external_secret_must_be_string(tmp_path: Path) -> None:
    """The singular external-secret field only accepts a string."""
    write_toml(
        tmp_path,
        "config.toml",
        """\
[[website]]
name = "my-app"
namespace = "default"
image = "nginx:latest"
external-secret = ["/api-key"]
""",
    )

    with pytest.raises(ValueError, match="'external-secret' must be a string"):
        load_test_configs(tmp_path)


def test_load_website_config_external_secrets_must_be_strings(tmp_path: Path) -> None:
    """external-secrets must be a string or list of strings."""
    write_toml(
        tmp_path,
        "config.toml",
        """\
[[website]]
name = "my-app"
namespace = "default"
image = "nginx:latest"
external-secrets = [1]
""",
    )

    with pytest.raises(
        ValueError,
        match="'external-secrets' must be a string or list of strings",
    ):
        load_test_configs(tmp_path)


def test_load_website_config_with_custom_token_audiences(tmp_path: Path) -> None:
    """Website config can specify custom audiences for projected tokens."""
    write_toml(
        tmp_path,
        "config.toml",
        """\
[[website]]
name = "my-app"
namespace = "default"
image = "nginx:latest"
custom-token-audiences = ["vault", "api"]
""",
    )

    configs = load_test_configs(tmp_path)
    config = only_config(configs)
    assert isinstance(config, WebsiteConfig)
    assert config.custom_token_audiences == ["vault", "api"]


def test_load_website_config_custom_token_audiences_must_be_list(
    tmp_path: Path,
) -> None:
    """Website custom token audiences must be configured as a string list."""
    write_toml(
        tmp_path,
        "config.toml",
        """\
[[website]]
name = "my-app"
namespace = "default"
image = "nginx:latest"
custom-token-audiences = "vault"
""",
    )

    with pytest.raises(
        ValueError,
        match="'custom-token-audiences' must be a list of strings",
    ):
        load_test_configs(tmp_path)


def test_load_website_config_with_replicas(tmp_path: Path) -> None:
    """Website config can specify replicas for the Deployment."""
    write_toml(
        tmp_path,
        "config.toml",
        """\
[[website]]
name = "my-app"
namespace = "default"
image = "nginx:latest"
replicas = 5
""",
    )

    configs = load_test_configs(tmp_path)
    config = only_config(configs)
    assert isinstance(config, WebsiteConfig)
    assert config.replicas == 5


def test_load_website_config_replicas_single(tmp_path: Path) -> None:
    """Website config can specify replicas=1."""
    write_toml(
        tmp_path,
        "config.toml",
        """\
[[website]]
name = "my-app"
namespace = "default"
image = "nginx:latest"
replicas = 1
""",
    )

    configs = load_test_configs(tmp_path)
    config = only_config(configs)
    assert isinstance(config, WebsiteConfig)
    assert config.replicas == 1


def test_load_website_config_replicas_not_specified(tmp_path: Path) -> None:
    """Website config without replicas should default to DEFAULT_REPLICA_COUNT."""
    write_toml(
        tmp_path,
        "config.toml",
        """\
[[website]]
name = "my-app"
namespace = "default"
image = "nginx:latest"
""",
    )

    configs = load_test_configs(tmp_path)
    config = only_config(configs)
    assert isinstance(config, WebsiteConfig)
    assert config.replicas == DEFAULT_REPLICA_COUNT
