// Renders the social preview and the PNG icons.  Usage: node tools/render_og.cjs
const { chromium } = require("playwright");
const path = require("node:path");
const at = p => path.join(__dirname, p);
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1200, height: 630 } });
  await page.goto("file://" + at("og.html"));
  if (process.env.OG_FONT_CSS) await page.addStyleTag({ path: process.env.OG_FONT_CSS });  // offline fallback for the web fonts
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: at("../og.png") });
  for (const size of [180, 192, 512]) {
    await page.setViewportSize({ width: size, height: size });
    await page.goto("file://" + at("../favicon.svg"));
    await page.screenshot({ path: at(`../icon-${size}.png`) });
  }
  await browser.close();
})();
