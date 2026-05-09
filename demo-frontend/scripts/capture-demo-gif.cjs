const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs');
const { spawnSync } = require('child_process');

function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

(async () => {
  const root = path.resolve(__dirname, '../..');
  const outDir = path.join(root, 'docs/assets');
  const frameDir = path.join(outDir, 'gif-frames');
  fs.mkdirSync(frameDir, { recursive: true });
  for (const f of fs.readdirSync(frameDir)) fs.unlinkSync(path.join(frameDir, f));

  const browser = await puppeteer.launch({
    headless: 'new',
    executablePath: '/usr/bin/google-chrome',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
    defaultViewport: { width: 390, height: 780, deviceScaleFactor: 1 },
  });
  const page = await browser.newPage();
  page.setDefaultTimeout(45000);

  const shot = async (name, repeat = 1) => {
    for (let i = 0; i < repeat; i++) {
      const idx = String(fs.readdirSync(frameDir).length).padStart(3, '0');
      await page.screenshot({ path: path.join(frameDir, `${idx}-${name}.png`), fullPage: false });
    }
  };

  await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle2' });
  await page.evaluate(() => {
    localStorage.removeItem('hei-chat-state');
    localStorage.removeItem('hei-session-state');
  });
  await page.reload({ waitUntil: 'networkidle2' });
  await page.waitForSelector('input[placeholder="输入你的健康问题..."]');
  await sleep(600);
  await shot('welcome', 6);

  const question = '高血压患者饮食需要注意什么？';
  for (const ch of question) {
    await page.type('input[placeholder="输入你的健康问题..."]', ch, { delay: 18 });
    if (Math.random() < 0.45) await shot('typing', 1);
  }
  await shot('typed', 5);

  // Seed a realistic loading state and final answer instead of relying on network latency,
  // so the GIF is stable and reproducible for README display.
  await page.evaluate(() => {
    const input = document.querySelector('input[placeholder="输入你的健康问题..."]');
    if (input) input.value = '';
    const messages = [
      { role: 'assistant', content: '你好！我是 Kitty 健康管家，有什么可以帮你的吗？' },
      { role: 'user', content: '高血压患者饮食需要注意什么？' },
    ];
    localStorage.setItem('hei-chat-state', JSON.stringify({ messages, inputText: '' }));
    localStorage.setItem('hei-session-state', JSON.stringify({
      sessions: [{ session_id: 'readme-gif-demo', title: '高血压饮食建议', message_count: 1, updated_at: new Date().toISOString() }],
      currentSessionId: 'readme-gif-demo',
      sidebarVisible: false,
    }));
  });
  await page.reload({ waitUntil: 'networkidle2' });
  await sleep(500);
  await page.evaluate(() => {
    const box = document.querySelector('.flex-1.overflow-y-auto');
    if (!box) return;
    const loading = document.createElement('div');
    loading.id = 'readme-demo-loading';
    loading.className = 'flex items-center gap-2 text-kitty-400 text-sm pl-10';
    loading.innerHTML = '<span>🎀</span> 思考中...';
    box.appendChild(loading);
  });
  await shot('loading', 10);

  const answer = {
    role: 'assistant',
    content: '好的，阿狸～Kitty 给你整理 3 条核心建议：\n\n**1. 控盐优先**：少吃咸菜、腊肉和高钠调味品。\n\n**2. 多吃蔬果**：补充钾和膳食纤维，帮助管理血压。\n\n**3. 少油少糖**：优先鱼肉、豆制品、低脂奶等优质蛋白。\n\n温馨提醒：用药调整请先咨询医生。',
    intent: 'search_health',
    latency: 5300,
    references: [
      { source: '高血压饮食建议.md', collection: 'health_knowledge', score: 0.91 },
      { source: '慢病饮食管理.md', collection: 'health_knowledge', score: 0.86 },
    ],
  };
  await page.evaluate((answer) => {
    const messages = [
      { role: 'assistant', content: '你好！我是 Kitty 健康管家，有什么可以帮你的吗？' },
      { role: 'user', content: '高血压患者饮食需要注意什么？' },
      answer,
    ];
    localStorage.setItem('hei-chat-state', JSON.stringify({ messages, inputText: '' }));
  }, answer);
  await page.reload({ waitUntil: 'networkidle2' });
  await sleep(500);
  await shot('answer', 16);

  await browser.close();

  const py = path.join(root, 'demo-frontend/scripts/make-gif.py');
  const result = spawnSync(path.join(root, '.venv/bin/python3'), [py, frameDir, path.join(outDir, 'demo-chat.gif')], {
    stdio: 'inherit',
    cwd: root,
  });
  process.exit(result.status || 0);
})();
