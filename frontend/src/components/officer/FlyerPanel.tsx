import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { CLUB_NAME } from "../../config";
import { Alert, Card, btn, inputCls, labelCls } from "../ui";

/**
 * FR-13: printable QR flyer. The QR is generated in the browser (bundled
 * `qrcode` library) — no external service is contacted.
 *
 * Phones can't reach "localhost", so officers should enter the hosting
 * computer's LAN address (e.g. http://192.168.1.25:8000) — risk #1 in the plan.
 */
export default function FlyerPanel() {
  const [url, setUrl] = useState(() => `${window.location.origin}/`);
  const [headline, setHeadline] = useState("Play chess with us!");
  const [details, setDetails] = useState("Thursdays 6:00 PM · Straub 145\nAll levels welcome — no experience needed");
  const [qr, setQr] = useState<string | null>(null);

  const isLocal = /\/\/(localhost|127\.0\.0\.1|\[::1\])/.test(url);

  useEffect(() => {
    let cancelled = false;
    QRCode.toDataURL(url || " ", { width: 600, margin: 1, errorCorrectionLevel: "M", color: { dark: "#064e3b" } })
      .then((d) => !cancelled && setQr(d))
      .catch(() => !cancelled && setQr(null));
    return () => {
      cancelled = true;
    };
  }, [url]);

  async function downloadPng() {
    if (!qr) return;
    const W = 1275; // 8.5in × 150dpi
    const H = 1650; // 11in × 150dpi
    const canvas = document.createElement("canvas");
    canvas.width = W;
    canvas.height = H;
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = "#065f46";
    ctx.fillRect(0, 0, W, 260);

    ctx.textAlign = "center";
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 64px system-ui, sans-serif";
    ctx.fillText(`♞ ${CLUB_NAME}`, W / 2, 150);
    ctx.font = "32px system-ui, sans-serif";
    ctx.fillText("University of Oregon", W / 2, 210);

    ctx.fillStyle = "#0f172a";
    ctx.font = "bold 80px system-ui, sans-serif";
    ctx.fillText(headline, W / 2, 400, W - 120);

    ctx.font = "40px system-ui, sans-serif";
    details.split("\n").forEach((line, i) => ctx.fillText(line, W / 2, 490 + i * 56, W - 120));

    const img = new Image();
    img.src = qr;
    await img.decode();
    const size = 640;
    ctx.drawImage(img, (W - size) / 2, 660, size, size);

    ctx.fillStyle = "#065f46";
    ctx.font = "bold 44px system-ui, sans-serif";
    ctx.fillText("Scan to see meeting times & register", W / 2, 1390);
    ctx.fillStyle = "#334155";
    ctx.font = "30px ui-monospace, monospace";
    ctx.fillText(url, W / 2, 1450, W - 120);

    const a = document.createElement("a");
    a.href = canvas.toDataURL("image/png");
    a.download = "ec-chesshub-flyer.png";
    a.click();
  }

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title="Flyer settings" className="no-print h-fit">
        <div className="space-y-4">
          <div>
            <label htmlFor="flyer-url" className={labelCls}>
              Link encoded in the QR code
            </label>
            <input
              id="flyer-url"
              className={`${inputCls} font-mono text-sm`}
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
          </div>
          {isLocal && (
            <Alert kind="info">
              Phones can't open <code>localhost</code>. Replace it with this computer's network address (e.g.{" "}
              <code>http://192.168.1.25:8000/</code>) — see the README for how to find it.
            </Alert>
          )}
          <div>
            <label htmlFor="flyer-headline" className={labelCls}>
              Headline
            </label>
            <input id="flyer-headline" className={inputCls} value={headline} onChange={(e) => setHeadline(e.target.value)} />
          </div>
          <div>
            <label htmlFor="flyer-details" className={labelCls}>
              Details (one line each)
            </label>
            <textarea
              id="flyer-details"
              rows={3}
              className={inputCls}
              value={details}
              onChange={(e) => setDetails(e.target.value)}
            />
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className={btn.primary} onClick={downloadPng} disabled={!qr}>
              ⬇ Download PNG
            </button>
            <button type="button" className={btn.secondary} onClick={() => window.print()}>
              🖨 Print / Save as PDF
            </button>
          </div>
        </div>
      </Card>

      {/* Preview — this is also exactly what prints */}
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white text-center shadow-sm print:border-0 print:shadow-none">
        <div className="bg-brand-800 px-4 py-6 text-white print:[-webkit-print-color-adjust:exact] print:[print-color-adjust:exact]">
          <p className="text-2xl font-bold">♞ {CLUB_NAME}</p>
          <p className="text-brand-100">University of Oregon</p>
        </div>
        <div className="space-y-4 p-6">
          <p className="break-words text-3xl font-extrabold text-slate-900">{headline}</p>
          <p className="whitespace-pre-line text-lg text-slate-700">{details}</p>
          {qr && <img src={qr} alt={`QR code linking to ${url}`} className="mx-auto w-56 sm:w-64 print:w-80" />}
          <p className="font-semibold text-brand-800">Scan to see meeting times &amp; register</p>
          <p className="break-all font-mono text-sm text-slate-600">{url}</p>
        </div>
      </div>
    </div>
  );
}
