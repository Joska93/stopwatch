# -*- coding: utf-8 -*-
"""Willog 30s promo — pointillism + paper cut-out + kinetic typography.
Renders frames with PIL, synthesizes BGM with numpy, mixes SAPI (Heami) narration, muxes with ffmpeg."""
import math, random, subprocess, sys, wave, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import imageio_ffmpeg

HERE = os.path.dirname(os.path.abspath(__file__))
VOICE_DIR = sys.argv[1] if len(sys.argv) > 1 else HERE
OUT = os.path.join(HERE, "willog_promo_30s.mp4")
W, H, FPS, DUR = 1920, 1080, 30, 30.0
SR = 44100

CREAM = (243, 237, 226)
NAVY = (27, 38, 74)
BLUE = (47, 91, 234)
CORAL = (255, 107, 74)
MINT = (60, 200, 160)
MUSTARD = (246, 185, 59)
WHITE = (255, 253, 248)
PAL = [NAVY, BLUE, CORAL, MINT, MUSTARD]

FB = r"C:\Windows\Fonts\malgunbd.ttf"
FR = r"C:\Windows\Fonts\malgun.ttf"
_fonts = {}
def font(size, bold=True):
    k = (size, bold)
    if k not in _fonts:
        _fonts[k] = ImageFont.truetype(FB if bold else FR, size)
    return _fonts[k]

def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def ease_out_cubic(p): return 1 - (1 - p) ** 3
def ease_in_out(p): return 4 * p * p * p if p < .5 else 1 - (-2 * p + 2) ** 3 / 2
def ease_out_back(p, s=1.70158):
    p -= 1
    return p * p * ((s + 1) * p + s) + 1
def jit(c, a=14):
    return tuple(int(clamp(v + random.randint(-a, a), 0, 255)) for v in c)

# --------------------------------------------------------------- paper sprites
def paper(mask, color, shadow=(10, 14), blur=9, grain=True):
    """mask: L image. returns RGBA sprite with soft drop shadow + paper fibre."""
    pad = 40
    w, h = mask.size
    out = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    sh = Image.new("L", out.size, 0)
    sh.paste(mask, (pad + shadow[0], pad + shadow[1]))
    sh = sh.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * 0.42))
    out.paste((40, 28, 18, 255), (0, 0), sh)
    body = Image.new("RGBA", (w, h), color + (255,))
    if grain:
        n = np.random.randint(-9, 10, (h, w, 1)).astype(np.int16)
        arr = np.clip(np.asarray(body).astype(np.int16)[:, :, :3] + n, 0, 255).astype(np.uint8)
        body = Image.fromarray(np.dstack([arr, np.full((h, w), 255, np.uint8)]), "RGBA")
    out.paste(body, (pad, pad), mask)
    return out

def rrect_mask(w, h, r):
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], r, fill=255)
    return m

def torn_rect_mask(w, h, amp=6, seed=0):
    rnd = random.Random(seed)
    pts = []
    for x in range(0, w + 1, 14): pts.append((x, rnd.uniform(0, amp)))
    for y in range(0, h + 1, 14): pts.append((w - rnd.uniform(0, amp), y))
    for x in range(w, -1, -14): pts.append((x, h - rnd.uniform(0, amp)))
    for y in range(h, -1, -14): pts.append((rnd.uniform(0, amp), y))
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    return m

def place(frame, spr, cx, cy, angle=0.0, scale=1.0, alpha=1.0):
    if alpha <= 0.01: return
    s = spr
    if abs(scale - 1) > 0.003:
        s = s.resize((max(1, int(s.width * scale)), max(1, int(s.height * scale))), Image.BILINEAR)
    if abs(angle) > 0.05:
        s = s.rotate(angle, Image.BICUBIC, expand=True)
    if alpha < 0.999:
        s = s.copy()
        s.putalpha(s.getchannel("A").point(lambda v: int(v * alpha)))
    frame.paste(s, (int(cx - s.width / 2), int(cy - s.height / 2)), s)

def dot(d, x, y, r, c):
    d.ellipse([x - r, y - r, x + r, y + r], fill=c)

# --------------------------------------------------------------- kinetic type
_chars = {}
def char_sprite(ch, size, color):
    k = (ch, size, color)
    if k in _chars: return _chars[k]
    f = font(size)
    asc, desc = f.getmetrics()
    w = max(1, int(f.getlength(ch))) + 4
    m = Image.new("L", (w, asc + desc), 0)
    ImageDraw.Draw(m).text((2, asc), ch, font=f, fill=255, anchor="ls")
    spr = paper(m, color, shadow=(4, 6), blur=4, grain=False)
    _chars[k] = (spr, w, asc)
    return _chars[k]

def ktext(frame, text, x, y, size, color, t0, t, anchor="left", stagger=0.045, style="drop"):
    f = font(size)
    adv = [f.getlength(c) for c in text]
    total = sum(adv)
    if anchor == "center": x -= total / 2
    cx = x
    for i, c in enumerate(text):
        p = clamp((t - t0 - i * stagger) / 0.5)
        if c != " " and p > 0:
            spr, w, asc = char_sprite(c, size, color)
            e = ease_out_back(p, 2.2)
            if style == "drop":
                dy, rot = (1 - e) * -90, (1 - p) * (18 if i % 2 else -18)
            else:  # rise
                dy, rot = (1 - e) * 110, (1 - p) * (-12 if i % 2 else 12)
            sc = 0.6 + 0.4 * ease_out_cubic(p)
            # sprite centre (pad 40) -> baseline position
            ccx = cx - 2 + spr.width / 2 - 40
            ccy = y - asc + spr.height / 2 - 40 + dy
            place(frame, spr, ccx, ccy, rot, sc, clamp(p * 2.5))
        cx += adv[i]

# --------------------------------------------------------------- backgrounds
def make_bg(seed, blobs, sparse=1800):
    random.seed(seed); np.random.seed(seed)
    im = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(im)
    for _ in range(sparse):
        dot(d, random.uniform(0, W), random.uniform(0, H), random.uniform(1.5, 3.5),
            jit(random.choice([(220, 210, 195), (205, 196, 182)]), 6))
    for (bx, by, rad, cols, n) in blobs:
        for _ in range(n):
            a = random.uniform(0, 2 * math.pi)
            rr = rad * math.sqrt(random.random()) ** 0.8
            x, y = bx + math.cos(a) * rr, by + math.sin(a) * rr
            k = rr / rad
            r = 2.2 + 5.5 * (1 - k) * random.random() + 1.2
            dot(d, x, y, r, jit(random.choice(cols), 18))
    return im

def grain_layer():
    g = np.random.normal(0, 5, (H, W, 1)).astype(np.int16)
    yy, xx = np.mgrid[0:H, 0:W]
    v = ((xx - W / 2) ** 2 / (W * .75) ** 2 + (yy - H / 2) ** 2 / (H * .75) ** 2)
    g = g - (np.clip(v - 0.35, 0, 1) * 38)[:, :, None].astype(np.int16)
    return g

# --------------------------------------------------------------- scene assets
random.seed(7); np.random.seed(7)
BG = [
    make_bg(1, [(1320, 560, 470, [MUSTARD, CORAL], 6500), (150, 120, 300, [MINT], 1600)]),
    make_bg(2, [(0, 0, 520, [CORAL, MUSTARD], 3800), (W, H, 560, [BLUE, MINT], 4200)]),
    make_bg(3, [(1500, 880, 640, [MINT, BLUE], 6000), (260, 160, 260, [MUSTARD], 1200)]),
    make_bg(4, [(1400, 560, 600, [BLUE, NAVY], 5200), (120, 980, 320, [CORAL], 1800)]),
    make_bg(5, [(960, 520, 760, [MUSTARD, CORAL, MINT], 5200)], sparse=2400),
]
GRAIN = grain_layer()

# Scene 1: globe + parcel
gm = Image.new("L", (520, 520), 0); ImageDraw.Draw(gm).ellipse([0, 0, 519, 519], fill=255)
GLOBE = paper(gm, BLUE)
gd = ImageDraw.Draw(GLOBE)
for (lx, ly, lr) in [(170, 170, 95), (360, 260, 80), (250, 390, 70), (120, 330, 45)]:
    for _ in range(420):
        a = random.uniform(0, 6.283); rr = lr * math.sqrt(random.random())
        x, y = 40 + lx + math.cos(a) * rr, 40 + ly + math.sin(a) * rr
        if (x - 300) ** 2 + (y - 300) ** 2 < 250 ** 2:
            dot(gd, x, y, random.uniform(2, 4.5), jit(random.choice([MINT, WHITE, MINT]), 12))
for i in range(5):  # latitude stitches
    yy = 40 + 70 + i * 95
    for xx in range(60, 540, 16):
        if (xx - 300) ** 2 + (yy - 300) ** 2 < 245 ** 2:
            dot(gd, xx, yy, 1.6, (200, 215, 255))
bm = Image.new("L", (110, 110), 0); ImageDraw.Draw(bm).rounded_rectangle([0, 0, 109, 109], 8, fill=255)
BOX = paper(bm, (214, 150, 86))
bd = ImageDraw.Draw(BOX)
bd.rectangle([40 + 44, 40, 40 + 66, 40 + 109], fill=(240, 220, 170))
bd.text((40 + 55, 40 + 80), "W", font=font(26), fill=NAVY, anchor="mm")

def route(s):
    p0, p1, p2 = (-60, 960), (780, 1080), (1075, 640)
    u = 1 - s
    return (u * u * p0[0] + 2 * u * s * p1[0] + s * s * p2[0], u * u * p0[1] + 2 * u * s * p1[1] + s * s * p2[1])

# Scene 2: risk cards
def card(word, label, color, seed):
    m = torn_rect_mask(400, 300, 7, seed)
    spr = paper(m, color)
    d = ImageDraw.Draw(spr)
    d.text((240, 205), word, font=font(140), fill=WHITE, anchor="mm")
    d.text((240, 300), label, font=font(30, False), fill=WHITE, anchor="mm")
    for i in range(14):
        dot(d, 80 + i * 23, 80, 3, WHITE)
    return spr
CARDS = [card("온도", "TEMPERATURE", CORAL, 1), card("습도", "HUMIDITY", MINT, 2), card("충격", "SHOCK", MUSTARD, 3)]

# Scene 3: sensor tag + data line
tm = rrect_mask(230, 320, 34)
TAG = paper(tm, NAVY)
td = ImageDraw.Draw(TAG)
td.ellipse([40 + 95, 40 + 26, 40 + 135, 40 + 46], fill=CREAM)  # hanger hole
td.text((40 + 115, 40 + 250), "willog", font=font(40), fill=WHITE, anchor="mm")
for i in range(6):
    for j in range(4):
        dot(td, 40 + 70 + i * 18, 40 + 120 + j * 18, 3, (90, 110, 170))
def data_y(x): return 700 + 110 * math.sin(x / 150) + 45 * math.sin(x / 53 + 1)
LINE_PTS = [(x, data_y(x)) for x in range(560, 1840, 13)]
random.seed(11)
FILL_PTS = [(x + random.uniform(-4, 4), y) for (x, _) in LINE_PTS[::1]
            for y in range(int(data_y(x)) + 22, 960, 20) if random.random() < 0.55]

# Scene 4: dashboard
DASH = paper(rrect_mask(820, 620, 26), WHITE)
dd = ImageDraw.Draw(DASH)
dd.text((40 + 92, 40 + 58), "LIVE", font=font(34), fill=NAVY, anchor="lm")
dd.text((40 + 190, 40 + 58), "실시간 모니터링", font=font(32, False), fill=(110, 115, 135), anchor="lm")
for x in range(80, 760, 14): dot(dd, 40 + x, 40 + 540, 2, (200, 200, 210))
BARS = [0.45, 0.62, 0.38, 0.92, 0.55, 0.70]
def pill(text, color):
    f = font(40)
    w = int(f.getlength(text)) + 90
    spr = paper(rrect_mask(w, 86, 43), color)
    d = ImageDraw.Draw(spr)
    dot(d, 40 + 40, 40 + 43, 10, WHITE)
    d.text((40 + 62, 40 + 43), text, font=f, fill=WHITE, anchor="lm")
    return spr
ALERT = pill("온도 이탈 감지", CORAL)
OKP = pill("대응 완료", MINT)

# Scene 5: dot logo
lm = Image.new("L", (W, H), 0)
ImageDraw.Draw(lm).text((960, 470), "willog", font=font(330), fill=255, anchor="mm")
la = np.asarray(lm)
random.seed(5)
LOGO = []
for y in range(0, H, 9):
    for x in range(0, W, 9):
        if la[y, x] > 140:
            c = random.choices([NAVY, BLUE, CORAL, MINT], [5, 4, 1, 1])[0]
            a = random.uniform(0, 6.283); r0 = random.uniform(700, 1300)
            LOGO.append((x, y, 960 + math.cos(a) * r0, 500 + math.sin(a) * r0 * .6,
                         random.uniform(0, 0.7), jit(c, 10), random.uniform(3.8, 5.2)))
SWOOSH = paper(rrect_mask(560, 26, 13), CORAL)

FLOAT = [(random.uniform(0, W), random.uniform(0, H), random.uniform(2, 5), random.choice(PAL),
          random.uniform(0, 6.28), random.uniform(10, 30)) for _ in range(90)]

# --------------------------------------------------------------- timeline
B = [0.0, 6.2, 12.9, 18.6, 24.4, 30.0]
VOICE_AT = [0.6, 6.4, 13.1, 18.9, 24.9]

def scene1(fr, d, t):
    s = clamp((t - 0.9) / 3.6)
    n = int(70 * ease_in_out(s))
    for i in range(n):
        x, y = route(i / 70)
        dot(d, x, y, 4, CORAL if i % 3 else NAVY)
    p = clamp((t - 0.2) / 1.1)
    place(fr, GLOBE, 1320, 580 + (1 - ease_out_back(p)) * 700, t * 5, 1.0, clamp(p * 3))
    if t > 0.9:
        bx, by = route(ease_in_out(s))
        bx2, by2 = route(clamp(ease_in_out(s) + 0.01))
        ang = -math.degrees(math.atan2(by2 - by, bx2 - bx)) + math.sin(t * 6) * 4
        place(fr, BOX, bx, by - 30, ang, 1.0 - 0.35 * clamp((s - .85) / .15))
    ktext(fr, "물건은 매일,", 150, 420, 92, NAVY, 0.6, t)
    ktext(fr, "세상을 건넙니다.", 150, 560, 124, BLUE, 1.7, t)

def scene2(fr, d, t):
    xs, angs, at = [400, 960, 1520], [-5, 3, -3], [6.55, 7.5, 8.45]
    for i in range(3):
        p = clamp((t - at[i]) / 0.42)
        if p <= 0: continue
        sc = 1 + (1 - ease_out_cubic(p)) * 0.9
        ang = angs[i]
        dx = 0
        if i == 2 and p >= 1:
            k = math.exp(-(t - at[i] - .42) * 5)
            ang += math.sin(t * 60) * 6 * k; dx = math.sin(t * 47) * 14 * k
        if p >= 1 and i < 2:
            ang += math.sin(t * 2 + i) * 1.2
        place(fr, CARDS[i], xs[i] + dx, 470 + math.sin(t * 1.6 + i) * 6, ang, sc, clamp(p * 2))
    ktext(fr, "보이지 않는 순간들.", 960, 880, 86, NAVY, 9.7, t, anchor="center", style="rise")
    ktext(fr, "RISK IN TRANSIT", 960, 200, 40, CORAL, 6.4, t, anchor="center", stagger=0.03)

def scene3(fr, d, t):
    p = clamp((t - 12.95) / 0.8)
    tx = -200 + ease_out_back(p) * 540
    place(fr, TAG, tx, 690, -6 + math.sin(t * 2) * 2)
    if p > 0.6:
        on = (int(t * 3) % 2 == 0)
        dot(d, tx - 4, 690 - 50, 12, MINT if on else (60, 90, 80))
    for i, (x, y) in enumerate(LINE_PTS):
        q = clamp((t - 13.7 - i * 0.03) / 0.35)
        if q > 0:
            c = tuple(int(MINT[k] + (BLUE[k] - MINT[k]) * i / len(LINE_PTS)) for k in range(3))
            dot(d, x, y + math.sin(t * 3 + i * .3) * 3, 7 * ease_out_back(q), c)
    for (x, y) in FILL_PTS:
        q = clamp((t - 13.9 - (x - 560) / 13 * 0.03) / 0.5)
        if q > 0:
            dot(d, x, y, 3.2 * q, (150, 190, 235))
    ktext(fr, "모든 순간을", 960, 220, 104, NAVY, 13.2, t, anchor="center")
    ktext(fr, "데이터로 기록합니다.", 960, 360, 104, BLUE, 14.3, t, anchor="center")

def scene4(fr, d, t):
    p = clamp((t - 18.7) / 0.9)
    cx, cy = 1370 + (1 - ease_out_back(p, 1.4)) * 900, 570
    place(fr, DASH, cx, cy, 0)
    ox, oy = cx - 450, cy - 350  # sprite origin incl pad (sprite = 900x700)
    dot(d, ox + 40 + 58, oy + 40 + 58, 9 if int(t * 2.5) % 2 else 6, CORAL)
    alert_t = 21.3
    for b, hgt in enumerate(BARS):
        g = ease_out_cubic(clamp((t - 19.4 - b * 0.18) / 1.0))
        if b == 3 and t > alert_t + 1.6:
            hgt = hgt - 0.35 * ease_out_cubic(clamp((t - alert_t - 1.6) / 0.6))
        rows = int(hgt * g * 22)
        col = CORAL if (b == 3 and alert_t < t < alert_t + 2.0) else BLUE
        for r in range(rows):
            for k in range(3):
                dot(d, ox + 40 + 130 + b * 108 + k * 18, oy + 40 + 515 - r * 19, 6.5, col if r > 1 else NAVY)
    q = clamp((t - alert_t) / 0.35)
    if t < alert_t + 1.7:
        place(fr, ALERT, 1560, 205, -4 + math.sin(t * 30) * 2 * math.exp(-(t - alert_t) * 3) if q else 0,
              0.4 + 0.6 * ease_out_back(q), q)
    else:
        q2 = clamp((t - alert_t - 1.7) / 0.35)
        place(fr, OKP, 1560, 205, 3, 0.4 + 0.6 * ease_out_back(q2), q2)
    ktext(fr, "실시간으로 보고,", 110, 480, 100, NAVY, 18.9, t)
    ktext(fr, "미리 대응하세요.", 110, 630, 112, CORAL, 20.3, t)

def scene5(fr, d, t):
    for (x, y, sx, sy, dl, c, r) in LOGO:
        q = ease_in_out(clamp((t - 24.5 - dl) / 1.3))
        if q <= 0: continue
        px = sx + (x - sx) * q + (1 - q) * math.sin(t * 3 + sx) * 30
        py = sy + (y - sy) * q
        dot(d, px, py, r * (0.5 + 0.5 * q), c)
    p = clamp((t - 26.3) / 0.6)
    place(fr, SWOOSH, 960 - (1 - ease_out_cubic(p)) * 300, 650, -2, 1, p)
    ktext(fr, "물류의 모든 여정을 투명하게.", 960, 800, 64, NAVY, 26.0, t, anchor="center", stagger=0.035, style="rise")
    ktext(fr, "willog.io", 960, 900, 34, BLUE, 27.6, t, anchor="center", stagger=0.03, style="rise")

SCENES = [scene1, scene2, scene3, scene4, scene5]

def wipe(d, t):
    for b in B[1:-1]:
        p = (t - (b - 0.45)) / 0.9
        if not (0 <= p <= 1): continue
        rnd = random.Random(int(b * 10))
        for gy in range(0, H + 60, 60):
            for gx in range(0, W + 60, 60):
                dl = gx / W * 0.15
                g = clamp((p - dl) / 0.3) - clamp((p - 0.5 - dl) / 0.3)
                c = rnd.choices(PAL, [6, 3, 1, 1, 1])[0]
                if g > 0:
                    dot(d, gx + (gy // 60 % 2) * 30, gy, 48 * ease_in_out(g), c)

def render_frame(t):
    si = max(i for i in range(5) if B[i] <= t)
    fr = BG[si].copy()
    d = ImageDraw.Draw(fr)
    for (x, y, r, c, ph, sp) in FLOAT:
        dot(d, (x + t * sp) % W, y + math.sin(t + ph) * 18, r, c)
    SCENES[si](fr, d, t)
    wipe(d, t)
    a = np.asarray(fr).astype(np.int16) + GRAIN
    return np.clip(a, 0, 255).astype(np.uint8)

# --------------------------------------------------------------- audio
def load_wav(path):
    w = wave.open(path)
    sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
    x = np.frombuffer(w.readframes(n), np.int16).astype(np.float32) / 32768
    if ch > 1: x = x.reshape(-1, ch).mean(1)
    tt = np.arange(int(len(x) * SR / sr)) * sr / SR
    return np.interp(tt, np.arange(len(x)), x)

def make_audio(path):
    N = int(DUR * SR)
    tt = np.arange(N) / SR
    mus = np.zeros(N)
    bpm = 96; beat = 60 / bpm; bar = beat * 4
    chords = [[261.63, 329.63, 392.0, 493.88], [220.0, 261.63, 329.63, 392.0],
              [174.61, 220.0, 261.63, 329.63], [196.0, 246.94, 293.66, 392.0]]
    nb = int(DUR / bar) + 1
    for bi in range(nb):
        ch = chords[bi % 4]
        s0 = int(bi * bar * SR); s1 = min(N, int((bi + 1) * bar * SR) + int(0.4 * SR))
        if s0 >= N: break
        lt = np.arange(s1 - s0) / SR
        env = np.minimum(1, lt / 0.35) * np.exp(-lt * 0.25) * np.clip((bar + 0.4 - lt) / 0.4, 0, 1)
        pad = sum(np.sin(2 * np.pi * f * k * lt) * a for f in ch for k, a in [(1, .5), (1.003, .35), (2, .08)])
        mus[s0:s1] += pad * env * 0.035
        # bass
        bl = np.arange(int(bar * SR)); bl = bl[:N - s0] / SR
        mus[s0:s0 + len(bl)] += np.sin(2 * np.pi * ch[0] / 2 * bl) * np.exp(-bl * 1.2) * 0.16
        # arpeggio 8ths
        for k in range(8):
            a0 = s0 + int(k * beat / 2 * SR)
            if a0 >= N: break
            f = ch[[0, 2, 1, 3, 2, 1, 3, 2][k]] * 2
            al = np.arange(min(int(0.5 * SR), N - a0)) / SR
            note = (np.sin(2 * np.pi * f * al) + 0.3 * np.sin(4 * np.pi * f * al)) * np.exp(-al * 9)
            gain = 0.05 if bi > 0 else 0.03
            mus[a0:a0 + len(al)] += note * gain
        # drums from bar 2
        if bi >= 1:
            for k in range(4):
                k0 = s0 + int(k * beat * SR)
                if k0 >= N: break
                kl = np.arange(min(int(0.3 * SR), N - k0)) / SR
                if k in (0, 2):
                    fr = 50 + 90 * np.exp(-kl * 30)
                    mus[k0:k0 + len(kl)] += np.sin(2 * np.pi * np.cumsum(fr) / SR) * np.exp(-kl * 9) * 0.32
                h0 = k0 + int(beat / 2 * SR)
                if h0 < N:
                    hl = min(int(0.06 * SR), N - h0)
                    nz = np.diff(np.random.randn(hl + 1))
                    mus[h0:h0 + hl] += nz * np.exp(-np.arange(hl) / SR * 70) * 0.025
                if k in (1, 3) and bi >= 2:
                    nz = np.random.randn(min(int(0.15 * SR), N - k0))
                    mus[k0:k0 + len(nz)] += nz * np.exp(-np.arange(len(nz)) / SR * 25) * 0.05
    # whoosh on transitions
    for b in B[1:-1]:
        w0 = int((b - 0.45) * SR); wl = int(0.9 * SR)
        nz = np.random.randn(wl); nz = np.convolve(nz, np.ones(30) / 30, "same")
        env = np.sin(np.linspace(0, np.pi, wl)) ** 2
        mus[w0:w0 + wl] += nz * env * 0.5
    voice = np.zeros(N)
    for i, at in enumerate(VOICE_AT):
        v = load_wav(os.path.join(VOICE_DIR, f"v{i}.wav"))
        s = int(at * SR); v = v[:N - s]
        voice[s:s + len(v)] += v
    voice /= (np.abs(voice).max() + 1e-9)
    venv = np.convolve(np.abs(voice) > 0.02, np.ones(int(0.25 * SR)) / (0.25 * SR), "same")
    duck = 1 - 0.45 * np.clip(venv * 3, 0, 1)
    fade = np.clip(tt / 0.8, 0, 1) * np.clip((DUR - tt) / 2.0, 0, 1)
    mus = mus / (np.abs(mus).max() + 1e-9) * 0.55 * duck * fade
    mix = mus + voice * 0.9
    mix /= max(1.0, np.abs(mix).max() / 0.95)
    st = np.stack([mix, mix], 1)
    st[:, 0] += np.roll(mus, 300) * 0.04  # tiny stereo width
    out = (np.clip(st, -1, 1) * 32767).astype(np.int16)
    w = wave.open(path, "wb"); w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes(out.tobytes()); w.close()

if __name__ == "__main__":
    apath = os.path.join(VOICE_DIR, "mix.wav")
    make_audio(apath)
    print("audio ok", flush=True)
    if len(sys.argv) > 2:  # preview stills
        for ts in sys.argv[2].split(","):
            Image.fromarray(render_frame(float(ts))).save(os.path.join(VOICE_DIR, f"still_{ts}.png"))
        sys.exit()
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    proc = subprocess.Popen([ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", apath,
                             "-c:v", "libx264", "-preset", "fast", "-crf", "19", "-pix_fmt", "yuv420p",
                             "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", OUT],
                            stdin=subprocess.PIPE)
    total = int(DUR * FPS)
    for i in range(total):
        proc.stdin.write(render_frame(i / FPS).tobytes())
        if i % 90 == 0: print(f"frame {i}/{total}", flush=True)
    proc.stdin.close(); proc.wait()
    print("done", OUT)
