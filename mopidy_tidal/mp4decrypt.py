from __future__ import annotations

"""fMP4 CBCS decryption: parse, decrypt, and clean fragmented MP4 segments.

Pure-Python replacement for mp4decrypt. Handles CBCS pattern encryption
as used by TIDAL (and other DASH/CENC streams). No external binary needed.

Requires: pycryptodome (Crypto.Cipher.AES)

Usage:
    from mopidy_tidal.mp4decrypt import decrypt_init, decrypt_segment, EncryptionParams

    params = decrypt_init(init_segment_bytes, key_hex)
    clean_init = params.clean_init
    for seg in segments:
        clean_seg = decrypt_segment(seg, params)
"""

import struct
from dataclasses import dataclass

_CONTAINERS = frozenset({b"moov", b"trak", b"mdia", b"minf", b"stbl",
                         b"mvex", b"moof", b"traf"})
_ENC_BOXES = frozenset({b"senc", b"saiz", b"saio", b"sbgp", b"sgpd"})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class EncryptionParams:
    """Encryption parameters extracted from an init segment."""

    key: bytes
    constant_iv: bytes
    per_sample_iv_size: int
    crypt_byte_block: int
    skip_byte_block: int
    clean_init: bytes


def decrypt_init(init_data: bytes, key_hex: str) -> EncryptionParams:
    """Parse encryption params from an encrypted init segment and return a
    cleaned (decrypted-ready) init segment.

    The cleaned init has enca renamed to the original codec and sinf removed,
    making it a valid non-encrypted fMP4 init that GStreamer can parse.
    """
    constant_iv, per_sample_iv_size, crypt_block, skip_block = _parse_tenc(init_data)
    return EncryptionParams(
        key=bytes.fromhex(key_hex),
        constant_iv=constant_iv,
        per_sample_iv_size=per_sample_iv_size,
        crypt_byte_block=crypt_block,
        skip_byte_block=skip_block,
        clean_init=_clean_init(init_data),
    )


def decrypt_segment(segment: bytes, params: EncryptionParams) -> bytes:
    """Decrypt and clean a media segment. Returns a valid non-encrypted fMP4
    fragment with mdat decrypted and all encryption boxes removed from moof."""
    return _clean_segment(
        segment, params.key, params.constant_iv,
        params.crypt_byte_block, params.skip_byte_block,
        params.per_sample_iv_size,
    )


# ---------------------------------------------------------------------------
# tenc / trun / tfhd / senc parsing
# ---------------------------------------------------------------------------

def _parse_tenc(init_data: bytes) -> tuple[bytes, int, int, int]:
    """Extract encryption defaults from init segment's tenc box.

    Returns (constant_iv, per_sample_iv_size, crypt_byte_block, skip_byte_block).
    """
    pos = init_data.find(b"tenc")
    if pos < 4:
        raise ValueError("No tenc box in init segment")
    off = pos + 4  # past 'tenc' tag
    version = init_data[off]
    off += 4  # version(1) + flags(3)
    off += 1  # reserved
    if version >= 1:
        crypt_skip = init_data[off]
        crypt_byte_block = (crypt_skip >> 4) & 0xF
        skip_byte_block = crypt_skip & 0xF
    else:
        crypt_byte_block = skip_byte_block = 0
    off += 1
    is_protected = init_data[off]; off += 1
    per_sample_iv_size = init_data[off]; off += 1
    off += 16  # defaultKID
    constant_iv = b""
    if per_sample_iv_size == 0 and is_protected:
        const_iv_size = init_data[off]; off += 1
        constant_iv = init_data[off:off + const_iv_size]
    elif not is_protected:
        raise ValueError(f"tenc: not protected (isProtected={is_protected})")
    return constant_iv, per_sample_iv_size, crypt_byte_block, skip_byte_block


def _parse_trun(segment: bytes) -> tuple[int, list[int]]:
    """Parse trun box. Returns (sample_count, sample_sizes).

    If sample_size_present flag is not set, sizes list will be empty —
    caller should fall back to tfhd default_sample_size.
    """
    pos = segment.find(b"trun")
    if pos < 4:
        raise ValueError("No trun box")
    trun_off = pos - 4
    flags = struct.unpack(">I", segment[trun_off + 8:trun_off + 12])[0] & 0xFFFFFF
    count = struct.unpack(">I", segment[trun_off + 12:trun_off + 16])[0]
    off = trun_off + 16
    if flags & 0x1:
        off += 4  # data_offset
    if flags & 0x4:
        off += 4  # first_sample_flags
    sizes = []
    for _ in range(count):
        if flags & 0x100:
            off += 4  # sample_duration
        if flags & 0x200:
            sizes.append(struct.unpack(">I", segment[off:off + 4])[0])
            off += 4
        if flags & 0x400:
            off += 4  # sample_flags
        if flags & 0x800:
            off += 4  # composition_time_offset
    return count, sizes


def _parse_tfhd_default_size(segment: bytes) -> int:
    """Extract default_sample_size from tfhd, or 0 if not present."""
    pos = segment.find(b"tfhd")
    if pos < 4:
        return 0
    tfhd_off = pos - 4
    flags = struct.unpack(">I", segment[tfhd_off + 8:tfhd_off + 12])[0] & 0xFFFFFF
    off = tfhd_off + 16  # past size + type + ver/flags + track_id
    if flags & 0x1:
        off += 8  # base_data_offset
    if flags & 0x2:
        off += 4  # sample_description_index
    if flags & 0x8:
        off += 4  # default_sample_duration
    if flags & 0x10:
        return struct.unpack(">I", segment[off:off + 4])[0]
    return 0


def _parse_senc(segment: bytes, sample_count: int, iv_size: int) -> list[bytes]:
    """Parse senc box to get per-sample IVs."""
    pos = segment.find(b"senc")
    if pos < 4:
        return []
    senc_off = pos - 4
    flags = struct.unpack(">I", segment[senc_off + 8:senc_off + 12])[0] & 0xFFFFFF
    count = struct.unpack(">I", segment[senc_off + 12:senc_off + 16])[0]
    off = senc_off + 16
    ivs = []
    for _ in range(min(count, sample_count)):
        ivs.append(segment[off:off + iv_size])
        off += iv_size
        if flags & 0x2:  # subsample encryption
            n_sub = struct.unpack(">H", segment[off:off + 2])[0]
            off += 2 + n_sub * 6
    return ivs


def _get_sample_sizes(segment: bytes) -> list[int]:
    """Get sample sizes from trun, falling back to tfhd default."""
    count, sizes = _parse_trun(segment)
    if sizes:
        return sizes
    default_size = _parse_tfhd_default_size(segment)
    if default_size:
        return [default_size] * count
    raise ValueError("No sample sizes in trun or tfhd")


# ---------------------------------------------------------------------------
# CBCS decryption
# ---------------------------------------------------------------------------

def _decrypt_cbcs(
    mdat_body: bytes,
    sample_sizes: list[int],
    key: bytes,
    constant_iv: bytes,
    per_sample_ivs: list[bytes],
    crypt_byte_block: int,
    skip_byte_block: int,
) -> bytes:
    """Decrypt CBCS-encrypted mdat samples.

    CBCS pattern: for every (crypt + skip) blocks of 16 bytes, only the first
    `crypt_byte_block` blocks are encrypted. IV resets per sample.
    When crypt=0 and skip=0, all full 16-byte blocks are encrypted (plain CBC).
    """
    from Crypto.Cipher import AES

    use_pattern = crypt_byte_block > 0 or skip_byte_block > 0
    enc_bytes = crypt_byte_block * 16
    skip_bytes = skip_byte_block * 16

    out = bytearray()
    off = 0
    for i, sz in enumerate(sample_sizes):
        sample = mdat_body[off:off + sz]
        iv = per_sample_ivs[i] if i < len(per_sample_ivs) else constant_iv
        if len(iv) < 16:
            iv = iv + b"\x00" * (16 - len(iv))

        if not use_pattern:
            full = (len(sample) // 16) * 16
            if full:
                out.extend(AES.new(key, AES.MODE_CBC, iv=iv).decrypt(sample[:full]))
                out.extend(sample[full:])
            else:
                out.extend(sample)
        else:
            dec = bytearray()
            pos = 0
            cipher = AES.new(key, AES.MODE_CBC, iv=iv)
            while pos + 16 <= len(sample):
                # Encrypted portion
                avail = len(sample) - pos
                n = min(enc_bytes, avail // 16 * 16)
                if n:
                    dec.extend(cipher.decrypt(sample[pos:pos + n]))
                    pos += n
                # Clear portion
                n = min(skip_bytes, len(sample) - pos)
                dec.extend(sample[pos:pos + n])
                pos += n
            dec.extend(sample[pos:])  # trailing sub-block bytes
            out.extend(dec)
        off += sz
    return bytes(out)


# ---------------------------------------------------------------------------
# MP4 box surgery
# ---------------------------------------------------------------------------

def _fixup_sizes(data: bytes) -> bytes:
    """Recompute all container box sizes bottom-up."""
    def _rebuild(buf: bytes) -> bytes:
        out = bytearray()
        off = 0
        while off + 8 <= len(buf):
            size = struct.unpack(">I", buf[off:off + 4])[0]
            btype = buf[off + 4:off + 8]
            if size < 8:
                out.extend(buf[off:])
                break
            end = min(off + size, len(buf))
            if btype in _CONTAINERS:
                children = _rebuild(buf[off + 8:end])
                out.extend(struct.pack(">I", 8 + len(children)))
                out.extend(btype)
                out.extend(children)
            else:
                out.extend(buf[off:end])
            off += size
        return bytes(out)
    return _rebuild(data)


def _strip_enc_boxes(buf: bytes) -> bytes:
    """Remove encryption-related boxes from a sequence of sibling boxes."""
    out = bytearray()
    off = 0
    while off + 8 <= len(buf):
        size = struct.unpack(">I", buf[off:off + 4])[0]
        btype = buf[off + 4:off + 8]
        if size < 8 or off + size > len(buf):
            out.extend(buf[off:])
            break
        if btype not in _ENC_BOXES:
            out.extend(buf[off:off + size])
        off += size
    return bytes(out)


def _clean_init(init_data: bytes) -> bytes:
    """Strip encryption wrappers: enca -> original codec, remove sinf."""
    enca_pos = init_data.find(b"enca")
    if enca_pos < 4:
        return init_data

    enca_off = enca_pos - 4
    enca_size = struct.unpack(">I", init_data[enca_off:enca_off + 4])[0]

    original_format = b"fLaC"
    sinf_pos = init_data.find(b"sinf", enca_off, enca_off + enca_size)
    sinf_size = 0
    if sinf_pos >= 4:
        frma_pos = init_data.find(b"frma", sinf_pos, enca_off + enca_size)
        if frma_pos >= 0:
            original_format = init_data[frma_pos + 4:frma_pos + 8]

        sinf_off = sinf_pos - 4
        sinf_size = struct.unpack(">I", init_data[sinf_off:sinf_off + 4])[0]
        # Remove sinf bytes
        init_data = init_data[:sinf_off] + init_data[sinf_off + sinf_size:]

    if sinf_size:
        # Subtract sinf_size from enca and all ancestor containers.
        # Must do this BEFORE renaming enca so we can still find it.
        for tag in (b"enca", b"stsd", b"stbl", b"minf", b"mdia", b"trak", b"moov"):
            pos = init_data.find(tag)
            if pos >= 4:
                off = pos - 4
                old = struct.unpack(">I", init_data[off:off + 4])[0]
                init_data = (
                    init_data[:off]
                    + struct.pack(">I", old - sinf_size)
                    + init_data[off + 4:]
                )

    # Rename enca -> original format (after size fixup)
    enca_pos = init_data.find(b"enca")
    if enca_pos >= 0:
        init_data = init_data[:enca_pos] + original_format + init_data[enca_pos + 4:]

    return init_data


def _clean_segment(
    segment: bytes,
    key: bytes,
    constant_iv: bytes,
    crypt_byte_block: int,
    skip_byte_block: int,
    per_sample_iv_size: int,
) -> bytes:
    """Decrypt mdat and strip all encryption boxes from a media segment.

    Returns a valid non-encrypted fMP4 fragment.
    """
    sample_sizes = _get_sample_sizes(segment)
    sample_count = len(sample_sizes)

    per_sample_ivs: list[bytes] = []
    if per_sample_iv_size > 0:
        per_sample_ivs = _parse_senc(segment, sample_count, per_sample_iv_size)

    mdat_pos = segment.find(b"mdat")
    if mdat_pos < 4:
        raise ValueError("No mdat box")
    mdat_off = mdat_pos - 4
    mdat_size = struct.unpack(">I", segment[mdat_off:mdat_off + 4])[0]
    mdat_body = segment[mdat_off + 8:mdat_off + mdat_size]

    dec_body = _decrypt_cbcs(
        mdat_body, sample_sizes, key, constant_iv,
        per_sample_ivs, crypt_byte_block, skip_byte_block,
    )

    # Rebuild moof without encryption boxes
    moof_data = segment[:mdat_off]
    new_body = bytearray()
    off = 8  # skip moof header
    while off + 8 <= len(moof_data):
        size = struct.unpack(">I", moof_data[off:off + 4])[0]
        btype = moof_data[off + 4:off + 8]
        if size < 8 or off + size > len(moof_data):
            new_body.extend(moof_data[off:])
            break
        if btype == b"traf":
            stripped = _strip_enc_boxes(moof_data[off + 8:off + size])
            new_body.extend(struct.pack(">I", 8 + len(stripped)))
            new_body.extend(b"traf")
            new_body.extend(stripped)
        else:
            new_body.extend(moof_data[off:off + size])
        off += size

    new_moof = struct.pack(">I", 8 + len(new_body)) + b"moof" + bytes(new_body)

    # Fix trun data_offset
    trun_pos = new_moof.find(b"trun")
    if trun_pos >= 4:
        trun_off = trun_pos - 4
        flags = struct.unpack(">I", new_moof[trun_off + 8:trun_off + 12])[0] & 0xFFFFFF
        if flags & 0x1:
            do_off = trun_off + 16
            new_moof = (
                new_moof[:do_off]
                + struct.pack(">i", len(new_moof) + 8)
                + new_moof[do_off + 4:]
            )

    return new_moof + struct.pack(">I", 8 + len(dec_body)) + b"mdat" + dec_body
