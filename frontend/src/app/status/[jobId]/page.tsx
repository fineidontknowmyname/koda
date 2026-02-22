'use client';

import { use } from 'react';
import Header from '@/components/layout/Header';
import JobStatusPoller from '@/components/JobStatusPoller';
import { useRouter } from 'next/navigation';

interface Props {
    params: Promise<{ jobId: string }>;
}

export default function JobStatusPage({ params }: Props) {
    const { jobId } = use(params);
    const router = useRouter();

    return (
        <div className="min-h-screen bg-black text-white">
            <Header />

            <main className="pt-24 px-6 max-w-xl mx-auto pb-20">
                {/* Back link */}
                <button
                    onClick={() => router.back()}
                    className="text-zinc-500 hover:text-white text-sm flex items-center gap-1 mb-8 transition-colors"
                >
                    ← Back to dashboard
                </button>

                <div className="mb-8">
                    <h1 className="text-2xl font-bold mb-1">Plan Generation</h1>
                    <p className="text-zinc-400 text-sm">
                        Job ID: <code className="text-yellow-500 font-mono">{jobId}</code>
                    </p>
                </div>

                {/* Card */}
                <div className="bg-zinc-900/40 border border-white/5 rounded-2xl p-8">
                    <JobStatusPoller
                        jobId={jobId}
                        onReset={() => router.push('/dashboard')}
                    />
                </div>

                <p className="text-xs text-zinc-600 text-center mt-6">
                    You can close this tab — your plan will still be generated. Come back with the job ID to download it.
                </p>
            </main>
        </div>
    );
}
