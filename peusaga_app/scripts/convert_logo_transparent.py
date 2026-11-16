"""Konverter logo PEUSAGA ke format PNG transparan (tanpa latar putih)."""
from pathlib import Path
from collections import deque
import numpy as np
from PIL import Image


def convert_to_transparent_png(src_path: Path, out_full: Path, out_web: Path, out_artifact: Path, img_dir: Path) -> None:
    """Menghapus latar belakang putih dengan alpha matting dan dekontaminasi warna tepi."""
    img = Image.open(src_path).convert("RGB")
    arr = np.array(img, dtype=np.float32)
    h, w, _ = arr.shape

    min_rgb = arr.min(axis=2)
    max_rgb = arr.max(axis=2)
    chroma = max_rgb - min_rgb
    lum = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]

    # Deteksi piksel latar putih murni yang terhubung dengan tepi kanvas
    pure_bg = (min_rgb >= 238.0) & (chroma <= 18.0)
    exterior = np.zeros((h, w), dtype=bool)
    queue = deque([(0, 0), (0, w - 1), (h - 1, 0), (h - 1, w - 1)])
    for r, c in list(queue):
        if pure_bg[r, c]:
            exterior[r, c] = True

    while queue:
        r, c = queue.popleft()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < h and 0 <= nc < w and not exterior[nr, nc] and pure_bg[nr, nc]:
                exterior[nr, nc] = True
                queue.append((nr, nc))

    # Dilasi 3 piksel dari area eksterior untuk menangani tepi anti-aliasing (halo putih)
    near_exterior = exterior.copy()
    for _ in range(3):
        padded = np.pad(near_exterior, 1, mode="edge")
        near_exterior = (
            near_exterior
            | padded[:-2, 1:-1]
            | padded[2:, 1:-1]
            | padded[1:-1, :-2]
            | padded[1:-1, 2:]
            | padded[:-2, :-2]
            | padded[:-2, 2:]
            | padded[2:, :-2]
            | padded[2:, 2:]
        )

    # Estimasi opasitas: 0 di latar eksterior, transisi halus pada zona tepi anti-aliasing
    alpha = np.ones((h, w), dtype=np.float32)
    alpha[exterior] = 0.0

    # Zona transisi netral terang yang berbatasan langsung dengan latar
    transition = near_exterior & (~exterior) & (chroma <= 45.0) & (lum >= 185.0)
    # Nilai luminans 250 -> alpha 0, 185 -> alpha 1
    alpha[transition] = np.clip((246.0 - lum[transition]) / (246.0 - 185.0), 0.0, 1.0)

    # Dekontaminasi warna latar putih: C_out = (C_in - (1 - alpha) * 255) / alpha
    rgb_out = arr.copy()
    safe_alpha = np.maximum(alpha, 0.05)
    mask_decontam = (alpha > 0.0) & (alpha < 0.99)
    for ch in range(3):
        c_corr = (arr[:, :, ch] - (1.0 - alpha) * 255.0) / safe_alpha
        rgb_out[:, :, ch] = np.where(mask_decontam, np.clip(c_corr, 0.0, 255.0), rgb_out[:, :, ch])
    rgb_out[alpha <= 0.01] = 0.0

    rgba = np.dstack([rgb_out, alpha * 255.0]).round().astype(np.uint8)
    full_img = Image.fromarray(rgba, mode="RGBA")

    # Simpan versi penuh ke direktori Branding
    out_full.parent.mkdir(parents=True, exist_ok=True)
    full_img.save(out_full, format="PNG", optimize=True)

    # Potong bounding box konten dan beri padding 4% agar proporsional di antarmuka web
    bbox = full_img.getbbox()
    if bbox:
        cropped = full_img.crop(bbox)
        side = int(max(cropped.width, cropped.height) * 1.08)
        square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        offset = ((side - cropped.width) // 2, (side - cropped.height) // 2)
        square.paste(cropped, offset, cropped)
    else:
        square = full_img

    web_img = square.resize((512, 512), Image.Resampling.LANCZOS)
    web_img.save(out_web, format="PNG", optimize=True)
    out_artifact.parent.mkdir(parents=True, exist_ok=True)
    web_img.save(out_artifact, format="PNG", optimize=True)

    for size in (64, 32, 16):
        fav = square.resize((size, size), Image.Resampling.LANCZOS)
        fav.save(img_dir / f"favicon-{size}.png", format="PNG", optimize=True)

    check = np.array(web_img)
    print(f"Saved full PNG: {out_full} ({full_img.size})")
    print(f"Saved web PNG : {out_web} ({web_img.size}), corner alpha={check[0,0,3]}")
    print(f"Transparent pixels: {(check[:,:,3] == 0).sum()} / {check.shape[0]*check.shape[1]}")


if __name__ == "__main__":
    app_dir = Path(__file__).resolve().parent.parent
    branding_dir = app_dir.parent.parent / "Branding"
    src = branding_dir / "logo_genai_opsi_4a.jpg"
    out_full = branding_dir / "logo_genai_opsi_4a_transparan.png"
    img_dir = app_dir / "static" / "img"
    out_web = img_dir / "logo_peusaga.png"
    out_artifact = app_dir.parent.parent.parent / "outputs" / "02_Peusaga_Fullstack" / "logo_peusaga_transparan.png"
    convert_to_transparent_png(src, out_full, out_web, out_artifact, img_dir)
