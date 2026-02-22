'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Header from '@/components/layout/Header';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { submitPlanJob } from '@/lib/api';
import JobStatusPoller from '@/components/JobStatusPoller';
import { Loader2, FileDown, Youtube, Plus, X } from 'lucide-react';

// ---------------------------------------------------------------------------
// Mock user profile — replaced by real profile from context/DB when auth is wired
// ---------------------------------------------------------------------------
const MOCK_USER_PROFILE = {
    biometrics: { age: 25, weight_kg: 75, height_cm: 180, gender: 'male' },
    metrics: { pushup_count: 20, situp_count: 30, squat_count: 25 },
    injuries: [],
    equipment: ['bodyweight'],
    experience_level: 'intermediate',
    fitness_goal: 'hypertrophy',
};

// ---------------------------------------------------------------------------
// Dashboard page
// ---------------------------------------------------------------------------

export default function DashboardPage() {
    const router = useRouter();
    const [urls, setUrls] = useState<string[]>(['']);
    const [submitting, setSubmitting] = useState(false);
    const [activeJobId, setActiveJobId] = useState<string | null>(null);

    // Multi-URL helpers
    const addUrl = () => setUrls(prev => [...prev, '']);
    const removeUrl = (i: number) => setUrls(prev => prev.filter((_, idx) => idx !== i));
    const updateUrl = (i: number, val: string) =>
        setUrls(prev => prev.map((u, idx) => (idx === i ? val : u)));

    const filledUrls = urls.filter(u => u.trim() !== '');

    const handleGenerate = useCallback(async () => {
        if (filledUrls.length === 0) {
            alert('Please enter at least one YouTube URL.');
            return;
        }

        setSubmitting(true);
        try {
            const job = await submitPlanJob({
                user_profile: MOCK_USER_PROFILE,
                youtube_urls: filledUrls,
            });
            // Optimistic: start inline poller; also navigate so the user can bookmark
            setActiveJobId(job.job_id);
            router.push(`/status/${job.job_id}`);
        } catch (err) {
            console.error('Job dispatch error:', err);
            alert('Failed to queue plan generation. Is the API running?');
        } finally {
            setSubmitting(false);
        }
    }, [filledUrls, router]);

    return (
        <div className="min-h-screen bg-black text-white selection:bg-yellow-500/30">
            <Header />

            <main className="pt-24 px-6 max-w-7xl mx-auto pb-20">
                {/* Title row */}
                <div className="flex flex-col md:flex-row gap-8 items-start justify-between mb-12">
                    <div>
                        <h1 className="text-3xl font-bold mb-2">My Dashboard</h1>
                        <p className="text-zinc-400">Welcome back, User</p>
                    </div>
                    <div className="bg-zinc-900/50 p-4 rounded-xl border border-white/5 flex gap-6 text-sm">
                        <div>
                            <span className="block text-zinc-500 mb-1">Current Goal</span>
                            <span className="font-semibold text-yellow-500">Hypertrophy</span>
                        </div>
                        <div className="w-px bg-white/10" />
                        <div>
                            <span className="block text-zinc-500 mb-1">Level</span>
                            <span className="font-semibold text-white">Intermediate</span>
                        </div>
                    </div>
                </div>

                <div className="grid md:grid-cols-3 gap-8">
                    {/* Main action card */}
                    <div className="md:col-span-2 space-y-8">
                        <section className="p-8 rounded-2xl bg-gradient-to-br from-zinc-900 to-black border border-white/10 relative overflow-hidden group">
                            <div className="absolute top-0 right-0 w-64 h-64 bg-yellow-500/5 rounded-full blur-[80px] -z-10 group-hover:bg-yellow-500/10 transition-all duration-500" />

                            <div className="mb-6">
                                <div className="w-12 h-12 bg-yellow-500/20 rounded-xl flex items-center justify-center mb-4 text-yellow-500">
                                    <FileDown className="w-6 h-6" />
                                </div>
                                <h2 className="text-2xl font-bold mb-2">Generate New Plan</h2>
                                <p className="text-zinc-400 max-w-lg">
                                    Create a fully customised 4-week PDF workout routine. Add multiple YouTube
                                    workout videos to blend training styles.
                                </p>
                            </div>

                            {/* URL inputs */}
                            <div className="space-y-4 max-w-xl">
                                <Label>Source Videos (YouTube)</Label>
                                <div className="space-y-3">
                                    {urls.map((url, i) => (
                                        <div key={i} className="flex gap-2 items-center">
                                            <div className="relative flex-1">
                                                <div className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500">
                                                    <Youtube className="w-4 h-4" />
                                                </div>
                                                <Input
                                                    placeholder="https://www.youtube.com/watch?v=..."
                                                    className="pl-9"
                                                    value={url}
                                                    onChange={e => updateUrl(i, e.target.value)}
                                                />
                                            </div>
                                            {urls.length > 1 && (
                                                <button
                                                    onClick={() => removeUrl(i)}
                                                    className="text-zinc-500 hover:text-red-400 transition-colors p-1"
                                                    title="Remove URL"
                                                >
                                                    <X className="w-4 h-4" />
                                                </button>
                                            )}
                                        </div>
                                    ))}
                                </div>

                                <button
                                    onClick={addUrl}
                                    className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-yellow-500 transition-colors"
                                >
                                    <Plus className="w-3.5 h-3.5" /> Add another video
                                </button>

                                <p className="text-xs text-zinc-500">
                                    Koda extracts exercise lists from video transcripts. Videos must have captions enabled.
                                </p>

                                <Button
                                    size="lg"
                                    className="w-full sm:w-auto min-w-[200px]"
                                    onClick={handleGenerate}
                                    disabled={submitting || filledUrls.length === 0}
                                >
                                    {submitting ? (
                                        <>
                                            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                            Queuing job…
                                        </>
                                    ) : (
                                        'Generate Plan PDF'
                                    )}
                                </Button>
                            </div>

                            {/* Inline poller (appears briefly before navigation) */}
                            {activeJobId && (
                                <div className="mt-8 p-6 bg-black/30 rounded-xl border border-white/5">
                                    <JobStatusPoller
                                        jobId={activeJobId}
                                        onReset={() => { setActiveJobId(null); setUrls(['']); }}
                                    />
                                </div>
                            )}
                        </section>

                        {/* Recent Activity */}
                        <section className="p-6 rounded-2xl bg-zinc-900/30 border border-white/5">
                            <h3 className="text-lg font-semibold mb-4">Recent Activity</h3>
                            <div className="flex items-center justify-center h-32 text-zinc-500 text-sm italic border-dashed border border-zinc-800 rounded-lg">
                                No recent workouts logged.
                            </div>
                        </section>
                    </div>

                    {/* Stats sidebar */}
                    <aside className="space-y-6">
                        <div className="p-6 rounded-2xl bg-zinc-900/30 border border-white/5">
                            <h3 className="font-semibold mb-4 text-sm uppercase tracking-wider text-zinc-500">My Stats</h3>
                            <div className="space-y-4">
                                <StatRow label="Weight" value="75 kg" />
                                <StatRow label="Height" value="180 cm" />
                                <StatRow label="Body Fat" value="-- %" />
                                <StatRow label="V-Taper" value="--" />
                            </div>
                            <Button variant="outline" size="sm" className="w-full mt-6 text-xs">
                                Update Biometrics
                            </Button>
                        </div>

                        <div className="p-6 rounded-2xl bg-zinc-900/30 border border-white/5">
                            <h3 className="font-semibold mb-4 text-sm uppercase tracking-wider text-zinc-500">Progression</h3>
                            <div className="space-y-4">
                                <ProgressBar label="Pushups" current={20} max={50} />
                                <ProgressBar label="Squats" current={25} max={100} />
                            </div>
                        </div>
                    </aside>
                </div>
            </main>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatRow({ label, value }: { label: string; value: string }) {
    return (
        <div className="flex justify-between items-center text-sm">
            <span className="text-zinc-400">{label}</span>
            <span className="font-medium">{value}</span>
        </div>
    );
}

function ProgressBar({ label, current, max }: { label: string; current: number; max: number }) {
    const pct = Math.min(100, (current / max) * 100);
    return (
        <div>
            <div className="flex justify-between text-xs mb-1">
                <span>{label}</span>
                <span className="text-zinc-400">{current}/{max}</span>
            </div>
            <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                <div className="h-full bg-yellow-500 rounded-full" style={{ width: `${pct}%` }} />
            </div>
        </div>
    );
}
