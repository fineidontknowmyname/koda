'use client';
import { motion } from 'framer-motion';
import { Button } from '@/components/ui/Button';
import Header from '@/components/layout/Header';
import { ArrowRight, Brain, Activity, FileText } from 'lucide-react';
import Link from 'next/link';

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-black text-white selection:bg-yellow-500/30">
      <Header />

      {/* Hero Section */}
      <section className="relative pt-32 pb-20 md:pt-48 md:pb-32 px-6 flex flex-col items-center text-center overflow-hidden">

        {/* Background Glow */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[600px] bg-yellow-500/10 rounded-full blur-[120px] -z-10" />

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          <span className="px-3 py-1 rounded-full bg-yellow-500/10 text-yellow-500 text-xs font-semibold tracking-wide border border-yellow-500/20 mb-6 inline-block">
            AI-POWERED FITNESS REVOLUTION
          </span>
          <h1 className="text-5xl md:text-7xl font-bold tracking-tight mb-6 max-w-4xl mx-auto leading-[1.1]">
            Your Personal Trainer <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-white via-zinc-200 to-zinc-500">
              Is Now Artificial Intelligence
            </span>
          </h1>
          <p className="text-lg md:text-xl text-zinc-400 max-w-2xl mx-auto mb-10 leading-relaxed">
            Koda analyzes your form, builds custom plans, and tracks your progress using advanced computer vision and Gemma AI. No expensive gym memberships required.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link href="/signup">
              <Button size="lg" className="w-full sm:w-auto group">
                Start
                <ArrowRight className="ml-2 w-4 h-4 group-hover:translate-x-1 transition-transform" />
              </Button>
            </Link>
          </div>
        </motion.div>
      </section>

      {/* Features Grid Removed per User Request */}


      {/* Footer */}
      <footer className="py-12 border-t border-white/5 text-center text-zinc-500 text-sm">
        <p>&copy; {new Date().getFullYear()} Genesis Tech. All rights reserved.</p>
      </footer>
    </div>
  );
}

function FeatureCard({ icon, title, description }: { icon: React.ReactNode, title: string, description: string }) {
  return (
    <motion.div
      whileHover={{ y: -5 }}
      className="p-8 rounded-2xl bg-zinc-900/50 border border-white/5 hover:border-yellow-500/20 transition-colors"
    >
      <div className="mb-6 p-3 rounded-xl bg-zinc-900 w-fit">{icon}</div>
      <h3 className="text-xl font-semibold mb-3">{title}</h3>
      <p className="text-zinc-400 leading-relaxed">{description}</p>
    </motion.div>
  );
}
