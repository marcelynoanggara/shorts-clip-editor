#!/usr/bin/env python3
"""Render clip SinPOD (standar 2026-10-07 malam) dari live Timothy Ronald 2026-10-08.

Perbedaan dari render_v2.py (Terus Terang):
- Cover 1,5 detik (bukan 0,4) + intro zoom-in & teks pop-in (frame PIL @30fps) + SFX khas
  SinPOD (assets/sinpod-hook-sfx.wav, peak -14 dBFS) di trek audio cover.
- Watermark tengah = "SinPOD" (channel Marcel); logo kiri atas "FULL VIDEO" / sumber.
- Subtitle dari transkrip SEGMENT large-v3 (build/sinpod/segN-large.json), koreksi istilah
  manual per segmen; ASS di timeline BODY mulai 0 -> bakar ke body -> cover ditempel.
- Sumber 1920x1080@60: crop 608x1080 @x=656 (wajah host di tengah) -> 1080x1920 @30fps.
"""
import json, os, subprocess, sys, re, math
from PIL import Image, ImageDraw, ImageFont

BASE = os.path.expanduser("~/workspace/podcast-clips")
SRC = os.environ.get("SINPOD_SRC", os.path.join(BASE, "source-mega-20261009.mp4"))
BLD = os.environ.get("SINPOD_BLD", os.path.join(BASE, "build/upgraded"))
TMP = os.path.expanduser("~/workspace/tmp")
SFX = os.path.join(BASE, "assets/sinpod-hook-sfx.wav")
os.makedirs(TMP, exist_ok=True)
os.environ["TMPDIR"] = TMP

FONT_COVER = "/usr/share/fonts/truetype/noto/NotoSans-BlackItalic.ttf"
FONT_WM = "/usr/share/fonts/truetype/noto/NotoSans-BlackItalic.ttf"

COVER_DUR = 2.5
FPS = 30
EPS = 0.02
CROP_FILTER = os.environ.get("SINPOD_CROP", "crop=527:720:407:0")
CROP_BOX = (407, 0, 527, 720)  # x, y, w, h pada frame sumber; sesuaikan sesudah inspeksi shot

# ---------------- koreksi ejaan per segmen (nucleus lowercase -> tampilan benar) ----------------
FIX3 = {
    "goh": "Koh", "telah": "tuh", "kelewatan": "klien saya ke sana",
    "timoti": "Timothy", "timothy": "Timothy", "ronald": "Ronald",
    "team": "Tim",
}
FIX4 = dict(FIX3)
FIX4.update({
    "kewajipannya": "kewajibannya", "kewajipan": "kewajiban",
    "orangtua": "orang tua", "kasihan": "kasianin",
})
FIX1 = dict(FIX3)
FIX1.update({
    "setak": "stuck", "disendiri": "sendiri", "montennya": "ngontennya",
    "terapis": "terapi",
})

def make_fix(fixmap):
    def fix_word(w):
        w = w.strip()
        if w.startswith("-"):           # pecahan kata Whisper: '-iya' -> 'iya'
            w = w[1:]
        m = re.match(r"^([^A-Za-z]*)([A-Za-z]+)([^A-Za-z]*)$", w)
        if not m:
            return w
        pre, core, post = m.groups()
        fixed = fixmap.get(core.lower())
        return (pre + fixed + post) if fixed else w
    return fix_word

def ass_time(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"

YELLOW = "&H0000FFFF&"
WHITE = "&H00FFFFFF&"

MIN_WORD = 0.30   # target tampil minimum per kata; timestamp Whisper TIDAK digeser
MAX_WORDS = 5
MAX_CHARS = 21  # font 66: grup maks 21 char supaya baris muat 1 baris di lebar 960px (FIX 2026-10-09: 26 char = s.d. 992px -> libass memampatkan teks)
SENT_END = (".", "!", "?", "…", "...")

def _group_words(words):
    groups, cur, curlen = [], [], 0
    for item in words:
        t = item[2]
        add = len(t) + (1 if cur else 0)
        prev_ends_sentence = bool(cur) and cur[-1][2].rstrip().endswith(SENT_END)
        if cur and (len(cur) >= MAX_WORDS or curlen + add > MAX_CHARS or prev_ends_sentence):
            groups.append(cur); cur = []; curlen = 0; add = len(t)
        cur.append(item); curlen += add
    if cur: groups.append(cur)
    return groups

def build_ass(words, path):
    """Karaoke per kata, timeline BODY dari 0. Event dibuat BERURUTAN (end event = start
    kata berikutnya) supaya libass tidak menumpuk dua baris subtitle yang sama; ekor kata
    terakhir tiap grup boleh memanjang ke jeda berikutnya tanpa menabrak grup sesudahnya."""
    groups = _group_words(words)
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
LayoutResX: 1080
LayoutResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,Noto Sans,66,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,5,0,2,60,60,758,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    flat_next_starts = [w[0] for w in words]
    idx = 0
    for gi, g in enumerate(groups):
        next_group_start = groups[gi + 1][0][0] if gi + 1 < len(groups) else None
        for i, (s, e, t) in enumerate(g):
            if i + 1 < len(g):
                nxt = g[i + 1][0]
                ev_end = max(e, min(nxt, s + MIN_WORD)) if nxt - s >= MIN_WORD else nxt
                ev_end = min(ev_end, nxt)
            else:
                ev_end = max(e, s + MIN_WORD)
                if next_group_start is not None:
                    ev_end = min(ev_end, next_group_start)
            parts = []
            for j, (s2, e2, t2) in enumerate(g):
                col = YELLOW if j == i else WHITE
                parts.append(f"{{\\1c{col}}}{t2}")
            lines.append(f"Dialogue: 0,{ass_time(s)},{ass_time(ev_end)},Karaoke,,0,0,0,,{' '.join(parts)}")
            idx += 1
    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return len(groups)

def qc_words(words, groups_count):
    """QC otomatis pra-render: urutan waktu, kata tercepat, grup terpanjang."""
    problems = []
    fast = 0
    for i, (s, e, t) in enumerate(words):
        if i and s < words[i - 1][0] - 0.001:
            problems.append(f"timestamp tidak naik pada kata {i}: {t!r}")
        nxt = words[i + 1][0] if i + 1 < len(words) else e
        if max(0.0, min(nxt, max(e, s + MIN_WORD)) - s) < MIN_WORD - 0.005 and nxt > s:
            fast += 1
    print(f"[QC] words={len(words)} groups={groups_count} fast_words_below_min={fast} problems={problems[:5]}")
    return problems

# ---------------- cover ----------------
def extract_still(t, out_jpg):
    subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t}", "-i", SRC,
                    "-frames:v", "1", "-q:v", "2", out_jpg, "-y"], check=True)

def crop_body(img):
    """Crop sama seperti body dari frame 1920x1080 -> 1080x1920."""
    x, y, w, h = CROP_BOX
    return img.crop((x, y, x + w, y + h)).resize((1080, 1920), Image.LANCZOS)

def make_cover_canvas(still_top, still_bot, white_line, yellow_lines):
    """Kembalikan (canvas_bg, text_layer RGBA, text_cy) untuk animasi intro."""
    top_c = crop_body(Image.open(still_top).convert("RGB"))
    bot_c = crop_body(Image.open(still_bot).convert("RGB"))
    canvas = bot_c.copy()
    canvas.paste(top_c.crop((0, 0, 1080, int(0.49 * 1920))), (0, 0))

    layer = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx = 540
    max_w = int(0.88 * 1080)
    y = int(0.315 * 1920)
    y_top = y
    f_w = ImageFont.truetype(FONT_COVER, 225)
    while d.textlength(white_line, font=f_w) > max_w and f_w.size > 60:
        f_w = ImageFont.truetype(FONT_COVER, f_w.size - 6)
    asc, desc = f_w.getmetrics()
    d.text((cx + 13, y + 13), white_line, font=f_w, fill=(150, 0, 0, 255), anchor="ma",
           stroke_width=15, stroke_fill=(0, 0, 0, 255))
    d.text((cx, y), white_line, font=f_w, fill=(255, 255, 255, 255), anchor="ma",
           stroke_width=15, stroke_fill=(0, 0, 0, 255))
    y += asc + desc + 6
    for line in yellow_lines:
        f_y = ImageFont.truetype(FONT_COVER, 168)
        while d.textlength(line, font=f_y) > max_w and f_y.size > 50:
            f_y = ImageFont.truetype(FONT_COVER, f_y.size - 5)
        asc, desc = f_y.getmetrics()
        d.text((cx + 12, y + 12), line, font=f_y, fill=(150, 0, 0, 255), anchor="ma",
               stroke_width=15, stroke_fill=(0, 0, 0, 255))
        d.text((cx, y), line, font=f_y, fill=(255, 255, 0, 255), anchor="ma",
               stroke_width=15, stroke_fill=(0, 0, 0, 255))
        y += asc + desc + 4
    return canvas, layer, (y_top + y) // 2

def ease_out(x):
    return 1 - (1 - x) ** 3

def make_cover_video(name, canvas, layer, text_cy):
    """Animasi: zoom-in latar 1,14->1,0 (0,45 dtk ease-out) + teks pop-in 0,6->1,05->1,0.
    Audio cover = SFX (1,5 dtk)."""
    fdir = os.path.join(BLD, f"{name}-coverframes")
    os.makedirs(fdir, exist_ok=True)
    n = int(COVER_DUR * FPS)
    for i in range(n):
        t = i / FPS
        z = 1.14 - 0.14 * ease_out(min(t / 0.45, 1.0))
        w2, h2 = int(1080 * z), int(1920 * z)
        frame = canvas.resize((w2, h2), Image.LANCZOS).crop(
            ((w2 - 1080) // 2, (h2 - 1920) // 2, (w2 + 1080) // 2, (h2 + 1920) // 2))
        if t < 0.28:
            s = 0.6 + 0.45 * ease_out(t / 0.28)
        elif t < 0.55:
            s = 1.05 - 0.05 * ((t - 0.28) / 0.27)
        else:
            s = 1.0
        alpha = min(1.0, t / 0.15) if t < 0.15 else 1.0
        tw, th = int(1080 * s), int(1920 * s)
        lay = layer.resize((tw, th), Image.LANCZOS)
        if alpha < 1.0:
            a = lay.split()[3].point(lambda v: int(v * alpha))
            lay.putalpha(a)
        frame.paste(lay, (540 - tw // 2, text_cy - int(th * (text_cy / 1920))), lay)
        frame.save(os.path.join(fdir, f"f{i:03d}.png"))
    cover_mp4 = os.path.join(BLD, f"{name}-cover.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-framerate", str(FPS), "-i", os.path.join(fdir, "f%03d.png"),
                    "-i", SFX,
                    "-filter_complex", "[1:a]apad=pad_dur=1.2[a]", "-map", "0:v", "-map", "[a]", "-t", f"{COVER_DUR}",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "160k", "-ar", "48000", cover_mp4, "-y"], check=True)
    return cover_mp4

def make_watermark_png(out_png, source_lines):
    W, H = 1080, 1920
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    lx, ly = int(0.11 * W), int(0.075 * H)
    box_w, box_h = int(0.065 * W), int(0.045 * H)
    d.rounded_rectangle([lx, ly, lx + box_w, ly + box_h], radius=14, fill=(255, 0, 0, 235))
    tri = [(lx + box_w * 0.32, ly + box_h * 0.24), (lx + box_w * 0.32, ly + box_h * 0.76),
           (lx + box_w * 0.74, ly + box_h * 0.5)]
    d.polygon(tri, fill=(255, 255, 255, 255))
    f_logo = ImageFont.truetype(FONT_WM, 38)
    d.text((lx + box_w + 18, ly - 2), "FULL VIDEO", font=f_logo, fill=(255, 255, 255, 255),
           stroke_width=4, stroke_fill=(0, 0, 0))
    yy = ly + 44
    for line in source_lines:
        d.text((lx + box_w + 18, yy), line, font=f_logo, fill=(255, 255, 255, 255),
               stroke_width=4, stroke_fill=(0, 0, 0))
        yy += 42
    f_wm = ImageFont.truetype(FONT_WM, 84)
    wm = "SinPOD"
    while d.textlength(wm, font=f_wm) > int(0.40 * W) and f_wm.size > 30:
        f_wm = ImageFont.truetype(FONT_WM, f_wm.size - 4)
    d.text((W // 2, int(0.545 * H)), wm, font=f_wm, fill=(255, 255, 255, 128), anchor="mm")
    img.save(out_png)
    return out_png

def find_phrase(words, phrase):
    """Cari urutan kata (lowercase) di words [(s,e,t)...]; kembalikan (start,end) atau None."""
    toks = [t.lower().strip(".,!?") for (_, _, t) in words]
    p = phrase.lower().split()
    for i in range(len(toks) - len(p) + 1):
        if toks[i:i + len(p)] == p:
            return words[i][0], words[i + len(p) - 1][1]
    return None


def ensure_fonts():
    """Pastikan fontsdir libass ada di build dir aktif (hindari fallback font yang menggeser posisi subtitle)."""
    fdir = os.path.join(BLD, "userdata/fonts")
    os.makedirs(fdir, exist_ok=True)
    for src in ("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
                "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"):
        dst = os.path.join(fdir, os.path.basename(src))
        if os.path.exists(src) and not os.path.exists(dst):
            import shutil; shutil.copyfile(src, dst)
    return fdir

def render_clip(name, words_file, windows, fixmap, white_line, yellow_lines,
                still_top_t, still_bot_t, out_name, bw_phrase=None, drop_starts=(),
                seg_off=0.0, source_lines=("AKBAR FAIZAL", "UNCENSORED"), src=None):
    raw = json.load(open(words_file))["words"]
    # words_file: timestamp RELATIF awal segmen; seg_off menggesernya ke timeline sumber.
    # windows diisi dalam timeline SUMBER.
    allw = [{"word": w["word"], "start": w["start"] + seg_off, "end": w["end"] + seg_off}
            for w in raw
            if not any(abs(w["start"] - d) < 0.06 for d in drop_starts)]
    fix_word = make_fix(fixmap)
    new_words, cursor, kept_ranges = [], 0.0, []
    for (a, b) in windows:
        ws = [w for w in allw if w["start"] >= a - EPS and w["end"] <= b + EPS]
        if not ws:
            print(f"[{name}] window kosong {a}-{b}"); continue
        va = max(ws[0]["start"] - 0.06, 0); vb = ws[-1]["end"] + 0.12
        kept_ranges.append((va, vb))
        off = cursor - ws[0]["start"]
        for w in ws:
            new_words.append((w["start"] + off, w["end"] + off, fix_word(w["word"])))
        cursor += (ws[-1]["end"] - ws[0]["start"])
    total_kept = cursor
    print(f"[{name}] ranges={[(round(a,2),round(b,2)) for a,b in kept_ranges]} body={total_kept:.2f}s words={len(new_words)}")

    # jendela B&W di timeline body (sebelum subtitle dibakar)
    bw = find_phrase(new_words, bw_phrase) if bw_phrase else None
    if bw: print(f"[{name}] B&W window body: {bw[0]:.2f}-{bw[1]:.2f}s")

    ass_path = os.path.join(BLD, f"{name}.ass")
    ng = build_ass(new_words, ass_path)
    qc_words(new_words, ng)

    still_top = os.path.join(BLD, f"{name}-top.jpg")
    still_bot = os.path.join(BLD, f"{name}-bot.jpg")
    extract_still(still_top_t, still_top)
    extract_still(still_bot_t, still_bot)
    canvas, layer, cy = make_cover_canvas(still_top, still_bot, white_line, yellow_lines)
    canvas.save(os.path.join(BLD, f"{name}-cover.png"))  # versi statis utk cek
    cover_mp4 = make_cover_video(name, canvas, layer, cy)

    wm_png = os.path.join(BLD, f"watermark-{name}.png")
    make_watermark_png(wm_png, list(source_lines))

    src = src or SRC
    inputs, filters = [], []
    for (a, b) in kept_ranges:
        inputs += ["-ss", f"{a}", "-to", f"{b}", "-i", src]
    n = len(kept_ranges)
    vlabels = "".join(f"[{i}:v]" for i in range(n))
    filters.append(vlabels + f"concat=n={n}:v=1:a=0[vc]")
    chain = f"[vc]{CROP_FILTER},scale=1080:1920:flags=lanczos,fps={FPS},unsharp=5:5:0.25:3:3:0.10"
    if bw:
        chain += f",hue=s=0:enable='between(t\\,{bw[0]:.2f}\\,{bw[1]:.2f})'"
    filters.append(chain + "[vs]")
    ass_esc = ass_path.replace("\\", "/").replace(":", "\\:")
    FONTS_DIR = ensure_fonts()
    force = "Alignment=2,MarginV=500"
    filters.append(f"[vs]subtitles='{ass_esc}':fontsdir='{FONTS_DIR}':force_style='{force}'[vsub]")
    filters.append(f"[vsub][{n}:v]overlay=0:0[vout]")
    alabels = "".join(f"[{i}:a]" for i in range(n))
    filters.append(alabels + f"concat=n={n}:v=0:a=1[araw]")
    filters.append("[araw]loudnorm=I=-14:TP=-1.0:LRA=11[aout]")
    inputs += ["-loop", "1", "-framerate", str(FPS), "-i", wm_png]

    body = os.path.join(BLD, f"{name}-body.mp4")
    subprocess.run(["ffmpeg", "-v", "error"] + inputs + [
        "-filter_complex", ";".join(filters),
        "-map", "[vout]", "-map", "[aout]", "-max_muxing_queue_size", "4096",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
        "-t", f"{total_kept:.3f}", body, "-y"], check=True)

    out = os.path.join(BASE, out_name)
    subprocess.run(["ffmpeg", "-v", "error", "-i", cover_mp4, "-i", body,
                    "-filter_complex",
                    f"[0:v][1:v]xfade=transition=fade:duration=0.05:offset={COVER_DUR - 0.05}[v];"
                    "[0:a][1:a]acrossfade=d=0.05[a]",
                    "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out, "-y"], check=True)
    print(f"[{name}] DONE -> {out} | groups={ng}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        demo = [(0.0, 0.36, "Kekuasaan"), (0.36, 0.48, "yang"), (0.48, 1.12, "eksesif."),
                (1.12, 1.26, "Itu"), (1.26, 1.52, "sumber"), (1.52, 1.90, "korupsi.")]
        out = os.path.join(BLD, "selftest.ass")
        os.makedirs(BLD, exist_ok=True)
        g = build_ass(demo, out)
        qc_words(demo, g)
        print("SELFTEST OK ->", out)
    else:
        print("Template render SinPOD (upgrade 2026-10-09). Isi config episode di pemanggilan render_clip().")
