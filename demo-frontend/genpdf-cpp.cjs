const puppeteer = require('puppeteer');
(async () => {
  const browser = await puppeteer.launch({
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
    executablePath: '/usr/bin/google-chrome',
    headless: true,
  });
  const page = await browser.newPage();
  await page.goto('http://localhost:5173/resume-cpp.html', { waitUntil: 'networkidle0' });
  await page.emulateMediaType('print');
  await page.pdf({
    path: '/home/admin/workspace/puck02/25届-袁浩-C++开发工程师-LogScope版.pdf',
    format: 'A4',
    printBackground: true,
    preferCSSPageSize: true,
    margin: { top: '0', bottom: '0', left: '0', right: '0' },
  });
  await page.setViewport({ width: 794, height: 1123, deviceScaleFactor: 1 });
  await page.emulateMediaType('screen');
  await page.screenshot({
    path: '/home/admin/workspace/puck02/25届-袁浩-C++开发工程师-LogScope版.png',
    fullPage: true,
  });
  await browser.close();
  console.log('C++ resume PDF and screenshot generated!');
})();
