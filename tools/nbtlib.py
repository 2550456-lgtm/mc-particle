"""最小 NBT 编解码器（只用于生成/校验 Minecraft 结构文件）。

不依赖第三方库。写出来的就是 gzip 压缩的 NBT，也就是 .nbt 结构文件。
"""
import gzip
import os
import struct

TAG_END, TAG_BYTE, TAG_SHORT, TAG_INT, TAG_LONG = 0, 1, 2, 3, 4
TAG_FLOAT, TAG_DOUBLE, TAG_BYTE_ARRAY, TAG_STRING = 5, 6, 7, 8
TAG_LIST, TAG_COMPOUND, TAG_INT_ARRAY, TAG_LONG_ARRAY = 9, 10, 11, 12


class B(int):
    """TAG_Byte"""


class S(int):
    """TAG_Short"""


class I(int):
    """TAG_Int"""


class L(int):
    """TAG_Long"""


class F(float):
    """TAG_Float"""


class D(float):
    """TAG_Double"""


class Str(str):
    """TAG_String"""


class Comp(dict):
    """TAG_Compound"""


class BA(bytes):
    """TAG_Byte_Array"""


class IA(list):
    """TAG_Int_Array"""


class LA(list):
    """TAG_Long_Array"""


_CLASS_TAG = {
    B: TAG_BYTE,
    S: TAG_SHORT,
    I: TAG_INT,
    L: TAG_LONG,
    F: TAG_FLOAT,
    D: TAG_DOUBLE,
    Str: TAG_STRING,
    Comp: TAG_COMPOUND,
}


class Lst:
    """TAG_List。tag 可以传数字 tag，也可以直接传下面的包装类（如 I、Comp）。"""

    def __init__(self, tag, items):
        self.tag = _CLASS_TAG.get(tag, tag)
        self.items = list(items)


def _tag_of(v):
    if isinstance(v, Comp):
        return TAG_COMPOUND
    if isinstance(v, Lst):
        return TAG_LIST
    if isinstance(v, B):
        return TAG_BYTE
    if isinstance(v, S):
        return TAG_SHORT
    if isinstance(v, L):
        return TAG_LONG
    if isinstance(v, I):
        return TAG_INT
    if isinstance(v, F):
        return TAG_FLOAT
    if isinstance(v, D):
        return TAG_DOUBLE
    if isinstance(v, BA):
        return TAG_BYTE_ARRAY
    if isinstance(v, IA):
        return TAG_INT_ARRAY
    if isinstance(v, LA):
        return TAG_LONG_ARRAY
    if isinstance(v, Str):
        return TAG_STRING
    raise TypeError(f"unsupported NBT value: {v!r} ({type(v).__name__})")


def _payload(tag, v):
    if tag == TAG_BYTE:
        return struct.pack(">b", int(v))
    if tag == TAG_SHORT:
        return struct.pack(">h", int(v))
    if tag == TAG_INT:
        return struct.pack(">i", int(v))
    if tag == TAG_LONG:
        return struct.pack(">q", int(v))
    if tag == TAG_FLOAT:
        return struct.pack(">f", float(v))
    if tag == TAG_DOUBLE:
        return struct.pack(">d", float(v))
    if tag == TAG_STRING:
        raw = str(v).encode("utf-8")
        return struct.pack(">H", len(raw)) + raw
    if tag == TAG_LIST:
        body = b"".join(_payload(v.tag, x) for x in v.items)
        return struct.pack(">bi", v.tag, len(v.items)) + body
    if tag == TAG_BYTE_ARRAY:
        raw = bytes(v)
        return struct.pack(">i", len(raw)) + raw
    if tag == TAG_INT_ARRAY:
        return struct.pack(">i", len(v)) + struct.pack(f">{len(v)}i", *v)
    if tag == TAG_LONG_ARRAY:
        return struct.pack(">i", len(v)) + struct.pack(f">{len(v)}q", *v)
    if tag == TAG_COMPOUND:
        body = b""
        for k, val in v.items():
            t = _tag_of(val)
            body += struct.pack(">b", t) + _payload(TAG_STRING, k) + _payload(t, val)
        return body + b"\x00"
    raise TypeError(f"cannot encode tag {tag}")


def dumps(root, root_name=""):
    """把 Comp 编码成未压缩的 NBT 字节串。"""
    return struct.pack(">b", TAG_COMPOUND) + _payload(TAG_STRING, root_name) + _payload(
        TAG_COMPOUND, root
    )


def save(path, root, root_name=""):
    data = dumps(root, root_name)          # 先序列化，失败也不会碰原文件
    tmp = path + ".tmp"
    with gzip.open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)                  # 原子替换
    return path


# ---------------------------------------------------------------- 读回（校验用）


def _read_payload(buf, pos, tag):
    if tag == TAG_BYTE:
        return B(struct.unpack_from(">b", buf, pos)[0]), pos + 1
    if tag == TAG_SHORT:
        return S(struct.unpack_from(">h", buf, pos)[0]), pos + 2
    if tag == TAG_INT:
        return I(struct.unpack_from(">i", buf, pos)[0]), pos + 4
    if tag == TAG_LONG:
        return L(struct.unpack_from(">q", buf, pos)[0]), pos + 8
    if tag == TAG_FLOAT:
        return F(struct.unpack_from(">f", buf, pos)[0]), pos + 4
    if tag == TAG_DOUBLE:
        return D(struct.unpack_from(">d", buf, pos)[0]), pos + 8
    if tag == TAG_STRING:
        n = struct.unpack_from(">H", buf, pos)[0]
        pos += 2
        return Str(buf[pos : pos + n].decode("utf-8")), pos + n
    if tag == TAG_BYTE_ARRAY:
        n = struct.unpack_from(">i", buf, pos)[0]
        return BA(buf[pos + 4 : pos + 4 + n]), pos + 4 + n
    if tag == TAG_INT_ARRAY:
        n = struct.unpack_from(">i", buf, pos)[0]
        vals = struct.unpack_from(f">{n}i", buf, pos + 4) if n else ()
        return IA(vals), pos + 4 + 4 * n
    if tag == TAG_LONG_ARRAY:
        n = struct.unpack_from(">i", buf, pos)[0]
        vals = struct.unpack_from(f">{n}q", buf, pos + 4) if n else ()
        return LA(vals), pos + 4 + 8 * n
    if tag == TAG_LIST:
        sub, n = struct.unpack_from(">bi", buf, pos)
        pos += 5
        items = []
        for _ in range(n):
            v, pos = _read_payload(buf, pos, sub)
            items.append(v)
        return Lst(sub, items), pos
    if tag == TAG_BYTE_ARRAY:
        raw = bytes(v)
        return struct.pack(">i", len(raw)) + raw
    if tag == TAG_INT_ARRAY:
        return struct.pack(">i", len(v)) + struct.pack(f">{len(v)}i", *v)
    if tag == TAG_LONG_ARRAY:
        return struct.pack(">i", len(v)) + struct.pack(f">{len(v)}q", *v)
    if tag == TAG_COMPOUND:
        out = Comp()
        while True:
            t = buf[pos]
            pos += 1
            if t == TAG_END:
                return out, pos
            name, pos = _read_payload(buf, pos, TAG_STRING)
            val, pos = _read_payload(buf, pos, t)
            out[name] = val
    raise TypeError(f"cannot decode tag {tag}")


def load(path):
    with gzip.open(path, "rb") as f:
        buf = f.read()
    tag = buf[0]
    if tag != TAG_COMPOUND:
        raise ValueError("root must be a compound")
    name, pos = _read_payload(buf, 1, TAG_STRING)
    root, pos = _read_payload(buf, pos, TAG_COMPOUND)
    if pos != len(buf):
        raise ValueError(f"trailing bytes: {len(buf) - pos}")
    return root
