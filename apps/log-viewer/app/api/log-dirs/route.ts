import { NextResponse } from 'next/server';
import { getLogDirs } from '@/lib/logs';

export async function GET() {
  try {
    const dirs = getLogDirs();
    return NextResponse.json(dirs);
  } catch (error) {
    console.error('Error fetching log dirs:', error);
    return NextResponse.json(
      { error: 'Failed to fetch log directories' },
      { status: 500 }
    );
  }
}
