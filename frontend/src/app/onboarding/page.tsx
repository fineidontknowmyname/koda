'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { Select } from '@/components/ui/Select';
import Header from '@/components/layout/Header';
import { ArrowLeft, ArrowRight, Upload, Brain, Plus, X } from 'lucide-react';
import { uploadPhotos } from '@/lib/api';
import type { UploadPhotosResult } from '@/lib/api';

const STEPS = [
    { id: 'biometrics', title: 'Biometrics', description: "Let's get to know your physical stats." },
    { id: 'activity', title: 'Activity', description: 'Tell us how active you already are.' },
    { id: 'metrics', title: 'Baseline', description: 'What can you do right now?' },
    { id: 'goals', title: 'Goals', description: 'What are you aiming for?' },
    { id: 'videos', title: 'Videos', description: 'Add YouTube videos to build your plan from.' },
    { id: 'photos', title: 'Analysis', description: 'Upload photos for AI body composition analysis.' },
];

interface FormData {
    age: string; weight: string; height: string; gender: 'male' | 'female';
    activityHoursPerWeek: number; activityLevel: string;
    pushups: string; situps: string; squats: string;
    goal: string; experience: string;
    youtubeUrls: string[];
    frontPhoto: File | null; sidePhoto: File | null; backPhoto: File | null;
}

const DEFAULT: FormData = {
    age: '', weight: '', height: '', gender: 'male',
    activityHoursPerWeek: 3, activityLevel: 'moderately_active',
    pushups: '', situps: '', squats: '',
    goal: 'hypertrophy', experience: 'beginner',
    youtubeUrls: [''],
    frontPhoto: null, sidePhoto: null, backPhoto: null,
};

export default function OnboardingPage() {
    const [step, setStep] = useState(0);
    const [form, setForm] = useState<FormData>(DEFAULT);
    const [analyzing, setAnalyzing] = useState(false);
    const [result, setResult] = useState<UploadPhotosResult | null>(null);
    const [ageError, setAgeError] = useState('');

    const set = (f: keyof FormData, v: unknown) => setForm(p => ({ ...p, [f]: v }));

    const addUrl = () => set('youtubeUrls', [...form.youtubeUrls, '']);
    const removeUrl = (i: number) => set('youtubeUrls', form.youtubeUrls.filter((_, x) => x !== i));
    const updateUrl = (i: number, v: string) => set('youtubeUrls', form.youtubeUrls.map((u, x) => x === i ? v : u));

    const handleNext = () => {
        if (step === 0) {
            const age = Number(form.age);
            if (!form.age || isNaN(age) || age < 15 || age > 60) {
                setAgeError('Age must be between 15 and 60.'); return;
            }
            setAgeError('');
        }
        if (step < STEPS.length - 1) { setStep(p => p + 1); }
        else { alert('Onboarding complete! Redirecting…'); window.location.href = '/dashboard'; }
    };

    const handleAnalyze = async () => {
        if (!form.frontPhoto) { alert('Please select a front-view photo.'); return; }
        setAnalyzing(true);
        try {
            setResult(await uploadPhotos(form.frontPhoto, form.sidePhoto, form.backPhoto));
        } catch { alert('Analysis failed. Use a clear full-body photo.'); }
        finally { setAnalyzing(false); }
    };

    const hoursLabel = (h: number) =>
        h === 0 ? 'Sedentary' : h <= 3 ? 'Lightly active' : h <= 6 ? 'Moderately active' : h <= 10 ? 'Very active' : 'Extremely active';

    return (
        <div className="min-h-screen bg-black text-white flex flex-col">
            <Header />
            <main className="flex-1 max-w-2xl mx-auto w-full px-6 py-20">
                {/* Progress */}
                <div className="mb-12">
                    <span className="text-yellow-500 font-medium text-sm block mb-1">Step {step + 1} of {STEPS.length}</span>
                    <h1 className="text-2xl font-bold">{STEPS[step].title}</h1>
                    <p className="text-zinc-400 mt-1">{STEPS[step].description}</p>
                    <div className="h-1 w-full bg-zinc-900 rounded-full overflow-hidden mt-4">
                        <motion.div className="h-full bg-yellow-500"
                            animate={{ width: `${((step + 1) / STEPS.length) * 100}%` }}
                            transition={{ duration: 0.3 }} />
                    </div>
                </div>

                <div className="bg-zinc-900/30 border border-white/5 rounded-2xl p-8">
                    <AnimatePresence mode="wait">
                        <motion.div key={step}
                            initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}
                            exit={{ opacity: 0, x: -20 }} transition={{ duration: 0.2 }}>

                            {/* Step 1 — Biometrics */}
                            {step === 0 && (
                                <div className="space-y-6">
                                    <div className="grid grid-cols-2 gap-4">
                                        <div className="space-y-2">
                                            <Label>Age <span className="text-xs text-zinc-500">(15–60)</span></Label>
                                            <Input type="number" placeholder="25" min={15} max={60}
                                                value={form.age} onChange={e => { set('age', e.target.value); setAgeError(''); }} />
                                            {ageError && <p className="text-red-400 text-xs">{ageError}</p>}
                                        </div>
                                        <div className="space-y-2">
                                            <Label>Gender</Label>
                                            <Select value={form.gender} onChange={e => set('gender', e.target.value as 'male' | 'female')}>
                                                <option value="male">Male</option>
                                                <option value="female">Female</option>
                                            </Select>
                                        </div>
                                    </div>
                                    <div className="grid grid-cols-2 gap-4">
                                        <div className="space-y-2">
                                            <Label>Weight (kg)</Label>
                                            <Input type="number" placeholder="70" value={form.weight} onChange={e => set('weight', e.target.value)} />
                                        </div>
                                        <div className="space-y-2">
                                            <Label>Height (cm)</Label>
                                            <Input type="number" placeholder="175" value={form.height} onChange={e => set('height', e.target.value)} />
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* Step 2 — Activity */}
                            {step === 1 && (
                                <div className="space-y-6">
                                    <div className="space-y-3">
                                        <Label>Weekly training hours: <span className="text-yellow-500 font-semibold">{form.activityHoursPerWeek} hr{form.activityHoursPerWeek !== 1 ? 's' : ''}</span></Label>
                                        <input type="range" min={0} max={20} step={1}
                                            value={form.activityHoursPerWeek}
                                            onChange={e => set('activityHoursPerWeek', Number(e.target.value))}
                                            className="w-full accent-yellow-500 cursor-pointer" />
                                        <div className="flex justify-between text-xs text-zinc-500"><span>0</span><span>10</span><span>20</span></div>
                                        <p className="text-sm text-zinc-300 font-medium">{hoursLabel(form.activityHoursPerWeek)}</p>
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Activity Level</Label>
                                        <Select value={form.activityLevel} onChange={e => set('activityLevel', e.target.value)}>
                                            <option value="sedentary">Sedentary</option>
                                            <option value="lightly_active">Light (1–3 days/week)</option>
                                            <option value="moderately_active">Moderate (3–5 days/week)</option>
                                            <option value="very_active">Active (6–7 days/week)</option>
                                            <option value="extra_active">Extra active</option>
                                        </Select>
                                    </div>
                                </div>
                            )}

                            {/* Step 3 — Baseline */}
                            {step === 2 && (
                                <div className="space-y-6">
                                    <div className="p-4 bg-yellow-500/10 border border-yellow-500/20 rounded-lg">
                                        <p className="text-sm text-yellow-500">Be honest — Koda needs accurate data to build a safe plan.</p>
                                    </div>
                                    {(['pushups', 'squats', 'situps'] as const).map(k => (
                                        <div key={k} className="space-y-2">
                                            <Label>Max {k.charAt(0).toUpperCase() + k.slice(1)} (in one go)</Label>
                                            <Input type="number" placeholder="20" value={form[k]} onChange={e => set(k, e.target.value)} />
                                        </div>
                                    ))}
                                </div>
                            )}

                            {/* Step 4 — Goals */}
                            {step === 3 && (
                                <div className="space-y-6">
                                    <div className="space-y-2">
                                        <Label>Primary Goal</Label>
                                        <Select value={form.goal} onChange={e => set('goal', e.target.value)}>
                                            <option value="hypertrophy">Hypertrophy (Build Muscle)</option>
                                            <option value="strength">Strength (Get Stronger)</option>
                                            <option value="endurance">Endurance</option>
                                            <option value="weight_loss">Weight Loss</option>
                                        </Select>
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Experience Level</Label>
                                        <Select value={form.experience} onChange={e => set('experience', e.target.value)}>
                                            <option value="beginner">Beginner (0–1 years)</option>
                                            <option value="intermediate">Intermediate (1–3 years)</option>
                                            <option value="advanced">Advanced (3+ years)</option>
                                        </Select>
                                    </div>
                                </div>
                            )}

                            {/* Step 5 — YouTube videos */}
                            {step === 4 && (
                                <div className="space-y-4">
                                    <p className="text-sm text-zinc-400">Add YouTube workout videos. Koda extracts exercises from captions.</p>
                                    <div className="space-y-3">
                                        {form.youtubeUrls.map((url, i) => (
                                            <div key={i} className="flex gap-2 items-center">
                                                <Input placeholder="https://www.youtube.com/watch?v=..." value={url}
                                                    onChange={e => updateUrl(i, e.target.value)} className="flex-1" />
                                                {form.youtubeUrls.length > 1 && (
                                                    <button onClick={() => removeUrl(i)} className="text-zinc-500 hover:text-red-400 transition-colors p-1">
                                                        <X className="w-4 h-4" />
                                                    </button>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                    <button onClick={addUrl} className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-yellow-500 transition-colors">
                                        <Plus className="w-3.5 h-3.5" /> Add another video
                                    </button>
                                </div>
                            )}

                            {/* Step 6 — Photos */}
                            {step === 5 && (
                                <div className="space-y-6">
                                    {([
                                        { key: 'frontPhoto' as const, label: 'Front view', required: true },
                                        { key: 'sidePhoto' as const, label: 'Side view', required: false },
                                        { key: 'backPhoto' as const, label: 'Back view', required: false },
                                    ]).map(({ key, label, required }) => (
                                        <div key={key} className="space-y-2">
                                            <Label>{label}{required && <span className="text-yellow-500 ml-1">*</span>}</Label>
                                            <div className="flex items-center gap-3">
                                                <input type="file" accept="image/jpeg,image/png,image/webp"
                                                    id={`photo-${key}`} className="hidden"
                                                    onChange={e => set(key, e.target.files?.[0] ?? null)} />
                                                <label htmlFor={`photo-${key}`}
                                                    className="flex items-center gap-2 px-4 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 cursor-pointer text-sm transition-colors border border-white/5">
                                                    <Upload className="w-4 h-4" />
                                                    {form[key] ? (form[key] as File).name : 'Choose file'}
                                                </label>
                                                {form[key] && <span className="text-xs text-green-400">✓</span>}
                                            </div>
                                        </div>
                                    ))}
                                    <Button variant="secondary" onClick={handleAnalyze}
                                        disabled={analyzing || !form.frontPhoto} className="w-full">
                                        {analyzing ? 'Analysing…' : 'Analyse Photos'}
                                    </Button>
                                    {result && (
                                        <div className="bg-zinc-900/50 border border-yellow-500/20 rounded-xl p-6 space-y-4">
                                            <div className="flex items-center gap-2">
                                                <Brain className="w-5 h-5 text-yellow-500" />
                                                <h4 className="font-semibold">AI Analysis Results</h4>
                                            </div>
                                            <div className="grid grid-cols-2 gap-4">
                                                <div className="bg-black/40 p-3 rounded-lg">
                                                    <span className="text-xs text-zinc-500 block">Est. Body Fat</span>
                                                    <span className="text-xl font-bold">{result.body_fat_percentage != null ? `${result.body_fat_percentage}%` : '--'}</span>
                                                </div>
                                                <div className="bg-black/40 p-3 rounded-lg">
                                                    <span className="text-xs text-zinc-500 block">V-Taper Ratio</span>
                                                    <span className="text-xl font-bold">{result.v_taper_ratio ?? '--'}</span>
                                                </div>
                                            </div>
                                            {result.posture_assessment && (
                                                <p className="text-sm"><span className="text-zinc-500">Posture: </span>{result.posture_assessment}</p>
                                            )}
                                        </div>
                                    )}
                                    <div className="flex gap-2 p-4 bg-zinc-950 rounded-lg text-sm text-zinc-400">
                                        <span>🔒</span>
                                        <p>Photos are processed privately on-device and never shared.</p>
                                    </div>
                                </div>
                            )}

                        </motion.div>
                    </AnimatePresence>

                    {/* Nav */}
                    <div className="mt-10 flex justify-between pt-6 border-t border-white/5">
                        <Button variant="ghost" onClick={() => setStep(p => p - 1)}
                            disabled={step === 0} className={step === 0 ? 'invisible' : ''}>
                            <ArrowLeft className="w-4 h-4 mr-2" /> Back
                        </Button>
                        <Button onClick={handleNext} className="w-32">
                            {step === STEPS.length - 1 ? 'Finish' : 'Next'}
                            {step !== STEPS.length - 1 && <ArrowRight className="w-4 h-4 ml-2" />}
                        </Button>
                    </div>
                </div>
            </main>
        </div>
    );
}
