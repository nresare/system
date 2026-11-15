# SPDX-License-Identifier: MIT
"""Check namespace-free copying with the installed manifest-builder dependency."""

import json
import tomllib
from pathlib import Path

import pytest
import yaml
from manifest_builder import generate
from manifest_builder.generator import ManifestError


def test_controller_rbac_copy_does_not_claim_namespace(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    config = tomllib.loads((root / "config.toml").read_text())
    block = next(
        block
        for block in config["copy"]
        if block["source"] == "external-envoy-controller/extra"
    )
    assert "namespace" not in block
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        "[[copy]]\n"
        f"name = {json.dumps(block['name'])}\n"
        f"source = {json.dumps(str(root / block['source']))}\n"
    )
    output = tmp_path / "output"
    owners = output / "owners"
    owners.mkdir(parents=True)
    owner = owners / "external-envoy-controller.toml"
    owner.write_text('owned = "external-envoy-controller"\n')
    namespace_dir = output / "external-envoy-controller"
    namespace_dir.mkdir()
    deployment = namespace_dir / "deployment-controller.yaml"
    deployment.write_text("managed by the controller's own deployment\n")

    result = generate(config_dir, output, repo_root=tmp_path)

    assert result.written_paths == {
        output / "cluster" / "clusterrole-external-envoy-controller.yaml",
        output / "cluster" / "clusterrolebinding-external-envoy-controller.yaml",
        owners / "system.toml",
    }
    assert tomllib.loads((owners / "system.toml").read_text()) == {"owned": ["cluster"]}
    assert owner.read_text() == 'owned = "external-envoy-controller"\n'
    assert deployment.read_text() == "managed by the controller's own deployment\n"
    for path in result.written_paths:
        if path.suffix == ".yaml":
            doc = yaml.safe_load(path.read_text())
            assert "namespace" not in doc["metadata"]
            if doc["kind"] == "ClusterRoleBinding":
                assert doc["subjects"][0]["namespace"] == "external-envoy-controller"


def test_copy_requires_namespace_for_unqualified_namespaced_manifest(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config"
    manifests = config / "manifests"
    manifests.mkdir(parents=True)
    (config / "config.toml").write_text(
        '[[copy]]\nname = "settings"\nsource = "manifests"\n'
    )
    (manifests / "settings.yaml").write_text(
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: settings\n"
    )
    output = tmp_path / "output"
    output.mkdir()

    with pytest.raises(ManifestError, match="namespace.*is required") as error:
        generate(config, output, repo_root=tmp_path)
    assert isinstance(error.value.__cause__, ValueError)
