'use client';
import { Button } from '@/components/ui/Button';
import Header from '@/components/layout/Header';
import { useState } from 'react';
import Link from 'next/link';

export default function LoginPage() {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        console.log('Login attempt:', { email, password });
        // TODO: Implement actual login logic
        localStorage.setItem('koda_user', 'true'); // Mock Auth
        alert("Login successful! Redirecting to onboarding...");
        window.location.href = '/onboarding';
    };

    return (
        <div className="min-h-screen bg-black text-white flex flex-col">
            <Header />

            <main className="flex-1 flex items-center justify-center px-6 pt-20">
                <div className="w-full max-w-md p-8 rounded-2xl bg-zinc-900/50 border border-white/5">
                    <div className="text-center mb-8">
                        <h1 className="text-3xl font-bold mb-2">Welcome Back</h1>
                        <p className="text-zinc-400">Sign in to continue your progress</p>
                    </div>

                    <form onSubmit={handleSubmit} className="space-y-6">
                        <div>
                            <label className="block text-sm font-medium text-zinc-300 mb-2">Email</label>
                            <input
                                type="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className="w-full px-4 py-3 rounded-lg bg-zinc-950 border border-white/10 text-white focus:outline-none focus:ring-2 focus:ring-yellow-500/50 focus:border-yellow-500/50 transition-all"
                                placeholder="you@example.com"
                                required
                            />
                        </div>

                        <div>
                            <label className="block text-sm font-medium text-zinc-300 mb-2">Password</label>
                            <input
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                className="w-full px-4 py-3 rounded-lg bg-zinc-950 border border-white/10 text-white focus:outline-none focus:ring-2 focus:ring-yellow-500/50 focus:border-yellow-500/50 transition-all"
                                placeholder="••••••••"
                                required
                            />
                        </div>

                        <Button type="submit" className="w-full" size="lg">Sign In</Button>
                    </form>

                    <p className="mt-6 text-center text-sm text-zinc-400">
                        Don't have an account?{' '}
                        <Link href="/signup" className="text-yellow-500 hover:text-yellow-400 font-medium">
                            Sign up
                        </Link>
                    </p>
                </div>
            </main>
        </div>
    );
}
