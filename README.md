# Shorts Clip Editor Skill

Standar editing untuk mengubah episode podcast panjang menjadi YouTube Shorts
vertikal (1080×1920), dipakai di channel SinPOD.

## Isi repo

- `SKILL.md` — standar lengkap: cover hook, subtitle karaoke, jump cut,
  watermark, intro & SFX, upload config, dan riwayat revisi standar.
- `skill.yaml` — metadata skill.
- `render_sinpod_upgraded.py` — template render generik (ffmpeg + libass):
  subtitle karaoke kuning anti-tumpuk, loudnorm, QC otomatis pra-render.

## Ringkasan standar

1. **Cover hook 2–3 detik** — kolase emosi: foto pembicara (atas), teks hook
   (tengah), foto reaksi (bawah). Tanpa voice-over, audio asli saja.
2. **Subtitle karaoke kuning** — per kata, hasil akhir Whisper large-v3 +
   koreksi istilah manual + QA ketat (tidak ada kata hilang/terpotong).
3. **Jump cut rapat**, watermark nama channel di tengah frame, logo
   "FULL VIDEO + nama sumber" di kiri atas.
4. **Intro & SFX khas** yang sama di setiap clip sebagai signature channel.

Detail terukur (posisi, ukuran font, margin) ada di `SKILL.md`.
