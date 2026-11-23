# -*- coding: utf-8 -*-
# 《星际矿工：深渊防线》 STAR MINER: ABYSS LINE
# 单文件 pygame 2.x 游戏，专为 Android + Pydroid 3 触屏设计。
# 所有图形均由 pygame.draw 绘制，无外部资源依赖。

import array
import json
import math
import os
import random
import sys
import time
import traceback

import pygame


# =====================================================================
# 运行平台
# =====================================================================
IS_ANDROID = ("ANDROID_ARGUMENT" in os.environ) or ("ANDROID_APP_PATH" in os.environ) or (sys.platform == "android")


def display_flags():
    return pygame.FULLSCREEN if IS_ANDROID else pygame.RESIZABLE


# =====================================================================
# 基础配置
# =====================================================================
class Config:
    TITLE = "星际矿工：深渊防线"
    SHORT = 480                 # 逻辑分辨率短边
    MIN_LONG = 600
    MAX_LONG = 1180
    WORLD_W = 2400
    WORLD_H = 2400
    TILE = 60
    GRID_W = WORLD_W // TILE    # 40
    GRID_H = WORLD_H // TILE
    MAX_BULLETS = 340
    MAX_PARTICLES = 220
    MAX_DMGTEXT = 60
    MAX_ENEMIES = 80
    MAX_TOWERS = 40
    MAX_PICKUPS = 70
    MAX_BEAMS = 24
    FPS = 60
    MAX_DT = 0.05
    SAVE_NAME = "savegame.json"
    LOG_NAME = "game_error.log"


C_BG = (7, 10, 22)
C_PANEL = (16, 22, 40)
C_PANEL2 = (24, 32, 56)
C_LINE = (58, 78, 120)
C_TEXT = (226, 236, 255)
C_DIM = (140, 160, 195)
C_CYAN = (90, 220, 255)
C_GREEN = (90, 240, 160)
C_RED = (255, 90, 100)
C_YELLOW = (255, 215, 90)
C_PURPLE = (200, 130, 255)
C_ORANGE = (255, 150, 70)
C_BLUE = (110, 170, 255)
C_WHITE = (255, 255, 255)


# =====================================================================
# 工具函数
# =====================================================================
def clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def dist2(ax, ay, bx, by):
    dx = ax - bx
    dy = ay - by
    return dx * dx + dy * dy


def dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def ang_diff(a, b):
    return (b - a + math.pi) % (math.pi * 2.0) - math.pi


def fmt_time(sec):
    sec = int(max(0, sec))
    return "%d:%02d" % (sec // 60, sec % 60)


def find_cjk_font():
    """查找系统里的中文字体；找不到就回退默认字体。"""
    cands = [
        "/system/fonts/NotoSansCJK-Regular.ttc",
        "/system/fonts/NotoSansCJK.ttc",
        "/system/fonts/NotoSansSC-Regular.otf",
        "/system/fonts/NotoSansSC-Regular.ttf",
        "/system/fonts/DroidSansFallback.ttf",
        "/system/fonts/DroidSansChinese.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
    ]
    for d in ("/system/fonts",):
        try:
            for fn in os.listdir(d):
                low = fn.lower()
                if any(k in low for k in ("cjk", "chinese", "fallback", "notosanssc", "sourcehansans", "misans")):
                    cands.append(os.path.join(d, fn))
        except Exception:
            pass
    try:
        for name in ("notosanscjksc", "notosanscjk", "notosanssc", "sourcehansanssc",
                     "wqyzenhei", "droidsansfallback", "microsoftyahei"):
            path = pygame.font.match_font(name)
            if path:
                cands.append(path)
    except Exception:
        pass
    seen = set()
    for path in cands:
        if path in seen or not os.path.isfile(path):
            continue
        seen.add(path)
        try:
            f = pygame.font.Font(path, 20)
            w, h = f.size("测试")
            if w >= 20 and h >= 10:
                return path
        except Exception:
            continue
    return None


class TextRenderer:
    """字体缓存；优先使用系统中文字体，失败则回退 pygame 默认字体。"""

    def __init__(self):
        self.cache = {}
        self.cjk_path = find_cjk_font()

    def font(self, size):
        size = max(8, int(size))
        f = self.cache.get(size)
        if f is None:
            try:
                if self.cjk_path:
                    f = pygame.font.Font(self.cjk_path, size)
                else:
                    f = pygame.font.Font(None, size)
            except Exception:
                try:
                    f = pygame.font.Font(None, size)
                except Exception:
                    f = None
            if f is not None:
                self.cache[size] = f
        return f

    def draw(self, surf, text, size, color, pos, anchor="topleft", shadow=False):
        f = self.font(size)
        if f is None:
            return None
        text = str(text)
        img = f.render(text, True, color)
        rect = img.get_rect()
        try:
            setattr(rect, anchor, (int(pos[0]), int(pos[1])))
        except Exception:
            rect.topleft = (int(pos[0]), int(pos[1]))
        if shadow:
            sh = f.render(text, True, (0, 0, 0))
            surf.blit(sh, (rect.x + 2, rect.y + 2))
        surf.blit(img, rect)
        return rect

    def size(self, text, size):
        f = self.font(size)
        if f is None:
            return (0, 0)
        return f.size(str(text))


def wrap_lines(fonts, text, size, maxw):
    f = fonts.font(size)
    if f is None:
        return [text]
    words = str(text).split()
    lines = []
    cur = ""
    for w in words:
        test = w if not cur else cur + " " + w
        if f.size(test)[0] <= maxw:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# =====================================================================
# 音频：程序化合成，失败自动静音
# =====================================================================
class AudioManager:
    def __init__(self, volume=0.25):
        self.ok = False
        self.volume = clamp(volume, 0.0, 1.0)
        self.sounds = {}
        self.last = {}
        try:
            pygame.mixer.quit()
            pygame.mixer.init(22050, -16, 1, 512)
        except Exception:
            self.ok = False
            return
        try:
            self.rate = 22050
            self.sounds["shoot"] = self._tone(760, 300, 0.07, "square", 0.30)
            self.sounds["laser"] = self._tone(1400, 200, 0.14, "saw", 0.35)
            self.sounds["hit"] = self._tone(300, 120, 0.05, "square", 0.35)
            self.sounds["explode"] = self._noise(0.25, 0.5)
            self.sounds["hurt"] = self._tone(220, 70, 0.20, "saw", 0.5)
            self.sounds["pickup"] = self._tone(600, 1100, 0.09, "sine", 0.35)
            self.sounds["ui"] = self._tone(500, 700, 0.05, "sine", 0.3)
            self.sounds["build"] = self._tone(180, 420, 0.16, "square", 0.4)
            self.sounds["upgrade"] = self._tone(500, 1200, 0.22, "sine", 0.45)
            self.sounds["wave"] = self._tone(160, 90, 0.5, "saw", 0.4)
            self.ok = True
        except Exception:
            self.ok = False

    def _tone(self, f0, f1, dur, kind, vol):
        n = max(1, int(self.rate * dur))
        buf = array.array("h")
        phase = 0.0
        for i in range(n):
            t = i / float(n)
            f = f0 + (f1 - f0) * t
            phase += 2.0 * math.pi * f / self.rate
            if kind == "square":
                v = 1.0 if math.sin(phase) >= 0 else -1.0
            elif kind == "saw":
                v = 2.0 * ((phase / (2.0 * math.pi)) % 1.0) - 1.0
            else:
                v = math.sin(phase)
            env = min(1.0, t * 18.0) * (1.0 - t)
            buf.append(int(v * env * vol * 16000))
        return pygame.mixer.Sound(buffer=buf.tobytes())

    def _noise(self, dur, vol):
        n = max(1, int(self.rate * dur))
        buf = array.array("h")
        rnd = random.Random(7)
        low = 0.0
        for i in range(n):
            t = i / float(n)
            low = low * 0.75 + (rnd.random() * 2.0 - 1.0) * 0.25
            env = (1.0 - t) ** 2
            buf.append(int(low * env * vol * 16000))
        return pygame.mixer.Sound(buffer=buf.tobytes())

    def set_volume(self, v):
        self.volume = clamp(v, 0.0, 1.0)

    def play(self, name, pan=1.0):
        if not self.ok or self.volume <= 0.001:
            return
        now = time.time()
        if now - self.last.get(name, 0.0) < 0.035:
            return
        self.last[name] = now
        s = self.sounds.get(name)
        if s is None:
            return
        try:
            s.set_volume(clamp(self.volume * pan, 0.0, 1.0))
            s.play()
        except Exception:
            pass


# =====================================================================
# 存档
# =====================================================================
class SaveManager:
    def __init__(self):
        self.dir = self._pick_dir()
        self.path = os.path.join(self.dir, Config.SAVE_NAME)
        self.data = self._default()
        self.load()

    def _pick_dir(self):
        cands = []
        try:
            cands.append(os.path.dirname(os.path.abspath(__file__)))
        except Exception:
            pass
        try:
            cands.append(os.getcwd())
        except Exception:
            pass
        for d in cands:
            try:
                if not d or not os.path.isdir(d):
                    continue
                probe = os.path.join(d, ".sm_write_test")
                with open(probe, "w", encoding="utf-8") as f:
                    f.write("ok")
                os.remove(probe)
                return d
            except Exception:
                continue
        return "."

    def _default(self):
        return {
            "version": 1,
            "best_wave": 0,
            "best_kills": 0,
            "total_ore": 0,
            "settings": {
                "volume": 0.25,
                "quality": 0,
                "particles": 1.0,
                "joystick": 1.0,
                "show_fps": True,
                "debug": False,
            },
            "leaderboard": [],
        }

    def load(self):
        try:
            if not os.path.exists(self.path):
                return
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if not isinstance(raw, dict):
                raise ValueError("bad save")
            base = self._default()
            for k in ("best_wave", "best_kills", "total_ore"):
                v = raw.get(k)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    base[k] = max(0, int(v))
            st = raw.get("settings")
            if isinstance(st, dict):
                s = base["settings"]
                for k in ("volume", "particles", "joystick"):
                    v = st.get(k)
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        s[k] = float(v)
                for k in ("quality",):
                    v = st.get(k)
                    if isinstance(v, int) and not isinstance(v, bool):
                        s[k] = int(clamp(v, 0, 1))
                for k in ("show_fps", "debug"):
                    v = st.get(k)
                    if isinstance(v, bool):
                        s[k] = v
                s["volume"] = clamp(s["volume"], 0.0, 1.0)
                s["particles"] = clamp(s["particles"], 0.4, 1.0)
                s["joystick"] = clamp(s["joystick"], 0.8, 1.2)
            lb = raw.get("leaderboard")
            if isinstance(lb, list):
                clean = []
                for e in lb[:8]:
                    if isinstance(e, dict) and isinstance(e.get("wave"), (int, float)):
                        clean.append({
                            "wave": max(0, int(e.get("wave", 0))),
                            "kills": max(0, int(e.get("kills", 0))),
                            "time": max(0, int(e.get("time", 0))),
                            "date": str(e.get("date", ""))[:10],
                        })
                clean.sort(key=lambda e: (-e["wave"], -e["kills"]))
                base["leaderboard"] = clean
            self.data = base
        except Exception:
            self.data = self._default()

    def save(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False)
            os.replace(tmp, self.path)
            return True
        except Exception:
            try:
                with open(self.path, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, ensure_ascii=False)
                return True
            except Exception:
                return False

    def add_score(self, wave, kills, secs):
        lb = self.data.get("leaderboard", [])
        lb.append({
            "wave": int(wave),
            "kills": int(kills),
            "time": int(secs),
            "date": time.strftime("%m-%d"),
        })
        lb.sort(key=lambda e: (-e["wave"], -e["kills"]))
        self.data["leaderboard"] = lb[:8]
        self.data["best_wave"] = max(int(self.data.get("best_wave", 0)), int(wave))
        self.data["best_kills"] = max(int(self.data.get("best_kills", 0)), int(kills))
        return self.save()


# =====================================================================
# 相机
# =====================================================================
class Camera:
    def __init__(self, game):
        self.game = game
        self.x = 0.0
        self.y = 0.0
        self.ox = 0.0
        self.oy = 0.0
        self.shake = 0.0

    def snap(self, target):
        self.x = target.x - self.game.LW * 0.5
        self.y = target.y - self.game.LH * 0.5
        self.clamp_to_world()
        self.ox = 0.0
        self.oy = 0.0

    def clamp_to_world(self):
        g = self.game
        if g.LW >= Config.WORLD_W:
            self.x = (Config.WORLD_W - g.LW) * 0.5
        else:
            self.x = clamp(self.x, 0.0, Config.WORLD_W - g.LW)
        if g.LH >= Config.WORLD_H:
            self.y = (Config.WORLD_H - g.LH) * 0.5
        else:
            self.y = clamp(self.y, 0.0, Config.WORLD_H - g.LH)

    def update(self, dt, target):
        g = self.game
        tx = target.x - g.LW * 0.5
        ty = target.y - g.LH * 0.5
        k = 1.0 - math.exp(-7.0 * dt)
        self.x += (tx - self.x) * k
        self.y += (ty - self.y) * k
        self.clamp_to_world()
        self.shake = max(0.0, self.shake - 34.0 * dt)
        if self.shake > 0.4:
            self.ox = random.uniform(-1.0, 1.0) * self.shake
            self.oy = random.uniform(-1.0, 1.0) * self.shake
        else:
            self.ox = 0.0
            self.oy = 0.0

    def add(self, amount):
        self.shake = min(22.0, self.shake + amount)


# =====================================================================
# 对象池 / 空间哈希
# =====================================================================
class ObjectPool:
    def __init__(self, factory):
        self.factory = factory
        self.free = []

    def acquire(self):
        if self.free:
            return self.free.pop()
        return self.factory()

    def release(self, obj):
        if len(self.free) < 512:
            self.free.append(obj)


class SpatialHash:
    def __init__(self, cell=110):
        self.cell = cell
        self.grid = {}

    def clear(self):
        self.grid.clear()

    def insert(self, obj):
        key = (int(obj.x // self.cell), int(obj.y // self.cell))
        lst = self.grid.get(key)
        if lst is None:
            self.grid[key] = [obj]
        else:
            lst.append(obj)

    def query(self, x, y, radius):
        out = []
        c = self.cell
        x0 = int((x - radius) // c)
        x1 = int((x + radius) // c)
        y0 = int((y - radius) // c)
        y1 = int((y + radius) // c)
        grid = self.grid
        for gy in range(y0, y1 + 1):
            for gx in range(x0, x1 + 1):
                lst = grid.get((gx, gy))
                if lst:
                    out.extend(lst)
        return out


# =====================================================================
# 粒子 / 伤害数字
# =====================================================================
class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size", "color", "grav", "alive")

    def __init__(self):
        self.alive = False

    def setup(self, x, y, vx, vy, life, size, color, grav=0.0):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.life = life
        self.max_life = max(0.01, life)
        self.size = size
        self.color = color
        self.grav = grav
        self.alive = True


class ParticleSystem:
    def __init__(self, limit):
        self.limit = limit
        self.pool = ObjectPool(Particle)
        self.items = []

    def set_limit(self, n):
        self.limit = max(20, int(n))
        while len(self.items) > self.limit:
            p = self.items.pop()
            p.alive = False
            self.pool.release(p)

    def emit(self, x, y, count, color, speed=90.0, life=0.45, size=3.0, angle=None, spread=6.28, grav=0.0):
        if self.limit <= 0:
            return
        count = int(count)
        for _ in range(max(0, count)):
            if len(self.items) >= self.limit:
                break
            p = self.pool.acquire()
            if angle is None:
                a = random.uniform(0.0, 6.2832)
            else:
                a = angle + random.uniform(-spread * 0.5, spread * 0.5)
            sp = random.uniform(0.35, 1.0) * speed
            p.setup(x, y, math.cos(a) * sp, math.sin(a) * sp,
                    life * random.uniform(0.6, 1.2), size * random.uniform(0.6, 1.3),
                    color, grav)
            self.items.append(p)

    def update(self, dt):
        alive = []
        for p in self.items:
            p.life -= dt
            if p.life <= 0.0:
                p.alive = False
                self.pool.release(p)
                continue
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vy += p.grav * dt
            p.vx *= max(0.0, 1.0 - 1.8 * dt)
            p.vy *= max(0.0, 1.0 - 1.8 * dt)
            alive.append(p)
        self.items = alive

    def draw(self, surf, cam, w, h):
        for p in self.items:
            sx = int(p.x - cam.x + cam.ox)
            sy = int(p.y - cam.y + cam.oy)
            if sx < -20 or sy < -20 or sx > w + 20 or sy > h + 20:
                continue
            r = int(max(1.0, p.size * (p.life / p.max_life)))
            pygame.draw.circle(surf, p.color, (sx, sy), r)


class DamageText:
    __slots__ = ("x", "y", "vy", "text", "life", "max_life", "color", "alive")

    def __init__(self):
        self.alive = False

    def setup(self, x, y, text, color, life=0.7):
        self.x = x
        self.y = y
        self.vy = -55.0
        self.text = text
        self.life = life
        self.max_life = life
        self.color = color
        self.alive = True


class DamageTextSystem:
    def __init__(self, limit):
        self.limit = limit
        self.pool = ObjectPool(DamageText)
        self.items = []

    def add(self, x, y, text, color):
        if len(self.items) >= self.limit:
            return
        d = self.pool.acquire()
        d.setup(x + random.uniform(-6, 6), y - 8, str(text), color)
        self.items.append(d)

    def update(self, dt):
        alive = []
        for d in self.items:
            d.life -= dt
            if d.life <= 0:
                d.alive = False
                self.pool.release(d)
                continue
            d.y += d.vy * dt
            d.vy *= (1.0 - 2.0 * dt)
            alive.append(d)
        self.items = alive

    def draw(self, surf, cam, fonts):
        for d in self.items:
            sx = int(d.x - cam.x + cam.ox)
            sy = int(d.y - cam.y + cam.oy)
            if -40 < sx < surf.get_width() + 40 and -30 < sy < surf.get_height() + 30:
                fonts.draw(surf, d.text, 16, d.color, (sx, sy), "center")


# =====================================================================
# 子弹
# =====================================================================
class Bullet:
    __slots__ = ("x", "y", "vx", "vy", "speed", "radius", "damage", "life", "color",
                 "owner", "pierce_left", "homing", "target", "angle", "alive", "hits", "kind")

    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.speed = 0.0
        self.radius = 4.0
        self.damage = 0.0
        self.life = 0.0
        self.color = C_WHITE
        self.owner = "player"
        self.pierce_left = 0
        self.homing = 0.0
        self.target = None
        self.angle = 0.0
        self.alive = False
        self.hits = None
        self.kind = "bolt"

    def setup(self, x, y, ang, speed, dmg, radius, color, owner, life,
              pierce=0, homing=0.0, kind="bolt"):
        self.x = float(x)
        self.y = float(y)
        self.angle = float(ang)
        self.speed = float(speed)
        self.vx = math.cos(ang) * speed
        self.vy = math.sin(ang) * speed
        self.damage = float(dmg)
        self.radius = float(radius)
        self.color = color
        self.owner = owner
        self.life = float(life)
        self.pierce_left = int(pierce)
        self.homing = float(homing)
        self.target = None
        self.hits = []
        self.kind = kind
        self.alive = True


# =====================================================================
# 资源点 / 掉落物
# =====================================================================
class ResourceNode:
    def __init__(self, kind, x, y, rng):
        self.kind = kind
        self.x = float(x)
        self.y = float(y)
        self.amount = {"ore": 34, "crystal": 22, "core": 9}.get(kind, 20)
        self.max_amount = self.amount
        self.respawn = 0.0
        self.phase = rng.uniform(0.0, 6.28)
        self.radius = 25 if kind != "core" else 20
        self.verts = []
        n = 7
        for i in range(n):
            a = i * 6.2832 / n
            rr = self.radius * rng.uniform(0.7, 1.1)
            self.verts.append((math.cos(a) * rr, math.sin(a) * rr))

    def update(self, dt):
        if self.amount <= 0:
            self.respawn -= dt
            if self.respawn <= 0:
                self.amount = self.max_amount
                self.respawn = 0.0


class Pickup:
    __slots__ = ("x", "y", "vx", "vy", "kind", "life", "delay", "alive")

    def __init__(self, kind, x, y):
        self.kind = kind
        self.x = float(x)
        self.y = float(y)
        a = random.uniform(0, 6.28)
        s = random.uniform(30, 90)
        self.vx = math.cos(a) * s
        self.vy = math.sin(a) * s
        self.life = 22.0
        self.delay = 0.45
        self.alive = True

    def update(self, dt, player):
        self.life -= dt
        if self.life <= 0:
            self.alive = False
            return
        if self.delay > 0:
            self.delay -= dt
            self.x += self.vx * dt
            self.y += self.vy * dt
            self.vx *= (1.0 - 2.0 * dt)
            self.vy *= (1.0 - 2.0 * dt)
        else:
            dx = player.x - self.x
            dy = player.y - self.y
            d = math.hypot(dx, dy)
            pull = 380.0 if d < player.magnet else 120.0
            if d > 1:
                self.vx += dx / d * pull * dt
                self.vy += dy / d * pull * dt
            self.x += self.vx * dt
            self.y += self.vy * dt
            self.vx *= (1.0 - 1.5 * dt)
            self.vy *= (1.0 - 1.5 * dt)


# =====================================================================
# 玩家
# =====================================================================
WEAPONS = {
    "pulse": {"name": "脉冲", "cd": 0.20, "heat": 9.0, "dmg": 13.0, "speed": 760.0, "color": (120, 230, 255)},
    "spread": {"name": "散射", "cd": 0.62, "heat": 20.0, "dmg": 9.0, "speed": 640.0, "color": (255, 200, 110)},
    "laser": {"name": "激光", "cd": 0.55, "heat": 26.0, "dmg": 36.0, "speed": 0.0, "color": (255, 110, 200)},
    "homing": {"name": "追踪", "cd": 0.52, "heat": 18.0, "dmg": 26.0, "speed": 430.0, "color": (160, 255, 150)},
}
WEAPON_ORDER = ["pulse", "spread", "laser", "homing"]


class Player:
    def __init__(self, x, y, game):
        self.game = game
        self.x = float(x)
        self.y = float(y)
        self.radius = 15.0
        self.max_hp = 100.0
        self.hp = 100.0
        self.max_shield = 40.0
        self.shield = 40.0
        self.max_energy = 100.0
        self.energy = 100.0
        self.base_speed = 205.0
        self.speed_mult = 1.0
        self.angle = -1.5708
        self.move_x = 0.0
        self.move_y = 0.0
        self.moving = False
        self.firing = False
        self.fire_cd = 0.0
        self.heat = 0.0
        self.overheated = 0.0
        self.dash_cd = 0.0
        self.dash_time = 0.0
        self.dash_cd_max = 1.6
        self.dash_dir_x = 0.0
        self.dash_dir_y = 0.0
        self.invuln = 0.0
        self.hit_flash = 0.0
        self.shield_delay = 0.0
        self.weapon = "pulse"
        self.weapon_levels = {"pulse": 1, "spread": 1, "laser": 1, "homing": 1}
        self.dmg_mult = 1.0
        self.rate_mult = 1.0
        self.crit = 0.05
        self.pierce_bonus = 0
        self.lifesteal = 0.0
        self.explosive = 0.0
        self.magnet = 95.0
        self.thorns = 0.0
        self.slow_aura = 0.0
        self.mine_mult = 1.0
        self.regen = 0.0
        self.xp_mult = 1.0
        self.mine_target = None
        self.mine_progress = 0.0
        self.mine_sound = 0.0
        self.thrust_cd = 0.0
        self.dead = False

    def set_input(self, mx, my, firing):
        self.move_x = mx
        self.move_y = my
        self.firing = firing
        self.moving = (mx * mx + my * my) > 0.02

    def dash(self):
        if self.dash_cd > 0 or self.energy < 25.0:
            return False
        dx, dy = self.move_x, self.move_y
        if abs(dx) + abs(dy) < 0.1:
            dx, dy = math.cos(self.angle), math.sin(self.angle)
        l = math.hypot(dx, dy)
        if l < 0.001:
            return False
        self.dash_dir_x = dx / l
        self.dash_dir_y = dy / l
        self.dash_time = 0.17
        self.dash_cd = self.dash_cd_max
        self.energy = max(0.0, self.energy - 25.0)
        self.invuln = max(self.invuln, 0.28)
        g = self.game
        g.particles.emit(self.x, self.y, 14, (120, 230, 255), speed=200, life=0.4, size=3)
        g.audio.play("build", 0.5)
        return True

    def update(self, dt):
        self.fire_cd = max(0.0, self.fire_cd - dt)
        self.dash_cd = max(0.0, self.dash_cd - dt)
        self.invuln = max(0.0, self.invuln - dt)
        self.hit_flash = max(0.0, self.hit_flash - dt)
        self.shield_delay = max(0.0, self.shield_delay - dt)
        self.mine_sound = max(0.0, self.mine_sound - dt)

        self.energy = min(self.max_energy, self.energy + 15.0 * dt)
        if self.shield_delay <= 0:
            self.shield = min(self.max_shield, self.shield + 7.0 * dt)
        if self.regen > 0:
            self.hp = min(self.max_hp, self.hp + self.regen * dt)

        if self.overheated > 0:
            self.overheated -= dt
            self.heat = max(0.0, self.heat - 55.0 * dt)
        else:
            self.heat = max(0.0, self.heat - 24.0 * dt)

        speed = self.base_speed * self.speed_mult
        if self.dash_time > 0:
            self.dash_time -= dt
            vx = self.dash_dir_x * 620.0
            vy = self.dash_dir_y * 620.0
        else:
            vx = self.move_x * speed
            vy = self.move_y * speed

        self.x += vx * dt
        self.y += vy * dt
        self.x = clamp(self.x, 22.0, Config.WORLD_W - 22.0)
        self.y = clamp(self.y, 22.0, Config.WORLD_H - 22.0)
        self.resolve_obstacles()

        if abs(self.move_x) + abs(self.move_y) > 0.1:
            self.angle = math.atan2(self.move_y, self.move_x)

        self.thrust_cd -= dt
        if self.moving and self.thrust_cd <= 0 and self.dash_time <= 0:
            self.thrust_cd = 0.06
            a = self.angle + math.pi
            self.game.particles.emit(self.x + math.cos(a) * 12, self.y + math.sin(a) * 12,
                                     1, (80, 160, 220), speed=40, life=0.3, size=2.5,
                                     angle=a, spread=0.8)

        if getattr(self, "firing", False):
            self.shoot(dt)

    def resolve_obstacles(self):
        game = self.game
        if game.map is None:
            return
        for ob in game.map.obstacles:
            dx = self.x - ob["x"]
            dy = self.y - ob["y"]
            rr = self.radius + ob["r"] * 0.85
            d2 = dx * dx + dy * dy
            if d2 < rr * rr and d2 > 0.001:
                d = math.sqrt(d2)
                push = (rr - d)
                self.x += dx / d * push
                self.y += dy / d * push

    def aim_point(self):
        g = self.game
        e = g.nearest_enemy(self.x, self.y, 560.0)
        if e is not None:
            return e.x, e.y
        if self.moving:
            return self.x + self.move_x * 100, self.y + self.move_y * 100
        return self.x + math.cos(self.angle) * 100, self.y + math.sin(self.angle) * 100

    def shoot(self, dt):
        if self.fire_cd > 0 or self.overheated > 0:
            return
        g = self.game
        tx, ty = self.aim_point()
        ang = math.atan2(ty - self.y, tx - self.x)
        self.angle = ang
        w = WEAPONS[self.weapon]
        lvl = self.weapon_levels[self.weapon]
        dmg = w["dmg"] * (1.0 + 0.22 * (lvl - 1)) * self.dmg_mult
        cd = w["cd"] / (self.rate_mult * (1.0 + 0.05 * (lvl - 1)))
        self.fire_cd = cd
        self.heat = min(100.0, self.heat + w["heat"])
        if self.heat >= 100.0:
            self.overheated = 1.5

        if self.weapon == "pulse":
            self.spawn_shot(ang, w["speed"], dmg, 4.0, self.pierce_bonus, w["color"])
            g.audio.play("shoot", 0.5)
        elif self.weapon == "spread":
            for i in range(5):
                a = ang + (i - 2) * 0.105
                self.spawn_shot(a, w["speed"], dmg, 3.5, self.pierce_bonus, w["color"])
            g.audio.play("shoot", 0.7)
        elif self.weapon == "laser":
            g.fire_laser(self.x, self.y, ang, 460.0, dmg * 1.3, w["color"])
        else:
            self.spawn_shot(ang, w["speed"], dmg, 5.0, self.pierce_bonus, w["color"], homing=True)
            g.audio.play("laser", 0.35)

    def spawn_shot(self, ang, speed, dmg, radius, pierce, color, homing=False):
        g = self.game
        b = g.spawn_bullet(self.x + math.cos(ang) * 18, self.y + math.sin(ang) * 18,
                           ang, speed, dmg, radius, color, "player", 1.6,
                           pierce=pierce, homing=(3.2 if homing else 0.0))
        if b is not None and homing:
            b.target = g.nearest_enemy(self.x, self.y, 700.0)

    def hurt(self, dmg, ignore_shield=False):
        if self.invuln > 0 or self.dead:
            return
        dmg = max(1.0, float(dmg))
        if self.shield > 0 and not ignore_shield:
            absorb = min(self.shield, dmg)
            self.shield -= absorb
            dmg -= absorb
        if dmg > 0:
            self.hp -= dmg
        self.invuln = 0.55
        self.hit_flash = 0.25
        self.shield_delay = 3.6
        self.game.on_player_hurt(dmg)
        if self.hp <= 0:
            self.hp = 0.0
            self.dead = True

    def add_shield(self, v):
        self.shield = min(self.max_shield, self.shield + v)


# =====================================================================
# 敌人
# =====================================================================
ENEMY_DEFS = {
    "drone":    {"hp": 30.0,  "speed": 100.0, "dmg": 8.0,  "r": 13.0, "xp": 1, "color": (255, 110, 120), "shape": "tri"},
    "shooter":  {"hp": 40.0,  "speed": 76.0,  "dmg": 7.0,  "r": 14.0, "xp": 2, "color": (255, 180, 90),  "shape": "dia"},
    "bomber":   {"hp": 48.0,  "speed": 122.0, "dmg": 26.0, "r": 17.0, "xp": 2, "color": (255, 95, 60),   "shape": "pent"},
    "splitter": {"hp": 62.0,  "speed": 82.0,  "dmg": 10.0, "r": 19.0, "xp": 3, "color": (190, 120, 255), "shape": "hex"},
    "healer":   {"hp": 46.0,  "speed": 64.0,  "dmg": 5.0,  "r": 15.0, "xp": 3, "color": (120, 255, 180), "shape": "cross"},
    "shield":   {"hp": 86.0,  "speed": 60.0,  "dmg": 10.0, "r": 21.0, "xp": 4, "color": (120, 180, 255), "shape": "shield"},
    "elite":    {"hp": 160.0, "speed": 88.0,  "dmg": 14.0, "r": 23.0, "xp": 6, "color": (255, 230, 80),  "shape": "star"},
    "boss":     {"hp": 950.0, "speed": 52.0,  "dmg": 28.0, "r": 46.0, "xp": 40, "color": (255, 70, 180),  "shape": "boss"},
}


class Enemy:
    def __init__(self, kind, x, y, wave, game, hp_scale=1.0):
        d = ENEMY_DEFS[kind]
        self.kind = kind
        self.game = game
        self.x = float(x)
        self.y = float(y)
        self.max_hp = d["hp"] * (1.0 + 0.15 * max(0, wave - 1)) * hp_scale
        self.hp = self.max_hp
        self.speed = d["speed"] * (1.0 + 0.012 * max(0, wave - 1))
        self.damage = d["dmg"] * (1.0 + 0.05 * max(0, wave - 1))
        self.radius = d["r"]
        self.xp = d["xp"]
        self.color = d["color"]
        self.boss = (kind == "boss")
        self.shield = 0.0
        self.shield_max = 0.0
        self.slow = 0.0
        self.hit_flash = 0.0
        self.contact_cd = 0.0
        self.shoot_cd = random.uniform(0.7, 1.8)
        self.aura_cd = random.uniform(0.8, 2.0)
        self.summon_cd = 4.0
        self.charge_cd = 3.0
        self.angle = 0.0
        self.state = "chase"
        self.alive = True
        self.phase = 0
        self.wob = random.uniform(0.0, 6.28)
        self.verts = []
        shape = d["shape"]
        n = {"tri": 3, "dia": 4, "pent": 5, "hex": 6, "cross": 4, "shield": 6, "star": 8, "boss": 10}.get(shape, 5)
        for i in range(n):
            a = i * 6.2832 / n
            rr = self.radius * random.uniform(0.78, 1.12)
            if shape == "star":
                rr = self.radius * (1.15 if i % 2 == 0 else 0.68)
            if shape == "cross":
                self.verts.append((math.cos(a) * self.radius, math.sin(a) * self.radius))
            else:
                self.verts.append((math.cos(a) * rr, math.sin(a) * rr))
        if shape == "cross":
            self.verts = [(0, -self.radius), (self.radius * 0.35, -self.radius * 0.35),
                          (self.radius, 0), (self.radius * 0.35, self.radius * 0.35),
                          (0, self.radius), (-self.radius * 0.35, self.radius * 0.35),
                          (-self.radius, 0), (-self.radius * 0.35, -self.radius * 0.35)]

    def move_toward(self, tx, ty, dt, mult=1.0):
        dx = tx - self.x
        dy = ty - self.y
        d = math.hypot(dx, dy)
        if d > 1.0:
            sp = self.speed * mult * (0.45 if self.slow > 0 else 1.0)
            self.x += dx / d * sp * dt
            self.y += dy / d * sp * dt
            self.angle = math.atan2(dy, dx)

    def keep_away(self, tx, ty, dt, min_dist=200.0):
        dx = self.x - tx
        dy = self.y - ty
        d = math.hypot(dx, dy)
        if d < min_dist and d > 1.0:
            sp = self.speed * (0.7 if self.slow > 0 else 1.0)
            self.x += dx / d * sp * dt
            self.y += dy / d * sp * dt
            self.angle = math.atan2(-dy, -dx)

    def update(self, dt):
        g = self.game
        p = g.player
        if p is None or p.dead:
            return
        self.contact_cd = max(0.0, self.contact_cd - dt)
        self.shoot_cd = max(0.0, self.shoot_cd - dt)
        self.aura_cd = max(0.0, self.aura_cd - dt)
        self.summon_cd = max(0.0, self.summon_cd - dt)
        self.charge_cd = max(0.0, self.charge_cd - dt)
        self.slow = max(0.0, self.slow - dt)
        self.hit_flash = max(0.0, self.hit_flash - dt)
        self.shield = max(0.0, self.shield - dt * 1.5)

        dx = p.x - self.x
        dy = p.y - self.y
        d = math.hypot(dx, dy)
        self.angle = math.atan2(dy, dx) if d > 0.1 else self.angle

        if self.kind == "boss":
            self.update_boss(dt, d)
        elif self.kind == "bomber":
            self.state = "chase"
            self.move_toward(p.x, p.y, dt)
            if d < self.radius + p.radius + 8:
                g.explode(self.x, self.y, 92.0, self.damage, (255, 120, 60), True, True)
                self.alive = False
                return
        elif self.kind in ("shooter", "elite"):
            if d > 300.0:
                self.state = "chase"
                self.move_toward(p.x, p.y, dt)
            elif d < 190.0:
                self.state = "retreat"
                self.keep_away(p.x, p.y, dt, 230.0)
            else:
                self.state = "strafe"
                ang = math.atan2(dy, dx) + 1.57
                self.x += math.cos(ang) * self.speed * 0.55 * dt
                self.y += math.sin(ang) * self.speed * 0.55 * dt
            if self.shoot_cd <= 0 and d < 420.0:
                self.shoot_cd = 1.6 if self.kind == "shooter" else 1.1
                if self.kind == "shooter":
                    self.fire_at(p.x, p.y, 250.0, self.damage * 0.8, 0.06)
                else:
                    for i in range(3):
                        self.fire_at(p.x, p.y, 280.0, self.damage * 0.55, 0.05, (i - 1) * 0.22)
        elif self.kind == "healer":
            self.keep_away(p.x, p.y, dt, 230.0)
            if d > 360.0:
                self.move_toward(p.x, p.y, dt, 0.8)
            if self.aura_cd <= 0:
                self.aura_cd = 1.4
                for e in g.hash_enemies.query(self.x, self.y, 150.0):
                    if e.alive and e is not self and dist2(e.x, e.y, self.x, self.y) < 150.0 * 150.0:
                        e.hp = min(e.max_hp, e.hp + e.max_hp * 0.09)
                        g.particles.emit(e.x, e.y, 2, (120, 255, 180), speed=40, life=0.4, size=2)
                g.particles.emit(self.x, self.y, 8, (90, 230, 160), speed=90, life=0.6, size=2)
        elif self.kind == "shield":
            self.move_toward(p.x, p.y, dt, 0.9)
            if self.aura_cd <= 0:
                self.aura_cd = 2.2
                for e in g.hash_enemies.query(self.x, self.y, 130.0):
                    if e.alive and dist2(e.x, e.y, self.x, self.y) < 130.0 * 130.0:
                        e.shield = max(e.shield, 12.0)
        elif self.kind == "splitter":
            self.move_toward(p.x, p.y, dt)
        else:
            self.move_toward(p.x, p.y, dt)
            if self.kind == "drone":
                self.x += math.cos(g.time * 2.0 + self.wob) * 8.0 * dt
                self.y += math.sin(g.time * 2.2 + self.wob) * 8.0 * dt

        if self.contact_cd <= 0 and not self.boss:
            for tw in g.hash_towers.query(self.x, self.y, 52.0):
                if tw.alive and dist2(tw.x, tw.y, self.x, self.y) < (self.radius + 28.0) ** 2:
                    tw.hp -= self.damage * 0.7
                    self.contact_cd = 1.0
                    g.particles.emit(tw.x, tw.y, 3, (255, 180, 90), speed=50, life=0.3, size=2)
                    if tw.hp <= 0:
                        tw.alive = False
                        g.explode(tw.x, tw.y, 50.0, 1.0, (255, 150, 80), False, False)
                    break

        if not self.boss and d < self.radius + p.radius + 2 and self.contact_cd <= 0:
            if self.kind != "bomber":
                self.contact_cd = 0.85
                p.hurt(self.damage)
        if d < self.radius + p.radius:
            if self.kind != "bomber":
                p.hurt(self.damage * 0.5)

        self.separate(dt)
        self.x = clamp(self.x, 10, Config.WORLD_W - 10)
        self.y = clamp(self.y, 10, Config.WORLD_H - 10)

    def separate(self, dt):
        if self.boss:
            return
        g = self.game
        for o in g.hash_enemies.query(self.x, self.y, self.radius * 2.2):
            if o is self or not o.alive:
                continue
            dx = self.x - o.x
            dy = self.y - o.y
            rr = self.radius + o.radius
            d2 = dx * dx + dy * dy
            if d2 < rr * rr and d2 > 0.01:
                d = math.sqrt(d2)
                f = (rr - d) * 1.6
                self.x += dx / d * f * dt
                self.y += dy / d * f * dt

    def fire_at(self, tx, ty, speed, dmg, spread=0.0, extra=0.0):
        ang = math.atan2(ty - self.y, tx - self.x) + spread + extra
        self.game.spawn_bullet(self.x + math.cos(ang) * self.radius, self.y + math.sin(ang) * self.radius,
                               ang, speed, dmg, 5.0, (255, 120, 140), "enemy", 3.6)

    def update_boss(self, dt, d):
        g = self.game
        p = g.player
        if self.hp > self.max_hp * 0.6:
            phase = 0
        elif self.hp > self.max_hp * 0.3:
            phase = 1
        else:
            phase = 2
        self.phase = phase
        if d > 260:
            self.move_toward(p.x, p.y, dt, 1.0)
        elif d < 160:
            self.keep_away(p.x, p.y, dt, 210)
        else:
            ang = math.atan2(p.y - self.y, p.x - self.x) + 1.57
            self.x += math.cos(ang) * self.speed * 0.6 * dt
            self.y += math.sin(ang) * self.speed * 0.6 * dt
        if self.shoot_cd <= 0:
            self.shoot_cd = 2.3 - phase * 0.35
            n = 10 + phase * 4
            for i in range(n):
                a = i * 6.2832 / n + g.time * 0.4
                g.spawn_bullet(self.x + math.cos(a) * self.radius, self.y + math.sin(a) * self.radius,
                               a, 185.0 + phase * 25, 12.0 + phase * 3, 5.5, (255, 100, 200), "enemy", 4.2)
        if self.summon_cd <= 0:
            self.summon_cd = 6.5 - phase * 1.0
            for i in range(2 + phase):
                a = random.uniform(0, 6.28)
                g.spawn_enemy(random.choice(["drone", "shooter"]),
                              self.x + math.cos(a) * 90, self.y + math.sin(a) * 90, 0.6)
        if self.charge_cd <= 0 and phase == 2:
            self.charge_cd = 4.5
            dx = p.x - self.x
            dy = p.y - self.y
            dd = math.hypot(dx, dy)
            if dd > 1:
                g.spawn_bullet(self.x, self.y, math.atan2(dy, dx), 340.0, 20.0, 12.0, (255, 80, 160), "enemy", 2.0, kind="orb")


# =====================================================================
# 炮塔
# =====================================================================
TOWER_DEFS = {
    "gun":   {"name": "机枪",   "cost": {"ore": 30, "crystal": 0},  "hp": 140.0, "range": 235.0, "cd": 0.55, "dmg": 11.0, "color": (110, 210, 255),  "desc": "快速单发"},
    "frost": {"name": "冰霜", "cost": {"ore": 45, "crystal": 8},  "hp": 120.0, "range": 190.0, "cd": 1.30, "dmg": 6.0,  "color": (140, 230, 255), "desc": "范围减速"},
    "laser": {"name": "激光", "cost": {"ore": 55, "crystal": 18}, "hp": 110.0, "range": 275.0, "cd": 0.95, "dmg": 30.0, "color": (255, 110, 200), "desc": "穿透光束"},
    "miner": {"name": "矿机", "cost": {"ore": 40, "crystal": 6},  "hp": 90.0,  "range": 0.0,   "cd": 2.60, "dmg": 0.0,  "color": (255, 200, 100), "desc": "持续产出矿石"},
}
TOWER_ORDER = ["gun", "frost", "laser", "miner"]


class Tower:
    def __init__(self, kind, gx, gy, game):
        d = TOWER_DEFS[kind]
        self.kind = kind
        self.game = game
        self.gx = gx
        self.gy = gy
        self.x = gx * Config.TILE + Config.TILE * 0.5
        self.y = gy * Config.TILE + Config.TILE * 0.5
        self.level = 1
        self.max_hp = d["hp"]
        self.hp = d["hp"]
        self.range = d["range"]
        self.cd = 0.6
        self.angle = -1.5708
        self.alive = True
        self.invested = {"ore": d["cost"]["ore"], "crystal": d["cost"]["crystal"]}
        self.pulse = 0.0

    def stats(self):
        d = TOWER_DEFS[self.kind]
        mult = 1.0 + (self.level - 1) * 0.45
        rmult = 1.0 + (self.level - 1) * 0.12
        return d["dmg"] * mult, d["range"] * rmult, d["cd"] * (0.92 ** (self.level - 1))

    def update(self, dt):
        g = self.game
        self.cd -= dt
        self.pulse += dt
        if self.kind == "miner":
            if self.cd <= 0:
                self.cd = TOWER_DEFS["miner"]["cd"]
                g.add_resource("ore", 2)
                g.particles.emit(self.x, self.y, 4, (255, 210, 110), speed=50, life=0.5, size=2)
            return
        dmg, rng, cd = self.stats()
        dmg *= g.tower_dmg_mult
        rng *= g.tower_range_mult
        if self.cd > 0:
            return
        target = g.nearest_enemy(self.x, self.y, rng)
        if target is None:
            return
        self.cd = cd
        self.angle = math.atan2(target.y - self.y, target.x - self.x)
        if self.kind == "gun":
            g.spawn_bullet(self.x + math.cos(self.angle) * 20, self.y + math.sin(self.angle) * 20,
                           self.angle, 520.0, dmg, 4.0, (120, 220, 255), "player", 1.8)
        elif self.kind == "laser":
            for e in g.hash_enemies.query(self.x, self.y, rng):
                if not e.alive:
                    continue
                vx = e.x - self.x
                vy = e.y - self.y
                d = math.hypot(vx, vy)
                if d > rng or d < 1:
                    continue
                cross = abs(vx * math.sin(self.angle) - vy * math.cos(self.angle))
                dot = vx * math.cos(self.angle) + vy * math.sin(self.angle)
                if cross < 26.0 and dot > 0:
                    g.damage_enemy(e, dmg, False)
                    g.particles.emit(e.x, e.y, 3, (255, 120, 210), speed=90, life=0.3, size=2)
            g.add_beam(self.x + math.cos(self.angle) * 18, self.y + math.sin(self.angle) * 18,
                       self.x + math.cos(self.angle) * rng, self.y + math.sin(self.angle) * rng,
                       (255, 110, 210), 0.18, 4)
            g.audio.play("laser", 0.4)
        else:
            g.particles.emit(self.x, self.y, 10, (150, 230, 255), speed=120, life=0.45, size=3)
            for e in g.hash_enemies.query(self.x, self.y, rng):
                if e.alive and dist2(e.x, e.y, self.x, self.y) < rng * rng:
                    e.slow = 1.7
                    g.damage_enemy(e, dmg, False)


# =====================================================================
# 程序化地图
# =====================================================================
class MapGenerator:
    def __init__(self, seed):
        self.seed = seed
        self.rng = random.Random(seed)
        self.obstacles = []
        self.nodes = []
        self.blocked = [[False] * Config.GRID_W for _ in range(Config.GRID_H)]
        self.spawn = (Config.WORLD_W * 0.5, Config.WORLD_H * 0.5)
        self._build()
        self.bg = self._render()

    def _build(self):
        rng = self.rng
        cx, cy = self.spawn
        tries = 0
        while len(self.obstacles) < 44 and tries < 500:
            tries += 1
            x = rng.uniform(110, Config.WORLD_W - 110)
            y = rng.uniform(110, Config.WORLD_H - 110)
            r = rng.uniform(26, 68)
            if dist(x, y, cx, cy) < 300 + r:
                continue
            ok = True
            for ob in self.obstacles:
                if dist(x, y, ob["x"], ob["y"]) < r + ob["r"] + 60:
                    ok = False
                    break
            if not ok:
                continue
            verts = []
            n = rng.randint(7, 10)
            for i in range(n):
                a = i * 6.2832 / n
                rr = r * rng.uniform(0.75, 1.15)
                verts.append((math.cos(a) * rr, math.sin(a) * rr))
            self.obstacles.append({"x": x, "y": y, "r": r, "verts": verts,
                                   "tone": rng.randint(-8, 8)})

        def free_spot(x, y, pad=44.0):
            for ob in self.obstacles:
                if dist(x, y, ob["x"], ob["y"]) < ob["r"] + pad:
                    return False
            for nd in self.nodes:
                if dist(x, y, nd.x, nd.y) < 95:
                    return False
            return True

        kinds = ["ore"] * 12 + ["crystal"] * 7 + ["core"] * 3
        rng.shuffle(kinds)
        for kind in kinds:
            for _ in range(50):
                x = rng.uniform(140, Config.WORLD_W - 140)
                y = rng.uniform(140, Config.WORLD_H - 140)
                if dist(x, y, cx, cy) < 150:
                    continue
                if not free_spot(x, y):
                    continue
                self.nodes.append(ResourceNode(kind, x, y, rng))
                break
        # 出生点附近保证有矿
        for i, kind in enumerate(("ore", "ore", "ore", "crystal")):
            a = i * 1.5708 + 0.4
            for attempt in range(24):
                rr = 210 + attempt * 18
                x = cx + math.cos(a) * rr
                y = cy + math.sin(a) * rr
                if free_spot(x, y, 40):
                    self.nodes.append(ResourceNode(kind, x, y, rng))
                    break

        # 标记阻挡格
        for ob in self.obstacles:
            gx0 = max(0, int((ob["x"] - ob["r"] - 18) // Config.TILE))
            gx1 = min(Config.GRID_W - 1, int((ob["x"] + ob["r"] + 18) // Config.TILE))
            gy0 = max(0, int((ob["y"] - ob["r"] - 18) // Config.TILE))
            gy1 = min(Config.GRID_H - 1, int((ob["y"] + ob["r"] + 18) // Config.TILE))
            for gy in range(gy0, gy1 + 1):
                for gx in range(gx0, gx1 + 1):
                    tx = gx * Config.TILE + Config.TILE * 0.5
                    ty = gy * Config.TILE + Config.TILE * 0.5
                    if dist(tx, ty, ob["x"], ob["y"]) < ob["r"] + 26:
                        self.blocked[gy][gx] = True
        for nd in self.nodes:
            gx = int(nd.x // Config.TILE)
            gy = int(nd.y // Config.TILE)
            if 0 <= gx < Config.GRID_W and 0 <= gy < Config.GRID_H:
                self.blocked[gy][gx] = True

    def _render(self):
        rng = random.Random(self.seed ^ 0x5A5A)
        bg = pygame.Surface((Config.WORLD_W, Config.WORLD_H))
        bg.fill((8, 12, 26))
        for _ in range(18):
            x = rng.uniform(0, Config.WORLD_W)
            y = rng.uniform(0, Config.WORLD_H)
            r = rng.uniform(190, 520)
            col = rng.choice([(11, 18, 40), (13, 15, 36), (9, 27, 40), (17, 13, 41)])
            pygame.draw.circle(bg, col, (int(x), int(y)), int(r))
        for _ in range(1200):
            x = int(rng.uniform(0, Config.WORLD_W))
            y = int(rng.uniform(0, Config.WORLD_H))
            b = rng.randint(55, 185)
            s = rng.choice((1, 1, 1, 2))
            bg.fill((b, b, min(255, b + 25)), (x, y, s, s))
        for x in range(0, Config.WORLD_W + 1, Config.TILE * 2):
            pygame.draw.line(bg, (14, 19, 33), (x, 0), (x, Config.WORLD_H))
        for y in range(0, Config.WORLD_H + 1, Config.TILE * 2):
            pygame.draw.line(bg, (14, 19, 33), (0, y), (Config.WORLD_W, y))
        pygame.draw.rect(bg, (30, 44, 70), (0, 0, Config.WORLD_W, Config.WORLD_H), 4)
        try:
            return bg.convert()
        except Exception:
            return bg


# =====================================================================
# 波次
# =====================================================================
class WaveManager:
    def __init__(self, game):
        self.game = game
        self.wave = 0
        self.state = "prep"
        self.timer = 7.0
        self.queue = []
        self.spawn_timer = 0.0
        self.boss_wave = False

    def compose(self, w):
        count = min(7 + w * 2, 44)
        choices = [("drone", 10)]
        if w >= 2:
            choices.append(("shooter", 6))
        if w >= 3:
            choices.append(("bomber", 4))
        if w >= 4:
            choices.append(("splitter", 4))
        if w >= 5:
            choices.append(("healer", 3))
        if w >= 6:
            choices.append(("shield", 3))
        if w >= 7:
            choices.append(("elite", 2))
        total_w = sum(c[1] for c in choices)
        seq = []
        delay = max(0.18, 0.62 - w * 0.02)
        for _ in range(count):
            r = random.uniform(0, total_w)
            acc = 0.0
            pick = "drone"
            for kind, weight in choices:
                acc += weight
                if r <= acc:
                    pick = kind
                    break
            seq.append((pick, delay))
        if w % 5 == 0:
            seq.insert(0, ("boss", 1.4))
            self.boss_wave = True
        else:
            self.boss_wave = False
        return seq

    def start_wave(self):
        self.wave += 1
        self.state = "fight"
        self.queue = self.compose(self.wave)
        self.spawn_timer = 0.6
        if self.boss_wave:
            self.game.banner("第 %d 波  //  深渊首领" % self.wave, 3.0)
        else:
            self.game.banner("第 %d 波" % self.wave, 2.0)
        self.game.audio.play("wave", 0.6)

    def spawn_one(self, kind):
        g = self.game
        p = g.player
        if p is None:
            return
        ang = random.uniform(0, 6.2832)
        dist_min, dist_max = 560.0, 780.0
        if kind == "boss":
            dist_min, dist_max = 620.0, 700.0
        x = p.x + math.cos(ang) * random.uniform(dist_min, dist_max)
        y = p.y + math.sin(ang) * random.uniform(dist_min, dist_max)
        x = clamp(x, 80, Config.WORLD_W - 80)
        y = clamp(y, 80, Config.WORLD_H - 80)
        g.spawn_enemy(kind, x, y, 1.0)

    def update(self, dt):
        g = self.game
        if self.state == "prep":
            self.timer -= dt
            if self.timer <= 0:
                self.start_wave()
            return
        if self.queue:
            self.spawn_timer -= dt
            while self.queue and self.spawn_timer <= 0:
                kind, delay = self.queue.pop(0)
                self.spawn_one(kind)
                self.spawn_timer += delay
        if not self.queue:
            any_alive = False
            for e in g.enemies:
                if e.alive:
                    any_alive = True
                    break
            if not any_alive:
                self.wave_clear()

    def wave_clear(self):
        g = self.game
        ore = 24 + self.wave * 6
        crystal = 7 + self.wave * 3
        g.add_resource("ore", ore)
        g.add_resource("crystal", crystal)
        if self.wave % 5 == 0:
            g.add_resource("core", 3)
            g.pending_upgrades += 1
        if g.player is not None:
            g.player.hp = min(g.player.max_hp, g.player.hp + 28)
            g.player.shield = g.player.max_shield
        self.state = "prep"
        self.timer = 12.0
        g.banner("第 %d 波已清空  +%d 矿石" % (self.wave, ore), 2.4)
        g.audio.play("upgrade", 0.7)


# =====================================================================
# 升级词条
# =====================================================================
def _up_dmg(g):
    g.player.dmg_mult *= 1.20


def _up_rate(g):
    g.player.rate_mult *= 1.15


def _up_speed(g):
    g.player.speed_mult *= 1.10


def _up_hp(g):
    g.player.max_hp += 25
    g.player.hp = min(g.player.max_hp, g.player.hp + 40)


def _up_shield(g):
    g.player.max_shield += 20
    g.player.shield = min(g.player.max_shield, g.player.shield + 25)


def _up_energy(g):
    g.player.max_energy += 25
    g.player.energy = g.player.max_energy


def _up_dash(g):
    g.player.dash_cd_max = max(0.55, g.player.dash_cd_max * 0.78)


def _up_crit(g):
    g.player.crit = min(0.65, g.player.crit + 0.08)


def _up_pierce(g):
    g.player.pierce_bonus += 1


def _up_lifesteal(g):
    g.player.lifesteal = min(0.30, g.player.lifesteal + 0.04)


def _up_explosive(g):
    g.player.explosive = min(0.75, g.player.explosive + 0.15)


def _up_magnet(g):
    g.player.magnet += 45


def _up_tower_dmg(g):
    g.tower_dmg_mult *= 1.20


def _up_tower_range(g):
    g.tower_range_mult *= 1.15


def _up_tower_cost(g):
    g.tower_cost_mult = max(0.50, g.tower_cost_mult * 0.90)


def _up_mine(g):
    g.player.mine_mult *= 1.35


def _up_res(g):
    g.res_mult *= 1.20


def _up_xp(g):
    g.player.xp_mult += 0.20


def _up_regen(g):
    g.player.regen += 1.5


def _up_thorns(g):
    g.player.thorns += 14


def _up_aura(g):
    g.player.slow_aura = min(1, g.player.slow_aura + 1)


def _up_weapons(g):
    for k in WEAPON_ORDER:
        g.player.weapon_levels[k] = min(9, g.player.weapon_levels[k] + 1)


UPGRADES = [
    {"id": "dmg", "name": "超载充能", "desc": "武器伤害 +20%", "color": C_ORANGE, "apply": _up_dmg},
    {"id": "rate", "name": "冷却回路", "desc": "射速 +15%，过热更慢", "color": C_CYAN, "apply": _up_rate},
    {"id": "speed", "name": "推进器", "desc": "移动速度 +10%", "color": C_GREEN, "apply": _up_speed},
    {"id": "hp", "name": "船体装甲", "desc": "生命上限 +25，回复 40", "color": C_RED, "apply": _up_hp},
    {"id": "shield", "name": "神盾电池", "desc": "护盾上限 +20", "color": C_BLUE, "apply": _up_shield},
    {"id": "energy", "name": "聚变核心", "desc": "能量上限 +25，立即回满", "color": C_YELLOW, "apply": _up_energy},
    {"id": "dash", "name": "相位驱动", "desc": "冲刺冷却 -22%", "color": C_CYAN, "apply": _up_dash},
    {"id": "crit", "name": "精准瞄准", "desc": "暴击率 +8%", "color": C_YELLOW, "apply": _up_crit},
    {"id": "pierce", "name": "磁轨弹头", "desc": "子弹穿透 +1", "color": C_PURPLE, "apply": _up_pierce},
    {"id": "leech", "name": "生物虹吸", "desc": "4% 伤害转化为生命", "color": C_GREEN, "apply": _up_lifesteal},
    {"id": "boom", "name": "高爆弹头", "desc": "命中爆炸 +15%", "color": C_ORANGE, "apply": _up_explosive},
    {"id": "magnet", "name": "牵引光束", "desc": "拾取范围 +45", "color": C_BLUE, "apply": _up_magnet},
    {"id": "tdmg", "name": "炮塔增幅", "desc": "炮塔伤害 +20%", "color": C_CYAN, "apply": _up_tower_dmg},
    {"id": "trange", "name": "目标链路", "desc": "炮塔射程 +15%", "color": C_BLUE, "apply": _up_tower_range},
    {"id": "tcost", "name": "建造工厂", "desc": "建造费用 -10%", "color": C_YELLOW, "apply": _up_tower_cost},
    {"id": "mine", "name": "钻头强化", "desc": "采矿速度 +35%", "color": C_ORANGE, "apply": _up_mine},
    {"id": "res", "name": "精炼厂", "desc": "资源获取 +20%", "color": C_GREEN, "apply": _up_res},
    {"id": "xp", "name": "神经链路", "desc": "经验获取 +20%", "color": C_PURPLE, "apply": _up_xp},
    {"id": "regen", "name": "纳米编织", "desc": "每秒回复 1.5 生命", "color": C_GREEN, "apply": _up_regen},
    {"id": "thorns", "name": "反应装甲", "desc": "受击时反伤 14", "color": C_RED, "apply": _up_thorns},
    {"id": "aura", "name": "重力井", "desc": "附近敌人减速", "color": C_PURPLE, "apply": _up_aura},
    {"id": "weapons", "name": "等离子锻造", "desc": "所有武器 +1 级", "color": C_YELLOW, "apply": _up_weapons},
]


class UpgradeSystem:
    def roll(self, n=3):
        return random.sample(UPGRADES, min(n, len(UPGRADES)))


# =====================================================================
# 主游戏
# =====================================================================
STYLES = {
    "primary": ((26, 88, 140), (80, 205, 255)),
    "ghost": ((17, 25, 43), (78, 104, 150)),
    "danger": ((118, 34, 46), (255, 110, 120)),
    "card": ((23, 31, 54), (72, 96, 145)),
    "good": ((26, 82, 60), (90, 240, 160)),
}


class Game:
    def __init__(self):
        pygame.init()
        try:
            pygame.font.init()
        except Exception:
            pass
        self.fonts = TextRenderer()
        self.save = SaveManager()
        self.settings = self.save.data["settings"]
        self.audio = AudioManager(self.settings.get("volume", 0.25))
        self.state = "menu"
        self.prev_state = "menu"
        self.rank_return = "menu"
        self.running = True
        self.fatal = ""
        self.clock = pygame.time.Clock()
        self.t = 0.0
        self.time = 0.0
        self.LW = 480
        self.LH = 800
        self.win = None
        self.win_w = 0
        self.win_h = 0
        self.canvas = None
        self.scaled = None
        self.scaled_size = (1, 1)
        self.scale = 1.0
        self.offx = 0
        self.offy = 0
        self.ui = []
        self.pointers = {}
        self.pressed_ids = set()
        self.fire_fingers = set()
        self.firing = False
        self.toast_text = ""
        self.toast_timer = 0.0
        self.banner_text = ""
        self.banner_timer = 0.0
        self.flash_timer = 0.0
        self.touch_mode = False
        self.last_size_check = 0.0
        self.player = None
        self.map = None
        self.camera = None
        self.wave_mgr = None
        self.bullet_pool = ObjectPool(Bullet)
        self.upgrade_system = UpgradeSystem()
        self.menu_stars = []
        for _ in range(85):
            self.menu_stars.append({
                "x": random.random(), "y": random.random(),
                "s": random.choice((1, 1, 2, 2, 3)),
                "sp": random.uniform(0.006, 0.035),
                "b": random.randint(80, 220),
            })
        self.init_display()
        self.apply_settings()
        self.build_ui()

    # ---------------- 屏幕与缩放 ----------------
    def init_display(self):
        w, h = 720, 1280
        try:
            info = pygame.display.Info()
            if info.current_w and info.current_h and info.current_w > 200 and info.current_h > 200:
                w, h = info.current_w, info.current_h
        except Exception:
            pass
        try:
            self.win = pygame.display.set_mode((w, h), display_flags())
        except Exception:
            try:
                self.win = pygame.display.set_mode((w, h))
            except Exception:
                self.win = pygame.display.set_mode((720, 1280), pygame.FULLSCREEN)
        if IS_ANDROID:
            try:
                pygame.display.set_allow_screensaver(False)
            except Exception:
                pass
        try:
            pygame.display.set_caption(Config.TITLE)
        except Exception:
            pass
        size = self.win.get_size()
        if size[0] < 200 or size[1] < 200:
            size = (720, 1280)
        self.apply_window_size(*size)

    def _calc_logical(self, w, h):
        if w <= 0 or h <= 0:
            w, h = 720, 1280
        if w >= h:
            lh = Config.SHORT
            lw = int(round(lh * w / float(h)))
            lw = clamp(lw, Config.MIN_LONG, Config.MAX_LONG)
            lh = int(round(lw * h / float(w)))
        else:
            lw = Config.SHORT
            lh = int(round(lw * h / float(w)))
            lh = clamp(lh, Config.MIN_LONG, Config.MAX_LONG)
            lw = int(round(lh * w / float(h)))
        return max(320, lw), max(480, lh)

    def apply_window_size(self, w, h):
        self.win_w = max(240, int(w))
        self.win_h = max(320, int(h))
        self.LW, self.LH = self._calc_logical(self.win_w, self.win_h)
        try:
            self.canvas = pygame.Surface((self.LW, self.LH)).convert()
        except Exception:
            self.canvas = pygame.Surface((self.LW, self.LH))
        self.scale = min(self.win_w / float(self.LW), self.win_h / float(self.LH))
        sw = max(1, int(self.LW * self.scale))
        sh = max(1, int(self.LH * self.scale))
        self.scaled_size = (sw, sh)
        self.offx = (self.win_w - sw) // 2
        self.offy = (self.win_h - sh) // 2
        try:
            self.scaled = pygame.Surface((sw, sh)).convert()
        except Exception:
            self.scaled = pygame.Surface((sw, sh))
        self.dim = pygame.Surface((self.LW, self.LH), pygame.SRCALPHA)
        self.dim.fill((0, 0, 0, 185))
        self.vignette = pygame.Surface((self.LW, self.LH), pygame.SRCALPHA)
        for i in range(5):
            a = 55 - i * 9
            pygame.draw.rect(self.vignette, (255, 40, 55, max(0, a)),
                             (i * 7, i * 7, self.LW - i * 14, self.LH - i * 14), 10)
        self.flash_surf = pygame.Surface((self.LW, self.LH), pygame.SRCALPHA)
        for i in range(3):
            pygame.draw.rect(self.flash_surf, (255, 30, 40, 75),
                             (i * 7, i * 7, self.LW - i * 14, self.LH - i * 14), 9)
        if self.camera is not None:
            self.camera.clamp_to_world()

    def screen_to_logical(self, pos):
        x = (pos[0] - self.offx) / max(0.0001, self.scale)
        y = (pos[1] - self.offy) / max(0.0001, self.scale)
        return (clamp(x, 0, self.LW - 1), clamp(y, 0, self.LH - 1))

    # ---------------- 设置 / 存档 ----------------
    def apply_settings(self):
        s = self.settings
        self.audio.set_volume(s.get("volume", 0.25))
        base = 0.55 if int(s.get("quality", 0)) == 0 else 1.0
        limit = int(Config.MAX_PARTICLES * float(s.get("particles", 1.0)) * base)
        if hasattr(self, "particles") and self.particles is not None:
            self.particles.set_limit(limit)
        self.particle_limit_now = limit

    def save_settings(self):
        self.save.data["settings"] = dict(self.settings)
        return self.save.save()

    def save_all(self):
        try:
            self.save.data["settings"] = dict(self.settings)
            self.save.save()
        except Exception:
            pass

    def show_toast(self, text, sec=2.2):
        self.toast_text = str(text)
        self.toast_timer = sec

    def banner(self, text, sec=2.0):
        self.banner_text = str(text)
        self.banner_timer = sec

    def set_state(self, st):
        self.prev_state = self.state
        self.state = st
        self.pointers.clear()
        self.pressed_ids.clear()
        self.fire_fingers.clear()
        self.firing = False
        if self.player is not None:
            self.player.set_input(0.0, 0.0, False)
        self.build_ui()

    # ---------------- 开局 ----------------
    def start_run(self):
        self.new_run()
        self.set_state("playing")
        self.apply_settings()

    def new_run(self):
        seed = random.randrange(1, 1000000000)
        self.run_seed = seed
        self.map = MapGenerator(seed)
        px, py = self.map.spawn
        self.player = Player(px, py, self)
        self.player.firing = False
        self.camera = Camera(self)
        self.camera.snap(self.player)
        self.enemies = []
        self.bullets = []
        self.towers = []
        self.pickups = []
        self.beams = []
        self.res = {"ore": 55, "crystal": 8, "core": 0}
        self.kills = 0
        self.level = 1
        self.xp = 0
        self.xp_next = 8
        self.pending_upgrades = 0
        self.upgrade_choices = []
        self.game_time = 0.0
        self.dead = False
        self.build_menu = False
        self.build_kind = None
        self.selected_tower = None
        self.tower_dmg_mult = 1.0
        self.tower_range_mult = 1.0
        self.tower_cost_mult = 1.0
        self.res_mult = 1.0
        self.hash_enemies = SpatialHash(110)
        self.hash_towers = SpatialHash(150)
        self.particles = ParticleSystem(int(Config.MAX_PARTICLES * self.settings["particles"]))
        self.dmg_text = DamageTextSystem(Config.MAX_DMGTEXT)
        self.bullet_pool = ObjectPool(Bullet)
        self.wave_mgr = WaveManager(self)
        self.toast_text = ""
        self.toast_timer = 0.0
        self.banner_timer = 0.0
        self.flash_timer = 0.0
        self.banner("第 1 波来袭", 2.2)
        self.show_toast("移动 · 采矿 · 建造 · 生存", 3.0)

    # ---------------- 输入 ----------------
    def get_joystick_vector(self):
        for info in self.pointers.values():
            if info.get("role") == "move":
                return info.get("vx", 0.0), info.get("vy", 0.0)
        return 0.0, 0.0

    def update_joystick(self, fid, pos):
        info = self.pointers.get(fid)
        if info is None or info.get("role") != "move":
            return
        r = 60.0 * float(self.settings.get("joystick", 1.0))
        dx = pos[0] - info["bx"]
        dy = pos[1] - info["by"]
        d = math.hypot(dx, dy)
        if d > r:
            dx = dx / d * r
            dy = dy / d * r
        info["kx"] = info["bx"] + dx
        info["ky"] = info["by"] + dy
        vx = dx / r
        vy = dy / r
        if abs(vx) < 0.13 and abs(vy) < 0.13:
            vx = 0.0
            vy = 0.0
        info["vx"] = vx
        info["vy"] = vy

    def button_at(self, pos):
        for b in reversed(self.ui):
            if b["shape"] == "circle":
                if dist2(pos[0], pos[1], b["cx"], b["cy"]) <= b["r"] * b["r"]:
                    return b
            else:
                if b["rect"].collidepoint(pos):
                    return b
        return None

    def on_pointer_down(self, fid, sx, sy):
        pos = self.screen_to_logical((sx, sy))
        if self.state == "playing":
            if self.build_menu:
                b = self.button_at(pos)
                if b is not None and b["id"].startswith("b_"):
                    self.pointers[fid] = {"role": "button", "button": b["id"], "pos": pos}
                    self.pressed_ids.add(b["id"])
                return
            b = self.button_at(pos)
            if b is not None:
                self.pointers[fid] = {"role": "button", "button": b["id"], "pos": pos}
                self.pressed_ids.add(b["id"])
                if b["id"] == "fire":
                    self.pointers[fid]["role"] = "fire"
                    self.fire_fingers.add(fid)
                    self.firing = True
                return
            if pos[0] < self.LW * 0.52 and pos[1] > self.LH * 0.50:
                self.pointers[fid] = {"role": "move", "bx": pos[0], "by": pos[1],
                                      "kx": pos[0], "ky": pos[1], "vx": 0.0, "vy": 0.0}
                self.update_joystick(fid, pos)
                return
            if self.build_kind is not None:
                self.try_place(pos)
                return
            self.select_tower_at(pos)
            return
        b = self.button_at(pos)
        if b is not None:
            self.pointers[fid] = {"role": "button", "button": b["id"], "pos": pos}
            self.pressed_ids.add(b["id"])

    def on_pointer_move(self, fid, sx, sy):
        info = self.pointers.get(fid)
        if info is None:
            return
        pos = self.screen_to_logical((sx, sy))
        info["pos"] = pos
        if info.get("role") == "move":
            self.update_joystick(fid, pos)

    def on_pointer_up(self, fid, sx, sy):
        info = self.pointers.pop(fid, None)
        if info is None:
            return
        pos = self.screen_to_logical((sx, sy))
        self.pressed_ids.discard(info.get("button"))
        role = info.get("role")
        if role == "fire":
            self.fire_fingers.discard(fid)
            self.firing = bool(self.fire_fingers)
            return
        if role == "move":
            return
        if role == "button":
            b = self.button_at(pos)
            if b is not None and b["id"] == info.get("button"):
                self.activate(b["id"])

    def _finger_xy(self, e):
        x = e.x
        y = e.y
        try:
            if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
                w, h = self.win.get_size()
                x = x * w
                y = y * h
        except Exception:
            pass
        return x, y

    def handle_events(self):
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.running = False
            elif e.type == pygame.VIDEORESIZE:
                try:
                    self.win = pygame.display.set_mode((e.w, e.h), display_flags())
                except Exception:
                    pass
                try:
                    self.apply_window_size(*self.win.get_size())
                except Exception:
                    pass
                self.build_ui()
            elif getattr(pygame, "FINGERDOWN", -1) == e.type:
                self.touch_mode = True
                x, y = self._finger_xy(e)
                self.on_pointer_down(e.finger_id, x, y)
            elif getattr(pygame, "FINGERMOTION", getattr(pygame, "FINGERMOVE", -1)) == e.type:
                x, y = self._finger_xy(e)
                self.on_pointer_move(e.finger_id, x, y)
            elif getattr(pygame, "FINGERUP", -1) == e.type:
                x, y = self._finger_xy(e)
                self.on_pointer_up(e.finger_id, x, y)
            elif (e.type == pygame.MOUSEBUTTONDOWN and not self.touch_mode
                  and e.button == 1 and not getattr(e, "touch", False)):
                self.on_pointer_down(1000, e.pos[0], e.pos[1])
            elif (e.type == pygame.MOUSEBUTTONUP and not self.touch_mode
                  and e.button == 1 and not getattr(e, "touch", False)):
                self.on_pointer_up(1000, e.pos[0], e.pos[1])
            elif e.type == pygame.KEYDOWN:
                self.on_key(e.key)

    def on_key(self, k):
        try:
            if k == pygame.K_ESCAPE:
                if self.state == "playing":
                    self.set_state("paused")
                elif self.state == "paused":
                    self.set_state("playing")
                elif self.state in ("settings", "help", "leaderboard"):
                    self.activate("back")
                elif self.state == "menu":
                    self.running = False
            elif k == pygame.K_p:
                if self.state == "playing":
                    self.set_state("paused")
                elif self.state == "paused":
                    self.set_state("playing")
            elif k == pygame.K_b and self.state == "playing" and not self.build_menu:
                self.activate("build")
            elif k == pygame.K_q and self.state == "playing":
                self.cycle_weapon()
            elif k == pygame.K_LSHIFT or k == pygame.K_RSHIFT:
                if self.state == "playing" and self.player is not None:
                    self.player.dash()
            elif self.state == "playing" and self.player is not None:
                for i in range(4):
                    if k == pygame.K_1 + i:
                        self.player.weapon = WEAPON_ORDER[i]
                        self.show_toast("武器：" + WEAPONS[self.player.weapon]["name"])
        except Exception:
            pass

    # ---------------- 按钮动作 ----------------
    def activate(self, aid):
        if not aid:
            return
        self.audio.play("ui", 0.45)
        if aid == "start" or aid == "retry":
            self.start_run()
            return
        if aid == "quit":
            self.save_all()
            self.running = False
            return
        if aid == "settings":
            self.prev_state = self.state
            self.set_state("settings")
            return
        if aid == "help":
            self.prev_state = self.state
            self.set_state("help")
            return
        if aid == "rank":
            self.rank_return = self.state
            self.set_state("leaderboard")
            return
        if aid == "back":
            if self.state == "settings":
                self.save_settings()
            if self.state == "leaderboard":
                self.set_state(self.rank_return if self.rank_return in ("menu", "paused", "gameover") else "menu")
            else:
                self.set_state(self.prev_state if self.prev_state in ("menu", "paused", "gameover") else "menu")
            return
        if aid == "resume":
            self.set_state("playing")
            return
        if aid == "menu":
            self.save_settings()
            self.set_state("menu")
            return
        if aid == "save":
            self.save.data["settings"] = dict(self.settings)
            ok = self.save.save()
            self.show_toast("已保存" if ok else "保存失败")
            self.audio.play("pickup", 0.6)
            return
        if aid == "pause":
            if self.state == "playing":
                self.set_state("paused")
            return
        if aid == "dash":
            if self.state == "playing" and self.player is not None:
                self.player.dash()
            return
        if aid == "weapon":
            if self.state == "playing":
                self.cycle_weapon()
            return
        if aid == "build":
            if self.state != "playing":
                return
            if self.build_menu:
                self.build_menu = False
            elif self.build_kind is not None:
                self.build_kind = None
                self.show_toast("退出建造模式", 1.2)
            else:
                self.build_menu = True
                self.build_kind = None
                self.selected_tower = None
            self.build_ui()
            return
        if aid == "b_close":
            self.build_menu = False
            self.build_kind = None
            self.build_ui()
            return
        if aid in ("b_gun", "b_frost", "b_laser", "b_miner"):
            if self.state == "playing":
                kind = aid[2:]
                cost = self.tower_cost(kind)
                if not self.can_afford(cost):
                    self.show_toast("资源不足")
                    return
                self.build_kind = kind
                self.build_menu = False
                self.show_toast("点击地图放置：" + TOWER_DEFS[kind]["name"], 2.4)
                self.build_ui()
            return
        if aid == "start_wave":
            if self.wave_mgr is not None and self.wave_mgr.state == "prep":
                self.wave_mgr.timer = 0.0
            return
        if aid in ("tup", "tfix", "tsell", "tclose"):
            self.tower_action(aid)
            return
        if aid.startswith("upg") and self.state == "upgrade":
            try:
                idx = int(aid[3:])
            except Exception:
                return
            self.pick_upgrade(idx)
            return
        if aid in ("vol_dn", "vol_up", "vol_val"):
            s = self.settings
            if aid == "vol_dn":
                s["volume"] = clamp(round(s["volume"] - 0.1, 2), 0.0, 1.0)
            elif aid == "vol_up":
                s["volume"] = clamp(round(s["volume"] + 0.1, 2), 0.0, 1.0)
            self.apply_settings()
            self.build_ui()
            return
        if aid == "quality":
            self.settings["quality"] = 1 - int(self.settings["quality"])
            self.apply_settings()
            self.build_ui()
            return
        if aid in ("part_dn", "part_up"):
            s = self.settings
            if aid == "part_dn":
                s["particles"] = clamp(round(s["particles"] - 0.2, 2), 0.4, 1.0)
            else:
                s["particles"] = clamp(round(s["particles"] + 0.2, 2), 0.4, 1.0)
            self.apply_settings()
            self.build_ui()
            return
        if aid in ("joy_dn", "joy_up"):
            s = self.settings
            if aid == "joy_dn":
                s["joystick"] = clamp(round(s["joystick"] - 0.1, 2), 0.8, 1.2)
            else:
                s["joystick"] = clamp(round(s["joystick"] + 0.1, 2), 0.8, 1.2)
            self.build_ui()
            return
        if aid == "fps":
            self.settings["show_fps"] = not bool(self.settings["show_fps"])
            self.build_ui()
            return
        if aid == "debug":
            self.settings["debug"] = not bool(self.settings["debug"])
            self.build_ui()
            return

    def cycle_weapon(self):
        if self.player is None:
            return
        try:
            i = WEAPON_ORDER.index(self.player.weapon)
        except ValueError:
            i = 0
        self.player.weapon = WEAPON_ORDER[(i + 1) % len(WEAPON_ORDER)]
        self.show_toast("武器：" + WEAPONS[self.player.weapon]["name"], 1.2)
        self.audio.play("ui", 0.5)

    # ---------------- 主循环更新 ----------------
    def update(self, dt):
        self.t += dt
        self.time += dt
        if self.toast_timer > 0:
            self.toast_timer -= dt
        if self.banner_timer > 0:
            self.banner_timer -= dt
        if self.flash_timer > 0:
            self.flash_timer -= dt

        if self.t - self.last_size_check > 0.5:
            self.last_size_check = self.t
            try:
                size = self.win.get_size()
                if size != (self.win_w, self.win_h):
                    self.apply_window_size(size[0], size[1])
                    self.build_ui()
            except Exception:
                pass

        if self.state in ("menu", "settings", "help", "leaderboard"):
            for s in self.menu_stars:
                s["y"] += s["sp"] * dt
                if s["y"] > 1.0:
                    s["y"] -= 1.0
        if self.state != "playing":
            return
        if self.build_menu:
            return
        self.update_play(dt)

    def update_play(self, dt):
        p = self.player
        if p is None or self.map is None:
            return
        self.game_time += dt
        mx, my = self.get_joystick_vector()
        firing = bool(self.fire_fingers)
        try:
            keys = pygame.key.get_pressed()
            kx = (1 if (keys[pygame.K_d] or keys[pygame.K_RIGHT]) else 0) - (1 if (keys[pygame.K_a] or keys[pygame.K_LEFT]) else 0)
            ky = (1 if (keys[pygame.K_s] or keys[pygame.K_DOWN]) else 0) - (1 if (keys[pygame.K_w] or keys[pygame.K_UP]) else 0)
            if kx or ky:
                l = math.hypot(kx, ky)
                mx, my = kx / l, ky / l
            if keys[pygame.K_SPACE]:
                firing = True
        except Exception:
            pass
        p.set_input(mx, my, firing)

        self.hash_enemies.clear()
        for e in self.enemies:
            if e.alive:
                self.hash_enemies.insert(e)
        self.hash_towers.clear()
        for t in self.towers:
            self.hash_towers.insert(t)

        if p.slow_aura > 0:
            for e in self.hash_enemies.query(p.x, p.y, 125.0):
                if e.alive and dist2(e.x, e.y, p.x, p.y) < 125.0 * 125.0:
                    e.slow = max(e.slow, 0.35)

        p.update(dt)
        self.update_mining(dt)

        for e in list(self.enemies):
            if e.alive:
                e.update(dt)
        self.update_bullets(dt)
        for t in self.towers:
            if t.alive:
                t.update(dt)
        for nd in self.map.nodes:
            nd.update(dt)
        for pk in self.pickups:
            if pk.alive:
                pk.update(dt, p)

        keep = []
        for pk in self.pickups:
            if not pk.alive:
                continue
            if dist2(pk.x, pk.y, p.x, p.y) < (p.radius + 16) ** 2:
                self.add_resource(pk.kind, 1)
                self.audio.play("pickup", 0.35)
                self.particles.emit(pk.x, pk.y, 4, (180, 255, 220), speed=60, life=0.4, size=2)
                continue
            keep.append(pk)
        self.pickups = keep
        if len(self.pickups) > Config.MAX_PICKUPS:
            self.pickups = self.pickups[:Config.MAX_PICKUPS]
        self.enemies = [e for e in self.enemies if e.alive]
        self.towers = [t for t in self.towers if t.alive]

        self.particles.update(dt)
        self.dmg_text.update(dt)
        for beam in self.beams:
            beam["life"] -= dt
        self.beams = [b for b in self.beams if b["life"] > 0]
        if len(self.beams) > Config.MAX_BEAMS:
            self.beams = self.beams[-Config.MAX_BEAMS:]

        if self.selected_tower is not None and not self.selected_tower.alive:
            self.selected_tower = None
        if self.camera is not None:
            self.camera.update(dt, p)
        if self.wave_mgr is not None:
            self.wave_mgr.update(dt)

        if p.dead and not self.dead:
            self.finish_run()
            return
        if self.pending_upgrades > 0 and self.state == "playing" and not self.build_menu:
            self.open_upgrade()
            return

    def update_bullets(self, dt):
        survivors = []
        p = self.player
        for b in self.bullets:
            if not b.alive:
                continue
            b.life -= dt
            if b.life <= 0:
                b.alive = False
                continue
            if b.homing > 0 and b.target is not None and b.target.alive:
                ta = math.atan2(b.target.y - b.y, b.target.x - b.x)
                b.angle += clamp(ang_diff(b.angle, ta), -b.homing * dt, b.homing * dt)
                b.vx = math.cos(b.angle) * b.speed
                b.vy = math.sin(b.angle) * b.speed
            b.x += b.vx * dt
            b.y += b.vy * dt
            if b.x < 0 or b.y < 0 or b.x > Config.WORLD_W or b.y > Config.WORLD_H:
                b.alive = False
                continue
            if b.owner == "player":
                for e in self.hash_enemies.query(b.x, b.y, b.radius + 40.0):
                    if not e.alive or e in b.hits:
                        continue
                    rr = e.radius + b.radius
                    if dist2(e.x, e.y, b.x, b.y) > rr * rr:
                        continue
                    b.hits.append(e)
                    crit = random.random() < p.crit
                    dmg = b.damage * (2.0 if crit else 1.0)
                    self.damage_enemy(e, dmg, crit)
                    if p.lifesteal > 0:
                        p.hp = min(p.max_hp, p.hp + dmg * p.lifesteal)
                    if p.explosive > 0:
                        self.explode(b.x, b.y, 52.0, b.damage * p.explosive, b.color, True, False)
                    b.pierce_left -= 1
                    if b.pierce_left < 0:
                        b.alive = False
                        break
                if b.alive:
                    survivors.append(b)
            else:
                if p is not None and not p.dead:
                    rr = p.radius + b.radius
                    if dist2(p.x, p.y, b.x, b.y) <= rr * rr:
                        p.hurt(b.damage)
                        self.particles.emit(b.x, b.y, 5, b.color, speed=70, life=0.3, size=2)
                        b.alive = False
                        continue
                if b.alive:
                    survivors.append(b)
        for b in self.bullets:
            if not b.alive:
                self.bullet_pool.release(b)
        self.bullets = survivors

    def update_mining(self, dt):
        p = self.player
        if p is None:
            return
        best = None
        bd = 120.0 * 120.0
        for nd in self.map.nodes:
            if nd.amount <= 0:
                continue
            d = dist2(nd.x, nd.y, p.x, p.y)
            if d < bd:
                bd = d
                best = nd
        p.mine_target = best
        if best is None:
            p.mine_progress = 0.0
            return
        p.mine_progress += dt * 0.95 * p.mine_mult
        if p.mine_progress >= 1.0:
            p.mine_progress = 0.0
            best.amount -= 1
            self.add_resource(best.kind, 1)
            self.particles.emit(best.x, best.y, 4, (200, 255, 210), speed=70, life=0.4, size=2)
            if p.mine_sound <= 0:
                p.mine_sound = 0.45
                self.audio.play("pickup", 0.3)
            if best.amount <= 0:
                best.respawn = 26.0
                self.show_toast("矿点耗尽，正在恢复", 1.5)

    # ---------------- 资源 / 建造 ----------------
    def add_resource(self, kind, n):
        if kind not in self.res:
            return
        amount = n * (self.res_mult if kind in ("ore", "crystal") else 1.0)
        self.res[kind] = self.res.get(kind, 0) + max(0, int(round(amount)))

    def can_afford(self, cost):
        return (self.res.get("ore", 0) >= cost.get("ore", 0) and
                self.res.get("crystal", 0) >= cost.get("crystal", 0) and
                self.res.get("core", 0) >= cost.get("core", 0))

    def spend(self, cost):
        if not self.can_afford(cost):
            return False
        for k, v in cost.items():
            self.res[k] = self.res.get(k, 0) - v
        return True

    def tower_cost(self, kind):
        c = TOWER_DEFS[kind]["cost"]
        return {"ore": int(round(c["ore"] * self.tower_cost_mult)),
                "crystal": int(round(c.get("crystal", 0) * self.tower_cost_mult))}

    def can_place(self, gx, gy):
        if gx < 0 or gy < 0 or gx >= Config.GRID_W or gy >= Config.GRID_H:
            return False
        if self.map.blocked[gy][gx]:
            return False
        for t in self.towers:
            if t.alive and t.gx == gx and t.gy == gy:
                return False
        if len(self.towers) >= Config.MAX_TOWERS:
            return False
        cx = gx * Config.TILE + Config.TILE * 0.5
        cy = gy * Config.TILE + Config.TILE * 0.5
        if dist2(cx, cy, self.player.x, self.player.y) > 340.0 * 340.0:
            return False
        return True

    def try_place(self, pos):
        if self.build_kind is None:
            return
        wx = pos[0] + self.camera.x - self.camera.ox
        wy = pos[1] + self.camera.y - self.camera.oy
        gx = int(wx // Config.TILE)
        gy = int(wy // Config.TILE)
        if not self.can_place(gx, gy):
            self.show_toast("此处无法建造", 1.2)
            self.audio.play("hurt", 0.2)
            return
        cost = self.tower_cost(self.build_kind)
        if not self.spend(cost):
            self.show_toast("资源不足")
            return
        tw = Tower(self.build_kind, gx, gy, self)
        self.towers.append(tw)
        self.selected_tower = tw
        self.particles.emit(tw.x, tw.y, 14, TOWER_DEFS[self.build_kind]["color"], speed=110, life=0.5, size=3)
        self.audio.play("build", 0.7)
        self.show_toast(TOWER_DEFS[self.build_kind]["name"] + " 已上线", 1.4)

    def select_tower_at(self, pos):
        wx = pos[0] + self.camera.x - self.camera.ox
        wy = pos[1] + self.camera.y - self.camera.oy
        best = None
        bd = 52.0 * 52.0
        for t in self.towers:
            d = dist2(t.x, t.y, wx, wy)
            if d < bd:
                bd = d
                best = t
        if best is None:
            self.selected_tower = None
        else:
            self.selected_tower = best

    def tower_action(self, aid):
        t = self.selected_tower
        if t is None:
            return
        if aid == "tclose":
            self.selected_tower = None
            return
        if aid == "tfix":
            cost = {"ore": max(8, int(t.max_hp * 0.06)), "crystal": 0}
            if t.hp >= t.max_hp - 0.5:
                self.show_toast("生命值已满")
                return
            if not self.spend(cost):
                self.show_toast("矿石不足")
                return
            t.hp = min(t.max_hp, t.hp + t.max_hp * 0.45)
            self.show_toast("炮塔已维修")
            return
        if aid == "tsell":
            refund = {"ore": int(t.invested.get("ore", 0) * 0.6),
                      "crystal": int(t.invested.get("crystal", 0) * 0.6)}
            self.add_resource_raw(refund)
            t.alive = False
            self.particles.emit(t.x, t.y, 12, (255, 200, 120), speed=90, life=0.4, size=3)
            self.selected_tower = None
            self.show_toast("炮塔已出售")
            return
        if aid == "tup":
            if t.level >= 3:
                self.show_toast("已满级")
                return
            base = TOWER_DEFS[t.kind]["cost"]
            cost = {"ore": int(base["ore"] * 0.8 * t.level),
                    "crystal": int(base.get("crystal", 0) * 0.8 * t.level)}
            if not self.spend(cost):
                self.show_toast("资源不足")
                return
            t.level += 1
            t.max_hp *= 1.25
            t.hp = t.max_hp
            t.invested["ore"] = t.invested.get("ore", 0) + cost["ore"]
            t.invested["crystal"] = t.invested.get("crystal", 0) + cost["crystal"]
            self.particles.emit(t.x, t.y, 10, C_YELLOW, speed=80, life=0.5, size=3)
            self.audio.play("upgrade", 0.6)
            self.show_toast("炮塔等级 %d" % t.level)

    def add_resource_raw(self, gains):
        for k, v in gains.items():
            self.res[k] = self.res.get(k, 0) + int(v)

    # ---------------- 敌人 / 子弹 / 特效 ----------------
    def nearest_enemy(self, x, y, radius):
        if not hasattr(self, "hash_enemies"):
            return None
        best = None
        bd = radius * radius
        for e in self.hash_enemies.query(x, y, radius):
            if not e.alive:
                continue
            d = dist2(e.x, e.y, x, y)
            if d < bd:
                bd = d
                best = e
        return best

    def spawn_enemy(self, kind, x, y, hp_scale=1.0):
        if kind not in ENEMY_DEFS:
            return None
        if len(self.enemies) >= Config.MAX_ENEMIES and kind != "boss":
            return None
        e = Enemy(kind, x, y, self.wave_mgr.wave if self.wave_mgr else 0, self, hp_scale)
        self.enemies.append(e)
        return e

    def spawn_bullet(self, x, y, ang, speed, dmg, radius, color, owner, life,
                     pierce=0, homing=0.0, kind="bolt"):
        if len(self.bullets) >= Config.MAX_BULLETS:
            return None
        b = self.bullet_pool.acquire()
        b.setup(x, y, ang, speed, dmg, radius, color, owner, life, pierce, homing, kind)
        self.bullets.append(b)
        return b

    def fire_laser(self, x, y, ang, length, dmg, color):
        self.add_beam(x, y, x + math.cos(ang) * length, y + math.sin(ang) * length, color, 0.14, 3)
        self.audio.play("laser", 0.6)
        hit = []
        cos_a = math.cos(ang)
        sin_a = math.sin(ang)
        for i in range(9):
            px = x + cos_a * length * i / 8.0
            py = y + sin_a * length * i / 8.0
            for e in self.hash_enemies.query(px, py, 60.0):
                if not e.alive or e in hit:
                    continue
                dx = e.x - x
                dy = e.y - y
                cross = abs(dx * sin_a - dy * cos_a)
                dot = dx * cos_a + dy * sin_a
                if cross <= e.radius + 15.0 and 0.0 < dot <= length:
                    hit.append(e)
                    crit = self.player is not None and random.random() < self.player.crit
                    self.damage_enemy(e, dmg * (2.0 if crit else 1.0), crit)
        self.particles.emit(x + cos_a * 28, y + sin_a * 28, 4, color,
                            speed=80, life=0.25, size=3, angle=ang, spread=0.8)

    def add_beam(self, x1, y1, x2, y2, color, life, width):
        self.beams.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2,
                           "color": color, "life": life, "max": life, "w": width})

    def explode(self, x, y, radius, damage, color=(255, 160, 80), friendly=True, hurt_player=False):
        self.camera.add(8.0)
        self.audio.play("explode", 0.8)
        self.particles.emit(x, y, 16, color, speed=230, life=0.55, size=4)
        if friendly and hasattr(self, "hash_enemies"):
            for e in self.hash_enemies.query(x, y, radius):
                if e.alive and dist2(e.x, e.y, x, y) <= radius * radius:
                    self.damage_enemy(e, damage, False)
        if hurt_player and self.player is not None and not self.player.dead:
            if dist2(self.player.x, self.player.y, x, y) <= (radius + self.player.radius) ** 2:
                self.player.hurt(damage * 0.8)
        if hurt_player and hasattr(self, "towers"):
            for tw in self.towers:
                if tw.alive and dist2(tw.x, tw.y, x, y) <= (radius + 22.0) ** 2:
                    tw.hp -= damage * 0.6
                    if tw.hp <= 0:
                        tw.alive = False

    def damage_enemy(self, e, dmg, crit=False):
        if not e.alive:
            return
        if e.shield > 0:
            absorb = min(e.shield, dmg)
            e.shield -= absorb
            dmg -= absorb
        if dmg <= 0:
            self.dmg_text.add(e.x, e.y - e.radius, "0", C_DIM)
            return
        e.hp -= dmg
        e.hit_flash = 0.12
        self.dmg_text.add(e.x, e.y - e.radius, str(int(dmg)), C_YELLOW if crit else C_WHITE)
        if e.hp <= 0:
            self.kill_enemy(e)

    def kill_enemy(self, e):
        if not e.alive:
            return
        e.alive = False
        p = self.player
        self.kills += 1
        self.gain_xp(e.xp * (p.xp_mult if p else 1.0))
        self.particles.emit(e.x, e.y, 18 if e.boss else 9, e.color,
                            speed=180 if e.boss else 110, life=0.7 if e.boss else 0.45,
                            size=4 if e.boss else 3)
        self.audio.play("explode", 0.7 if e.boss else 0.35)
        if e.boss:
            self.camera.add(18)
            self.add_resource("core", 6)
            self.add_resource("crystal", 25)
            self.banner("深渊首领已击败", 2.5)
            for i in range(6):
                a = i * 1.047
                self.pickups.append(Pickup("core", e.x + math.cos(a) * 30, e.y + math.sin(a) * 30))
        if e.kind == "splitter":
            for i in range(2):
                a = random.uniform(0, 6.28)
                self.spawn_enemy("drone", e.x + math.cos(a) * 24, e.y + math.sin(a) * 24, 0.55)
        if not e.boss:
            r = random.random()
            if r < 0.42:
                self.pickups.append(Pickup("crystal" if r < 0.14 else "ore", e.x, e.y))
            elif r < 0.48:
                self.pickups.append(Pickup("core", e.x, e.y))

    def gain_xp(self, amount):
        self.xp += amount
        while self.xp >= self.xp_next:
            self.xp -= self.xp_next
            self.level += 1
            self.xp_next = int(self.xp_next * 1.35 + 4)
            self.pending_upgrades += 1
            if self.player is not None:
                self.player.max_hp += 3
                self.player.hp = min(self.player.max_hp, self.player.hp + 12)
            self.show_toast("等级 %d" % self.level, 1.4)
            self.audio.play("upgrade", 0.8)

    def open_upgrade(self):
        if self.state != "playing":
            return
        self.upgrade_choices = self.upgrade_system.roll(3)
        self.set_state("upgrade")
        self.audio.play("upgrade", 0.9)

    def pick_upgrade(self, idx):
        if idx < 0 or idx >= len(self.upgrade_choices):
            return
        up = self.upgrade_choices[idx]
        try:
            up["apply"](self)
        except Exception:
            pass
        self.pending_upgrades = max(0, self.pending_upgrades - 1)
        if self.player is not None:
            self.player.hp = min(self.player.max_hp, self.player.hp + 10)
        self.audio.play("upgrade", 1.0)
        self.particles.emit(self.player.x, self.player.y, 20, up["color"], speed=160, life=0.7, size=4)
        self.show_toast(up["name"] + " 已安装", 1.8)
        if self.pending_upgrades > 0 and self.state == "upgrade":
            self.upgrade_choices = self.upgrade_system.roll(3)
            self.build_ui()
        else:
            self.state = "playing"
            self.build_ui()

    def on_player_hurt(self, dmg):
        self.camera.add(7.0)
        self.flash_timer = 0.18
        self.audio.play("hurt", 0.7)
        p = self.player
        if p is not None and p.thorns > 0:
            for e in self.hash_enemies.query(p.x, p.y, 110.0):
                if e.alive and dist2(e.x, e.y, p.x, p.y) < 110.0 * 110.0:
                    self.damage_enemy(e, p.thorns, False)

    def finish_run(self):
        self.dead = True
        self.player.dead = True
        wave = self.wave_mgr.wave if self.wave_mgr else 0
        if wave > 0 or self.kills > 0 or self.game_time > 3.0:
            self.save.add_score(wave, self.kills, self.game_time)
        self.save.data["total_ore"] = int(self.save.data.get("total_ore", 0)) + int(self.res.get("ore", 0))
        self.save.save()
        self.set_state("gameover")
        self.audio.play("explode", 1.0)

    # ---------------- UI 构建 ----------------
    def add_rect(self, aid, label, rect, size=20, style="primary", skip=False):
        b = {"id": aid, "label": label, "rect": pygame.Rect(int(rect[0]), int(rect[1]),
                                                            int(rect[2]), int(rect[3])),
             "size": size, "style": style, "shape": "rect", "skip": skip}
        self.ui.append(b)
        return b

    def add_circle(self, aid, label, cx, cy, r, size=18, style="primary"):
        b = {"id": aid, "label": label, "cx": int(cx), "cy": int(cy), "r": int(r),
             "size": size, "style": style, "shape": "circle", "skip": False,
             "rect": pygame.Rect(int(cx - r), int(cy - r), int(r * 2), int(r * 2))}
        self.ui.append(b)
        return b

    def build_ui(self):
        self.ui = []
        st = self.state
        if st == "menu":
            self.ui_menu()
        elif st == "settings":
            self.ui_settings()
        elif st == "help":
            self.add_rect("back", "返回", (self.LW // 2 - 90, self.LH - 62, 180, 42), 22, "primary")
        elif st == "leaderboard":
            self.add_rect("back", "返回", (self.LW // 2 - 90, self.LH - 62, 180, 42), 22, "primary")
        elif st == "playing":
            self.ui_playing()
        elif st == "paused":
            self.ui_pause()
        elif st == "upgrade":
            self.ui_upgrade_cards()
        elif st == "gameover":
            self.ui_gameover()

    def menu_layout(self):
        short = self.LH < 620
        ts = int(clamp(self.LW * 0.12, 34, 64))
        if short:
            ts = min(ts, 42)
        ty = int(self.LH * 0.06) if short else int(self.LH * 0.16)
        sub_size = int(ts * 0.62)
        try:
            title_h = self.fonts.font(ts).get_height()
            sub_h = self.fonts.font(sub_size).get_height()
            tag_h = self.fonts.font(12).get_height()
        except Exception:
            title_h = int(ts * 1.45)
            sub_h = int(sub_size * 1.45)
            tag_h = 18
        sub = ty + title_h + 2
        tag = sub + sub_h + 2
        best = tag + tag_h + 10
        by = max(best + (34 if short else 46), int(self.LH * (0.38 if short else 0.40)))
        bh = 40 if short else 44
        gap = 6 if short else 8
        return short, ts, ty, sub, tag, best, by, bh, gap

    def ui_menu(self):
        w = min(320, self.LW - 70)
        x = (self.LW - w) // 2
        short, ts, ty, sub, tag, best, y, h, gap = self.menu_layout()
        self.add_rect("start", "开始游戏", (x, y, w, h), 24 if not short else 21, "primary")
        self.add_rect("rank", "排行榜", (x, y + (h + gap), w, h), 20 if not short else 18, "ghost")
        self.add_rect("settings", "设置", (x, y + (h + gap) * 2, w, h), 20 if not short else 18, "ghost")
        self.add_rect("help", "玩法说明", (x, y + (h + gap) * 3, w, h), 20 if not short else 18, "ghost")
        self.add_rect("quit", "退出", (x, y + (h + gap) * 4, w, h), 20 if not short else 18, "danger")

    def settings_row(self, i):
        return 64 + i * 44

    def ui_settings(self):
        s = self.settings
        lw = self.LW
        for i, key in enumerate(("volume", "quality", "particles", "joystick", "fps", "debug")):
            y = self.settings_row(i)
            if key in ("volume", "particles", "joystick"):
                self.add_rect(key + "_dn", "-", (lw - 176, y, 36, 30), 22, "ghost")
                if key == "volume":
                    val = "%d%%" % int(round(s["volume"] * 100))
                elif key == "particles":
                    val = "%d%%" % int(round(s["particles"] * 100))
                else:
                    val = "%d%%" % int(round(s["joystick"] * 100))
                self.add_rect(key + "_val", val, (lw - 134, y, 72, 30), 16, "card")
                self.add_rect(key + "_up", "+", (lw - 56, y, 36, 30), 22, "ghost")
            elif key == "quality":
                label = "低" if int(s["quality"]) == 0 else "高"
                self.add_rect("quality", label, (lw - 176, y, 156, 30), 17, "ghost")
            elif key == "fps":
                self.add_rect("fps", "开" if s["show_fps"] else "关", (lw - 176, y, 156, 30), 17, "ghost")
            elif key == "debug":
                self.add_rect("debug", "开" if s["debug"] else "关", (lw - 176, y, 156, 30), 17, "ghost")
        self.add_rect("back", "返回并保存", (self.LW // 2 - 100, self.LH - 60, 200, 42), 21, "primary")

    def ui_playing(self):
        lw, lh = self.LW, self.LH
        self.add_circle("fire", "开火", lw - 82, lh - 86, 52, 20, "primary")
        self.add_circle("dash", "冲刺", lw - 180, lh - 46, 26, 12, "ghost")
        self.add_circle("build", "建造", lw - 180, lh - 124, 27, 11, "good")
        self.add_circle("weapon", "武器", lw - 82, lh - 202, 26, 12, "ghost")
        self.add_circle("pause", "暂停", lw - 30, 116, 20, 12, "ghost")
        if self.wave_mgr is not None and self.wave_mgr.state == "prep":
            self.add_rect("start_wave", "开始波次", (lw // 2 - 60, 100, 120, 26), 14, "ghost")
        if self.build_menu:
            self.ui_build_menu()
        if self.selected_tower is not None and not self.build_menu:
            self.ui_tower_panel()

    def ui_build_menu(self):
        lw, lh = self.LW, self.LH
        w = min(440, lw - 30)
        h = min(380, lh - 100)
        x = (lw - w) // 2
        y = (lh - h) // 2
        card_w = (w - 42) // 2
        card_h = (h - 110) // 2
        kinds = TOWER_ORDER
        for i, kind in enumerate(kinds):
            cx = x + 14 + (i % 2) * (card_w + 14)
            cy = y + 52 + (i // 2) * (card_h + 12)
            self.add_rect("b_" + kind, "", (cx, cy, card_w, card_h), 18, "card", True)
        self.add_rect("b_close", "关闭", (lw // 2 - 70, y + h - 44, 140, 36), 18, "ghost")

    def ui_tower_panel(self):
        t = self.selected_tower
        rect = self.tower_panel_rect()
        bx = rect.x + 8
        bw = (rect.w - 16 - 15) // 4
        by = rect.y + 58
        self.add_rect("tup", "升级", (bx, by, bw, 34), 15, "good")
        self.add_rect("tfix", "维修", (bx + (bw + 5), by, bw, 34), 15, "primary")
        self.add_rect("tsell", "出售", (bx + (bw + 5) * 2, by, bw, 34), 15, "danger")
        self.add_rect("tclose", "关闭", (bx + (bw + 5) * 3, by, bw, 34), 15, "ghost")

    def tower_panel_rect(self):
        w = min(300, self.LW - 40)
        return pygame.Rect((self.LW - w) // 2, self.LH - 340, w, 104)

    def ui_pause(self):
        w = min(280, self.LW - 80)
        x = (self.LW - w) // 2
        y = int(self.LH * 0.38)
        self.add_rect("resume", "继续", (x, y, w, 46), 23, "primary")
        self.add_rect("save", "保存", (x, y + 56, w, 42), 20, "good")
        self.add_rect("rank", "排行榜", (x, y + 108, w, 42), 20, "ghost")
        self.add_rect("menu", "返回主菜单", (x, y + 160, w, 42), 17, "danger")

    def ui_upgrade_cards(self):
        lw, lh = self.LW, self.LH
        w = min(560, lw - 56)
        x = (lw - w) // 2
        h = 96
        total = 3 * h + 24
        y0 = max(72, (lh - total) // 2)
        for i in range(3):
            self.add_rect("upg%d" % i, "", (x, y0 + i * (h + 12), w, h), 18, "card", True)

    def ui_gameover(self):
        w = min(280, self.LW - 80)
        x = (self.LW - w) // 2
        y = int(self.LH * 0.56)
        self.add_rect("retry", "再试一次", (x, y, w, 44), 22, "primary")
        self.add_rect("menu", "主菜单", (x, y + 54, w, 40), 19, "ghost")
        self.add_rect("rank", "排行榜", (x, y + 104, w, 40), 19, "ghost")

    # ---------------- 绘制基础 ----------------
    def draw_button(self, b):
        c = self.canvas
        pressed = b["id"] in self.pressed_ids
        fill, edge = STYLES.get(b["style"], STYLES["ghost"])
        if b["id"] == "fire":
            fill, edge = (165, 58, 42), (255, 160, 100)
        elif b["id"] == "build":
            fill, edge = (32, 96, 70), (110, 255, 180)
        elif b["id"] == "dash":
            fill, edge = (26, 66, 96), (110, 220, 255)
        elif b["id"] == "weapon":
            fill, edge = (70, 44, 104), (200, 140, 255)
        if pressed:
            fill = (min(255, fill[0] + 24), min(255, fill[1] + 24), min(255, fill[2] + 24))
        if b["shape"] == "circle":
            cx, cy, r = b["cx"], b["cy"], b["r"]
            pygame.draw.circle(c, (0, 0, 0), (cx + 2, cy + 3), r)
            pygame.draw.circle(c, fill, (cx, cy + (2 if pressed else 0)), r)
            pygame.draw.circle(c, edge, (cx, cy + (2 if pressed else 0)), r, 2)
            if b["label"]:
                self.fonts.draw(c, b["label"], b["size"], C_WHITE,
                                (cx, cy + (2 if pressed else 0)), "center")
        else:
            r = b["rect"].move(0, 2 if pressed else 0)
            pygame.draw.rect(c, (0, 0, 0), r.move(2, 3), border_radius=10)
            pygame.draw.rect(c, fill, r, border_radius=10)
            pygame.draw.rect(c, edge, r, 2, border_radius=10)
            if b["label"]:
                self.fonts.draw(c, b["label"], b["size"], C_WHITE, r.center, "center")

    def draw_ui_buttons(self):
        for b in self.ui:
            if b.get("skip"):
                continue
            self.draw_button(b)

    # ---------------- 场景绘制 ----------------
    def draw(self):
        if self.canvas is None:
            return
        if self.state == "upgrade":
            if self.map is not None:
                self.draw_world()
            self.draw_upgrade()
        else:
            if self.state in ("playing", "paused", "gameover"):
                if self.map is not None:
                    self.draw_world()
                if self.flash_timer > 0 and self.state in ("playing", "paused"):
                    self.flash_surf.set_alpha(int(255 * clamp(self.flash_timer / 0.18, 0, 1)))
                    self.canvas.blit(self.flash_surf, (0, 0))
                if self.state in ("playing", "paused"):
                    self.draw_hud()
            else:
                self.draw_menu_bg()
            if self.state == "menu":
                self.draw_menu()
            elif self.state == "settings":
                self.draw_settings()
            elif self.state == "help":
                self.draw_help()
            elif self.state == "leaderboard":
                self.draw_leaderboard()
            elif self.state == "paused":
                self.draw_pause()
            elif self.state == "gameover":
                self.draw_gameover()
            if self.state == "playing" and self.build_menu:
                self.draw_build_menu()
            self.draw_ui_buttons()

        try:
            pygame.transform.scale(self.canvas, self.scaled_size, self.scaled)
        except Exception:
            try:
                self.scaled = pygame.transform.scale(self.canvas, self.scaled_size)
            except Exception:
                pass
        self.win.fill((0, 0, 0))
        try:
            self.win.blit(self.scaled, (self.offx, self.offy))
        except Exception:
            pass
        pygame.display.flip()

    def draw_menu_bg(self):
        c = self.canvas
        c.fill((6, 9, 20))
        for i in range(10):
            col = (7 + i, 10 + i, 22 + i * 2)
            pygame.draw.rect(c, col, (0, int(self.LH * i / 10.0), self.LW, self.LH // 10 + 2))
        for s in self.menu_stars:
            x = int(s["x"] * self.LW)
            y = int(s["y"] * self.LH)
            b = s["b"]
            pygame.draw.rect(c, (b, b, min(255, b + 30)), (x, y, s["s"], s["s"]))
        pygame.draw.circle(c, (18, 30, 60), (int(self.LW * 0.8), int(self.LH * 0.2)),
                           int(min(self.LW, self.LH) * 0.35))
        pygame.draw.circle(c, (12, 20, 44), (int(self.LW * 0.15), int(self.LH * 0.75)),
                           int(min(self.LW, self.LH) * 0.30))

    def draw_menu(self):
        c = self.canvas
        cx = self.LW // 2
        short, title_size, ty, sub, tag, best_y, by, bh, gap = self.menu_layout()
        self.fonts.draw(c, "星际矿工", title_size, C_CYAN, (cx, ty), "midtop", True)
        self.fonts.draw(c, "深渊防线", int(title_size * 0.62), C_YELLOW,
                        (cx, sub), "midtop", True)
        self.fonts.draw(c, "肉鸽  /  塔防  /  弹幕",
                        12, C_DIM, (cx, tag), "midtop")
        best = int(self.save.data.get("best_wave", 0))
        self.fonts.draw(c, "最高波次  %d" % best, 17, C_ORANGE, (cx, best_y), "midtop")
        self.fonts.draw(c, "触摸屏幕开始", 13, C_DIM, (cx, self.LH - 24), "midtop")

    def draw_settings(self):
        c = self.canvas
        self.fonts.draw(c, "设置", 30, C_CYAN, (self.LW // 2, 20), "midtop", True)
        labels = ["音量", "画质", "粒子", "摇杆", "显示帧率", "调试信息"]
        for i, lab in enumerate(labels):
            self.fonts.draw(c, lab, 18, C_TEXT, (22, self.settings_row(i) + 15), "midleft")
        self.fonts.draw(c, "低画质在手机上更流畅", 12, C_DIM,
                        (self.LW // 2, self.LH - 92), "midtop")

    def draw_help(self):
        c = self.canvas
        self.fonts.draw(c, "玩法说明", 28, C_CYAN, (self.LW // 2, 26), "midtop", True)
        lines = [
            "左侧触摸拖动：移动飞船",
            "开火键：自动瞄准最近的敌人",
            "冲刺键：消耗能量短暂无敌",
            "建造键：选炮塔后点击地图放置",
            "靠近矿点会自动采矿",
            "收集矿石 / 晶体 / 核心",
            "清空波次后三选一强化",
            "每 5 波出现深渊首领",
            "暂停菜单可以保存或退出",
        ]
        y = 82
        for ln in lines:
            self.fonts.draw(c, ln, 15, C_TEXT, (24, y), "midleft")
            y += 27
        self.fonts.draw(c, "无需键盘、网络或外部素材", 13, C_DIM,
                        (self.LW // 2, self.LH - 96), "midtop")

    def draw_leaderboard(self):
        c = self.canvas
        self.fonts.draw(c, "排行榜", 28, C_CYAN, (self.LW // 2, 26), "midtop", True)
        lb = self.save.data.get("leaderboard", [])
        if not lb:
            self.fonts.draw(c, "还没有记录", 18, C_DIM,
                            (self.LW // 2, self.LH // 2 - 20), "midtop")
        else:
            y = 78
            for i, e in enumerate(lb[:8]):
                self.fonts.draw(c, "%d" % (i + 1), 16, C_YELLOW, (30, y), "midleft")
                self.fonts.draw(c, "第 %d 波" % e.get("wave", 0), 19, C_TEXT, (70, y), "midleft")
                self.fonts.draw(c, "%d 击杀" % e.get("kills", 0), 15, C_DIM, (210, y), "midleft")
                self.fonts.draw(c, e.get("date", ""), 13, C_DIM, (self.LW - 20, y), "midright")
                pygame.draw.line(c, (35, 48, 76), (22, y + 14), (self.LW - 22, y + 14))
                y += 38
        self.fonts.draw(c, "按波次、击杀排序，取前 8", 12, C_DIM,
                        (self.LW // 2, self.LH - 92), "midtop")

    def draw_world(self):
        c = self.canvas
        cam = self.camera
        if cam is None or self.map is None:
            return
        left = cam.x - cam.ox
        top = cam.y - cam.oy
        right = left + self.LW
        bottom = top + self.LH
        c.blit(self.map.bg, (-int(left), -int(top)))
        if self.build_kind is not None:
            self.draw_build_grid(left, top, right, bottom)
        for nd in self.map.nodes:
            if left - 70 < nd.x < right + 70 and top - 70 < nd.y < bottom + 70:
                self.draw_node(nd, left, top)
        for ob in self.map.obstacles:
            if left - 120 < ob["x"] < right + 120 and top - 120 < ob["y"] < bottom + 120:
                self.draw_obstacle(ob, left, top)
        if self.selected_tower is not None and self.selected_tower.alive:
            t = self.selected_tower
            rng = t.stats()[1] * self.tower_range_mult
            if rng > 0:
                sx = int(t.x - left)
                sy = int(t.y - top)
                pygame.draw.circle(c, (60, 110, 90), (sx, sy), int(rng), 1)
        for t in self.towers:
            if t.alive and left - 60 < t.x < right + 60 and top - 60 < t.y < bottom + 60:
                self.draw_tower(t, left, top)
        for pk in self.pickups:
            if pk.alive and left - 30 < pk.x < right + 30 and top - 30 < pk.y < bottom + 30:
                sx = int(pk.x - left)
                sy = int(pk.y - top)
                col = {"ore": (190, 190, 210), "crystal": (110, 210, 255), "core": (255, 150, 255)}.get(pk.kind, C_WHITE)
                pygame.draw.circle(c, col, (sx, sy), 5)
                pygame.draw.circle(c, (255, 255, 255), (sx, sy), 5, 1)
        for e in self.enemies:
            if e.alive and left - 80 < e.x < right + 80 and top - 80 < e.y < bottom + 80:
                self.draw_enemy(e, left, top)
        self.draw_player(left, top)
        for b in self.bullets:
            if not b.alive:
                continue
            sx = int(b.x - left)
            sy = int(b.y - top)
            if -20 < sx < self.LW + 20 and -20 < sy < self.LH + 20:
                tx = int(b.x - b.vx * 0.02 - left)
                ty = int(b.y - b.vy * 0.02 - top)
                pygame.draw.line(c, b.color, (tx, ty), (sx, sy), max(1, int(b.radius * 0.7)))
                pygame.draw.circle(c, b.color, (sx, sy), int(b.radius))
        self.particles.draw(c, cam, self.LW, self.LH)
        for beam in self.beams:
            a = clamp(beam["life"] / max(0.01, beam["max"]), 0, 1)
            col = beam["color"]
            w = max(1, int(beam["w"] * a))
            pygame.draw.line(c, col, (int(beam["x1"] - left), int(beam["y1"] - top)),
                             (int(beam["x2"] - left), int(beam["y2"] - top)), w)
        self.dmg_text.draw(c, cam, self.fonts)

    def draw_build_grid(self, left, top, right, bottom):
        c = self.canvas
        gx0 = max(0, int(left // Config.TILE))
        gx1 = min(Config.GRID_W - 1, int(right // Config.TILE) + 1)
        gy0 = max(0, int(top // Config.TILE))
        gy1 = min(Config.GRID_H - 1, int(bottom // Config.TILE) + 1)
        p = self.player
        for gy in range(gy0, gy1 + 1):
            for gx in range(gx0, gx1 + 1):
                if self.map.blocked[gy][gx]:
                    continue
                cx = gx * Config.TILE + Config.TILE * 0.5
                cy = gy * Config.TILE + Config.TILE * 0.5
                if dist2(cx, cy, p.x, p.y) > 340.0 * 340.0:
                    continue
                sx = int(cx - left - Config.TILE * 0.5)
                sy = int(cy - top - Config.TILE * 0.5)
                pygame.draw.rect(c, (33, 64, 50), (sx, sy, Config.TILE, Config.TILE), 1)
        # 幽灵塔
        gx = int(p.x // Config.TILE)
        gy = int(p.y // Config.TILE)
        cx = gx * Config.TILE + Config.TILE * 0.5 - left
        cy = gy * Config.TILE + Config.TILE * 0.5 - top
        col = (80, 240, 140) if self.can_place(gx, gy) else (240, 80, 90)
        pygame.draw.rect(c, col, (int(cx - 24), int(cy - 24), 48, 48), 2, border_radius=6)

    def draw_node(self, nd, left, top):
        c = self.canvas
        sx = int(nd.x - left)
        sy = int(nd.y - top)
        if nd.amount <= 0:
            pygame.draw.circle(c, (45, 52, 68), (sx, sy), int(nd.radius), 2)
            return
        pulse = 0.5 + 0.5 * math.sin(self.time * 2.4 + nd.phase)
        if nd.kind == "ore":
            col = (120, 128, 150)
            glow = (170, 180, 205)
        elif nd.kind == "crystal":
            col = (70, 170, 230)
            glow = (150, 230, 255)
        else:
            col = (200, 100, 240)
            glow = (255, 170, 255)
        pts = [(sx + dx, sy + dy) for dx, dy in nd.verts]
        pygame.draw.polygon(c, col, pts)
        pygame.draw.polygon(c, (20, 26, 40), pts, 2)
        pygame.draw.circle(c, glow, (sx, sy), int(nd.radius * (0.35 + pulse * 0.15)))
        self.fonts.draw(c, {"ore": "矿", "crystal": "晶", "core": "核"}.get(nd.kind, "?"), 12, (10, 12, 22), (sx, sy), "center")

    def draw_obstacle(self, ob, left, top):
        c = self.canvas
        sx = int(ob["x"] - left)
        sy = int(ob["y"] - top)
        pts = [(sx + dx, sy + dy) for dx, dy in ob["verts"]]
        tone = ob.get("tone", 0)
        pygame.draw.polygon(c, (32 + tone, 38 + tone, 52 + tone), pts)
        pygame.draw.polygon(c, (52 + tone, 62 + tone, 84 + tone), pts, 2)
        pygame.draw.circle(c, (24, 29, 42), (sx - 6, sy - 4), max(4, int(ob["r"] * 0.22)))

    def draw_tower(self, t, left, top):
        c = self.canvas
        sx = int(t.x - left)
        sy = int(t.y - top)
        col = TOWER_DEFS[t.kind]["color"]
        pygame.draw.rect(c, (22, 30, 48), (sx - 24, sy - 24, 48, 48), border_radius=8)
        pygame.draw.rect(c, col, (sx - 24, sy - 24, 48, 48), 2, border_radius=8)
        ex = sx + int(math.cos(t.angle) * 20)
        ey = sy + int(math.sin(t.angle) * 20)
        pygame.draw.line(c, col, (sx, sy), (ex, ey), 6)
        pygame.draw.circle(c, col, (sx, sy), 10)
        pygame.draw.circle(c, (255, 255, 255), (sx, sy), 4)
        for i in range(t.level):
            pygame.draw.circle(c, C_YELLOW, (sx - 14 + i * 9, sy + 18), 2)
        if t.hp < t.max_hp - 0.5:
            frac = clamp(t.hp / max(1.0, t.max_hp), 0, 1)
            pygame.draw.rect(c, (20, 20, 26), (sx - 20, sy - 32, 40, 4))
            pygame.draw.rect(c, C_GREEN, (sx - 20, sy - 32, int(40 * frac), 4))

    def draw_enemy(self, e, left, top):
        c = self.canvas
        sx = int(e.x - left)
        sy = int(e.y - top)
        ca = math.cos(e.angle)
        sa = math.sin(e.angle)
        pts = []
        for dx, dy in e.verts:
            pts.append((sx + dx * ca - dy * sa, sy + dx * sa + dy * ca))
        body = C_WHITE if e.hit_flash > 0 else e.color
        pygame.draw.polygon(c, body, pts)
        pygame.draw.polygon(c, (15, 18, 30), pts, 2)
        if e.shield > 0:
            pygame.draw.circle(c, (110, 180, 255), (sx, sy), int(e.radius + 7), 2)
        if e.slow > 0:
            pygame.draw.circle(c, (120, 230, 255), (sx, sy), int(e.radius + 4), 1)
        if e.kind == "healer":
            pygame.draw.circle(c, (90, 255, 170), (sx, sy), int(e.radius + 16), 1)
        if e.boss:
            pygame.draw.circle(c, (255, 90, 190), (sx, sy), int(e.radius + 12), 2)
            pygame.draw.circle(c, (255, 180, 230), (sx, sy), int(e.radius + 20), 1)
        if e.hp < e.max_hp or e.boss or e.kind == "elite":
            frac = clamp(e.hp / max(1.0, e.max_hp), 0, 1)
            bw = int(e.radius * 2.2)
            pygame.draw.rect(c, (20, 20, 30), (sx - bw // 2, sy - int(e.radius) - 12, bw, 4))
            pygame.draw.rect(c, C_RED if not e.boss else C_PURPLE,
                             (sx - bw // 2, sy - int(e.radius) - 12, int(bw * frac), 4))

    def draw_player(self, left, top):
        p = self.player
        if p is None:
            return
        c = self.canvas
        sx = int(p.x - left)
        sy = int(p.y - top)
        if p.invuln > 0 and int(self.time * 30) % 2 == 0:
            pygame.draw.circle(c, (120, 220, 255), (sx, sy), p.radius + 4, 1)
        cos_a = math.cos(p.angle)
        sin_a = math.sin(p.angle)
        base = [(20, 0), (-13, 11), (-7, 0), (-13, -11)]
        pts = [(sx + x * cos_a - y * sin_a, sy + x * sin_a + y * cos_a) for x, y in base]
        pygame.draw.polygon(c, (90, 220, 255) if p.hit_flash <= 0 else C_WHITE, pts)
        pygame.draw.polygon(c, (10, 20, 34), pts, 2)
        pygame.draw.circle(c, (220, 250, 255), (int(sx + cos_a * 5), int(sy + sin_a * 5)), 4)
        if p.shield > 0:
            a = clamp(p.shield / max(1.0, p.max_shield), 0, 1)
            pygame.draw.circle(c, (90, 160, 255), (sx, sy), int(p.radius + 9), 2 if a > 0.3 else 1)
        if p.mine_target is not None and p.mine_target.amount > 0:
            tx = int(p.mine_target.x - left)
            ty = int(p.mine_target.y - top)
            pygame.draw.line(c, (150, 255, 190), (sx, sy), (tx, ty), 2)
            pygame.draw.circle(c, (220, 255, 230), (tx, ty), 4, 1)

    def draw_bar(self, x, y, w, h, frac, col, bg=(22, 28, 44)):
        c = self.canvas
        frac = clamp(frac, 0.0, 1.0)
        pygame.draw.rect(c, bg, (int(x), int(y), int(w), int(h)), border_radius=max(1, h // 2))
        if frac > 0:
            pygame.draw.rect(c, col, (int(x), int(y), max(1, int(w * frac)), int(h)),
                             border_radius=max(1, h // 2))
        pygame.draw.rect(c, (70, 90, 130), (int(x), int(y), int(w), int(h)), 1,
                         border_radius=max(1, h // 2))

    def draw_hud(self):
        c = self.canvas
        p = self.player
        if p is None:
            return
        # 资源与状态条
        self.draw_bar(10, 12, 152, 13, p.hp / max(1.0, p.max_hp), C_RED)
        self.draw_bar(10, 28, 152, 6, p.shield / max(1.0, p.max_shield), (80, 150, 255))
        self.draw_bar(10, 37, 152, 6, p.energy / max(1.0, p.max_energy), C_YELLOW)
        self.fonts.draw(c, "%d/%d" % (int(p.hp), int(p.max_hp)), 11, C_TEXT, (86, 18), "center")
        self.fonts.draw(c, "矿石 %d" % self.res.get("ore", 0), 14, (200, 205, 220), (10, 50), "topleft")
        self.fonts.draw(c, "晶体 %d" % self.res.get("crystal", 0), 14, (120, 220, 255), (96, 50), "topleft")
        self.fonts.draw(c, "核心 %d" % self.res.get("core", 0), 14, (240, 150, 255), (184, 50), "topleft")
        w = WEAPONS[p.weapon]
        self.fonts.draw(c, "%s L%d" % (w["name"], p.weapon_levels[p.weapon]), 13, w["color"],
                        (10, 70), "topleft")
        self.draw_bar(10, 94, 120, 5, p.heat / 100.0, C_ORANGE)
        if p.overheated > 0:
            self.fonts.draw(c, "过热", 11, C_RED, (134, 88), "topleft")
        # 波次
        wm = self.wave_mgr
        if wm is not None:
            wave_title = "准备阶段" if wm.wave <= 0 else "第 %d 波" % wm.wave
            self.fonts.draw(c, wave_title, 20, C_CYAN, (self.LW // 2, 4), "midtop", True)
            if wm.state == "prep":
                self.fonts.draw(c, "下一波 %d" % max(0, int(math.ceil(wm.timer))), 9, C_DIM,
                                (self.LW // 2, 34), "midtop")
            else:
                alive = 0
                for e in self.enemies:
                    if e.alive:
                        alive += 1
                self.fonts.draw(c, "敌人 %d" % alive, 9, C_DIM, (self.LW // 2, 34), "midtop")
        # 玩家等级
        self.fonts.draw(c, "等级 %d" % self.level, 11, C_YELLOW, (10, 101), "topleft")
        self.draw_bar(58, 105, 82, 4, self.xp / max(1.0, self.xp_next), C_PURPLE)
        # 小地图
        self.draw_minimap()
        # BOSS 血条
        boss = None
        for e in self.enemies:
            if e.boss and e.alive:
                boss = e
                break
        if boss is not None and self.selected_tower is None:
            bw = int(self.LW * 0.58)
            x = (self.LW - bw) // 2
            self.draw_bar(x, 148, bw, 8, boss.hp / max(1.0, boss.max_hp), (255, 70, 170))
            self.fonts.draw(c, "深渊首领", 10, C_TEXT, (self.LW // 2, 158), "midtop")
        # 摇杆
        info = None
        for i in self.pointers.values():
            if i.get("role") == "move":
                info = i
                break
        js = float(self.settings.get("joystick", 1.0))
        if info is not None:
            bx, by = info["bx"], info["by"]
            kx, ky = info.get("kx", bx), info.get("ky", by)
        else:
            bx, by = 80, self.LH - 96
            kx, ky = bx, by
        r = int(60 * js)
        pygame.draw.circle(c, (16, 24, 40), (int(bx), int(by)), r)
        pygame.draw.circle(c, (70, 105, 155), (int(bx), int(by)), r, 2)
        pygame.draw.circle(c, (90, 150, 210), (int(kx), int(ky)), int(r * 0.42))
        pygame.draw.circle(c, (170, 220, 255), (int(kx), int(ky)), int(r * 0.42), 1)
        if self.selected_tower is not None:
            self.draw_tower_panel()
        # 波次提示
        if self.banner_timer > 0 and self.banner_text:
            a = clamp(self.banner_timer / 0.5, 0.0, 1.0)
            size = int(26 + 4 * (1.0 - a))
            self.fonts.draw(c, self.banner_text, size, C_YELLOW,
                            (self.LW // 2, int(self.LH * 0.30)), "center", True)
        if self.toast_timer > 0 and self.toast_text:
            th = 26
            tw = self.fonts.size(self.toast_text, 14)[0] + 26
            tx = (self.LW - tw) // 2
            ty = self.LH - 236
            pygame.draw.rect(c, (12, 18, 32), (tx, ty, tw, th), border_radius=8)
            pygame.draw.rect(c, (70, 95, 140), (tx, ty, tw, th), 1, border_radius=8)
            self.fonts.draw(c, self.toast_text, 14, C_TEXT, (self.LW // 2, ty + th // 2), "center")
        # FPS / 调试
        if self.settings.get("show_fps", True):
            self.fonts.draw(c, "帧率 %d" % int(self.clock.get_fps()), 10, C_DIM,
                            (10, 132), "topleft")
        if self.settings.get("debug", False):
            x = 10
            y = 146
            dbg = [
                "敌:%d 弹:%d 塔:%d 粒:%d" % (len(self.enemies), len(self.bullets),
                                         len(self.towers), len(self.particles.items)),
                "种子 %d" % getattr(self, "run_seed", 0),
                "状态 %s" % {"menu": "菜单", "settings": "设置", "help": "帮助",
                              "leaderboard": "排行榜", "playing": "游戏",
                              "paused": "暂停", "upgrade": "升级",
                              "gameover": "结算"}.get(self.state, self.state),
                "网格 %dx%d" % (Config.GRID_W, Config.GRID_H),
            ]
            for ln in dbg:
                self.fonts.draw(c, ln, 10, C_GREEN, (x, y), "topleft")
                y += 13
        # 低血量红屏
        if p.hp < p.max_hp * 0.30:
            k = 1.0 - (p.hp / (p.max_hp * 0.30))
            self.vignette.set_alpha(int(clamp(k, 0.0, 1.0) * 255))
            c.blit(self.vignette, (0, 0))

    def draw_tower_panel(self):
        c = self.canvas
        t = self.selected_tower
        if t is None or not t.alive:
            return
        r = self.tower_panel_rect()
        pygame.draw.rect(c, (12, 18, 32), r, border_radius=12)
        pygame.draw.rect(c, TOWER_DEFS[t.kind]["color"], r, 2, border_radius=12)
        self.fonts.draw(c, "%s炮塔  Lv%d" % (TOWER_DEFS[t.kind]["name"], t.level), 13,
                        TOWER_DEFS[t.kind]["color"], (r.x + 10, r.y + 7), "topleft")
        self.fonts.draw(c, "生命 %d/%d" % (int(t.hp), int(t.max_hp)), 11, C_TEXT,
                        (r.right - 10, r.y + 7), "topright")
        if t.kind == "miner":
            extra = "自动采矿"
        elif t.kind == "frost":
            extra = "减速力场"
        else:
            extra = "射程 %d" % int(t.stats()[1] * self.tower_range_mult)
        self.fonts.draw(c, extra, 10, C_DIM, (r.x + 10, r.y + 31), "topleft")

    def draw_minimap(self):
        c = self.canvas
        mw = 84
        mx = self.LW - mw - 8
        my = 8
        pygame.draw.rect(c, (9, 14, 26), (mx, my, mw, mw), border_radius=5)
        k = mw / float(Config.WORLD_W)
        for nd in self.map.nodes:
            if nd.amount > 0:
                col = (170, 170, 190) if nd.kind == "ore" else ((100, 200, 255) if nd.kind == "crystal" else (240, 150, 255))
                c.fill(col, (mx + int(nd.x * k), my + int(nd.y * k), 2, 2))
        for t in self.towers:
            if t.alive:
                c.fill((90, 240, 170), (mx + int(t.x * k) - 1, my + int(t.y * k) - 1, 3, 3))
        for e in self.enemies:
            if e.alive:
                c.fill((255, 90, 100), (mx + int(e.x * k), my + int(e.y * k), 2, 2))
        if self.player is not None:
            px = mx + int(self.player.x * k)
            py = my + int(self.player.y * k)
            pygame.draw.circle(c, (140, 240, 255), (px, py), 3)
        pygame.draw.rect(c, (70, 95, 140), (mx, my, mw, mw), 1, border_radius=5)

    # ---------------- 覆盖界面 ----------------
    def draw_pause(self):
        c = self.canvas
        c.blit(self.dim, (0, 0))
        self.fonts.draw(c, "已暂停", 38, C_CYAN, (self.LW // 2, int(self.LH * 0.20)), "midtop", True)
        self.fonts.draw(c, "保存会记录最高波次与排行榜", 12, C_DIM,
                        (self.LW // 2, int(self.LH * 0.20) + 58), "midtop")

    def draw_gameover(self):
        c = self.canvas
        c.blit(self.dim, (0, 0))
        cx = self.LW // 2
        self.fonts.draw(c, "航行终止", 30, C_RED, (cx, int(self.LH * 0.12)), "midtop", True)
        stats = [
            ("到达波次", "%d" % (self.wave_mgr.wave if self.wave_mgr else 0)),
            ("击杀", "%d" % self.kills),
            ("存活时间", fmt_time(self.game_time)),
            ("矿石储量", "%d" % self.res.get("ore", 0)),
        ]
        y = int(self.LH * 0.24)
        for label, value in stats:
            self.fonts.draw(c, label, 16, C_DIM, (cx - 14, y), "midright")
            self.fonts.draw(c, value, 16, C_TEXT, (cx + 14, y), "midleft")
            y += 29
        best = int(self.save.data.get("best_wave", 0))
        self.fonts.draw(c, "最高波次 %d" % best, 15, C_ORANGE, (cx, y + 6), "midtop")

    def draw_build_menu(self):
        c = self.canvas
        c.blit(self.dim, (0, 0))
        lw, lh = self.LW, self.LH
        w = min(440, lw - 30)
        h = min(380, lh - 100)
        x = (lw - w) // 2
        y = (lh - h) // 2
        pygame.draw.rect(c, (12, 18, 32), (x, y, w, h), border_radius=14)
        pygame.draw.rect(c, (70, 110, 170), (x, y, w, h), 2, border_radius=14)
        self.fonts.draw(c, "建造炮塔", 22, C_CYAN, (x + w // 2, y + 12), "midtop", True)
        cards = [b for b in self.ui if b["id"].startswith("b_") and b["id"] != "b_close"]
        for b in cards:
            kind = b["id"][2:]
            d = TOWER_DEFS[kind]
            cost = self.tower_cost(kind)
            r = b["rect"]
            afford = self.can_afford(cost)
            edge = d["color"] if afford else (110, 80, 90)
            pygame.draw.rect(c, (24, 33, 54), r, border_radius=10)
            pygame.draw.rect(c, edge, r, 2, border_radius=10)
            self.fonts.draw(c, d["name"], 22, d["color"], (r.centerx, r.y + 14), "midtop")
            self.fonts.draw(c, "%d 矿石  %d 晶体" % (cost["ore"], cost["crystal"]),
                            13, C_YELLOW if afford else C_RED, (r.centerx, r.y + 44), "midtop")
            self.fonts.draw(c, d["desc"], 11, C_DIM, (r.centerx, r.y + 66), "midtop")
            self.fonts.draw(c, "点击选择", 10, C_DIM, (r.centerx, r.bottom - 18), "midtop")

    def draw_upgrade(self):
        c = self.canvas
        c.blit(self.dim, (0, 0))
        lw = self.LW
        self.fonts.draw(c, "升级", 30, C_YELLOW, (lw // 2, max(16, int(self.LH * 0.04))), "midtop", True)
        self.fonts.draw(c, "选择一项强化", 13, C_DIM,
                        (lw // 2, max(16, int(self.LH * 0.04)) + 46), "midtop")
        cards = [b for b in self.ui if b["id"].startswith("upg")]
        for i, b in enumerate(cards):
            if i >= len(self.upgrade_choices):
                break
            up = self.upgrade_choices[i]
            r = b["rect"]
            pressed = b["id"] in self.pressed_ids
            pygame.draw.rect(c, (0, 0, 0), r.move(2, 3), border_radius=12)
            pygame.draw.rect(c, (20, 28, 46), r.move(0, 2 if pressed else 0), border_radius=12)
            pygame.draw.rect(c, up["color"], r.move(0, 2 if pressed else 0), 2, border_radius=12)
            pygame.draw.rect(c, up["color"], (r.x + 10, r.y + 10, 8, r.h - 20), border_radius=4)
            self.fonts.draw(c, up["name"], 23, up["color"], (r.x + 30, r.y + 12), "topleft")
            lines = wrap_lines(self.fonts, up["desc"], 15, r.w - 70)
            ty = r.y + 44
            for ln in lines[:2]:
                self.fonts.draw(c, ln, 15, C_TEXT, (r.x + 30, ty), "topleft")
                ty += 19
            self.fonts.draw(c, "%d" % (i + 1), 26, (60, 76, 110),
                            (r.right - 24, r.centery), "center")

    # ---------------- 主循环 ----------------
    def run(self):
        while self.running:
            try:
                dt = self.clock.tick(Config.FPS) / 1000.0
                if dt < 0.0:
                    dt = 0.0
                dt = min(dt, Config.MAX_DT)
                self.build_ui()
                self.handle_events()
                self.update(dt)
                self.draw()
            except Exception:
                self.fatal = traceback.format_exc()
                self.running = False
                write_error_log(self.fatal)
                break


def write_error_log(text):
    for d in (os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd(),
              os.getcwd()):
        try:
            path = os.path.join(d, Config.LOG_NAME)
            with open(path, "a", encoding="utf-8") as f:
                f.write("\n===== %s =====\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
                f.write(text)
                f.write("\n")
            return True
        except Exception:
            continue
    return False


def show_fatal(text):
    try:
        pygame.init()
        try:
            pygame.mixer.quit()
        except Exception:
            pass
        info = pygame.display.Info()
        w = info.current_w if info and info.current_w > 200 else 720
        h = info.current_h if info and info.current_h > 200 else 1280
        screen = pygame.display.set_mode((w, h))
        fonts = TextRenderer()
        screen.fill((18, 4, 8))
        fonts.draw(screen, "游戏崩溃", max(20, w // 16), C_RED, (w // 2, 22), "midtop", True)
        lines = text.strip().splitlines()[-14:]
        y = 80
        for ln in lines:
            fonts.draw(screen, ln[:110], 13, C_TEXT, (12, y), "topleft")
            y += 17
        fonts.draw(screen, "触摸屏幕退出", 18, C_DIM, (w // 2, h - 40), "midtop")
        pygame.display.flip()
        t0 = time.time()
        while time.time() - t0 < 8.0:
            for e in pygame.event.get():
                if e.type in (pygame.QUIT, pygame.FINGERDOWN, pygame.MOUSEBUTTONDOWN):
                    return
            pygame.time.wait(50)
    except Exception:
        pass


def main():
    game = Game()
    try:
        game.run()
    finally:
        if game.fatal:
            try:
                pygame.display.quit()
            except Exception:
                pass
            show_fatal(game.fatal)
        game.save_all()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        tb = traceback.format_exc()
        write_error_log(tb)
        try:
            show_fatal(tb)
        except Exception:
            pass
    finally:
        try:
            pygame.quit()
        except Exception:
            pass

