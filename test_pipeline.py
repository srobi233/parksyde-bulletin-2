#!/usr/bin/env python3
"""Does the generator write what the player reads?

Nobody checked that before, and the answer was no for the life of the project:
the player fetched output/latest.mp3, which generate_bulletin.py has never
written, and read a `segments` array the manifest has never contained. It
failed over to six invented stories and looked fine doing it.

So this runs the real main() against a real past bulletin with the two network
calls stubbed, then asserts the manifest against what player.js actually reads.
No dependencies, run it with `python3 test_pipeline.py`.
"""
import json, os, re, shutil, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "output" / "2026-06-01"      # a real day off the press

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used")
os.environ.pop("ELEVENLABS_API_KEY", None)     # set per-case below

ok = fail = 0
def check(label, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1; print("  \033[32m✓\033[0m " + label)
    else:
        fail += 1; print("  \033[31m✗ " + label + "\033[0m" + (("\n      " + detail) if detail else ""))


def load_fixture():
    """The scripts from a day that really went out, in the shape main() expects."""
    data = {"stories": json.loads((FIXTURE / "manifest.json").read_text())["stories"]}
    for seg in ["seg1_open", "seg2_green", "seg3_science", "seg5_sports", "seg6_outro"]:
        data[seg] = json.loads((FIXTURE / (seg + ".json")).read_text())
    data["seg4_weather"] = (FIXTURE / "seg4_weather.txt").read_text()
    return data


def run(voice_works):
    """Run the generator in a scratch directory with both APIs stubbed.

    Returns the parsed output/latest.json."""
    work = Path(tempfile.mkdtemp())
    cwd = os.getcwd()
    try:
        os.chdir(work)
        sys.path.insert(0, str(HERE))
        for m in list(sys.modules):
            if m == "generate_bulletin":
                del sys.modules[m]
        import generate_bulletin as gb

        fixture = load_fixture()
        gb.claude = lambda **kw: json.dumps(fixture)
        # Stand in for ElevenLabs: write a real (tiny) file so the "did the
        # write happen" path is exercised, or refuse, as the case requires.
        def fake_tts(text, speaker, filename):
            if not voice_works:
                return False
            Path(filename).write_bytes(b"\xff\xfb\x90\x00")   # 4 bytes of nothing
            return True
        gb.generate_tts = fake_tts
        gb.time.sleep = lambda *_: None

        gb.main()
        return json.loads((work / "output" / "latest.json").read_text()), work
    finally:
        os.chdir(cwd)


print("\n\033[1mPipeline — the generator writes what the player reads\033[0m")

man, work = run(voice_works=True)

# --- the shape player.js depends on -----------------------------------------
check("manifest has a segments array", isinstance(man.get("segments"), list))
check("every segment has the three fields the player renders",
      all(all(k in s for k in ("id", "title", "lines")) for s in man["segments"]),
      "player.js reads seg.id, seg.title, seg.script and seg.lines")
check("every segment has a readable script for sound-off visitors",
      all(s.get("script", "").strip() for s in man["segments"]))

# --- broadcast order, not file order ----------------------------------------
check("the weather sits fourth, where the hosts read it",
      [s["id"] for s in man["segments"]] ==
      ["seg1_open", "seg2_green", "seg3_science", "seg4_weather", "seg5_sports", "seg6_outro"],
      "got: " + str([s["id"] for s in man["segments"]]))

# --- the audio paths must actually resolve ----------------------------------
# player.js builds its URL as REPO_BASE + '/' + line.audio, where REPO_BASE
# ends at .../output — so the path has to be relative to output/, date first.
paths = [l["audio"] for s in man["segments"] for l in s["lines"] if l.get("audio")]
check("audio paths are relative to output/, dated first",
      bool(paths) and all(re.match(r"^\d{4}-\d{2}-\d{2}/audio/.+\.mp3$", p) for p in paths),
      "player.js prepends the repo's output/ URL; an absolute or bare name 404s")
check("every audio path names a file that was really written",
      all((work / "output" / p).exists() for p in paths))

# --- the honesty of has_audio ------------------------------------------------
check("has_audio is true when files exist", man["has_audio"] is True)
check("audio_files counts the files, not the key",
      man["audio_files"] == len(paths) and man["audio_files"] > 0,
      "audio_files=" + str(man.get("audio_files")) + " files=" + str(len(paths)))
shutil.rmtree(work, ignore_errors=True)

# --- and the case that shipped the lie: key present, every voice fails -------
man2, work2 = run(voice_works=False)
check("has_audio is FALSE when every voice failed", man2["has_audio"] is False,
      "this is the 1 June 2026 case — key set, no audio written, manifest said true")
check("audio_files is 0, not the line count", man2["audio_files"] == 0)
check("the scripts still survive a total voice failure",
      all(s.get("script", "").strip() for s in man2["segments"]) and len(man2["segments"]) == 6,
      "a failed voice must never cost the day's words")
check("lines are still counted so the gap is visible", man2["lines"] > 0)
shutil.rmtree(work2, ignore_errors=True)

# --- the player must not invent a bulletin ----------------------------------
raw = (HERE / "player.js").read_text()

# Strip comments before asserting on code. player.js EXPLAINS in its header
# why it no longer fetches latest.mp3 and no longer carries a SAMPLE, so a
# check reading the whole file fails on the explanation — it is satisfied by
# never mentioning the bug, and broken by documenting it, which is precisely
# backwards. (This is the second time today: test/cases/workflows.js in
# ParkSyde-Map had the mirror image, passing on a comment after the real
# directive was deleted. Prose is not the artefact.)
player = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)
player = re.sub(r"(?m)^\s*//.*$", "", player)

check("player.js has no invented fallback stories",
      "Bremer River" not in player and "SAMPLE" not in player,
      "the old player showed six made-up stories when the fetch failed, "
      "and nothing on screen said they were not today's news")
check("player.js says plainly when there is no bulletin",
      "isn’t available yet" in player or "isn't available yet" in player)
check("player.js reads the per-line playlist, not a latest.mp3 that never existed",
      "latest.mp3" not in player and "line.audio" in player)
check("the comment-stripping above did not simply empty the file",
      "function load()" in player and len(player) > 2000)

print("\n" + "-" * 52)
if fail:
    print("\033[31m" + str(fail) + " failed\033[0m, " + str(ok) + " passed")
    sys.exit(1)
print("\033[32mAll " + str(ok) + " checks passed\033[0m")
