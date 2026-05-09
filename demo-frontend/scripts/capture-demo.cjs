const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs');

(async () => {
  const outDir = path.resolve(__dirname, '../../docs/assets');
  fs.mkdirSync(outDir, { recursive: true });
  const outPath = path.join(outDir, 'demo-chat.png');

  const browser = await puppeteer.launch({
    headless: 'new',
    executablePath: '/usr/bin/google-chrome',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
    defaultViewport: { width: 430, height: 860, deviceScaleFactor: 2 },
  });
  const page = await browser.newPage();
  page.setDefaultTimeout(45000);

  const messages = [
    { role: 'assistant', content: '你好！我是 Kitty 健康管家，有什么可以帮你的吗？' },
    { role: 'user', content: '高血压患者饮食需要注意什么？请给我3条建议' },
    {
      role: 'assistant',
      content: '好的，阿狸～Kitty 给你整理 3 条最核心的建议：\n\n**1. 控盐是第一优先级**\n每天食盐尽量控制在 5g 左右，少吃咸菜、腊肉、加工肉和高钠调味品。\n\n**2. 多吃蔬果和高钾食物**\n比如菠菜、番茄、香蕉、豆类等，有助于钠钾平衡。\n\n**3. 少油少糖，优先优质蛋白**\n少吃油炸食品、肥肉和甜点，可以选择鱼肉、豆制品、低脂奶。\n\n温馨提醒：如果已经在服降压药，不要自行停药或改剂量，调整方案请先咨询医生。',
      intent: 'search_health',
      latency: 5300,
      references: [
        { source: '高血压饮食建议.md', collection: 'health_knowledge', score: 0.91 },
        { source: '慢病饮食管理.md', collection: 'health_knowledge', score: 0.86 },
      ],
    },
  ];

  await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle2' });
  await page.evaluate((messages) => {
    localStorage.setItem('hei-chat-state', JSON.stringify({ messages, inputText: '' }));
    localStorage.setItem('hei-session-state', JSON.stringify({
      sessions: [{ session_id: 'readme-demo', title: '高血压饮食建议', message_count: 2, updated_at: new Date().toISOString() }],
      currentSessionId: 'readme-demo',
      sidebarVisible: false,
    }));
  }, messages);
  await page.reload({ waitUntil: 'networkidle2' });
  await page.waitForSelector('input[placeholder="输入你的健康问题..."]');
  await new Promise(resolve => setTimeout(resolve, 800));
  await page.screenshot({ path: outPath, fullPage: false });
  console.log(outPath);
  await browser.close();
})();
