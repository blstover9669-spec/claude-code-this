"""Builds dist/LastNight.mcaddon (and the two .mcpack files) from src/."""
import io
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC, DIST = ROOT / "src", ROOT / "dist"


def pack_bytes(folder: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(folder.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(folder).as_posix())
    return buf.getvalue()


DIST.mkdir(exist_ok=True)
bp, rp = pack_bytes(SRC / "BP"), pack_bytes(SRC / "RP")
(DIST / "LastNight_BP.mcpack").write_bytes(bp)
(DIST / "LastNight_RP.mcpack").write_bytes(rp)
with zipfile.ZipFile(DIST / "LastNight.mcaddon", "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("LastNight_BP.mcpack", bp)
    z.writestr("LastNight_RP.mcpack", rp)
print("built", DIST / "LastNight.mcaddon")
