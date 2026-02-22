import { SelectHTMLAttributes, forwardRef } from 'react';
import { cn } from '@/components/ui/Button';

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> { }

const Select = forwardRef<HTMLSelectElement, SelectProps>(
    ({ className, children, ...props }, ref) => {
        return (
            <div className="relative">
                <select
                    className={cn(
                        "flex h-12 w-full items-center justify-between rounded-lg border border-white/10 bg-zinc-950 px-3 py-2 text-sm text-white ring-offset-black placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-yellow-500/50 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 appearance-none",
                        className
                    )}
                    ref={ref}
                    {...props}
                >
                    {children}
                </select>
                {/* Custom Chevron */}
                <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-4 text-zinc-400">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6" /></svg>
                </div>
            </div>
        );
    }
);
Select.displayName = "Select";

export { Select };
