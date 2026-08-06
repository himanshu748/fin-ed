import type { Metadata, Viewport } from 'next';
import { IBM_Plex_Mono, Manrope, Source_Sans_3 } from 'next/font/google';
import { headers } from 'next/headers';
import { getAppConfig } from '@/lib/utils';
import '@/styles/globals.css';

const manrope = Manrope({
  variable: '--font-manrope',
  subsets: ['latin'],
  weight: ['600', '700'],
});

const sourceSans = Source_Sans_3({
  variable: '--font-source-sans-3',
  subsets: ['latin'],
  weight: ['400', '600'],
  display: 'swap',
});

const ibmPlexMono = IBM_Plex_Mono({
  variable: '--font-ibm-plex-mono',
  subsets: ['latin'],
  weight: ['400', '500'],
  display: 'swap',
});

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
};

export async function generateMetadata(): Promise<Metadata> {
  const hdrs = await headers();
  const appConfig = await getAppConfig(hdrs);

  return {
    title: appConfig.pageTitle,
    description: appConfig.pageDescription,
    openGraph: {
      title: appConfig.pageTitle,
      description: appConfig.pageDescription,
      type: 'website',
      locale: 'en_IN',
    },
  };
}

interface RootLayoutProps {
  children: React.ReactNode;
}

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html
      lang="en-IN"
      className={`${manrope.variable} ${sourceSans.variable} ${ibmPlexMono.variable}`}
    >
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body>{children}</body>
    </html>
  );
}
