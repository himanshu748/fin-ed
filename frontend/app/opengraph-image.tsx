import { ImageResponse } from 'next/og';

export const alt = 'FinEd Saathi explains Indian market concepts and costs in English or Hindi';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          alignItems: 'center',
          background: '#F6F2E8',
          color: '#15233B',
          display: 'flex',
          height: '100%',
          justifyContent: 'space-between',
          padding: '72px 80px',
          width: '100%',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', width: 650 }}>
          <div
            style={{
              color: '#174EA6',
              display: 'flex',
              fontSize: 22,
              fontWeight: 700,
              letterSpacing: 2,
            }}
          >
            FINANCIAL SERVICES · VOICE FOR BHARAT
          </div>
          <div
            style={{
              display: 'flex',
              fontSize: 72,
              fontWeight: 700,
              letterSpacing: -4,
              lineHeight: 0.98,
              marginTop: 32,
            }}
          >
            Same price. Why did I still lose money?
          </div>
          <div style={{ color: '#526174', display: 'flex', fontSize: 28, marginTop: 32 }}>
            FinEd Saathi explains concepts, charges and risks in English or Hindi.
          </div>
        </div>

        <div
          style={{
            background: '#FFFCF5',
            border: '2px solid #D8D0C0',
            borderRadius: 16,
            display: 'flex',
            flexDirection: 'column',
            padding: 32,
            width: 350,
          }}
        >
          <div style={{ color: '#526174', display: 'flex', fontSize: 18 }}>
            NSE DELIVERY ILLUSTRATION
          </div>
          <div
            style={{
              borderBottom: '2px solid #E9E3D7',
              display: 'flex',
              fontSize: 25,
              justifyContent: 'space-between',
              padding: '24px 0',
            }}
          >
            <span>Price P&amp;L</span>
            <span>zero</span>
          </div>
          <div
            style={{
              borderBottom: '2px solid #E9E3D7',
              display: 'flex',
              fontSize: 25,
              justifyContent: 'space-between',
              padding: '24px 0',
            }}
          >
            <span>Charges</span>
            <span>illustrative</span>
          </div>
          <div
            style={{
              color: '#A13D35',
              display: 'flex',
              fontSize: 28,
              fontWeight: 700,
              justifyContent: 'space-between',
              paddingTop: 24,
            }}
          >
            <span>Net</span>
            <span>negative after costs</span>
          </div>
        </div>
      </div>
    ),
    size
  );
}
