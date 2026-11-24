#!/usr/bin/env python3
"""Dựng YouTube Shorts cho kênh Bắt Sóng Hóng Trent bằng ffmpeg.

Đầu vào: job.json (do Make gửi sang qua GitHub repository_dispatch)
  {
    "job_id": "20261124-1303",
    "channel": "Bắt Sóng Hóng Trent",
    "title": "Tiêu đề video",
    "thumb_text": "Chữ lớn trên thumbnail",
    "pages": ["url trang Canva 1", ..., "url trang 6"],
    "texts": ["lời đọc cảnh 1", ..., "lời đọc cảnh 6"],
    "voice": "vi-VN-HoaiMyNeural"
  }

Đầu ra (thư mục out/): short.mp4, thumbnail.jpg, result.json
Từng cảnh: ảnh trang Canva chuyển động chậm (Ken Burns) + giọng đọc HoaiMy.
Thêm intro thẻ tên kênh (~1,2 giây) và outro "Đăng ký kênh" ở cảnh cuối.
"""
import argparse
import asyncio
import json
import math
import subprocess
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
ROOT = Path(__file__).resolve().parent
FONT = ROOT / "fonts" / "Montserrat.ttf"
INTRO_SEC = 1.2
SCENE_PAD = 0.25      # khoảng lặng sau mỗi câu
OUTRO_EXTRA = 1.0     # giữ thêm ở cảnh cuối sau lời mời đăng ký
ZOOM = 0.07           # Ken Burns nhẹ để không cắt mất chữ Canva ở mép
ACCENT = (255, 204, 0)


# ---------- tiện ích ----------
def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Lệnh lỗi: {' '.join(map(str, cmd[:6]))}...\n{p.stderr[-1500:]}")
    return p.stdout


def duration(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "default=nw=1:nk=1", str(path)]).strip())


def font(size, weight="ExtraBold"):
    f = ImageFont.truetype(str(FONT), size)
    try:
        f.set_variation_by_name(weight)
    except Exception:
        pass
    return f


def wrap(draw, text, fnt, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=fnt) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit_text(draw, text, max_w, max_lines, start, minimum=40, weight="ExtraBold"):
    size = start
    while size > minimum:
        f = font(size, weight)
        lines = wrap(draw, text, f, max_w)
        if len(lines) <= max_lines:
            return f, lines
        size -= 4
    f = font(minimum, weight)
    return f, wrap(draw, text, f, max_w)[:max_lines]


def strip_emoji(s):
    # font không có emoji -> bỏ để khỏi hiện ô vuông
    return "".join(ch for ch in s if ord(ch) < 0x2190 or 0x1E00 <= ord(ch) <= 0x1EFF).strip()


def cover(img, w, h):
    img = img.convert("RGB")
    r = max(w / img.width, h / img.height)
    img = img.resize((math.ceil(img.width * r), math.ceil(img.height * r)), Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


# ---------- tải ảnh, giọng đọc ----------
def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        f.write(r.read())
    # chuẩn hóa về PNG 1080x1920
    cover(Image.open(dest), W, H).save(dest.with_suffix(".png"))
    return dest.with_suffix(".png")


async def _tts(text, voice, out, rate):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate).save(str(out))


def tts(text, voice, out_mp3, rate="+8%", fake=False):
    if fake:  # chạy thử khi không có mạng tới máy chủ giọng đọc
        secs = max(1.5, len(text.split()) * 0.33)
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
             f"sine=frequency=220:sample_rate=44100:duration={secs:.2f}",
             "-af", "volume=0.05", str(out_mp3)])
    else:
        for attempt in range(3):
            try:
                asyncio.run(_tts(text, voice, out_mp3, rate))
                break
            except Exception:
                if attempt == 2:
                    raise
    wav = out_mp3.with_suffix(".wav")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(out_mp3), "-af", f"apad=pad_dur={SCENE_PAD}",
         "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(wav)])
    return wav, duration(wav)


# ---------- hình phụ: intro, outro, thumbnail ----------
def make_intro(bg_png, channel, out_png):
    bg = Image.open(bg_png).convert("RGB").filter(ImageFilter.GaussianBlur(28))
    bg = Image.blend(bg, Image.new("RGB", bg.size, (0, 0, 0)), 0.55)
    d = ImageDraw.Draw(bg)
    f_small = font(46, "SemiBold")
    tag = "KÊNH HÀI MỖI NGÀY"
    d.text(((W - d.textlength(tag, font=f_small)) / 2, H * 0.40), tag, font=f_small, fill=ACCENT)
    f, lines = fit_text(d, channel.upper(), W - 140, 3, 132)
    y = H * 0.40 + 90
    for ln in lines:
        d.text(((W - d.textlength(ln, font=f)) / 2, y), ln, font=f, fill="white",
               stroke_width=6, stroke_fill="black")
        y += f.size * 1.12
    d.rounded_rectangle([W / 2 - 160, y + 30, W / 2 + 160, y + 42], radius=6, fill=ACCENT)
    bg.save(out_png)
    return out_png


def make_outro_overlay(channel, out_png):
    # đặt ở phần trên khung hình để không đè lên chữ Canva (thường nằm phía dưới)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    f1 = font(56, "Bold")
    f2, lines = fit_text(d, channel, W - 240, 2, 96)
    f3 = font(54, "ExtraBold")
    t1, t3 = "Theo dõi kênh", "ĐĂNG KÝ"
    line_h = f2.size * 1.12
    box_h = 60 + 70 + len(lines) * line_h + 40 + 92 + 60
    y0 = 260
    d.rounded_rectangle([70, y0, W - 70, y0 + box_h], radius=48, fill=(0, 0, 0, 190))
    y = y0 + 60
    d.text(((W - d.textlength(t1, font=f1)) / 2, y), t1, font=f1, fill="white")
    y += 70
    for ln in lines:
        d.text(((W - d.textlength(ln, font=f2)) / 2, y), ln, font=f2, fill=ACCENT)
        y += line_h
    y += 40
    bw = d.textlength(t3, font=f3) + 120
    bx = (W - bw) / 2
    d.rounded_rectangle([bx, y, bx + bw, y + 92], radius=46, fill=(230, 33, 23))
    d.text((bx + 60, y + 14), t3, font=f3, fill="white")
    ov.save(out_png)
    return out_png


def make_thumbnail(bg_png, text, channel, out_jpg):
    TW, TH = 1280, 720
    src = Image.open(bg_png).convert("RGB")
    canvas = cover(src, TW, TH).filter(ImageFilter.GaussianBlur(22))
    canvas = Image.blend(canvas, Image.new("RGB", canvas.size, (0, 0, 0)), 0.35)
    # ảnh dọc đặt bên phải
    ph = TH - 60
    pw = int(ph * W / H)
    portrait = src.resize((pw, ph), Image.LANCZOS)
    px = TW - pw - 40
    border = Image.new("RGB", (pw + 12, ph + 12), ACCENT)
    canvas.paste(border, (px - 6, 24))
    canvas.paste(portrait, (px, 30))
    d = ImageDraw.Draw(canvas)
    max_w = px - 90
    f, lines = fit_text(d, strip_emoji(text).upper(), max_w, 4, 104, minimum=52)
    total = len(lines) * f.size * 1.12
    y = (TH - total) / 2 - 30
    for i, ln in enumerate(lines):
        d.text((50, y), ln, font=f, fill=ACCENT if i == 0 else "white",
               stroke_width=7, stroke_fill="black")
        y += f.size * 1.12
    # nhãn tên kênh
    fc = font(40, "Bold")
    cw = d.textlength(channel, font=fc) + 60
    d.rounded_rectangle([40, TH - 100, 40 + cw, TH - 40], radius=30, fill=(230, 33, 23))
    d.text((70, TH - 95), channel, font=fc, fill="white")
    canvas.save(out_jpg, quality=90)
    return out_jpg


# ---------- dựng từng đoạn ----------
def kenburns(n, mode):
    if mode == "in":
        z = f"1+{ZOOM}*on/{n}"
    elif mode == "out":
        z = f"1+{ZOOM}-{ZOOM}*on/{n}"
    else:
        z = f"1+{ZOOM / 2}"
    return (f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={n}:s={W}x{H}:fps={FPS}")


def render_still(png, secs, out, mode="in", overlay=None, fade_in=0.15, fade_out=0.15):
    n = max(2, round(secs * FPS))
    d = n / FPS
    big = f"scale={W * 2}:{H * 2}"  # phóng to trước để zoompan không bị rung
    chain = (f"[0:v]{big},{kenburns(n, mode)},setsar=1,format=yuv420p[bg]")
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(png)]
    tail = (f"fade=t=in:st=0:d={fade_in},fade=t=out:st={max(d - fade_out, 0):.3f}:d={fade_out},"
            f"format=yuv420p[v]")
    if overlay:
        cmd += ["-loop", "1", "-framerate", str(FPS), "-t", f"{d:.3f}", "-i", str(overlay)]
        chain += (f";[1:v]format=rgba,fade=t=in:st=0.3:d=0.4:alpha=1[ov];"
                  f"[bg][ov]overlay=0:0:shortest=1,{tail}")
    else:
        chain += f";[bg]{tail}"
    cmd += ["-filter_complex", chain, "-map", "[v]", "-frames:v", str(n), "-r", str(FPS),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-an", str(out)]
    run(cmd)
    return n


def build(job, work, out_dir, fake_tts=False):
    work.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    channel = job.get("channel", "Bắt Sóng Hóng Trent")
    voice = job.get("voice", "vi-VN-HoaiMyNeural")
    pages, texts = job["pages"], job["texts"]
    if len(pages) != len(texts):
        raise ValueError(f"Số trang ({len(pages)}) khác số câu đọc ({len(texts)})")

    imgs = []
    for i, url in enumerate(pages, 1):
        src = Path(url)
        if src.exists():  # chạy thử bằng ảnh trên máy
            p = work / f"page_{i}.png"
            cover(Image.open(src), W, H).save(p)
        else:
            p = download(url, work / f"page_{i}.img")
        imgs.append(p)

    clips, audio, frames = [], [], 0
    # intro: thẻ tên kênh, im lặng
    intro_png = make_intro(imgs[0], channel, work / "intro.png")
    c = work / "c00_intro.mp4"
    n = render_still(intro_png, INTRO_SEC, c, mode="in", fade_in=0.05, fade_out=0.2)
    clips.append(c)
    frames += n
    silence = work / "intro.wav"
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
         "-t", f"{n / FPS:.3f}", "-c:a", "pcm_s16le", str(silence)])
    audio.append(silence)

    outro_ov = make_outro_overlay(channel, work / "outro_ov.png")
    modes = ["in", "out", "in", "out", "in", "still"]
    chapters = []
    for i, (img, text) in enumerate(zip(imgs, texts), 1):
        wav, secs = tts(text.strip(), voice, work / f"v{i}.mp3", fake=fake_tts)
        last = i == len(imgs)
        if last:
            secs += OUTRO_EXTRA
            padded = work / f"v{i}_pad.wav"
            run(["ffmpeg", "-y", "-v", "error", "-i", str(wav), "-af", f"apad=pad_dur={OUTRO_EXTRA}",
                 "-c:a", "pcm_s16le", str(padded)])
            wav = padded
        chapters.append({"start": frames / FPS, "text": text})
        c = work / f"c{i:02d}.mp4"
        n = render_still(img, secs, c, mode=modes[(i - 1) % len(modes)],
                         overlay=outro_ov if last else None, fade_out=0.35 if last else 0.15)
        clips.append(c)
        frames += n
        # cắt/đệm audio đúng bằng số khung hình để không lệch tiếng
        exact = work / f"a{i:02d}.wav"
        run(["ffmpeg", "-y", "-v", "error", "-i", str(wav), "-af", "apad",
             "-t", f"{n / FPS:.3f}", "-c:a", "pcm_s16le", str(exact)])
        audio.append(exact)

    # ghép hình
    lst = work / "clips.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in clips))
    video = work / "video.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c", "copy", str(video)])
    # ghép tiếng
    alst = work / "audio.txt"
    alst.write_text("".join(f"file '{p.name}'\n" for p in audio))
    voice_wav = work / "voice.wav"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(alst),
         "-c", "copy", str(voice_wav)])

    final = out_dir / "short.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(voice_wav),
         "-map", "0:v", "-map", "1:a", "-c:v", "copy",
         "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
         "-shortest", "-movflags", "+faststart", str(final)])

    thumb = make_thumbnail(imgs[0], job.get("thumb_text") or job.get("title", ""), channel,
                           out_dir / "thumbnail.jpg")
    result = {
        "job_id": job.get("job_id"),
        "duration": round(duration(final), 2),
        "size_mb": round(final.stat().st_size / 1e6, 2),
        "scenes": len(imgs),
        "timeline": chapters,
    }
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return final, thumb, result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job", help="đường dẫn job.json")
    ap.add_argument("--out", default="out")
    ap.add_argument("--work", default="work")
    ap.add_argument("--fake-tts", action="store_true", help="giọng giả để chạy thử không cần mạng")
    a = ap.parse_args()
    job = json.loads(Path(a.job).read_text(encoding="utf-8"))
    final, thumb, result = build(job, Path(a.work), Path(a.out), fake_tts=a.fake_tts)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
