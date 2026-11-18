"""生成一个 4 方块的结构文件，用来一次性验证四件事：

  1. .nbt 结构格式能被这个版本读进去（/place structure 成功）
  2. 结构里的命令方块 NBT 写对了（auto / Command / id 字段）
  3. 方块落地后命令方块会自己开始跑（不需要玩家再点一下）
  4. dust 的 SNBT 颜色语法（1.20.5+）在这个版本上是对的，且 RGB 显示准确

用法：
  python make_probe.py                       # 默认按 1.21.1 (DataVersion 3955)
  python make_probe.py --data-version 4671   # 按 1.21.11 出
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nbtlib import B, Comp, I, L, Lst, Str, load, save  # noqa: E402

# 1.21.1 = 3955,  1.21.11 = 4671   （直接从游戏 jar 的 version.json 的 world_version 读到）
DEFAULT_DATA_VERSION = 3955

PROBE_COMMANDS = [
    (
        "red",
        "particle dust{color:[1.0,0.10,0.10],scale:2.0} ~ ~2 ~1.5 0.4 0.4 0.4 0 60 force",
    ),
    (
        "green",
        "particle dust{color:[0.10,1.0,0.20],scale:2.0} ~ ~2 ~1.5 0.4 0.4 0.4 0 60 force",
    ),
    (
        "blue",
        "particle dust{color:[0.10,0.35,1.0],scale:2.0} ~ ~2 ~1.5 0.4 0.4 0.4 0 60 force",
    ),
    (
        "alive",
        'title @a actionbar {"text":"[probe] command blocks are running","color":"green"}',
    ),
]


def command_block_nbt(index, command):
    """1.21.1 的方块实体 NBT。auto=1b 等于 GUI 里的“保持开启”。"""
    return Comp(
        {
            "id": Str("minecraft:repeating_command_block"),
            "x": I(0),
            "y": I(0),
            "z": I(index),
            "Command": Str(command),
            "auto": B(1),
            "powered": B(0),
            "conditionMet": B(0),
            "TrackOutput": B(0),
            "UpdateLastExecution": B(0),
            "LastExecution": L(0),
            "CustomName": Str(f'{{"text":"probe:{PROBE_COMMANDS[index][0]}"}}'),
        }
    )


def build(data_version=DEFAULT_DATA_VERSION):
    n = len(PROBE_COMMANDS)
    palette = [
        Comp(
            {
                "Name": Str("minecraft:repeating_command_block"),
                "Properties": Comp({"facing": Str("north"), "conditional": Str("false")}),
            }
        )
    ]
    blocks = []
    for i in range(n):
        blocks.append(
            Comp(
                {
                    "pos": Lst(I, [I(0), I(0), I(i)]),
                    "state": I(0),
                    "nbt": command_block_nbt(i, PROBE_COMMANDS[i][1]),
                }
            )
        )
    return Comp(
        {
            "DataVersion": I(data_version),
            "size": Lst(I, [I(1), I(1), I(n)]),
            "palette": Lst(Comp, palette),
            "blocks": Lst(Comp, blocks),
            "entities": Lst(Comp, []),
        }
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-version", type=int, default=DEFAULT_DATA_VERSION)
    ap.add_argument("--name", default="mcparticle_probe")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "..", "test", "out"))
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, f"{args.name}.nbt")
    save(path, build(args.data_version))

    # 立刻读回来自检，别把坏文件交出去
    root = load(path)
    assert root["DataVersion"] == args.data_version, root["DataVersion"]
    assert root["size"] == [1, 1, len(PROBE_COMMANDS)], root["size"]
    assert len(root["blocks"]) == len(PROBE_COMMANDS)
    for i, b in enumerate(root["blocks"]):
        assert b["pos"] == [0, 0, i]
        assert b["nbt"]["auto"] == 1
        print(f"  block[{i}] {b['nbt']['CustomName']}")
        print(f"           {b['nbt']['Command']}")
        if i < 3:  # 前三块必须是 dust SNBT 语法，第四块是状态提示
            assert b["nbt"]["Command"].startswith("particle dust{color:["), b["nbt"]["Command"]

    print(f"\nOK  {path}  ({os.path.getsize(path)} bytes)  DataVersion={args.data_version}")


if __name__ == "__main__":
    main()
