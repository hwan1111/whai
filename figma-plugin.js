// Figma Plugin: WHAi Design System
// Paste this in Figma Developer Console

const tokens = {
  "colors": {
    "primary": "#2563eb",
    "background": "#ffffff",
    "surface": "#f8fafc",
    "border": "#e2e8f0",
    "text": {
      "primary": "#1e293b",
      "secondary": "#64748b",
      "light": "#94a3b8"
    },
    "status": {
      "positive": "#16a34a",
      "negative": "#dc2626"
    },
    "assets": {
      "KOSPI": "#06b6d4",
      "005930": "#1e40af",
      "000660": "#eab308",
      "005380": "#dc2626",
      "000270": "#ef4444",
      "079550": "#0369a1",
      "012450": "#ea580c",
      "105560": "#fbbf24",
      "055550": "#2563eb",
      "051910": "#b91c1c",
      "096770": "#0891b2",
      "KRW/USD": "#3b82f6",
      "KRW/JPY": "#f59e0b",
      "KRW/EUR": "#f97316",
      "KRW/CNY": "#991b1b",
      "KRW/CHF": "#6366f1",
      "KRW/GBP": "#8b5cf6"
    }
  },
  "typography": {
    "heading1": { "fontSize": 24, "fontWeight": 700 },
    "heading2": { "fontSize": 19, "fontWeight": 800 },
    "heading3": { "fontSize": 17, "fontWeight": 700 },
    "body": { "fontSize": 14, "fontWeight": 400 },
    "bodySm": { "fontSize": 12, "fontWeight": 400 },
    "label": { "fontSize": 11, "fontWeight": 700 },
    "caption": { "fontSize": 10, "fontWeight": 400 }
  }
};

// 색상 라이브러리 생성
function createColorLibrary() {
  const page = figma.createPage();
  page.name = "🎨 Color System";

  let yOffset = 0;
  Object.entries(tokens.colors).forEach(([category, colors]) => {
    if (typeof colors === 'object' && !Array.isArray(colors)) {
      Object.entries(colors).forEach(([name, hex]) => {
        const rect = figma.createRectangle();
        rect.x = 0;
        rect.y = yOffset;
        rect.width = 200;
        rect.height = 80;
        rect.fills = [{ type: 'SOLID', color: hexToRgb(hex) }];

        const text = figma.createText();
        text.characters = `${category}/${name}\n${hex}`;
        text.fontSize = 12;
        text.x = 220;
        text.y = yOffset;

        page.appendChild(rect);
        page.appendChild(text);
        yOffset += 100;
      });
    }
  });
}

// Hex to RGB 변환
function hexToRgb(hex) {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return {
    r: parseInt(result[1], 16) / 255,
    g: parseInt(result[2], 16) / 255,
    b: parseInt(result[3], 16) / 255
  };
}

// 실행
createColorLibrary();
figma.notify("✅ 색상 라이브러리 생성 완료!");
