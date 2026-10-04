import importlib.util
from pathlib import Path

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location(
    "prepare_vad", Path(__file__).parents[2] / "scripts/prepare-vad.py"
)
vad = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vad)


def test_silence_and_short_impulse_are_not_activity():
    x = np.zeros(16000, dtype=np.int16)
    assert vad.label(x) == {"starts": [], "durations": []}
    x[8000] = 32767
    assert vad.label(x) == {"starts": [], "durations": []}


def test_energy_regions_are_padded_merged_and_clipped():
    x = np.zeros(48000, dtype=np.int16)
    x[:8000] = 4000
    x[24000:28000] = 4000
    x[28800:] = 4000
    result = vad.label(x)
    assert result["starts"] == pytest.approx([0, 1.44])
    assert result["durations"] == pytest.approx([0.56, 1.56])


def test_five_minute_contract():
    assert vad.CLIP_SECONDS * vad.RATE == 4_800_000


@pytest.fixture()
def audiofolder(tmp_path):
    import json
    import wave

    for index, split in enumerate(["train", "validation", "test"]):
        folder = tmp_path / split
        folder.mkdir()
        audio = folder / "clip.wav"
        with wave.open(str(audio), "wb") as wav:
            wav.setparams((1, 2, vad.RATE, 0, "NONE", "not compressed"))
            wav.writeframes(np.full(vad.RATE * vad.CLIP_SECONDS, index, dtype="<i2").tobytes())
        row = {
            "file_name": "clip.wav",
            "id": split,
            "source_id": split,
            "source_offset_seconds": 300,
            "audio_sha256": vad.digest(audio),
            "seconds": {"starts": [0.5], "durations": [1.0]},
            "annotation_method": "energy-v1",
            "annotation_status": "unreviewed",
        }
        (folder / "metadata.jsonl").write_text(json.dumps(row) + "\n")
    return tmp_path


def test_validation_rejects_cross_split_source_leakage(audiofolder):
    import json

    assert vad.validate(audiofolder)["train"]["seconds"] == 300
    path = audiofolder / "test/metadata.jsonl"
    row = json.loads(path.read_text())
    row["source_id"] = "train"
    path.write_text(json.dumps(row))
    with pytest.raises(AssertionError, match="Source leakage"):
        vad.validate(audiofolder)


def test_validation_rejects_out_of_bounds_labels(audiofolder):
    import json

    path = audiofolder / "test/metadata.jsonl"
    row = json.loads(path.read_text())
    row["seconds"] = {"starts": [299.5], "durations": [1.0]}
    path.write_text(json.dumps(row))
    with pytest.raises(AssertionError):
        vad.validate(audiofolder)


def test_parquet_embeds_audio_and_preserves_intervals(audiofolder, tmp_path):
    pq = pytest.importorskip("pyarrow.parquet")
    destination = tmp_path / "parquet"
    vad.export_parquet(audiofolder, destination)
    rows = pq.read_table(destination / "train-00000-of-00001.parquet").to_pylist()
    assert rows[0]["audio"]["bytes"] == (audiofolder / "train/clip.wav").read_bytes()
    assert rows[0]["seconds"] == {"starts": [0.5], "durations": [1.0]}
