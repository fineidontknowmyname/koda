'use client';

import { useCallback } from 'react';
import { Loader2, CheckCircle2, XCircle, Download } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { useJobStatus } from '@/hooks/useJobStatus';
import { downloadPlanPdf } from '@/lib/api';
import type { JobStatus } from '@/lib/api';

// ---------------------------------------------------------------------------
// Step labels shown alongside the progress bar
// ---------------------------------------------------------------------------

const PIPELINE_STEPS = [
    { label: 'Queued', statuses: ['pending'] as JobStatus[] },
    { label: 'Fetching transcript', statuses: ['running'] as JobStatus[] },
    { label: 'Analysing content', statuses: ['running'] as JobStatus[] },
    { label: 'Building plan', statuses: ['running'] as JobStatus[] },
    { label: 'Rendering PDF', statuses: ['success', 'failed'] as JobStatus[] },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function statusToProgress(status: JobStatus | null): number {
    switch (status) {
        case 'pending': return 15;
        case 'running': return 55;
        case 'success': return 100;
        case 'failed': return 100;
        default: return 0;
    }
}

function activeStepIndex(status: JobStatus | null): number {
    switch (status) {
        case 'pending': return 0;
        case 'running': return 2;   // middle of running steps
        case 'success':
        case 'failed': return PIPELINE_STEPS.length - 1;
        default: return -1;
    }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface Props {
    jobId: string;
    /** Called when the user clicks "Generate Another" after a terminal state. */
    onReset?: () => void;
}

export default function JobStatusPoller({ jobId, onReset }: Props) {
    const { status, error, isPolling, pollCount, stop } = useJobStatus(jobId);
    const progress = statusToProgress(status);
    const activeStep = activeStepIndex(status);
    const isTerminal = status === 'success' || status === 'failed';

    const handleDownload = useCallback(async () => {
        try {
            const blob = await downloadPlanPdf(jobId);
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `koda_plan_${jobId.slice(0, 8)}.pdf`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
        } catch (err) {
            console.error('PDF download failed:', err);
            alert('PDF download failed. The plan may still be processing.');
        }
    }, [jobId]);

    return (
        <div className="space-y-6">
            {/* Progress bar */}
            <div className="space-y-2">
                <div className="flex justify-between text-xs text-zinc-400">
                    <span>
                        {status === 'success' ? 'Complete!' :
                            status === 'failed' ? 'Failed' :
                                isPolling ? `Processing… (${pollCount} checks)` :
                                    'Waiting…'}
                    </span>
                    <span>{progress}%</span>
                </div>
                <div className="h-2 w-full bg-zinc-800 rounded-full overflow-hidden">
                    <div
                        className={`h-full rounded-full transition-all duration-700 ease-in-out ${status === 'failed'
                                ? 'bg-red-500'
                                : 'bg-gradient-to-r from-yellow-500 to-yellow-400'
                            }`}
                        style={{ width: `${progress}%` }}
                    />
                </div>
            </div>

            {/* Step indicators */}
            <ol className="space-y-2">
                {PIPELINE_STEPS.map((step, i) => {
                    const done = isTerminal ? status === 'success' && i < PIPELINE_STEPS.length
                        : i < activeStep;
                    const current = !isTerminal && i === activeStep;
                    const failed = status === 'failed' && i === activeStep;

                    return (
                        <li key={step.label} className="flex items-center gap-3 text-sm">
                            <span className={`flex-shrink-0 w-5 h-5 flex items-center justify-center rounded-full text-xs font-bold ${failed ? 'bg-red-500/20 text-red-400' :
                                    done ? 'bg-yellow-500/20 text-yellow-400' :
                                        current ? 'bg-zinc-700 text-white animate-pulse' :
                                            'bg-zinc-800 text-zinc-500'
                                }`}>
                                {failed ? '✕' :
                                    done ? '✓' :
                                        current ? '…' :
                                            i + 1}
                            </span>
                            <span className={`${done ? 'text-zinc-300' : current ? 'text-white' : 'text-zinc-500'}`}>
                                {step.label}
                                {current && (
                                    <Loader2 className="inline-block w-3 h-3 ml-2 animate-spin text-yellow-500" />
                                )}
                            </span>
                        </li>
                    );
                })}
            </ol>

            {/* Terminal state actions */}
            {status === 'success' && (
                <div className="space-y-3 pt-2">
                    <div className="flex items-center gap-2 text-green-400 text-sm font-medium">
                        <CheckCircle2 className="w-5 h-5" />
                        Your plan is ready!
                    </div>
                    <Button
                        size="lg"
                        className="w-full gap-2 bg-yellow-500 hover:bg-yellow-400 text-black font-semibold"
                        onClick={handleDownload}
                    >
                        <Download className="w-4 h-4" />
                        Download PDF Plan
                    </Button>
                    {onReset && (
                        <Button variant="ghost" size="sm" className="w-full text-zinc-400" onClick={() => { stop(); onReset(); }}>
                            Generate Another
                        </Button>
                    )}
                </div>
            )}

            {status === 'failed' && (
                <div className="space-y-3 pt-2">
                    <div className="flex items-center gap-2 text-red-400 text-sm">
                        <XCircle className="w-5 h-5" />
                        <span>{error ?? 'An error occurred during plan generation.'}</span>
                    </div>
                    {onReset && (
                        <Button variant="outline" size="sm" className="w-full" onClick={() => { stop(); onReset(); }}>
                            Try Again
                        </Button>
                    )}
                </div>
            )}
        </div>
    );
}
