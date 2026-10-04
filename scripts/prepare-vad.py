"""可复现的 AVA 音频下载、能量粗标注和 AudioFolder 数据校验。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import shutil
import wave
from pathlib import Path

import numpy as np
import typer

app = typer.Typer()
logger = logging.getLogger(__name__)
RATE = 16000
CLIP_SECONDS = 300
# Parameters are versioned with the recipe; no tuning on validation/test labels.
ENERGY = {
    "frame_ms": 20,
    "hop_ms": 10,
    "threshold_dbfs": -35.0,
    "min_active_ms": 100,
    "merge_gap_ms": 150,
    "pad_ms": 50,
}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def label(samples):
    """Return ordered non-overlapping half-open active intervals in seconds."""
    x = np.asarray(samples, dtype=np.float64) / 32768.0
    hop, frame = 160, 320
    starts = np.arange(0, len(x), hop)
    power = np.concatenate(([0.0], np.cumsum(x * x)))
    ends = np.minimum(starts + frame, len(x))
    rms = np.sqrt((power[ends] - power[starts]) / (ends - starts))
    active = rms >= 10 ** (ENERGY["threshold_dbfs"] / 20)
    edges = np.diff(np.concatenate(([False], active, [False])).astype(int))
    spans = [
        (int(a * hop), min(int(b * hop + frame - hop), len(x)))
        for a, b in zip(np.where(edges == 1)[0], np.where(edges == -1)[0])
    ]
    merged = []
    for a, b in spans:
        if merged and a - merged[-1][1] <= RATE * ENERGY["merge_gap_ms"] / 1000:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    padded = []
    for a, b in merged:
        if b - a < RATE * ENERGY["min_active_ms"] / 1000:
            continue
        a = max(0, a - 800)
        b = min(len(x), b + 800)
        if padded and a <= padded[-1][1]:
            padded[-1][1] = b
        else:
            padded.append([a, b])
    return {
        "starts": [a / RATE for a, _ in padded],
        "durations": [(b - a) / RATE for a, b in padded],
    }


def validate(root):
    groups = {}
    ids, hashes = set(), set()
    result = {}
    for split in ["train", "validation", "test"]:
        seconds = speech = count = 0
        for line in (root / split / "metadata.jsonl").read_text().splitlines():
            row = json.loads(line)
            path = (root / split / row["file_name"]).resolve()
            if not path.is_relative_to((root / split).resolve()):
                raise ValueError("Audio path escapes split")
            with wave.open(str(path)) as wav:
                assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (RATE, 1, 2)
                duration = wav.getnframes() / RATE
            assert duration == CLIP_SECONDS
            assert row["id"] not in ids
            ids.add(row["id"])
            sha = digest(path)
            assert sha == row["audio_sha256"] and sha not in hashes
            hashes.add(sha)
            group = row["source_id"]
            assert groups.setdefault(group, split) == split, "Source leakage"
            starts, durations = row["seconds"]["starts"], row["seconds"]["durations"]
            assert len(starts) == len(durations)
            previous = 0
            for start, length in zip(starts, durations):
                assert np.isfinite(start) and np.isfinite(length)
                assert start >= previous - 1e-8 and length > 0 and start + length <= duration + 1e-8
                previous = start + length
                speech += length
            seconds += duration
            count += 1
        result[split] = {
            "clips": count,
            "seconds": seconds,
            "active_seconds": round(speech, 3),
            "active_fraction": round(speech / seconds, 4),
        }
    return result


def export_parquet(root, destination):
    """Self-contained HF Audio Parquet with embedded WAV bytes and explicit schema."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    fields = [
        ("audio", pa.struct([("bytes", pa.binary()), ("path", pa.string())])),
        ("id", pa.string()),
        (
            "seconds",
            pa.struct([("starts", pa.list_(pa.float64())), ("durations", pa.list_(pa.float64()))]),
        ),
        ("source_id", pa.string()),
        ("source_offset_seconds", pa.int64()),
        ("audio_sha256", pa.string()),
        ("annotation_method", pa.string()),
        ("annotation_status", pa.string()),
    ]
    features = {
        key: {"dtype": "string", "_type": "Value"}
        for key in ["id", "source_id", "audio_sha256", "annotation_method", "annotation_status"]
    }
    features.update(
        audio={"sampling_rate": RATE, "_type": "Audio"},
        seconds={
            k: {"feature": {"dtype": "float64", "_type": "Value"}, "_type": "List"}
            for k in ["starts", "durations"]
        },
        source_offset_seconds={"dtype": "int64", "_type": "Value"},
    )
    schema = pa.schema(
        fields, metadata={b"huggingface": json.dumps({"info": {"features": features}}).encode()}
    )
    destination.mkdir(parents=True)
    for split in ["train", "validation", "test"]:
        target = destination / f"{split}-00000-of-00001.parquet"
        with pq.ParquetWriter(target, schema, compression="zstd") as writer:
            for line in (root / split / "metadata.jsonl").read_text().splitlines():
                row = json.loads(line)
                name = row.pop("file_name")
                row["audio"] = {"bytes": (root / split / name).read_bytes(), "path": name}
                writer.write_table(pa.Table.from_pylist([row], schema=schema))
        # Check bytes and labels survive serialization without requiring external paths.
        original = [
            json.loads(x) for x in (root / split / "metadata.jsonl").read_text().splitlines()
        ]
        restored = pq.read_table(target).to_pylist()
        assert len(original) == len(restored)
        for before, after in zip(original, restored):
            assert before["seconds"] == after["seconds"]
            assert hashlib.sha256(after["audio"]["bytes"]).hexdigest() == before["audio_sha256"]
    (destination / "README.md").write_text(
        '# VAD Parquet 数据副本\n\n音频以 WAV bytes 内嵌，每条严格 300 秒；无需访问 AudioFolder 路径。\n使用 datasets.load_dataset(目录, split="train") 加载。粗标注及来源同对应 AudioFolder。\n'
    )


@app.command()
def build(
    output: Path = typer.Option(Path("data-bin/vad-ava-energy-v1")),
    lock: Path = typer.Option(Path("examples/vad/source-lock.json")),
):
    """下载固定 commit 的 40 段 15 分钟录音；产出 10h 和严格 2h 子集。"""
    from huggingface_hub import snapshot_download

    if importlib.util.find_spec("pyarrow") is None:
        raise typer.BadParameter("先运行 poetry run pip install 'pyarrow>=17,<22'")
    source = json.loads(lock.read_text())
    output.mkdir(parents=True, exist_ok=True)
    for name in ["10h", "2h"]:
        if (output / name).exists():
            raise ValueError(f"{output / name} already exists; use a new version directory")
    snapshot_download(
        source["repo_id"],
        repo_type="dataset",
        revision=source["revision"],
        local_dir=output / "original",
        max_workers=4,
        allow_patterns=["README.md"] + [r["path"] for r in source["sources"]],
    )
    shutil.copyfile(lock, output / "source-lock.json") if lock.resolve() != (
        output / "source-lock.json"
    ).resolve() else None
    rows = {name: {s: [] for s in ["train", "validation", "test"]} for name in ["10h", "2h"]}
    provenance = []
    selected_per_split = {"train": 20, "validation": 2, "test": 2}
    seen_per_split = dict.fromkeys(selected_per_split, 0)
    for entry in source["sources"]:
        path = output / "original" / entry["path"]
        with wave.open(str(path)) as wav:
            assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (RATE, 1, 2)
            assert wav.getnframes() == 900 * RATE
            samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
        source_id = path.stem
        split = entry["split"]
        provenance.append({**entry, "sha256": digest(path), "seconds": 900})
        # One central five-minute clip from each selected recording.
        subset_indices = {1} if seen_per_split[split] < selected_per_split[split] else set()
        seen_per_split[split] += 1
        for index in range(3):
            start = index * CLIP_SECONDS
            clip = samples[start * RATE : (start + CLIP_SECONDS) * RATE]
            relative = f"audio/{source_id}-{index:03d}.wav"
            target = output / "10h" / split / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(target), "wb") as wav:
                wav.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
                wav.writeframes(clip.tobytes())
            row = {
                "file_name": relative,
                "id": f"{source_id}-{index:03d}",
                "seconds": label(clip),
                "source_id": source_id,
                "source_offset_seconds": start,
                "audio_sha256": digest(target),
                "annotation_method": "energy-v1",
                "annotation_status": "unreviewed",
            }
            rows["10h"][split].append(row)
            if index in subset_indices:
                subset = output / "2h" / split / relative
                subset.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(target, subset)
                rows["2h"][split].append(row)
        logger.info("Prepared %s", source_id)
    reports = {}
    for name in rows:
        root = output / name
        for split, values in rows[name].items():
            (root / split / "metadata.jsonl").write_text(
                "".join(json.dumps(r) + "\n" for r in values)
            )
        report = validate(root)
        expected = [28800, 3600, 3600] if name == "10h" else [6000, 600, 600]
        assert [report[s]["seconds"] for s in ["train", "validation", "test"]] == expected
        reports[name] = report
        export_parquet(root, output / (name + "-parquet"))
        (root / "README.md").write_text(
            f"# AVA 能量粗标注 {name}\n\n固定 16 kHz 单声道 PCM16，300 秒切片；10h 划分 96/12/12 条，2h 划分 20/2/2 条。\n"
            "标注仅为能量阈值检测到的活动区间，音乐和噪声可能误报，不是人工语音真值。\n"
            "seconds.starts/durations 单位秒；人工修标请创建新版本。\n"
            f"来源：{source['repo_id']}，commit {source['revision']}。\n"
            "上游数据卡标为 Apache-2.0；原始 AVA 影片另有权利归属，不据此推断影片可再授权。\n"
        )
    for split in rows["2h"]:
        parent = {r["id"]: r for r in rows["10h"][split]}
        assert all(parent[r["id"]] == r for r in rows["2h"][split])
    manifest = {
        "schema_version": 1,
        "source": source,
        "source_files": provenance,
        "energy": ENERGY,
        "sample_rate": RATE,
        "clip_seconds": CLIP_SECONDS,
        "subset_clip_indices": [1],
        "subset_sources_per_split": selected_per_split,
        "reports": reports,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    typer.echo(json.dumps(reports, indent=2))


@app.command()
def check(root: Path = typer.Argument(...)):
    """校验文件、哈希、采样格式、区间、重复和跨 split 泄漏。"""
    typer.echo(json.dumps(validate(root), indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app()
