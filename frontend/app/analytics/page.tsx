import type { Metadata } from 'next';
import { CallAnalyticsDashboard } from '@/components/analytics/call-analytics-dashboard';

export const metadata: Metadata = {
  title: 'Call Analytics | FinEd Saathi',
  description: 'Anonymous real-call outcomes for the FinEd Saathi voice learning agent.',
};

export default function AnalyticsPage() {
  return <CallAnalyticsDashboard />;
}
