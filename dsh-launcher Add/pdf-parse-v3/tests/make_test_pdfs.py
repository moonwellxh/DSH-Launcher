#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate deterministic test PDFs WITHOUT extra libs (manual xref builder).

Usage:
  python make_test_pdfs.py <outdir>
Creates:
  t_text.pdf   1 page, text layer "Hello PDF 2026 Alpha Beta Gamma"
  t_hybrid.pdf 2 pages: page1 text layer, page2 blank (no text => image page)
  t_img.pdf    1 page embedding <outdir>/t_img_src.jpg (DCTDecode) if present
"""
import os
import sys


def _escape(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(path, pages, w=595, h=842):
    """pages: list of content-stream bytes (one per page)."""
    font_no = 3 + 2 * len(pages)   # font object number depends on page count
    objs = []
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = []
    for i in range(len(pages)):
        kids.append("%d 0 R" % (3 + 2 * i))
    objs.append(b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(k.encode() for k in kids), len(pages)))
    for i, content in enumerate(pages):
        page_no = 3 + 2 * i
        content_no = page_no + 1
        objs.append(
            ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Contents %d 0 R "
             "/Resources << /Font << /F1 %d 0 R >> >> >>" % (w, h, content_no, font_no)).encode()
        )
        objs.append(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for o in objs:
        offsets.append(len(out))
        out.extend(b"%d 0 obj\n" % (len(offsets)))
        out.extend(o)
        out.extend(b"\nendobj\n")
    xref_pos = len(out)
    out.extend(b"xref\n0 %d\n" % (len(objs) + 1))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets:
        out.extend(("%010d 00000 n \n" % off).encode())
    out.extend(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref_pos))
    with open(path, "wb") as f:
        f.write(bytes(out))


def text_page(text, size=48, x=60, y=720):
    cmd = "BT /F1 %d Tf %d %d Td (%s) Tj ET" % (size, x, y, _escape(text))
    return cmd.encode("latin-1")


def image_page(jpeg_path, w=595, h=842, img_w=300, img_h=200):
    with open(jpeg_path, "rb") as f:
        data = f.read()
    # page object with image XObject; content scales image into upper area.
    content = (
        b"q %d 0 0 %d 148 500 cm /Im1 Do Q" % (img_w, img_h)
    )
    xobj = b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length %d >>\nstream\n" % (
        img_w, img_h, len(data)
    ) + data + b"\nendstream"
    # custom build: page with image resource
    return content, xobj


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(outdir, exist_ok=True)

    t1 = text_page("Hello PDF 2026 Alpha Beta Gamma Delta", 44)
    build_pdf(os.path.join(outdir, "t_text.pdf"), [t1])

    blank = b""
    build_pdf(os.path.join(outdir, "t_hybrid.pdf"), [t1, blank])

    ts = text_page("Short title page", 40)
    build_pdf(os.path.join(outdir, "t_short.pdf"), [ts])

    jpg = os.path.join(outdir, "t_img_src.jpg")
    if os.path.isfile(jpg):
        content, xobj = image_page(jpg)
        # manual single page w/ image resource
        objs = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /XObject << /Im1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
            xobj,
        ]
        out = bytearray(b"%PDF-1.4\n")
        offsets = []
        for o in objs:
            offsets.append(len(out))
            out.extend(b"%d 0 obj\n" % (len(offsets)))
            out.extend(o)
            out.extend(b"\nendobj\n")
        xref_pos = len(out)
        out.extend(b"xref\n0 %d\n" % (len(objs) + 1))
        out.extend(b"0000000000 65535 f \n")
        for off in offsets:
            out.extend(("%010d 00000 n \n" % off).encode())
        out.extend(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref_pos))
        with open(os.path.join(outdir, "t_img.pdf"), "wb") as f:
            f.write(bytes(out))
    print("made in " + outdir)


if __name__ == "__main__":
    main()
