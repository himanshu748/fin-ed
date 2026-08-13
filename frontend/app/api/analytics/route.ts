import { NextResponse } from 'next/server';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { decodeCallAnalyticsSummary, emptyCallAnalyticsSummary } from '@/lib/call-analytics';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

const SNAPSHOT_PATH =
  process.env.FINED_ANALYTICS_SNAPSHOT_PATH ??
  resolve(process.cwd(), '../backend/data/analytics/public-summary.json');

export async function GET() {
  try {
    const payload = JSON.parse(await readFile(SNAPSHOT_PATH, 'utf8'));
    return NextResponse.json(decodeCallAnalyticsSummary(payload), {
      headers: { 'Cache-Control': 'no-store' },
    });
  } catch {
    return NextResponse.json(emptyCallAnalyticsSummary(), {
      headers: { 'Cache-Control': 'no-store' },
    });
  }
}
