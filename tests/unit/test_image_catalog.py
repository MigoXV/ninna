from copy import deepcopy

import pytest

from ninna.services.image_catalog import browse, location, parse_reference


def asset(source, name="demo", version="v1", image_id="sha256:aaa", tags=None):
    return dict(
        id=f"image:{name}:{version}",
        name=name,
        version=version,
        source_reference=source,
        image_id=image_id,
        tags=tags or [],
        os="linux",
        architecture="amd64",
        size=10,
        created_at="2026-09-25",
    )


@pytest.mark.parametrize(
    "source, expected",
    [
        ("alpine", ("docker.io", "library", "alpine", "latest")),
        ("pytorch/pytorch:2.8", ("docker.io", "pytorch", "pytorch", "2.8")),
        ("localhost:5000/a/b/image:v1", ("localhost:5000", "a/b", "image", "v1")),
        ("registry.example/image@sha256:abcd", ("registry.example", "_", "image", "sha256:abcd")),
        ("index.docker.io/library/alpine:3", ("docker.io", "library", "alpine", "3")),
    ],
)
def test_reference_parser(source, expected):
    assert tuple(parse_reference(source).values()) == expected


def test_registered_source_wins_over_sorted_aliases():
    value = asset(
        "registry.example/migo-dl/pytorch:2.8",
        tags=["a/python:3", "registry.example/migo-dl/pytorch:2.8"],
    )
    assert location(value)["repository"] == "pytorch"
    assert location(value)["registry"] == "registry.example"


def test_local_identity_without_ambiguous_repository_guess():
    assert location(asset("sha256:aaa", tags=["ninna/runtime:v3"])) == dict(
        registry="local", namespace="ninna", repository="runtime", reference="v3"
    )
    assert (
        location(asset("sha256:aaa", tags=["ninna/runtime:v3", "other/runtime:v3"]))["repository"]
        == "unclassified"
    )
    assert location(asset("sha256:aaa"))["registry"] == "local"
    assert (
        location(asset("sha256:aaa", tags=["ninna/runtime:v2", "ninna/runtime:v3"]))["reference"]
        == "sha256:aaa"
    )


def test_hierarchy_merges_registrations_not_distinct_tags_or_content():
    values = [
        asset("registry.example/migo-dl/pytorch:v1"),
        asset("registry.example/migo-dl/pytorch:v1", name="duplicate"),
        asset("registry.example/migo-dl/pytorch:v2"),
        asset("registry.example/migo-dl/pytorch:v1", name="changed", image_id="sha256:bbb"),
        asset("registry.example/migo-dl/preludio2:v1"),
    ]
    before = deepcopy(values)
    assert browse(values)["items"][0]["namespace_count"] == 1
    assert browse(values, "registry.example")["items"][0]["repository_count"] == 2
    rows = browse(values, "registry.example", "migo-dl")["items"]
    assert [(r["name"], r["version_count"]) for r in rows] == [("preludio2", 1), ("pytorch", 3)]
    versions = browse(values, "registry.example", "migo-dl", "pytorch")
    assert versions["asset_count"] == 4
    assert sorted(len(r["assets"]) for r in versions["items"]) == [1, 1, 2]
    assert values == before


def test_scoped_search_and_invalid_parent():
    values = [asset("registry.example/migo-dl/pytorch:v1"), asset("elsewhere.test/team/pytorch:v1")]
    assert browse(values, registry="registry.example", q="PYTORCH")["version_count"] == 1
    assert browse(values, q="no-match")["items"] == []
    with pytest.raises(ValueError):
        browse(values, namespace="migo-dl")


@pytest.mark.parametrize("source", ["registry.example/team/", "registry.example/team/image:"])
def test_preview_rejects_incomplete_paths(source):
    with pytest.raises(ValueError):
        parse_reference(source)
