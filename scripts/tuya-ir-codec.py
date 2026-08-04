#!/usr/bin/env python3
"""
Tuya / Moes UFO-R11 IR codec.

Wire format: base64( FastLZ level 1 ( little-endian uint16 durations in us ) ).
Durations alternate mark / space and always start with a mark.

Usage:
    tuya-ir-codec.py decode <base64> [<base64> ...]
    tuya-ir-codec.py encode <addr_hex> <cmd_hex> [repeat_frames]
    tuya-ir-codec.py burst  <addr_hex> <cmd_hex> <frames> [gap_us]
    tuya-ir-codec.py hold   <addr_hex> <cmd_hex> <repeats>

Examples:
    tuya-ir-codec.py decode "BSgjlBEwAuADAQGaBuAJD..."
    tuya-ir-codec.py encode 88 46          # single NEC frame
    tuya-ir-codec.py encode 88 46 9        # frame + 9 NEC repeat frames
    tuya-ir-codec.py burst  88 46 10       # 10 complete frames at a 108 ms period
    tuya-ir-codec.py hold   88 46 10       # frame + 10 spec-correct repeats = key held

A NEC receiver treats a complete frame as a new key press and a repeat frame as
"key still held", and these usually drive different logic: volume ramping hangs
off the held-key path, while new presses are debounced. So a volume ramp needs
`hold`, not `burst`.

The Tuya container stores durations as uint16, capping a single gap at 65535 us,
while a 110 ms repeat period needs a 98 ms gap. `hold` works around this by
splitting the gap around a 150 us mark, which is below the ~400 us a receiver
needs to register a pulse and is swallowed by its AGC.
"""
import base64
import sys

# NEC protocol timings, microseconds
HDR_MARK, HDR_SPACE = 9000, 4500
RPT_MARK, RPT_SPACE = 9000, 2250
BIT_MARK, ZERO_SPACE, ONE_SPACE = 560, 560, 1690
FRAME_GAP = 40000            # space between the initial frame and the first repeat
REPEAT_GAP = 65535           # uint16 ceiling; the Tuya format cannot encode longer gaps
NEC_PERIOD = 110000          # repeat period, leading edge to leading edge
UINT16_MAX = 65535
BLIP_MARK = 150              # sub-threshold mark used to split an over-long space


def fastlz_decompress(data: bytes) -> bytes:
    out = bytearray()
    i, n = 0, len(data)
    while i < n:
        ctrl = data[i]
        i += 1
        op = ctrl >> 5
        if op == 0:
            ln = (ctrl & 0x1F) + 1
            out += data[i:i + ln]
            i += ln
        else:
            ln = op
            if ln == 7:
                ln += data[i]
                i += 1
            ofs = ((ctrl & 0x1F) << 8) | data[i]
            i += 1
            ref = len(out) - ofs - 1
            for _ in range(ln + 2):
                out.append(out[ref])
                ref += 1
    return bytes(out)


def fastlz_compress(data: bytes) -> bytes:
    """Greedy FastLZ level 1 encoder. Payloads are a few hundred bytes, so brute force is fine."""
    out, lit = bytearray(), bytearray()
    i, n = 0, len(data)

    def flush():
        nonlocal lit
        while lit:
            chunk = lit[:32]
            out.append(len(chunk) - 1)
            out.extend(chunk)
            lit = lit[32:]

    while i < n:
        best_len = best_ofs = 0
        for j in range(max(0, i - 8191), i):
            ln = 0
            while i + ln < n and ln < 264 and data[j + ln] == data[i + ln]:
                ln += 1
            if ln > best_len:
                best_len, best_ofs = ln, i - j - 1
        if best_len >= 3:
            flush()
            ln = best_len - 2
            if ln < 7:
                out.append((ln << 5) | (best_ofs >> 8))
                out.append(best_ofs & 0xFF)
            else:
                out.append((7 << 5) | (best_ofs >> 8))
                out.append(ln - 7)
                out.append(best_ofs & 0xFF)
            i += best_len
        else:
            lit.append(data[i])
            i += 1
    flush()
    return bytes(out)


def durations_to_bytes(d):
    return b"".join(int(x).to_bytes(2, "little") for x in d)


def bytes_to_durations(raw: bytes):
    return [int.from_bytes(raw[k:k + 2], "little") for k in range(0, len(raw) - 1, 2)]


def nec_durations(addr: int, cmd: int, repeats: int = 0):
    """Build raw timings for one NEC frame plus `repeats` NEC repeat frames."""
    d = [HDR_MARK, HDR_SPACE]
    for byte in (addr, addr ^ 0xFF, cmd, cmd ^ 0xFF):
        for bit in range(8):                       # LSB first
            d.append(BIT_MARK)
            d.append(ONE_SPACE if (byte >> bit) & 1 else ZERO_SPACE)
    d.append(BIT_MARK)                             # stop mark
    for k in range(repeats):
        d.append(FRAME_GAP if k == 0 else REPEAT_GAP)
        d += [RPT_MARK, RPT_SPACE, BIT_MARK]
    return d


def nec_burst(addr: int, cmd: int, frames: int = 1, gap: int = FRAME_GAP):
    """Build raw timings for `frames` complete NEC frames separated by `gap` us."""
    one = nec_durations(addr, cmd)
    d = list(one)
    for _ in range(frames - 1):
        d.append(gap)
        d += one
    return d


def long_space(us: int):
    """Emit a space longer than uint16 by splitting it around a sub-threshold mark."""
    if us <= UINT16_MAX:
        return [us]
    out, left = [], us
    while left > UINT16_MAX:
        out += [UINT16_MAX, BLIP_MARK]
        left -= UINT16_MAX + BLIP_MARK
    out.append(left)
    return out


def nec_hold(addr: int, cmd: int, repeats: int = 0):
    """Initial NEC frame plus `repeats` repeat frames at the spec 110 ms period."""
    d = nec_durations(addr, cmd)
    if repeats:
        d += long_space(NEC_PERIOD - sum(d))
    for k in range(repeats):
        d += [RPT_MARK, RPT_SPACE, BIT_MARK]
        if k < repeats - 1:
            d += long_space(NEC_PERIOD - (RPT_MARK + RPT_SPACE + BIT_MARK))
    return d


def nec_decode(d):
    if len(d) < 67:
        return None
    if not (7500 < d[0] < 10500 and 3500 < d[1] < 5500):
        return None
    bits = "".join("1" if d[k + 1] > 1000 else "0" for k in range(2, 66, 2))
    addr = int(bits[0:8][::-1], 2)
    addr_i = int(bits[8:16][::-1], 2)
    cmd = int(bits[16:24][::-1], 2)
    cmd_i = int(bits[24:32][::-1], 2)
    repeats = sum(1 for k in range(67, len(d) - 1)
                  if 7500 < d[k] < 10500 and 1500 < d[k + 1] < 3000)
    return dict(addr=addr, cmd=cmd, repeats=repeats, count=len(d),
                valid=(addr ^ addr_i) == 0xFF and (cmd ^ cmd_i) == 0xFF)


def _pack(d) -> str:
    raw = durations_to_bytes(d)
    code = base64.b64encode(fastlz_compress(raw)).decode()
    if fastlz_decompress(base64.b64decode(code)) != raw:
        raise RuntimeError("compression roundtrip failed")
    return code


def encode(addr: int, cmd: int, repeats: int = 0) -> str:
    return _pack(nec_durations(addr, cmd, repeats))


def burst(addr: int, cmd: int, frames: int = 1, gap: int = FRAME_GAP) -> str:
    return _pack(nec_burst(addr, cmd, frames, gap))


def hold(addr: int, cmd: int, repeats: int = 0) -> str:
    return _pack(nec_hold(addr, cmd, repeats))


def decode(b64: str):
    return nec_decode(bytes_to_durations(fastlz_decompress(base64.b64decode(b64))))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    mode = sys.argv[1]
    if mode == "encode":
        addr, cmd = int(sys.argv[2], 16), int(sys.argv[3], 16)
        repeats = int(sys.argv[4]) if len(sys.argv) > 4 else 0
        print(encode(addr, cmd, repeats))
    elif mode == "burst":
        addr, cmd = int(sys.argv[2], 16), int(sys.argv[3], 16)
        frames = int(sys.argv[4])
        gap = int(sys.argv[5]) if len(sys.argv) > 5 else FRAME_GAP
        print(burst(addr, cmd, frames, gap))
    elif mode == "hold":
        addr, cmd = int(sys.argv[2], 16), int(sys.argv[3], 16)
        print(hold(addr, cmd, int(sys.argv[4])))
    elif mode == "decode":
        for b in sys.argv[2:]:
            print(decode(b))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
