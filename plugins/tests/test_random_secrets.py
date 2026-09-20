"""Random-secret behavior shared by both deployment plugins."""

from pathlib import Path

import pytest
import yaml
from manifest_builder.discovery import discover_blocks

from simple import SimpleBlock, generate_simple
from website import WebsiteBlock, generate_website


@pytest.mark.parametrize("block_type", [SimpleBlock, WebsiteBlock])
@pytest.mark.parametrize(
    "fields,expected",
    [
        ({}, None),
        ({"random-secret": "KEY"}, ["KEY"]),
        ({"random-secrets": ["A", "B"]}, ["A", "B"]),
        ({"random-secrets": []}, []),
    ],
)
def test_parse(block_type, fields, expected, tmp_path):
    block = block_type()
    block.load_config(
        [{"name": "app.example", "namespace": "apps", "image": "app:1", **fields}],
        tmp_path / "config.toml",
        {},
    )
    assert block.configs[0].random_secrets == expected


@pytest.mark.parametrize("block_type", [SimpleBlock, WebsiteBlock])
@pytest.mark.parametrize(
    "fields,message",
    [
        ({"random-secret": "A", "random-secrets": ["B"]}, "Cannot specify both"),
        ({"random-secret": ["A"]}, "'random-secret' must be a string"),
        ({"random-secrets": "A"}, "'random-secrets' must be a list of strings"),
        ({"random-secrets": ["A", 1]}, "'random-secrets' must be a list of strings"),
    ],
)
def test_invalid(block_type, fields, message, tmp_path):
    with pytest.raises(ValueError, match=message):
        block_type().load_config(
            [{"name": "app.example", "namespace": "apps", "image": "app:1", **fields}],
            tmp_path / "config.toml",
            {},
        )


@pytest.mark.parametrize("mode", ["simple", "website", "hugo"])
@pytest.mark.parametrize("keys", [None, [], ["KEY"], ["A", "B"]])
def test_generation(mode, keys, tmp_path):
    block = SimpleBlock() if mode == "simple" else WebsiteBlock()
    fields = (
        {"hugo-repo": "https://example.com/site.git"}
        if mode == "hugo"
        else {"image": "app:1"}
    )
    if keys is not None:
        fields["random-secrets"] = keys
    block.load_config(
        [{"name": "app.example", "namespace": "apps", **fields}],
        tmp_path / "config.toml",
        {},
    )
    generate = generate_simple if mode == "simple" else generate_website
    docs = [
        yaml.safe_load(path.read_text())
        for path in generate(block.configs[0], tmp_path)
    ]
    secrets = [doc for doc in docs if doc["kind"] == "RandomSecret"]
    pod = next(doc for doc in docs if doc["kind"] == "Deployment")["spec"]["template"][
        "spec"
    ]
    mounts = [
        mount
        for container in pod["containers"]
        for mount in container.get("volumeMounts", [])
        if mount["name"] == "random-secrets"
    ]
    volumes = [
        volume
        for volume in pod.get("volumes", [])
        if volume["name"] == "random-secrets"
    ]
    if not keys:
        assert secrets == mounts == volumes == []
        return
    assert secrets == [
        {
            "apiVersion": "noa.re/v1alpha1",
            "kind": "RandomSecret",
            "metadata": {"name": "app-example", "namespace": "apps"},
            "spec": {"secrets": [{"name": key} for key in keys]},
        }
    ]
    assert mounts == [{"name": "random-secrets", "mountPath": "/random-secrets"}] * len(
        pod["containers"]
    )
    assert volumes == [
        {"name": "random-secrets", "secret": {"secretName": "app-example"}}
    ]


def test_discovery():
    blocks = discover_blocks(Path(__file__).resolve().parents[2])
    assert {"simple", "website"} <= {block.top_level_config_name() for block in blocks}
