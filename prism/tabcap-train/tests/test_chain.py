import argparse
import shlex
from pathlib import Path

import pytest

import chain


def test_steps_equal_sidecar() -> None:
    cmds = [s["cmd"] for s in chain.sidecar()["train"]["chain"]]
    assert [shlex.join(s.argv) for s in chain.steps()] == cmds
    assert [s.num for s in chain.steps()] == list(range(1, 9))


def test_outputs_and_needs() -> None:
    by = {s.num: s for s in chain.steps()}
    assert by[1].out == "v3n_s8.pkl"
    assert by[3].needs == ["v3n_s8.pkl", "comp3_s1.pkl"]
    assert by[6].needs == ["v3k_s1.pkl", "v3c3_tf.pt", "compk_s1.pkl"]
    assert by[7].out == "realk_all.pkl"
    assert by[8].out == "rk4_all.onnx"
    assert by[8].needs == ["v3k_s1.pkl", "kf4.pt", "realk_all.pkl"]


def test_n_changes_only_gen_n() -> None:
    for a, b in zip(chain.steps(), chain.steps(2000)):
        if a.script == "c2_gen.py":
            assert b.argv[2] == "2000"
            assert b.argv[:2] + b.argv[3:] == a.argv[:2] + a.argv[3:]
        else:
            assert a.argv == b.argv


@pytest.mark.parametrize(
    "v, want", [("3", [3]), ("1-4", [1, 2, 3, 4]), ("7,1,2", [1, 2, 7])]
)
def test_parse_steps(v: str, want: list[int]) -> None:
    assert chain.parse_steps(v) == want


def test_parse_steps_range() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        chain.parse_steps("0-8")


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for v in ("TABCAP_RESOURCE_PACKS", "TABCAP_NAMES"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("TABCAP_RESULTS", str(tmp_path / "results"))
    monkeypatch.setenv("PRISM_TEST_FIXTURES_DIR", str(tmp_path / "fixtures"))
    return tmp_path


def test_preflight_short_missing(env: Path) -> None:
    errors, _ = chain.preflight([chain.steps()[7]], None)
    assert errors == [
        "step 8: missing c2/v3k_s1.pkl",
        "step 8: missing c2/kf4.pt",
        "step 8: missing c2/realk_all.pkl",
    ]


def test_preflight_full_inputs(env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (env / "packs/fonts").mkdir(parents=True)
    (env / "names.txt").write_text("a\n")
    monkeypatch.setenv("TABCAP_RESOURCE_PACKS", str(env / "packs"))
    monkeypatch.setenv("TABCAP_NAMES", str(env / "names.txt"))
    errors, _ = chain.preflight(chain.steps(), None)
    # earlier steps make what later steps need; only step 7 inputs are missing
    assert [e.split(":")[0] for e in errors] == ["step 7", "step 7"]
    assert errors[1] == "step 7: missing tl/cache_c2_v3_tf.pkl"


def test_preflight_skip_done(env: Path) -> None:
    c2 = env / "results/c2"
    c2.mkdir(parents=True)
    for f in ("v3k_s1.pkl", "kf4.pt", "realk_all.pkl", "rk4_all.onnx"):
        (c2 / f).write_bytes(b"")
    errors, notes = chain.preflight([chain.steps()[7]], None)
    assert errors == []
    assert notes == ["step 8: rk4_all.onnx exists, skip"]


def test_preflight_n_guard(env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gen = [chain.steps(2000)[0]]
    assert not any("--n" in e for e in chain.preflight(gen, 2000)[0])
    assert any("multiple" in e for e in chain.preflight(gen, 3000)[0])
    monkeypatch.delenv("TABCAP_RESULTS")
    assert any("TABCAP_RESULTS" in e for e in chain.preflight(gen, 2000)[0])
