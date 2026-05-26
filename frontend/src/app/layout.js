import './globals.css';

export const metadata = {
  title: 'WHAi',
  description: '다중 자산 지표 통합 분석 AI',
};

export default function RootLayout({ children }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
