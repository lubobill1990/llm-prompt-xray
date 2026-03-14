import { NextRequest, NextResponse } from 'next/server';
import { getLogEntries } from '@/lib/logs';

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const startTime = searchParams.get('startTime');
  const endTime = searchParams.get('endTime');
  const dir = searchParams.get('dir') || undefined;

  const start = startTime ? parseInt(startTime) : undefined;
  const end = endTime ? parseInt(endTime) : undefined;

  try {
    const entries = await getLogEntries(start, end, dir);
    return NextResponse.json(entries);
  } catch (error) {
    console.error('Error fetching logs:', error);
    return NextResponse.json(
      { error: 'Failed to fetch logs' },
      { status: 500 }
    );
  }
}
