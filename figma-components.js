/* WHAi Design System - Figma Component Structure */

export const components = {
  // 버튼
  Button: {
    Primary: {
      size: { width: "auto", height: 32 },
      padding: "8px 12px",
      backgroundColor: "#2563eb",
      textColor: "#ffffff",
      borderRadius: 6,
      fontSize: 12,
      fontWeight: 600
    },
    Secondary: {
      size: { width: "auto", height: 24 },
      padding: "4px 9px",
      backgroundColor: "#ffffff",
      textColor: "#64748b",
      border: "1px solid #e2e8f0",
      borderRadius: 5,
      fontSize: 11
    }
  },

  // 카드
  Card: {
    Default: {
      backgroundColor: "#ffffff",
      borderRadius: 12,
      border: "1px solid #e2e8f0",
      padding: "18px 20px",
      shadow: "none"
    }
  },

  // 칩
  Chip: {
    Default: {
      backgroundColor: "#eff6ff",
      border: "1px solid #bfdbfe",
      borderRadius: 20,
      padding: "4px 11px",
      textColor: "#1d4ed8",
      fontSize: 12,
      fontWeight: 700
    },
    Add: {
      backgroundColor: "#ffffff",
      border: "1px dashed #cbd5e1",
      borderRadius: 20,
      padding: "4px 11px",
      textColor: "#64748b",
      fontWeight: 500
    }
  },

  // 입력 필드
  Input: {
    Select: {
      backgroundColor: "#ffffff",
      border: "1px solid #cbd5e1",
      borderRadius: 8,
      padding: "10px 12px",
      fontSize: 12
    }
  },

  // 레이아웃
  Layout: {
    Sidebar: {
      width: 250,
      backgroundColor: "#1e293b",
      padding: 0
    },
    Header: {
      height: 60,
      backgroundColor: "#ffffff",
      borderBottom: "1px solid #e2e8f0",
      padding: "0 24px"
    },
    ContentArea: {
      padding: "24px",
      backgroundColor: "#ffffff"
    }
  },

  // 네비게이션 아이템
  NavItem: {
    Default: {
      height: 44,
      padding: "12px 16px",
      textColor: "#cbd5e1",
      fontSize: 14,
      fontWeight: 500,
      icon: true
    },
    Active: {
      height: 44,
      padding: "12px 16px",
      backgroundColor: "rgba(37, 99, 235, 0.1)",
      textColor: "#2563eb",
      fontSize: 14,
      fontWeight: 500,
      borderLeft: "3px solid #2563eb"
    }
  },

  // 메트릭 박스
  MetricBox: {
    Default: {
      backgroundColor: "#f8fafc",
      borderRadius: 8,
      padding: "10px 11px",
      label: { fontSize: 10, color: "#64748b" },
      value: { fontSize: 15, fontWeight: 700 }
    }
  },

  // 범위 버튼
  RangeButton: {
    Default: {
      padding: "4px 9px",
      backgroundColor: "#ffffff",
      textColor: "#64748b",
      border: "1px solid #e2e8f0",
      borderRadius: 5,
      fontSize: 11,
      cursor: "pointer"
    },
    Active: {
      padding: "4px 9px",
      backgroundColor: "#2563eb",
      textColor: "#ffffff",
      border: "1px solid #2563eb",
      borderRadius: 5,
      fontSize: 11
    }
  },

  // 뉴스 아이템
  NewsItem: {
    Default: {
      padding: "12px 0",
      borderBottom: "1px solid #f1f5f9",
      meta: { fontSize: 10, color: "#64748b" },
      title: { fontSize: 13, fontWeight: 600, lineHeight: 1.4 },
      body: { fontSize: 12, color: "#64748b", lineHeight: 1.6, marginTop: 4 }
    }
  },

  // AI 분석 박스
  AIBox: {
    Default: {
      backgroundColor: "#f8fafc",
      borderRadius: 8,
      padding: "12px 14px",
      border: "1px solid #e2e8f0",
      badge: {
        backgroundColor: "#7c3aed",
        textColor: "#ffffff",
        fontSize: 9,
        padding: "2px 6px",
        borderRadius: 4
      },
      text: {
        fontSize: 11,
        color: "#1e293b",
        lineHeight: 1.6,
        marginTop: 6
      }
    }
  }
};

/* 사용 예시:
1. design-tokens.json을 Figma에 import
2. figma-plugin.js를 Figma Developer Console에 실행
3. 위 컴포넌트 구조에 따라 Figma에서 컴포넌트 생성
4. 각 컴포넌트에 variants 추가 (Default, Active, Hover, Disabled 등)
*/
