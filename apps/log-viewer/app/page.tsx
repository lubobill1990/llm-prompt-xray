'use client';

import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import RequestList from '@/components/RequestList';
import RequestDetail from '@/components/RequestDetail';
import { LogEntry, LogDetail } from '@/types/log';

interface LogDir {
  name: string;
  path: string;
}

export default function Home() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [selectedLog, setSelectedLog] = useState<LogDetail | null>(null);
  const [selectedId, setSelectedId] = useState<string | undefined>();
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [isDark, setIsDark] = useState(false);
  const [logDirs, setLogDirs] = useState<LogDir[]>([]);
  const [currentDir, setCurrentDir] = useState<string>('');

  // Detect dark mode
  useEffect(() => {
    const checkDarkMode = () => {
      setIsDark(
        window.matchMedia &&
        window.matchMedia('(prefers-color-scheme: dark)').matches
      );
    };

    checkDarkMode();

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    mediaQuery.addEventListener('change', checkDarkMode);

    return () => mediaQuery.removeEventListener('change', checkDarkMode);
  }, []);

  const fetchLogs = async (startTime?: number, endTime?: number, dir?: string) => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (startTime) params.append('startTime', startTime.toString());
      if (endTime) params.append('endTime', endTime.toString());
      const dirToUse = dir ?? currentDir;
      if (dirToUse) params.append('dir', dirToUse);

      const response = await fetch(`/api/logs?${params.toString()}`);
      const data = await response.json();
      setLogs(data);
      return data;
    } catch (error) {
      console.error('Error fetching logs:', error);
      return [];
    } finally {
      setLoading(false);
    }
  };

  const fetchLogDetail = async (id: string) => {
    setDetailLoading(true);
    try {
      const params = new URLSearchParams();
      if (currentDir) params.append('dir', currentDir);
      const response = await fetch(`/api/logs/${id}?${params.toString()}`);
      const data = await response.json();
      setSelectedLog(data);
    } catch (error) {
      console.error('Error fetching log detail:', error);
    } finally {
      setDetailLoading(false);
    }
  };

  // Load log directories
  useEffect(() => {
    const loadDirs = async () => {
      try {
        const response = await fetch('/api/log-dirs');
        const dirs: LogDir[] = await response.json();
        setLogDirs(dirs);
        // Use dir from URL or default to first
        const urlDir = searchParams.get('dir');
        const initialDir = urlDir && dirs.some(d => d.name === urlDir) ? urlDir : dirs[0]?.name || '';
        setCurrentDir(initialDir);
      } catch (error) {
        console.error('Error fetching log dirs:', error);
      }
    };
    loadDirs();
  }, []);

  // Load initial logs when currentDir is set
  useEffect(() => {
    if (!currentDir) return;

    const loadInitialData = async () => {
      const loadedLogs = await fetchLogs(undefined, undefined, currentDir);

      const logId = searchParams.get('log');
      if (logId && loadedLogs.length > 0) {
        const logExists = loadedLogs.some((log: LogEntry) => log.id === logId);
        if (logExists) {
          setSelectedId(logId);
          fetchLogDetail(logId);
        }
      }
    };

    loadInitialData();
  }, [currentDir]);

  const handleSelect = (id: string) => {
    setSelectedId(id);
    fetchLogDetail(id);

    // Update URL with selected log and current dir
    const params = new URLSearchParams(window.location.search);
    params.set('log', id);
    if (currentDir) params.set('dir', currentDir);
    router.push(`?${params.toString()}`, { scroll: false });
  };

  const handleFilterChange = (startTime?: number, endTime?: number) => {
    setSelectedId(undefined);
    setSelectedLog(null);

    // Clear log selection from URL
    const params = new URLSearchParams();
    if (startTime) params.append('startTime', startTime.toString());
    if (endTime) params.append('endTime', endTime.toString());
    if (currentDir) params.append('dir', currentDir);

    router.push(params.toString() ? `?${params.toString()}` : '/', { scroll: false });
    fetchLogs(startTime, endTime);
  };

  const handleDirChange = (dirName: string) => {
    setCurrentDir(dirName);
    setSelectedId(undefined);
    setSelectedLog(null);
    setLogs([]);

    const params = new URLSearchParams();
    params.set('dir', dirName);
    router.push(`?${params.toString()}`, { scroll: false });
  };

  return (
    <main className="flex h-screen overflow-hidden bg-white dark:bg-gray-900">
      {/* Left Panel - Request List */}
      <div className="w-96 shrink-0 border-r border-gray-200 dark:border-gray-700 flex flex-col overflow-hidden">
        <div className="p-4 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
          <h1 className="text-xl font-bold text-gray-900 dark:text-white">
            HTTP Proxy Logs
          </h1>
          {logDirs.length > 1 && (
            <select
              value={currentDir}
              onChange={(e) => handleDirChange(e.target.value)}
              className="mt-2 w-full px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-sm text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              {logDirs.map((dir) => (
                <option key={dir.name} value={dir.name}>
                  {dir.name}
                </option>
              ))}
            </select>
          )}
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            {logs.length} requests
          </p>
        </div>
        <div className="flex-1 min-h-0 overflow-hidden">
          {loading ? (
            <div className="h-full flex items-center justify-center text-gray-500 dark:text-gray-400">
              Loading...
            </div>
          ) : (
            <RequestList
              logs={logs}
              selectedId={selectedId}
              onSelect={handleSelect}
              onFilterChange={handleFilterChange}
            />
          )}
        </div>
      </div>

      {/* Right Panel - Request Detail */}
      <div className="flex-1 min-w-0 flex flex-col">
        {detailLoading ? (
          <div className="flex-1 flex items-center justify-center text-gray-500 dark:text-gray-400">
            Loading details...
          </div>
        ) : (
          <RequestDetail log={selectedLog} isDark={isDark} />
        )}
      </div>
    </main>
  );
}
