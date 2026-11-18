"""粒子墙工作台 · 本地服务

作用：让网页能"自己找 particleImages、自己存图片"，不再需要手点文件夹授权。

启动：
    python server.py            # 默认 8765 端口
    python server.py 9000       # 指定端口

然后浏览器打开 http://127.0.0.1:8765

接口：
    GET  /api/detect?world=<存档绝对路径>
         -> {ok, game, images, imagesExists, datapacks, datapacksExists}
    GET  /api/list?world=<存档绝对路径>
         -> {ok, images:[文件名...]}
    POST /api/save   {"world": "...", "name": "0.png", "data": "<base64>"}
         -> {ok, path}
"""
import base64
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = os.path.join(ROOT, "particle-wall-studio.html")
DEFAULT_PORT = 8765
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


def split_saves(path):
    """把 <gameDir>/saves/<world> 拆成 (gameDir, worldName)；拆不出来返回 (None, None)。"""
    p = str(path or "").replace("\\", "/").rstrip("/")
    m = re.match(r"^(.*?)/saves/([^/]+)$", p, re.I)
    if m:
        return m.group(1), m.group(2)
    return None, None


def resolve(world):
    """由存档路径推导出 particleImages / datapacks 的绝对路径。"""
    world = str(world or "").strip().strip('"')
    game, _name = split_saves(world)
    if game is None:
        # 用户直接给了版本目录（gameDir）
        game = world.rstrip("\\/")
        images = os.path.join(game, "particleImages")
        return {
            "game": game,
            "images": images,
            "imagesExists": os.path.isdir(images),
            "datapacks": None,
            "datapacksExists": False,
        }
    images = os.path.join(game, "particleImages")
    datapacks = os.path.join(world, "datapacks")
    return {
        "game": game,
        "images": images,
        "imagesExists": os.path.isdir(images),
        "datapacks": datapacks,
        "datapacksExists": os.path.isdir(datapacks),
    }


# ------------------------------------------------------------------ 自动定位
def _score_mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def _mc_roots():
    """列出可能存在的 .minecraft 根目录。"""
    roots = []
    for env in ("APPDATA", "LOCALAPPDATA"):
        v = os.environ.get(env)
        if v:
            roots.append(os.path.join(v, ".minecraft"))
    for drive in "CDEFG":
        for pat in ("games\\PCL\\.minecraft", "PCL\\.minecraft", ".minecraft",
                    "Minecraft\\.minecraft", "games\\.minecraft"):
            roots.append(drive + ":\\" + pat)
    # 去重 + 只保留存在的
    out, seen = [], set()
    for r in roots:
        key = os.path.normcase(os.path.abspath(r))
        if key in seen or not os.path.isdir(r):
            continue
        seen.add(key)
        out.append(os.path.abspath(r))
    return out


def auto_detect():
    """找出最近使用过的游戏目录（gameDir）和它下面最新的存档。"""
    candidates = []
    for mc in _mc_roots():
        versions = os.path.join(mc, "versions")
        if os.path.isdir(versions):
            for name in os.listdir(versions):
                gd = os.path.join(versions, name)
                if os.path.isdir(gd):
                    candidates.append(gd)
        candidates.append(mc)          # 没开版本隔离的情况

    if not candidates:
        return None

    def score(gd):
        log = os.path.join(gd, "logs", "latest.log")
        has_img = os.path.isdir(os.path.join(gd, "particleImages"))
        return (_score_mtime(log) if os.path.isfile(log) else 0.0) + (1e9 if has_img else 0.0)

    candidates.sort(key=score, reverse=True)
    game = candidates[0]
    if score(game) <= 0:
        return None

    world = None
    saves = os.path.join(game, "saves")
    if os.path.isdir(saves):
        worlds = [( _score_mtime(os.path.join(saves, w, "level.dat")), w)
                  for w in os.listdir(saves) if os.path.isdir(os.path.join(saves, w))]
        worlds = [x for x in worlds if x[0] > 0]
        if worlds:
            worlds.sort(reverse=True)
            world = os.path.join(saves, worlds[0][1])

    images = os.path.join(game, "particleImages")
    return {
        "ok": True,
        "auto": True,
        "game": game,
        "world": world,
        "images": images,
        "imagesExists": os.path.isdir(images),
        "datapacks": os.path.join(world, "datapacks") if world else None,
        "datapacksExists": bool(world) and os.path.isdir(os.path.join(world, "datapacks")),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "ParticleWallStudio/1.0"

    def log_message(self, fmt, *args):  # 静音，保持控制台干净
        pass

    # ------------------------------------------------------------ 输出工具
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, text):
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # ------------------------------------------------------------ GET
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)

        if u.path in ("/", "/index.html"):
            if not os.path.isfile(HTML_FILE):
                return self._json({"ok": False, "error": "找不到 particle-wall-studio.html"}, 500)
            with open(HTML_FILE, "r", encoding="utf-8") as f:
                return self._html(f.read())

        if u.path == "/api/detect":
            world = (q.get("world") or [""])[0]
            if world:
                info = resolve(world)
                info["ok"] = bool(info.get("game"))
                return self._json(info)
            auto = auto_detect()
            return self._json(auto or {"ok": False, "error": "找不到 Minecraft 目录"})

        if u.path == "/api/list":
            world = (q.get("world") or [""])[0]
            info = resolve(world) if world else (auto_detect() or {})
            names = []
            if info.get("imagesExists"):
                try:
                    names = sorted(
                        n for n in os.listdir(info["images"])
                        if os.path.splitext(n)[1].lower() in ALLOWED_EXT
                    )
                except OSError as e:
                    return self._json({"ok": False, "error": str(e)}, 500)
            return self._json({"ok": True, "images": names, "dir": info.get("images")})

        return self._json({"ok": False, "error": "unknown endpoint"}, 404)

    # ------------------------------------------------------------ POST
    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/api/save":
            return self._json({"ok": False, "error": "unknown endpoint"}, 404)

        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception as e:
            return self._json({"ok": False, "error": "bad json: %s" % e}, 400)

        world = payload.get("world", "")
        name = os.path.basename(str(payload.get("name", "")).strip())
        data = payload.get("data", "")

        if not name:
            return self._json({"ok": False, "error": "文件名为空"}, 400)
        ext = os.path.splitext(name)[1].lower()
        if ext not in ALLOWED_EXT:
            return self._json({"ok": False, "error": "不支持的扩展名: %s" % ext}, 400)

        info = resolve(world) if world else (auto_detect() or {})
        images = info.get("images")
        if not images:
            return self._json({"ok": False, "error": "无法从路径推导 particleImages"}, 400)

        try:
            raw = base64.b64decode(data.split(",")[-1], validate=False)
        except Exception as e:
            return self._json({"ok": False, "error": "图片数据解码失败: %s" % e}, 400)

        written = []
        try:
            # 游戏读取目录（必须叫 particleImages）
            os.makedirs(images, exist_ok=True)
            target = os.path.join(images, name)
            with open(target, "wb") as f:
                f.write(raw)
            written.append(target)

            # 用户自己的素材文件夹（可选，随便放哪儿）
            library = str(payload.get("library", "")).strip().strip('"')
            if library:
                os.makedirs(library, exist_ok=True)
                lib_target = os.path.join(library, name)
                with open(lib_target, "wb") as f:
                    f.write(raw)
                written.append(lib_target)
        except Exception as e:
            return self._json({"ok": False, "error": "写入失败: %s" % e}, 500)

        return self._json({"ok": True, "path": target, "written": written, "bytes": len(raw)})


def main():
    port = DEFAULT_PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("粒子墙工作台已启动： http://127.0.0.1:%d" % port)
    print("页面文件： %s" % HTML_FILE)
    print("按 Ctrl+C 停止")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
