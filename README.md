# batsong-shorts

Bộ dựng YouTube Shorts tự động cho kênh **Bắt Sóng Hóng Trent**, chạy miễn phí trên GitHub Actions bằng ffmpeg.

## Luồng chạy

1. Make (scenario A) viết kịch bản, vẽ ảnh, điền template Canva, xuất 6 trang PNG.
2. Make gọi GitHub API `repository_dispatch` (`event_type: render-short`) kèm `client_payload.job`.
3. Workflow `.github/workflows/render.yml` chạy `render.py`:
   - giọng đọc HoaiMy (edge-tts, miễn phí);
   - ảnh trang Canva chuyển động chậm (Ken Burns);
   - intro thẻ tên kênh khoảng 1,2 giây và outro "Đăng ký kênh";
   - thumbnail 1280x720 có tên kênh;
   - xuất `short.mp4` 1080x1920, 30fps, âm lượng chuẩn -14 LUFS.
4. Video và thumbnail được đưa lên một Release của repo, rồi `callback.py` gọi webhook Make (scenario B).
5. Make (scenario B) tải video lên YouTube, đặt thumbnail, kiểm tra, đăng công khai và báo Telegram.

Mỗi lần dựng mất khoảng 2–3 phút. Repo chỉ giữ 30 release gần nhất.

## Chạy thử trên máy

```bash
pip install -r requirements.txt   # cần ffmpeg trong PATH
python render.py job.json --out out --work work            # giọng thật (cần mạng)
python render.py job.json --out out --work work --fake-tts # giọng giả để thử nhanh
```

Cấu trúc `job.json`:

```json
{
  "job_id": "20261124-1303",
  "channel": "Bắt Sóng Hóng Trent",
  "title": "Tiêu đề video",
  "thumb_text": "Chữ lớn trên thumbnail",
  "pages": ["url trang 1", "...", "url trang 6"],
  "texts": ["lời đọc cảnh 1", "...", "lời đọc cảnh 6"],
  "voice": "vi-VN-HoaiMyNeural",
  "callback_url": "https://hook.us2.make.com/...",
  "meta": {"title": "...", "description": "...", "hashtags": "#shorts ..."}
}
```

Font Montserrat thuộc giấy phép SIL Open Font License (`fonts/OFL-Montserrat.txt`).
