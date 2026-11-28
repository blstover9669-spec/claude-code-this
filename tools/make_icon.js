// Draws the app icon (a fuzzling with a mushroom hat) to a 512x512 PNG.
// Usage: node tools/make_icon.js quest/icon.png
const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const b64 = await page.evaluate(() => {
    const c = document.createElement('canvas');
    c.width = c.height = 512;
    const g = c.getContext('2d');
    const bg = g.createLinearGradient(0, 0, 0, 512);
    bg.addColorStop(0, '#5a8ef0'); bg.addColorStop(0.62, '#ffc8a2'); bg.addColorStop(1, '#d99bc6');
    g.fillStyle = bg; g.fillRect(0, 0, 512, 512);
    // island
    g.fillStyle = '#6b4329'; g.beginPath(); g.ellipse(256, 470, 230, 70, 0, 0, Math.PI * 2); g.fill();
    g.fillStyle = '#5fb24c'; g.beginPath(); g.ellipse(256, 440, 236, 52, 0, 0, Math.PI * 2); g.fill();
    // fuzzy body
    const cx = 256, cy = 300, r = 150;
    g.fillStyle = '#ff6b6b';
    g.beginPath();
    for (let i = 0; i <= 64; i++) {
      const a = (i / 64) * Math.PI * 2, rr = r + (i % 2 ? 9 : -4);
      const x = cx + Math.cos(a) * rr, y = cy + Math.sin(a) * rr;
      i ? g.lineTo(x, y) : g.moveTo(x, y);
    }
    g.fill();
    g.fillStyle = 'rgba(255,255,255,0.18)'; g.beginPath(); g.ellipse(cx - 50, cy - 60, 70, 45, -0.5, 0, Math.PI * 2); g.fill();
    // mitts
    g.fillStyle = '#c94f4f';
    g.beginPath(); g.ellipse(112, 380, 44, 36, -0.4, 0, Math.PI * 2); g.fill();
    g.beginPath(); g.ellipse(400, 380, 44, 36, 0.4, 0, Math.PI * 2); g.fill();
    // eyes
    for (const s of [-1, 1]) {
      g.fillStyle = '#ffffff'; g.beginPath(); g.arc(cx + s * 52, cy - 8, 44, 0, Math.PI * 2); g.fill();
      g.fillStyle = '#1d1530'; g.beginPath(); g.arc(cx + s * 52 + 6, cy - 2, 22, 0, Math.PI * 2); g.fill();
      g.fillStyle = '#ffffff'; g.beginPath(); g.arc(cx + s * 52 + 14, cy - 12, 7, 0, Math.PI * 2); g.fill();
    }
    g.fillStyle = '#5a1f2e'; g.beginPath(); g.ellipse(cx, cy + 62, 26, 14, 0, 0, Math.PI); g.fill();
    // mushroom hat
    g.fillStyle = '#f6e9d3'; g.fillRect(cx - 18, 118, 36, 50);
    g.fillStyle = '#ff5fa8'; g.beginPath(); g.ellipse(cx, 128, 104, 66, 0, Math.PI, Math.PI * 2); g.fill();
    g.fillRect(cx - 104, 126, 208, 10);
    g.fillStyle = '#fff7f0';
    for (const [x, y, rr] of [[-50, 100, 15], [12, 82, 18], [60, 108, 13], [-14, 116, 9]]) { g.beginPath(); g.arc(cx + x, y, rr, 0, Math.PI * 2); g.fill(); }
    return c.toDataURL('image/png').split(',')[1];
  });
  fs.writeFileSync(process.argv[2] || 'icon.png', Buffer.from(b64, 'base64'));
  await browser.close();
})();
