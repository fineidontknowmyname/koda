'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { pollJobStatus, JobStatus, JobStatusResponse } from '@/lib/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UseJobStatusOptions {
    /** Interval in ms between poll requests. Default: 3000 */
    intervalMs?: number;
    /** Maximum number of polls before giving up. Default: 120 (= 6 min @ 3 s) */
    maxPolls?: number;
    /** Called once when the job reaches SUCCESS or FAILED. */
    onSettled?: (result: JobStatusResponse) => void;
}

export interface UseJobStatusReturn {
    status: JobStatus | null;
    result: Record<string, unknown> | null | undefined;
    error: string | null | undefined;
    isPolling: boolean;
    pollCount: number;
    /** Manually stop polling (e.g. when the component unmounts or user cancels). */
    stop: () => void;
    /** Restart polling with the same jobId (useful after a transient error). */
    restart: () => void;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * useJobStatus
 *
 * Polls GET /api/v1/plans/job/{jobId} every `intervalMs` milliseconds until
 * the backend reports SUCCESS or FAILED (or `maxPolls` is reached).
 *
 * Usage:
 *   const { status, result, error, isPolling } = useJobStatus(jobId);
 */
export function useJobStatus(
    jobId: string | null,
    {
        intervalMs = 3_000,
        maxPolls = 120,
        onSettled,
    }: UseJobStatusOptions = {},
): UseJobStatusReturn {
    const [statusData, setStatusData] = useState<JobStatusResponse | null>(null);
    const [isPolling, setIsPolling] = useState(false);
    const [pollCount, setPollCount] = useState(0);

    const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const pollCountRef = useRef(0);
    const settledRef = useRef(false);

    const stop = useCallback(() => {
        if (timerRef.current) {
            clearInterval(timerRef.current);
            timerRef.current = null;
        }
        setIsPolling(false);
    }, []);

    const doPoll = useCallback(async () => {
        if (!jobId) return;
        if (settledRef.current) return;

        pollCountRef.current += 1;
        setPollCount(pollCountRef.current);

        try {
            const data = await pollJobStatus(jobId);
            setStatusData(data);

            const terminal = data.status === 'success' || data.status === 'failed';
            if (terminal || pollCountRef.current >= maxPolls) {
                settledRef.current = true;
                stop();
                if (onSettled) onSettled(data);
            }
        } catch (err) {
            console.error('[useJobStatus] poll error:', err);
            // Don't stop on network error — retry next interval
        }
    }, [jobId, maxPolls, stop, onSettled]);

    const restart = useCallback(() => {
        stop();
        pollCountRef.current = 0;
        settledRef.current = false;
        setStatusData(null);
        setPollCount(0);
        if (!jobId) return;
        setIsPolling(true);
        // Immediate first poll
        doPoll();
        timerRef.current = setInterval(doPoll, intervalMs);
    }, [jobId, intervalMs, stop, doPoll]);

    // Start polling when jobId appears
    useEffect(() => {
        if (!jobId) return;
        restart();
        return () => stop(); // cleanup on unmount
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [jobId]);

    return {
        status: statusData?.status ?? null,
        result: statusData?.result,
        error: statusData?.error,
        isPolling,
        pollCount,
        stop,
        restart,
    };
}
